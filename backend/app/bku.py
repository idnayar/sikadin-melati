"""Buku Kas Umum (BKU) — format sama dengan contoh Puskesmas Melati (Agustus 2026), bulanan dan tahunan.
Empat buku, masing-masing satu akun kas:
  BOK / DAU  : BKU Bendahara Pengeluaran Pembantu   (kolom: No Urut, Tanggal, Kode Rekening/Bukti, Uraian, Penerimaan, Pengeluaran)
  RETRIBUSI  : BKU Bendahara Penerimaan             (format sama + judul Pemerintah Kabupaten, kolom bernomor, sisa kas NIHIL)
  BLUD       : Buku Kas Bendahara Dana BLUD         (kolom: No, Tanggal, No. Bukti, Uraian, Pendapatan, Belanja, Saldo + rincian saldo)
Setiap baris BKU = satu jurnal berbasis KAS yang menyentuh akun kas buku itu (penerimaan = debit kas, pengeluaran = kredit kas).
SPJ yang dibayar otomatis masuk; transaksi lain (pendapatan, setor, bunga giro, Qris) dicatat lewat /api/bku/transaksi."""
import datetime as dt
import io
import json

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response

from . import dokumen as dk
from .akuntansi import buat_jurnal
from .core import Gagal, audit, auth, get_db
from .surat import DOCX, _pdf_ke_docx

router = APIRouter(prefix="/api/bku")
BULAN = dk.BULAN
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BUKU = {
    "BOK": {"nama": "BKU Bendahara Pengeluaran Pembantu — BOK", "kas": "1.1.1.01", "dana": "BOK", "format": "pembantu", "peran": "Bendahara Pengeluaran Pembantu", "tulis": ("kepala", "bendahara"), "baca": ("kepala", "bendahara", "bendahara_blud")},
    "DAU": {"nama": "BKU Bendahara Pengeluaran Pembantu — DAU", "kas": "1.1.1.04", "dana": "DAU", "format": "pembantu", "peran": "Bendahara Pengeluaran Pembantu", "tulis": ("kepala", "bendahara"), "baca": ("kepala", "bendahara", "bendahara_blud")},
    "RETRIBUSI": {"nama": "BKU Bendahara Penerimaan (Retribusi)", "kas": "1.1.1.03", "dana": "BLUD", "format": "penerimaan", "peran": "Bendahara Penerimaan", "tulis": ("kepala", "bendahara_blud"), "baca": ("kepala", "bendahara_blud")},
    "BLUD": {"nama": "Buku Kas Bendahara Dana BLUD", "kas": "1.1.1.02", "dana": "BLUD", "format": "blud", "peran": "Bendahara Dana Kapitasi/BLUD", "tulis": ("kepala", "bendahara_blud"), "baca": ("kepala", "bendahara_blud")},
}
TEMPAT = ("Bank", "Kas JKN", "Kas Lain-lain", "Panjar")
DANA = ("JKN Kapitasi", "JKN Non Kapitasi", "Pelayanan Umum")


def _set(db, k, d=""):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    return r["nilai"] if r and r["nilai"] is not None else d


def _izin(user, kode, tulis=False):
    if kode not in BUKU:
        raise Gagal("Buku tidak dikenal.", 404)
    if user["role"] not in BUKU[kode]["tulis" if tulis else "baca"]:
        raise Gagal("Anda tidak berwenang atas buku kas ini.", 403)


def _akun_id(db, kode):
    r = db.execute("SELECT id FROM akun WHERE kode=?", (kode,)).fetchone()
    if not r:
        raise Gagal(f"Akun {kode} tidak ada.", 500)
    return r["id"]


# ---------------------------------------------------------------- perhitungan
def _rincian_saldo(db, akun_id, sampai):
    """Saldo kas BLUD per (tempat, dana) sampai tanggal — dari penandaan pada baris jurnal (kosong = Bank / Pelayanan Umum)."""
    out: dict = {}
    for r in db.execute("""SELECT COALESCE(b.tempat,'Bank') t, COALESCE(b.dana,'Pelayanan Umum') d, SUM(b.debit-b.kredit) s FROM jurnal_baris b JOIN jurnal j ON j.id=b.jurnal_id
        WHERE b.akun_id=? AND j.tanggal<=? GROUP BY 1,2""", (akun_id, sampai)).fetchall():
        out[(r["t"], r["d"])] = r["s"]
    return out


def _baris_buku(db, kode, tanggal_awal, tanggal_akhir):
    """Baris BKU (per jurnal) antara dua tanggal."""
    akun = _akun_id(db, BUKU[kode]["kas"])
    rows = db.execute("""SELECT j.id jid, j.tanggal, j.no_bukti, j.uraian, j.uraian_buku, j.ref_jenis, j.basis, SUM(b.debit) pen, SUM(b.kredit) peng
        FROM jurnal j JOIN jurnal_baris b ON b.jurnal_id=j.id WHERE b.akun_id=? AND j.basis!='AWAL' AND j.tanggal BETWEEN ? AND ? GROUP BY j.id ORDER BY j.tanggal, j.id""", (akun, tanggal_awal, tanggal_akhir)).fetchall()
    out = []
    for r in rows:
        ub = json.loads(r["uraian_buku"]) if r["uraian_buku"] else {}
        out.append({"jid": r["jid"], "tanggal": r["tanggal"], "no_bukti": r["no_bukti"], "uraian": ub.get(kode) or r["uraian"], "pen": r["pen"], "peng": r["peng"], "otomatis": bool(r["ref_jenis"]) and r["ref_jenis"] != "BKU"})
    return out


def _saldo_awal(db, kode, tanggal):
    """Saldo kas sebelum tanggal (termasuk jurnal saldo awal)."""
    akun = _akun_id(db, BUKU[kode]["kas"])
    return db.execute("""SELECT COALESCE(SUM(b.debit-b.kredit),0) s FROM jurnal_baris b JOIN jurnal j ON j.id=b.jurnal_id
        WHERE b.akun_id=? AND (j.basis='AWAL' OR j.tanggal<?)""", (akun, tanggal)).fetchone()["s"]


def _akhir_bulan(tahun, bulan):
    return (dt.date(tahun + (bulan == 12), bulan % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


def susun(db, kode, tahun, bulan):
    """bulan 1-12 = BKU bulanan; 0 = BKU tahunan (seluruh tahun, dengan jumlah per bulan)."""
    if not 2000 < tahun < 2100 or not 0 <= bulan <= 12:
        raise Gagal("Tahun/bulan tidak valid.")
    bulan_list = [bulan] if bulan else list(range(1, 13))
    urut = 0
    seksi = []
    sd_pen = sd_peng = 0
    awal_tahun = _saldo_awal(db, kode, f"{tahun}-01-01")
    if bulan:   # urutan nomor dilanjutkan dari bulan-bulan sebelumnya pada tahun yang sama
        for m in range(1, bulan):
            urut += len(_baris_buku(db, kode, f"{tahun}-{m:02d}-01", _akhir_bulan(tahun, m))) + (1 if BUKU[kode]["format"] == "pembantu" else 0)
            b = _baris_buku(db, kode, f"{tahun}-{m:02d}-01", _akhir_bulan(tahun, m))
            sd_pen += sum(x["pen"] for x in b)
            sd_peng += sum(x["peng"] for x in b)
    for m in bulan_list:
        awal = f"{tahun}-{m:02d}-01"
        akhir = _akhir_bulan(tahun, m)
        b = _baris_buku(db, kode, awal, akhir)
        saldo_awal = _saldo_awal(db, kode, awal)
        nomor_awal = None
        if BUKU[kode]["format"] == "pembantu":
            urut += 1
            nomor_awal = urut
        for x in b:
            urut += 1
            x["urut"] = urut
        pen = sum(x["pen"] for x in b)
        peng = sum(x["peng"] for x in b)
        seksi.append({"bulan": m, "awal": awal, "akhir": akhir, "saldo_awal": saldo_awal, "nomor_awal": nomor_awal, "baris": b, "pen": pen, "peng": peng,
                      "lalu_pen": sd_pen, "lalu_peng": sd_peng, "sd_pen": sd_pen + pen, "sd_peng": sd_peng + peng})
        sd_pen += pen
        sd_peng += peng
    return {"kode": kode, "tahun": tahun, "bulan": bulan, "seksi": seksi, "saldo_awal_tahun": awal_tahun, "buku": {k: v for k, v in BUKU[kode].items() if k not in ("tulis", "baca")},
            "akhir": _saldo_awal(db, kode, (dt.date.fromisoformat(seksi[-1]["akhir"]) + dt.timedelta(days=1)).isoformat())}


def _pejabat(db, peran):
    r = db.execute("SELECT nama, nip, jabatan FROM pejabat WHERE aktif=1 AND peran LIKE ? ORDER BY id LIMIT 1", (f"%{peran}%",)).fetchone()
    return r or {"nama": "", "nip": "", "jabatan": peran}


def _kpa(db):
    r = db.execute("SELECT nama, nip, jabatan FROM pejabat WHERE aktif=1 AND (peran LIKE '%Penandatangan%' OR jabatan LIKE 'Kepala%') ORDER BY id LIMIT 1").fetchone()
    return r or {"nama": "", "nip": "", "jabatan": "Kepala"}


# ---------------------------------------------------------------- API
@router.get("")
def lihat(buku: str, tahun: int, bulan: int = 0, user=Depends(auth), db=Depends(get_db)):
    _izin(user, buku)
    d = susun(db, buku, tahun, bulan)
    d["bisa_tulis"] = user["role"] in BUKU[buku]["tulis"]
    d["pejabat"] = {"bendahara": _pejabat(db, BUKU[buku]["peran"]), "kpa": _kpa(db)}
    if BUKU[buku]["format"] == "blud":
        akun = _akun_id(db, BUKU[buku]["kas"])
        d["rincian"] = [{"tempat": t, "dana": dn, "jumlah": s} for (t, dn), s in sorted(_rincian_saldo(db, akun, d["seksi"][-1]["akhir"]).items())]
    return d


@router.get("/akun")
def akun_pilihan(user=Depends(auth), db=Depends(get_db)):
    """Akun lawan yang dapat dipilih saat mencatat transaksi BKU (bukan akun kas)."""
    if not any(user["role"] in v["tulis"] for v in BUKU.values()):
        raise Gagal("Tidak ada akses.", 403)
    return db.execute("SELECT id, kode, nama, jenis, aktif, kas FROM akun WHERE aktif=1 AND kas=0 ORDER BY kode").fetchall()


@router.get("/daftar")
def daftar(user=Depends(auth), db=Depends(get_db)):
    return [{"kode": k, "nama": v["nama"], "format": v["format"], "tulis": user["role"] in v["tulis"]} for k, v in BUKU.items() if user["role"] in v["baca"]]


def _angka(v, nama="Jumlah"):
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        raise Gagal(f"{nama} harus berupa angka.")
    if n < 0:
        raise Gagal(f"{nama} tidak boleh negatif.")
    return n


@router.post("/transaksi")
def catat(body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    """Catat transaksi BKU. jenis: penerimaan | pengeluaran | pindah (kas ke kas, mis. setor retribusi ke BLUD) | teruskan (terima lalu langsung teruskan ke BLUD, mis. Qris)."""
    kode, jenis = str(body.get("buku") or "").upper(), str(body.get("jenis") or "")
    _izin(user, kode, tulis=True)
    try:
        tanggal = dt.date.fromisoformat(str(body.get("tanggal"))[:10]).isoformat()
    except ValueError:
        raise Gagal("Tanggal tidak valid.")
    uraian = str(body.get("uraian") or "").strip()
    jumlah = _angka(body.get("jumlah"))
    if len(uraian) < 3 or jumlah <= 0:
        raise Gagal("Uraian dan jumlah (lebih dari nol) wajib diisi.")
    no_bukti = str(body.get("no_bukti") or "").strip() or None
    kas = _akun_id(db, BUKU[kode]["kas"])
    sd = db.execute("SELECT id FROM sumber_dana WHERE kode=?", (BUKU[kode]["dana"],)).fetchone()["id"]
    tempat = body.get("tempat") if body.get("tempat") in TEMPAT else None
    dana = body.get("dana") if body.get("dana") in DANA else None
    lawan = None
    if jenis in ("penerimaan", "pengeluaran", "teruskan"):
        lawan = db.execute("SELECT * FROM akun WHERE id=? AND aktif=1", (body.get("akun_lawan_id"),)).fetchone()
        if not lawan:
            raise Gagal("Pilih akun lawan (pendapatan/belanja).")
    if jenis == "penerimaan":
        baris = [(kas, jumlah, 0, tempat, dana), (lawan["id"], 0, jumlah)]
        ub = None
    elif jenis == "pengeluaran":
        baris = [(kas, 0, jumlah, tempat, dana), (lawan["id"], jumlah, 0)]
        ub = None
    elif jenis == "pindah":
        ke = str(body.get("ke_buku") or "").upper()
        _izin(user, ke, tulis=True)
        if ke == kode or ke not in BUKU:
            raise Gagal("Pilih buku tujuan yang berbeda.")
        kas2 = _akun_id(db, BUKU[ke]["kas"])
        baris = [(kas, 0, jumlah), (kas2, jumlah, 0, tempat, dana)]
        ub = {ke: str(body.get("uraian_tujuan") or uraian).strip()}
    elif jenis == "teruskan":
        ke = str(body.get("ke_buku") or "BLUD").upper()
        _izin(user, ke, tulis=True)
        if ke == kode or ke not in BUKU:
            raise Gagal("Pilih buku tujuan yang berbeda.")
        kas2 = _akun_id(db, BUKU[ke]["kas"])
        baris = [(kas, jumlah, 0), (lawan["id"], 0, jumlah), (kas, 0, jumlah), (kas2, jumlah, 0, tempat, dana)]
        ub = {ke: str(body.get("uraian_tujuan") or uraian).strip()}
    else:
        raise Gagal("Jenis transaksi tidak dikenal.")
    jid = buat_jurnal(db, user, tanggal, uraian, "KAS", baris, sd, no_bukti, ("BKU", None), ub)
    audit(db, user, "jurnal", jid, "BKU-" + jenis.upper(), None, {"buku": kode, "jumlah": jumlah, "uraian": uraian}, BUKU[kode]["dana"])
    return {"id": jid}


@router.delete("/transaksi/{jid}")
def hapus(jid: int, user=Depends(auth), db=Depends(get_db)):
    j = db.execute("SELECT * FROM jurnal WHERE id=?", (jid,)).fetchone()
    if not j or j["ref_jenis"] != "BKU":
        raise Gagal("Hanya transaksi BKU manual yang dapat dihapus di sini (pembayaran SPJ dikoreksi lewat SPJ).", 403)
    akun = [r["akun_id"] for r in db.execute("SELECT DISTINCT akun_id FROM jurnal_baris WHERE jurnal_id=?", (jid,)).fetchall()]
    buku = [k for k, v in BUKU.items() if _akun_id(db, v["kas"]) in akun]
    if not buku or not all(user["role"] in BUKU[k]["tulis"] for k in buku):
        raise Gagal("Anda tidak berwenang menghapus transaksi ini.", 403)
    db.execute("DELETE FROM jurnal WHERE id=?", (jid,))
    audit(db, user, "jurnal", jid, "BKU-HAPUS", {"uraian": j["uraian"], "tanggal": j["tanggal"]}, None, "BLUD")
    return {"ok": True}


@router.get("/saldo-awal")
def lihat_saldo_awal(buku: str, tahun: int, user=Depends(auth), db=Depends(get_db)):
    _izin(user, buku)
    akun = _akun_id(db, BUKU[buku]["kas"])
    rows = db.execute("""SELECT COALESCE(b.tempat,'Bank') tempat, COALESCE(b.dana,'Pelayanan Umum') dana, SUM(b.debit-b.kredit) jumlah FROM jurnal_baris b JOIN jurnal j ON j.id=b.jurnal_id
        WHERE j.basis='AWAL' AND j.ref_jenis='BKU_AWAL' AND j.tahun=? AND b.akun_id=? GROUP BY 1,2""", (tahun, akun)).fetchall()
    return {"buku": buku, "tahun": tahun, "baris": rows, "total": sum(r["jumlah"] for r in rows), "tempat": TEMPAT, "dana": DANA}


@router.put("/saldo-awal")
def simpan_saldo_awal(body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    """Saldo awal kas per buku (1 Januari). Untuk BLUD boleh dirinci per tempat & jenis dana. Lawannya otomatis ke akun Ekuitas."""
    kode = str(body.get("buku") or "").upper()
    _izin(user, kode, tulis=True)
    tahun = int(body.get("tahun") or 0)
    if not 2000 < tahun < 2100:
        raise Gagal("Tahun tidak valid.")
    kas = _akun_id(db, BUKU[kode]["kas"])
    ekuitas = _akun_id(db, "3.1.1.01")
    for j in db.execute("SELECT j.id FROM jurnal j JOIN jurnal_baris b ON b.jurnal_id=j.id WHERE j.basis='AWAL' AND j.ref_jenis='BKU_AWAL' AND j.tahun=? AND b.akun_id=?", (tahun, kas)).fetchall():
        db.execute("DELETE FROM jurnal WHERE id=?", (j["id"],))
    baris, total = [], 0
    for x in body.get("baris") or []:
        v = _angka(x.get("jumlah") or 0)
        if v:
            baris.append((kas, v, 0, x.get("tempat") if x.get("tempat") in TEMPAT else None, x.get("dana") if x.get("dana") in DANA else None))
            total += v
    if total:
        buat_jurnal(db, user, f"{tahun}-01-01", f"Saldo awal {BUKU[kode]['nama']} {tahun}", "AWAL", baris + [(ekuitas, 0, total)], None, None, ("BKU_AWAL", None))
    audit(db, user, "jurnal", tahun, "BKU-SALDO-AWAL", None, {"buku": kode, "total": total}, BUKU[kode]["dana"])
    return {"ok": True, "total": total}


# ---------------------------------------------------------------- cetak
def _id(n):   # 1.234.567
    return f"{int(n):,}".replace(",", ".")


def _en(n):   # 1,234,567 (gaya BKU Bendahara Pengeluaran Pembantu)
    return f"{int(n):,}"


def _tgl_slash(s):
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}"


def _kata(n):   # "Tiga Puluh Satu" (tanpa kata rupiah)
    return dk.terbilang(n).rsplit(" ", 1)[0].title()


def _tgl_hari_kata(akhir):
    d = dt.date.fromisoformat(akhir)
    return f"{HARI[d.weekday()]}", _kata(d.day), BULAN[d.month - 1], _kata(d.year)


def _tabel_kotak(data, lebar, gaya=None, fs=8.4, header_baris=1):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    t = Table(data, colWidths=[w * dk.cm for w in lebar], repeatRows=header_baris)
    st = [("FONTNAME", (0, 0), (-1, -1), dk.FONT), ("FONTSIZE", (0, 0), (-1, -1), fs), ("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
          ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    t.setStyle(TableStyle(st + (gaya or [])))
    return t


def _p(t, rata="l", tebal=False, ukuran=8.4):
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    return Paragraph(str(t if t is not None else ""), ParagraphStyle("b", fontName=dk.FONTB if tebal else dk.FONT, fontSize=ukuran, leading=ukuran + 1.8, alignment={"l": TA_LEFT, "c": TA_CENTER, "r": TA_RIGHT}[rata]))


def _blok_ttd(kiri, kanan, tebal_nama=True):
    from reportlab.platypus import Spacer, Table, TableStyle
    t = Table([[kiri, "", kanan]], colWidths=[7.3 * dk.cm, 3.0 * dk.cm, 7.3 * dk.cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [Spacer(1, 10), t]


def _judul_pembantu(d, db, seksi, hal):
    from reportlab.platypus import Spacer, Table, TableStyle
    skpd = _set(db, "bku_skpd", "PUSKESMAS MELATI")
    kpa, bd = d["pejabat"]["kpa"], d["pejabat"]["bendahara"]
    peran = "Bendahara Pengeluaran Pembantu" if d["buku"]["format"] == "pembantu" else "Bendahara Penerimaan"
    periode = f"Bulan : {BULAN[seksi['bulan'] - 1]} {d['tahun']}"
    rows = [[_p("SKPD"), _p(f": {skpd}"), "", ""], [_p("Pengguna Anggaran/Kuasa Pengguna Anggaran"), _p(f": {kpa['nama']}"), "", ""], [_p(f"Bendahara Pengeluaran Pembantu" if d["buku"]["format"] == "pembantu" else "Bendahara Penerimaan"), _p(f": {bd['nama']}"), _p(periode, "r"), _p(f"Hal. {hal}", "r")]]
    t = Table(rows, colWidths=[6.2 * dk.cm, 6.2 * dk.cm, 3.6 * dk.cm, 1.6 * dk.cm])
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _story_pembantu(db, d, hal_awal=1):
    from reportlab.platypus import PageBreak, Spacer
    story, hal = [], hal_awal
    B = d["buku"]
    kpa, bd = d["pejabat"]["kpa"], d["pejabat"]["bendahara"]
    for i, s in enumerate(d["seksi"]):
        if i:
            story.append(PageBreak())
        story += [_p("<b>BUKU KAS UMUM</b>", "c", True, 11), Spacer(1, 6), _judul_pembantu(d, db, s, hal), Spacer(1, 4)]
        data = [[_p("No Urut", "c"), _p("Tanggal", "c"), _p("Kode Rekening", "c"), _p("Uraian", "c"), _p("Peneriman", "c"), _p("Pengeluaran", "c")]]
        data.append([_p(s["nomor_awal"], "r"), _p(_tgl_slash(s["awal"]), "r"), "", _p("Saldo Awal"), _p(f"Rp &nbsp;&nbsp;{_en(s['saldo_awal'])}", "r"), _p("0", "r")])
        for x in s["baris"]:
            data.append([_p(x["urut"], "r"), _p(_tgl_slash(x["tanggal"]), "r"), _p(x["no_bukti"] or ""), _p(x["uraian"]), _p(f"Rp &nbsp;&nbsp;{_en(x['pen'])}" if x["pen"] else "", "r"), _p(f"Rp &nbsp;&nbsp;{_en(x['peng'])}" if x["peng"] else "", "r")])
        for _ in range(4):
            data.append(["", "", "", "", "", ""])
        tot_pen, tot_peng = s["saldo_awal"] + s["pen"], s["peng"]
        data.append(["", "", "", _p("Total", "c"), _p(f"Rp &nbsp;&nbsp;{_en(tot_pen)}", "r"), _p(_en(tot_peng), "r")])
        story.append(_tabel_kotak(data, [1.3, 1.9, 3.0, 6.6, 2.6, 2.4]))
        lalu = s["saldo_awal"]
        akhir = dt.date.fromisoformat(s["akhir"])
        bln, bln_lalu = BULAN[akhir.month - 1], BULAN[(akhir.month - 2) % 12]
        ringkas = [
            [_p(f"Jumlah bulan / tanggal &nbsp;&nbsp;: {bln} / {akhir.day} {akhir.year}"), _p("Rp.", "r"), _p(_en(s["pen"]), "r"), _p("Rp.", "r"), _p(_en(s["peng"]), "r")],
            [_p(f"Jumlah sampai dengan bulan lalu / tanggal : {bln_lalu} / {_tgl_akhir_lalu(s)}"), _p("Rp.", "r"), _p(_en(lalu), "r"), _p("Rp.", "r"), _p("0", "r")],
            [_p(f"Jumlah bulan / tanggal &nbsp;&nbsp;: {bln} / {akhir.day} {akhir.year}"), _p("Rp.", "r"), _p(_en(tot_pen), "r"), _p("Rp.", "r"), _p(_en(tot_peng), "r")],
            [_p("Sisa"), "", "", "", _p(_en(tot_pen - tot_peng), "r")],
            [_p(f"Pada hari ini / tanggal &nbsp;{HARI[akhir.weekday()]} / {akhir.day} {bln} {akhir.year}"), "", "", "", ""],
        ]
        from reportlab.platypus import Table, TableStyle
        t = Table(ringkas, colWidths=[8.2 * dk.cm, 1.0 * dk.cm, 3.0 * dk.cm, 1.0 * dk.cm, 3.4 * dk.cm])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), dk.FONT), ("FONTSIZE", (0, 0), (-1, -1), 8.4), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (1, 1), (4, 1), 0.5, (0, 0, 0))]))
        story += [Spacer(1, 6), t]
        kiri = [_p("Mengetahui"), _p("Pengguna Anggaran/Kuasa Pengguna Anggaran"), Spacer(1, 38), _p(kpa["nama"]), _p(f"NIP : {kpa['nip']}")]
        kanan = [Spacer(1, 12), _p("Bendahara Pengeluaran Pembantu"), Spacer(1, 38), _p(f"<u><b>{bd['nama']}</b></u>"), _p(f"<b>NIP. {bd['nip']}</b>")]
        story += _blok_ttd(kiri, kanan)
        hal += 1
    return story


def _tgl_akhir_lalu(s):
    d = dt.date.fromisoformat(s["awal"]) - dt.timedelta(days=1)
    return f"{d.day} {d.year}"


def _story_penerimaan(db, d, hal_awal=1):
    from reportlab.platypus import PageBreak, Spacer
    story = []
    kpa, bd = d["pejabat"]["kpa"], d["pejabat"]["bendahara"]
    skpd = _set(db, "bku_skpd", "PUSKESMAS MELATI").title()
    kota = _set(db, "kota_surat", "Kuala Kapuas")
    for i, s in enumerate(d["seksi"]):
        if i:
            story.append(PageBreak())
        akhir = dt.date.fromisoformat(s["akhir"])
        bln = BULAN[akhir.month - 1]
        story += [_p("<b>PEMERINTAH KABUPATEN KAPUAS</b>", "c", True, 9), _p("<u><b>BUKU KAS UMUM</b></u>", "c", True, 9), _p(f"<b>BULAN : {bln.upper()} {d['tahun']}</b>", "c", True, 9), Spacer(1, 8)]
        from reportlab.platypus import Table, TableStyle
        h = Table([[_p("<b>SKPD</b>", ukuran=8), _p(f": {skpd}", ukuran=8)], [_p("<b>Pengguna Anggaran</b>", ukuran=8), _p(f": {kpa['nama']}", ukuran=8)], [_p("<b>Bendahara Penerimaan</b>", ukuran=8), _p(f": {bd['nama']}", ukuran=8)]], colWidths=[3.6 * dk.cm, 8 * dk.cm])
        h.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [h, Spacer(1, 4)]
        data = [[_p("No.<br/>Urut", "c", True), _p("Tanggal", "c", True), _p("Kode Rekening", "c", True), _p("Uraian", "c", True), _p("Penerimaan (Rp)", "c", True), _p("Pengeluaran (Rp)", "c", True)],
                [_p("1", "c", True), _p("2", "c", True), _p("3", "c", True), _p("4", "c", True), _p("5", "c", True), _p("6", "c", True)]]
        for x in s["baris"]:
            data.append([_p(x["urut"], "c"), _p(_tgl_slash(x["tanggal"]), "c"), _p(x["no_bukti"] or ""), _p(x["uraian"]), _p(_id(x["pen"]) if x["pen"] else "", "r"), _p(_id(x["peng"]) if x["peng"] else "", "r")])
        data.append(["", "", "", "", "", ""])
        story.append(_tabel_kotak(data, [1.2, 1.9, 2.0, 7.4, 2.6, 2.6], header_baris=2, fs=8))
        sisa = (s["sd_pen"]) - (s["sd_peng"])
        awal_d = dt.date.fromisoformat(s["awal"]) - dt.timedelta(days=1)
        ringkas = [
            [_p("<b>Jumlah bulan/tanggal</b>", ukuran=8), _p(f"<b>{akhir.day} {bln} {akhir.year}</b>", "c", ukuran=8), _p(f"Rp &nbsp;{_id(s['pen'])}", "r", ukuran=8), _p(f"Rp &nbsp;{_id(s['peng'])}", "r", ukuran=8)],
            [_p("<b>Jumlah sampai bulan lalu/tgl</b>", ukuran=8), _p(f"<b>{awal_d.day} {BULAN[awal_d.month - 1]} {awal_d.year}</b>", "c", ukuran=8), _p(f"Rp &nbsp;{_id(s['lalu_pen'])}", "r", ukuran=8), _p(f"Rp &nbsp;{_id(s['lalu_peng'])}", "r", ukuran=8)],
            [_p("<b>Jumlah semua s/d bulan/tanggal</b>", ukuran=8), _p(f"<b>{akhir.day} {bln} {akhir.year}</b>", "c", ukuran=8), _p(f"Rp &nbsp;{_id(s['sd_pen'])}", "r", ukuran=8), _p(f"Rp &nbsp;{_id(s['sd_peng'])}", "r", ukuran=8)],
        ]
        t = Table(ringkas, colWidths=[5.0 * dk.cm, 4.4 * dk.cm, 3.6 * dk.cm, 3.6 * dk.cm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (2, 0), (3, 0), 0.5, (0, 0, 0))]))
        d_tgl = dt.date.fromisoformat(s["akhir"])
        story += [Spacer(1, 5), t, Spacer(1, 2),
                  _p(f"<b>Sisa Kas pada hari ini tanggal: {_kata(d_tgl.day)} Bulan {bln} Tahun {_kata(d_tgl.year)}</b>", ukuran=8),
                  _p(f"<b>oleh kami didapat dalam kas Rp. &nbsp;&nbsp;{'NIHIL' if sisa == 0 else _id(sisa)}</b>", ukuran=8), Spacer(1, 4),
                  _tabel_kotak([[_p("terdiri dari :<br/>a. Kuitansi &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Rp. &nbsp;&nbsp;&nbsp;-<br/>b. Saldo Bank &nbsp;&nbsp;&nbsp;&nbsp;Rp.<br/>c. Surat Berharga Rp.", ukuran=7.6)]], [5.0], fs=7.6, header_baris=0)]
        kiri = [_p("<b>Mengetahui :</b>", ukuran=8), _p("<b>Kepala UPT Puskesmas Melati</b>", ukuran=8), Spacer(1, 34), _p(f"<u><b>{kpa['nama']}</b></u>", ukuran=8), _p(f"<b>NIP. {kpa['nip']}</b>", ukuran=8)]
        kanan = [_p(f"<b>{kota}, {akhir.day} {bln} {akhir.year}</b>", ukuran=8), _p("<b>Bendahara Penerimaan,</b>", ukuran=8), Spacer(1, 34), _p(f"<u><b>{bd['nama']}</b></u>", ukuran=8), _p(f"<b>NIP. {bd['nip']}</b>", ukuran=8)]
        story += _blok_ttd(kiri, kanan)
    return story


def _story_blud(db, d, hal_awal=1):
    from reportlab.platypus import PageBreak, Spacer, Table, TableStyle
    story = []
    kpa, bd = d["pejabat"]["kpa"], d["pejabat"]["bendahara"]
    for i, s in enumerate(d["seksi"]):
        if i:
            story.append(PageBreak())
        akhir = dt.date.fromisoformat(s["akhir"])
        bln = BULAN[akhir.month - 1]
        story += [_p("<b>BUKU KAS BENDAHARA DANA BLUD PUSKESMAS MELATI DALAM RANGKA PENCATATAN</b>", "c", True, 8.6), _p("<b>PENDAPATAN DAN BELANJA</b>", "c", True, 8.6), Spacer(1, 8)]
        h = Table([[_p("<b>Kepala FKTP</b>", ukuran=8.2), _p(f"<b>{kpa['nama']}</b>", ukuran=8.2)], [_p("<b>Bendahara Dana Kapitasi/BLUD</b>", ukuran=8.2), _p(f"<b>{bd['nama']}</b>", ukuran=8.2)], [_p("<b>Bulan</b>", ukuran=8.2), _p(f"<b>: {bln} {d['tahun']}</b>", ukuran=8.2)]], colWidths=[5.0 * dk.cm, 9 * dk.cm])
        h.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [h, Spacer(1, 3)]
        data = [[_p("NO", "c", True), _p("TANGGAL", "c", True), _p("NO. BUKTI", "c", True), _p("URAIAN", "c", True), _p("PENDAPATAN", "c", True), _p("BELANJA", "c", True), _p("SALDO", "c", True)],
                [_p(x, "c", True) for x in "1234567"[:3]] + [_p("4", "c", True), _p("5", "c", True), _p("6", "c", True), _p("7", "c", True)]]
        data.append(["", "", "", _p("<i>Saldo Bulan Lalu</i>"), "", "", _p(_id(s["saldo_awal"]), "r")])
        for x in s["baris"]:
            bukti = x["no_bukti"] or f"{x['urut']}/BKU/{'D' if x['pen'] and not x['peng'] else 'K'}"
            data.append([_p(x["urut"], "c"), _p(_tgl_slash(x["tanggal"]).replace("/", "."), "c"), _p(bukti, "c"), _p(x["uraian"]), _p(_id(x["pen"]) if x["pen"] else "", "r"), _p(_id(x["peng"]) if x["peng"] else "", "r"), ""])
        data.append(["", "", "", "", "", "", ""])
        data.append(["", "", "", _p("<i>Jumlah bulan ini ...........</i>"), _p(f"<b>{_id(s['pen'])}</b>", "r"), _p(f"<b>{_id(s['peng'])}</b>", "r"), _p(f"<b>{_id(s['pen'] - s['peng'])}</b>", "r")])
        sd_pen = s["sd_pen"] + d["saldo_awal_tahun"]
        data.append(["", "", "", _p("<i>Jumlah sampai dengan bulan ini ........</i>"), _p(f"<b>{_id(sd_pen)}</b>", "r"), _p(f"<b>{_id(s['sd_peng'])}</b>", "r"), _p(f"<b>{_id(sd_pen - s['sd_peng'])}</b>", "r")])
        story.append(_tabel_kotak(data, [0.9, 2.0, 2.2, 6.3, 2.4, 2.2, 2.2], header_baris=2, fs=7.8))
        saldo = sd_pen - s["sd_peng"]
        story += [Spacer(1, 3), _p(f"Pada hari ini {HARI[akhir.weekday()]} Tanggal {_kata(akhir.day)} Bulan {bln} Tahun {_kata(akhir.year)}, buku kas umum ini ditutup oleh bendahara JKN ( BLUD ) dengan keadaan sbb.:", ukuran=7.6), Spacer(1, 3)]
        akun = _akun_id(db, BUKU["BLUD"]["kas"])
        r_ = _rincian_saldo(db, akun, s["akhir"])
        bank = {dn: v for (t_, dn), v in r_.items() if t_ == "Bank"}
        kas_jkn = sum(v for (t_, _), v in r_.items() if t_ == "Kas JKN")
        kas_lain = sum(v for (t_, _), v in r_.items() if t_ == "Kas Lain-lain")
        panjar = sum(v for (t_, _), v in r_.items() if t_ == "Panjar")
        total_bank = sum(bank.values())
        rows = [[_p("Jumlah pendapatan", ukuran=7.8), _p("..................................................... Rp.", "r", ukuran=7.8), _p(f"<b>{_id(sd_pen)}</b>", "r", ukuran=7.8), ""],
                [_p("Jumlah Belanja", ukuran=7.8), _p("..................................................... Rp.", "r", ukuran=7.8), _p(f"<b>{_id(s['sd_peng'])}</b>", "r", ukuran=7.8), ""],
                [_p("Saldo", ukuran=7.8), _p("..................................................... Rp.", "r", ukuran=7.8), _p(f"<b>{_id(saldo)}</b>", "r", ukuran=7.8), ""],
                [_p("1. Pada Bank :", ukuran=7.8), "", "", _p(_id(total_bank), "r", ukuran=7.8)]]
        for nm in DANA:
            rows.append([_p(f"* {nm}", ukuran=7.8), _p("..........Rp.", "r", ukuran=7.8), "", _p(_id(bank.get(nm, 0)), "r", ukuran=7.8)])
        rows += [[_p("2. Pada Kas JKN", ukuran=7.8), _p("..........Rp.", "r", ukuran=7.8), "", _p(_id(kas_jkn), "r", ukuran=7.8)], [_p("3. Pada Kas Lain lain", ukuran=7.8), _p("..........Rp.", "r", ukuran=7.8), "", _p(_id(kas_lain), "r", ukuran=7.8)],
                 [_p("4. Pada Panjar", ukuran=7.8), _p("..........Rp.", "r", ukuran=7.8), "", _p(_id(panjar), "r", ukuran=7.8)], [_p("Jumlah", ukuran=7.8), _p("..........Rp.", "r", ukuran=7.8), "", _p(f"<b>{_id(total_bank + kas_jkn + kas_lain + panjar)}</b>", "r", ukuran=7.8)]]
        t = Table(rows, colWidths=[4.0 * dk.cm, 3.8 * dk.cm, 3.0 * dk.cm, 3.0 * dk.cm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOX", (2, 0), (2, 2), 0.5, (0, 0, 0))]))
        story.append(t)
        kiri = [_p("<b>Mengetahui</b>", ukuran=8), _p("<b>Kuasa Pengguna Anggaran</b>", ukuran=8), Spacer(1, 34), _p(f"<b>{kpa['nama']}</b>", ukuran=8), _p(f"NIP. {kpa['nip']}", ukuran=8)]
        kanan = [Spacer(1, 12), _p("<b>Bendahara Pengeluaran BLUD</b>", ukuran=8), Spacer(1, 34), _p(f"<b>{bd['nama']}</b>", ukuran=8), _p(f"NIP. {bd['nip']}", ukuran=8)]
        story += _blok_ttd(kiri, kanan)
    return story


@router.get("/dok")
def dokumen(buku: str, tahun: int, bulan: int = 0, format: str = "pdf", user=Depends(auth), db=Depends(get_db)):
    _izin(user, buku)
    d = susun(db, buku, tahun, bulan)
    d["pejabat"] = {"bendahara": _pejabat(db, BUKU[buku]["peran"]), "kpa": _kpa(db)}
    nama = f"BKU_{buku}_{tahun}" + (f"_{bulan:02d}" if bulan else "_tahunan")
    if format == "xlsx":
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "BKU"
        fm = BUKU[buku]["format"]
        ws.append([BUKU[buku]["nama"] + f" — {'Tahun ' + str(tahun) if not bulan else BULAN[bulan - 1] + ' ' + str(tahun)}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([])
        kolom = {"pembantu": ["No Urut", "Tanggal", "Kode Rekening", "Uraian", "Penerimaan", "Pengeluaran"], "penerimaan": ["No Urut", "Tanggal", "Kode Rekening", "Uraian", "Penerimaan (Rp)", "Pengeluaran (Rp)"],
                 "blud": ["NO", "TANGGAL", "NO. BUKTI", "URAIAN", "PENDAPATAN", "BELANJA", "SALDO"]}[fm]
        ws.append(kolom)
        for c in ws[3]:
            c.font = Font(bold=True)
        for s in d["seksi"]:
            ws.append([None, s["awal"], None, ("Saldo Awal" if fm == "pembantu" else "Saldo Bulan Lalu"), s["saldo_awal"] if fm == "pembantu" else None, 0 if fm == "pembantu" else None] + ([s["saldo_awal"]] if fm == "blud" else []))
            for x in s["baris"]:
                ws.append([x["urut"], x["tanggal"], x["no_bukti"], x["uraian"], x["pen"] or None, x["peng"] or None])
            ws.append([None, None, None, f"Jumlah bulan {BULAN[s['bulan'] - 1]}", s["pen"], s["peng"]])
        for col, w in zip("ABCDEFG", (8, 12, 18, 70, 16, 16, 16)):
            ws.column_dimensions[col].width = w
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{nama}.xlsx"', "Cache-Control": "no-store"})
    fm = BUKU[buku]["format"]
    story = {"pembantu": _story_pembantu, "penerimaan": _story_penerimaan, "blud": _story_blud}[fm](db, d)
    pdf = dk.build_pdf(story, nama)
    if format == "docx":
        return Response(_pdf_ke_docx(pdf), media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{nama}.docx"', "Cache-Control": "no-store"})
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nama}.pdf"', "Cache-Control": "no-store"})
