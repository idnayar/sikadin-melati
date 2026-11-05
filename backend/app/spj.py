"""Tahap 5 — Realisasi & SPJ (tanpa panjar).
Alur: Draft -> Diajukan -> Diverifikasi -> Dibayar (atau Dikembalikan untuk diperbaiki). Hanya SPJ Dibayar yang dihitung sebagai realisasi.
SPJ perjalanan dinas (jenis SPD) lahir dari SPD pada ST yang terbit: biaya realisasi per komponen tidak boleh melebihi tarif SPD.
SPJ jenis UMUM untuk belanja lain pada baris RAB. Total dibayar per baris tidak boleh melebihi pagu baris."""
import datetime as dt
import io
import json
import re

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response

from . import akuntansi, sinkron
from . import dokumen as dk
from .core import Gagal, akses_uang, audit, auth, cek_uang, get_db
from .surat import DOCX, _pdf_ke_docx

router = APIRouter(prefix="/api/spj")
STATUS = ("Draft", "Diajukan", "Dikembalikan", "Diverifikasi", "Dibayar")
EDIT = ("Draft", "Dikembalikan")


def _set(db, k, d=""):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    return r["nilai"] if r and r["nilai"] is not None else d


def _int(v, nama="Jumlah") -> int:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        raise Gagal(f"{nama} harus berupa angka.")
    if n < 0:
        raise Gagal(f"{nama} tidak boleh negatif.")
    return n


def _tgl(v, nama="Tanggal") -> str:
    try:
        return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise Gagal(f"{nama} tidak valid (format TTTT-BB-HH).")


def _ambil(db, sid):
    r = db.execute("""SELECT s.*, sd.kode dana, b.uraian baris_uraian, b.jumlah pagu_baris, b.kode_rekening, p.nama pegawai_nama, p.nip pegawai_nip,
        st.nomor st_nomor, st.nomor_srikandi st_srikandi, st.status st_status
        FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id JOIN bok_baris b ON b.id=s.baris_id
        LEFT JOIN pegawai p ON p.id=s.pegawai_id LEFT JOIN surat_tugas st ON st.id=s.st_id WHERE s.id=?""", (sid,)).fetchone()
    if not r:
        raise Gagal("SPJ tidak ditemukan.", 404)
    return r


def _akses(user, r) -> tuple[bool, bool]:
    """(boleh_lihat, penuh). penuh = berhak atas sumber dananya (bukan sekadar petugas yang bersangkutan)."""
    if user["role"] != "pegawai" and akses_uang(user, r["dana"], "baca"):
        return True, True
    return (bool(user.get("pegawai_id")) and r["jenis"] == "SPD" and r["pegawai_id"] == user.get("pegawai_id")), False


def _lihat(user, r):
    boleh, penuh = _akses(user, r)
    if not boleh:
        raise Gagal("Anda tidak berhak atas SPJ ini.", 403)
    return penuh


def _bisa_ubah(user, r, penuh) -> bool:
    if r["status"] not in EDIT:
        return False
    if r["jenis"] == "SPD":
        return (penuh and akses_uang(user, r["dana"], "rencana")) or (not penuh)
    return penuh and akses_uang(user, r["dana"], "rencana")


def _bentuk(r, penuh, user) -> dict:
    o = {k: r[k] for k in r.keys() if k not in ("rincian_json",)}
    o["rincian"] = json.loads(r["rincian_json"] or "[]")
    o["penuh"] = penuh
    o["bisa_ubah"] = _bisa_ubah(user, r, penuh)
    pagu_ok = user["role"] != "pegawai" and akses_uang(user, r["dana"], "pagu")
    o["bisa_verifikasi"] = pagu_ok and r["status"] == "Diajukan"
    o["bisa_bayar"] = pagu_ok and r["status"] == "Diverifikasi"
    o["bisa_koreksi"] = user["role"] == "kepala" and r["status"] == "Dibayar"
    o["bisa_ajukan"] = o["bisa_ubah"]
    o["bisa_hapus"] = o["bisa_ubah"] and (r["jenis"] == "UMUM" or r["status"] in EDIT)
    return o


def _dibayar_baris(db, baris_id, excl=0) -> int:
    return db.execute("SELECT COALESCE(SUM(total),0) t FROM spj WHERE baris_id=? AND status='Dibayar' AND id!=?", (baris_id, excl)).fetchone()["t"]


def _hitung_rincian(rincian_lama: list, masuk: list | None) -> tuple[list, int]:
    """Terapkan realisasi per komponen dari klien; jumlah tak boleh melebihi tarif (rencana) dan tidak negatif."""
    if masuk is None:
        return rincian_lama, sum(int(x.get("jumlah") or 0) for x in rincian_lama)
    if not isinstance(masuk, list) or len(masuk) != len(rincian_lama):
        raise Gagal("Rincian realisasi tidak sesuai dengan rincian SPD.")
    hasil, total = [], 0
    for lama, baru in zip(rincian_lama, masuk):
        j = _int((baru or {}).get("jumlah"), f"Jumlah «{lama['uraian']}»")
        if j > int(lama["rencana"]):
            raise Gagal(f"Realisasi «{lama['uraian']}» ({dk.rp(j)}) melebihi tarif SPD ({dk.rp(lama['rencana'])}).")
        hasil.append({**lama, "jumlah": j, "bukti": str((baru or {}).get("bukti") or "").strip()[:200]})
        total += j
    return hasil, total


# ---------------------------------------------------------------- daftar & pembuatan
@router.get("")
def daftar(tahun: int, sumber: str = "", status: str = "", bulan: int = 0, user=Depends(auth), db=Depends(get_db)):
    rows = db.execute("""SELECT s.id FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE s.tahun=?
        AND (?='' OR sd.kode=?) AND (?='' OR s.status=?) AND (?=0 OR CAST(substr(COALESCE(s.tanggal_bayar,s.tanggal),6,2) AS INTEGER)=?)
        ORDER BY s.tanggal DESC, s.id DESC""", (tahun, sumber.upper(), sumber.upper(), status, status, bulan, bulan)).fetchall()
    out = []
    for x in rows:
        r = _ambil(db, x["id"])
        boleh, penuh = _akses(user, r)
        if boleh:
            out.append(_bentuk(r, penuh, user))
    return out


@router.get("/belum")
def belum(tahun: int, user=Depends(auth), db=Depends(get_db)):
    """SPD pada ST yang terbit tetapi SPJ-nya belum dibuat (untuk petugas: miliknya saja)."""
    rows = db.execute("""SELECT d.id spd_id, d.total, d.pegawai_id, p.nama pegawai, st.id st_id, st.nomor, st.maksud, sd.kode dana, j.mulai, j.selesai, l.nama lokasi
        FROM spd d JOIN surat_tugas st ON st.id=d.st_id AND st.status='Terbit' JOIN jadwal j ON j.id=st.jadwal_id JOIN pegawai p ON p.id=d.pegawai_id
        JOIN sumber_dana sd ON sd.id=st.sumber_dana_id JOIN lokasi l ON l.id=j.lokasi_id
        WHERE j.tahun=? AND NOT EXISTS(SELECT 1 FROM spj s WHERE s.spd_id=d.id) ORDER BY j.mulai, st.id, p.nama""", (tahun,)).fetchall()
    out = []
    for r in rows:
        if user["role"] != "pegawai" and akses_uang(user, r["dana"], "rencana"):
            out.append(r)
        elif user.get("pegawai_id") and r["pegawai_id"] == user["pegawai_id"]:
            out.append(r)
    return out


@router.post("/spd/{spd_id}")
def dari_spd(spd_id: int, user=Depends(auth), db=Depends(get_db)):
    d = db.execute("""SELECT d.*, st.status st_status, st.sumber_dana_id, st.tahun, st.jadwal_id, st.nomor, j.baris_id, j.mulai, j.selesai, j.kegiatan, p.nama pegawai, sd.kode dana
        FROM spd d JOIN surat_tugas st ON st.id=d.st_id JOIN jadwal j ON j.id=st.jadwal_id JOIN pegawai p ON p.id=d.pegawai_id JOIN sumber_dana sd ON sd.id=st.sumber_dana_id
        WHERE d.id=?""", (spd_id,)).fetchone()
    if not d:
        raise Gagal("SPD tidak ditemukan.", 404)
    own = bool(user.get("pegawai_id")) and d["pegawai_id"] == user["pegawai_id"]
    if not (own or (user["role"] != "pegawai" and akses_uang(user, d["dana"], "rencana"))):
        raise Gagal("Anda tidak berhak membuat SPJ ini.", 403)
    if d["st_status"] != "Terbit":
        raise Gagal("ST sudah dibatalkan; SPJ tidak dapat dibuat.")
    ada = db.execute("SELECT id FROM spj WHERE spd_id=?", (spd_id,)).fetchone()
    if ada:
        return {"id": ada["id"], "sudah_ada": True}
    return {"id": sinkron.buat_spj_dari_spd(db, user, spd_id), "sudah_ada": False}


@router.post("")
def buat_umum(body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    b = db.execute("""SELECT b.id, b.jumlah, m.tahun, m.sumber_dana_id, sd.kode dana FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id
        JOIN bok_menu m ON m.id=r.menu_id JOIN sumber_dana sd ON sd.id=m.sumber_dana_id WHERE b.id=?""", (body.get("baris_id"),)).fetchone()
    if not b:
        raise Gagal("Baris RAB tidak ditemukan.", 404)
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    cek_uang(user, b["dana"], "rencana")
    uraian = str(body.get("uraian") or "").strip()
    if len(uraian) < 3:
        raise Gagal("Uraian belanja wajib diisi.")
    jumlah = _int(body.get("jumlah"))
    if jumlah <= 0:
        raise Gagal("Jumlah harus lebih dari nol.")
    tanggal = _tgl(body.get("tanggal"))
    rinci = [{"uraian": uraian, "volume": 1, "satuan": "paket", "tarif": jumlah, "rencana": jumlah, "jumlah": jumlah, "bukti": str(body.get("bukti") or "")[:200]}]
    sid = db.execute("""INSERT INTO spj(jenis,tahun,sumber_dana_id,baris_id,tanggal,uraian,penerima,rincian_json,total_rencana,total,catatan,dibuat_oleh)
        VALUES('UMUM',?,?,?,?,?,?,?,?,?,?,?)""", (b["tahun"], b["sumber_dana_id"], b["id"], tanggal, uraian, str(body.get("penerima") or "").strip(),
                                                json.dumps(rinci, ensure_ascii=False), jumlah, jumlah, str(body.get("catatan") or "").strip() or None, user["username"])).lastrowid
    audit(db, user, "spj", sid, "BUAT", None, {"jenis": "UMUM", "uraian": uraian, "total": jumlah}, b["dana"])
    return {"id": sid}


@router.get("/ringkasan")
def ringkasan(tahun: int, sumber: str, user=Depends(auth), db=Depends(get_db)):
    """Pagu, rencana, SPJ berjalan, dan realisasi (dibayar) per menu/rincian/baris untuk satu sumber dana."""
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    sumber = sumber.upper()
    cek_uang(user, sumber, "baca")
    sd = db.execute("SELECT id FROM sumber_dana WHERE kode=?", (sumber,)).fetchone()
    if not sd:
        raise Gagal("Sumber dana tidak dikenal.", 404)
    rows = db.execute("""SELECT m.id menu_id, m.no menu_no, m.nama menu, r.id rincian_id, r.no rincian_no, r.nama rincian, b.id baris_id, b.uraian, b.kode_rekening, b.jumlah pagu,
        COALESCE((SELECT SUM(x.estimasi) FROM rencana x WHERE x.baris_id=b.id AND x.status IN ('Disetujui','Terjadwal','Terlaksana','SPJ Selesai')),0) rencana,
        COALESCE((SELECT SUM(s.total) FROM spj s WHERE s.baris_id=b.id AND s.status IN ('Diajukan','Diverifikasi')),0) proses,
        COALESCE((SELECT SUM(s.total) FROM spj s WHERE s.baris_id=b.id AND s.status='Dibayar'),0) realisasi
        FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id
        WHERE m.tahun=? AND m.sumber_dana_id=? ORDER BY m.id, r.id, b.urut, b.id""", (tahun, sd["id"])).fetchall()
    menu: dict = {}
    for x in rows:
        m = menu.setdefault(x["menu_id"], {"id": x["menu_id"], "no": x["menu_no"], "nama": x["menu"], "pagu": 0, "realisasi": 0, "proses": 0, "rincian": {}})
        ri = m["rincian"].setdefault(x["rincian_id"], {"id": x["rincian_id"], "no": x["rincian_no"], "nama": x["rincian"], "pagu": 0, "realisasi": 0, "proses": 0, "baris": []})
        x["sisa"] = x["pagu"] - x["realisasi"]
        x["persen"] = round(100 * x["realisasi"] / x["pagu"], 1) if x["pagu"] else 0
        ri["baris"].append(x)
        for k in ("pagu", "realisasi", "proses"):
            ri[k] += x[k]
            m[k] += x[k]
    out = []
    for m in menu.values():
        m["rincian"] = list(m["rincian"].values())
        m["sisa"] = m["pagu"] - m["realisasi"]
        m["persen"] = round(100 * m["realisasi"] / m["pagu"], 1) if m["pagu"] else 0
        for ri in m["rincian"]:
            ri["sisa"] = ri["pagu"] - ri["realisasi"]
            ri["persen"] = round(100 * ri["realisasi"] / ri["pagu"], 1) if ri["pagu"] else 0
        out.append(m)
    tot = {k: sum(m[k] for m in out) for k in ("pagu", "realisasi", "proses")}
    tot["sisa"] = tot["pagu"] - tot["realisasi"]
    tot["persen"] = round(100 * tot["realisasi"] / tot["pagu"], 1) if tot["pagu"] else 0
    return {"tahun": tahun, "sumber": sumber, "total": tot, "menu": out}


# ---------------------------------------------------------------- rekap (PDF / DOCX / XLSX) — didefinisikan sebelum /{sid}
def _kop(db) -> dict:
    return {"baris1": _set(db, "kop_baris1"), "baris2": _set(db, "kop_baris2"), "baris3": _set(db, "kop_baris3"), "alamat": _set(db, "kop_alamat"),
            "jalan": _set(db, "kop_jalan"), "kodepos": _set(db, "kop_kodepos"), "laman": _set(db, "kop_laman"), "email": _set(db, "kop_email")}


def _pejabat(db, kata) -> dict:
    if kata == "Kepala":   # penandatangan/KPA = Kepala Puskesmas
        r = db.execute("SELECT nama, nip, jabatan, peran FROM pejabat WHERE aktif=1 AND (peran LIKE '%Penandatangan%' OR jabatan LIKE 'Kepala%') ORDER BY id LIMIT 1").fetchone()
        return r or {"nama": "", "nip": "", "jabatan": "Kepala", "peran": "Kepala"}
    r = db.execute("SELECT nama, nip, jabatan, peran FROM pejabat WHERE aktif=1 AND peran LIKE ? ORDER BY id LIMIT 1", (f"%{kata}%",)).fetchone()
    return r or {"nama": "", "nip": "", "jabatan": kata, "peran": kata}


@router.get("/rekap/dok")
def rekap(tahun: int, sumber: str, bulan: int = 0, format: str = "pdf", user=Depends(auth), db=Depends(get_db)):
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    sumber = sumber.upper()
    cek_uang(user, sumber, "baca")
    ids = db.execute("""SELECT s.id FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE s.tahun=? AND sd.kode=? AND s.status='Dibayar'
        AND (?=0 OR CAST(substr(s.tanggal_bayar,6,2) AS INTEGER)=?) ORDER BY s.tanggal_bayar, s.id""", (tahun, sumber, bulan, bulan)).fetchall()
    rows = [_ambil(db, x["id"]) for x in ids]
    total = sum(r["total"] for r in rows)
    periode = f"{dk.BULAN[bulan - 1]} {tahun}" if bulan else f"Tahun {tahun}"
    if format == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Rekap SPJ"
        ws.append([f"REKAP REALISASI (SPJ DIBAYAR) — {sumber} — {periode}"])
        ws.append(["No", "Tanggal bayar", "No. bukti", "Uraian", "Penerima", "Kode rekening", "No. ST", "Jumlah (Rp)"])
        for i, r in enumerate(rows, 1):
            ws.append([i, r["tanggal_bayar"], r["no_bukti"], r["uraian"], r["pegawai_nama"] or r["penerima"], r["kode_rekening"], r["st_nomor"], r["total"]])
        ws.append(["", "", "", "", "", "", "JUMLAH", total])
        for col, w in zip("ABCDEFGH", (5, 14, 22, 50, 28, 18, 38, 16)):
            ws.column_dimensions[col].width = w
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="Rekap_SPJ_{sumber}_{tahun}{bulan or ""}.xlsx"', "Cache-Control": "no-store"})
    story = dk.kop(_kop(db)) + [dk.P("<b>REKAP REALISASI BELANJA (SPJ TELAH DIBAYAR)</b>", "judul"), dk.Spacer(1, 4),
                                dk.P(f"Sumber dana : <b>{sumber}</b><br/>Periode : {periode}", "n"), dk.Spacer(1, 6)]
    data = [["No", "Tgl bayar", "No. bukti", "Uraian / penerima", "Jumlah"]]
    for i, r in enumerate(rows, 1):
        data.append([str(i), dk.P(dk.tgl(r["tanggal_bayar"]), "kecil"), dk.P(dk.esc(r["no_bukti"]), "kecil"), dk.P(f"{dk.esc(r['uraian'])}<br/><i>{dk.esc(r['pegawai_nama'] or r['penerima'])}</i>", "kecil"), dk.P(dk.rp(r["total"]), "r")])
    if len(data) == 1:
        data.append(["", "", "", dk.P("(belum ada SPJ yang dibayar pada periode ini)", "kecil"), ""])
    data.append(["", "", "", dk.P("<b>Jumlah</b>", "n"), dk.P(f"<b>{dk.rp(total)}</b>", "r")])
    kep, bend = _pejabat(db, "Kepala"), _pejabat(db, "Bendahara")
    ttd = dk.Table([[dk.P(f"Mengetahui,<br/>{dk.esc(kep['jabatan'] or 'Kepala')}<br/><br/><br/><br/><u>{dk.esc(kep['nama'])}</u><br/>NIP. {dk.esc(kep['nip'] or '-')}", "n"),
                     dk.P(f"{dk.esc(_set(db, 'kota_surat', 'Kuala Kapuas'))}, {dk.tgl(dt.date.today().isoformat())}<br/>{dk.esc(bend['jabatan'] or 'Bendahara')}<br/><br/><br/><br/><u>{dk.esc(bend['nama'])}</u><br/>NIP. {dk.esc(bend['nip'] or '-')}", "n")]],
                   colWidths=[8.4 * dk.cm, 8.4 * dk.cm])
    story += [dk._tabel(data, [1.0 * dk.cm, 2.6 * dk.cm, 3.4 * dk.cm, 6.6 * dk.cm, 3.2 * dk.cm]), dk.Spacer(1, 6),
              dk.P(f"Terbilang : <i>{dk.esc(dk.terbilang(total))}</i>", "n"), dk.Spacer(1, 16), ttd]
    pdf = dk.build_pdf(story, f"Rekap SPJ {sumber} {periode}")
    if format == "docx":
        return Response(_pdf_ke_docx(pdf), media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="Rekap_SPJ_{sumber}_{tahun}{bulan or ""}.docx"', "Cache-Control": "no-store"})
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="Rekap_SPJ_{sumber}_{tahun}{bulan or ""}.pdf"', "Cache-Control": "no-store"})


# ---------------------------------------------------------------- satu SPJ
MAKS_BERKAS, MAKS_UKURAN = 8, 4 * 1024 * 1024


def _tipe(data: bytes):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if data[:5] == b"%PDF-":
        return "application/pdf", ".pdf"
    return None, None


def _daftar_bukti(db, sid):
    return db.execute("SELECT id, nama, tipe, ukuran, diunggah_oleh, diunggah_pada FROM spj_bukti WHERE spj_id=? ORDER BY id", (sid,)).fetchall()


@router.post("/{sid}/bukti")
async def unggah_bukti(sid: int, request: Request, nama: str = "bukti", user=Depends(auth), db=Depends(get_db)):
    """Unggah satu foto/PDF bukti (badan permintaan = berkas mentah, mis. dari kamera HP). Foto dikompres di browser; batas 4 MB, 8 berkas per SPJ."""
    r = _ambil(db, sid)
    penuh = _lihat(user, r)
    if not _bisa_ubah(user, r, penuh):
        raise Gagal("Bukti hanya dapat ditambah saat SPJ berstatus Draft/Dikembalikan dan oleh yang berwenang.", 403)
    data = await request.body()
    if not data:
        raise Gagal("Berkas kosong.")
    if len(data) > MAKS_UKURAN:
        raise Gagal(f"Berkas terlalu besar ({len(data) // 1024} KB); maksimal {MAKS_UKURAN // 1024 // 1024} MB.")
    tipe, ekt = _tipe(data)
    if not tipe:
        raise Gagal("Format tidak didukung. Gunakan foto JPG/PNG/WebP atau PDF.")
    if db.execute("SELECT COUNT(*) c FROM spj_bukti WHERE spj_id=?", (sid,)).fetchone()["c"] >= MAKS_BERKAS:
        raise Gagal(f"Maksimal {MAKS_BERKAS} berkas bukti per SPJ.")
    bersih = re.sub(r"\.{2,}", ".", "".join(ch for ch in nama if ch.isalnum() or ch in " ._-"))[:60].lstrip(". ").strip() or "bukti"
    if not bersih.lower().endswith(ekt):
        bersih += ekt
    bid = db.execute("INSERT INTO spj_bukti(spj_id,nama,tipe,ukuran,data,diunggah_oleh) VALUES(?,?,?,?,?,?)", (sid, bersih, tipe, len(data), data, user["username"])).lastrowid
    audit(db, user, "spj_bukti", bid, "UNGGAH", None, {"spj_id": sid, "nama": bersih, "ukuran": len(data)}, r["dana"])
    return {"id": bid, "nama": bersih, "tipe": tipe, "ukuran": len(data)}


@router.get("/bukti/{bid}")
def lihat_bukti(bid: int, user=Depends(auth), db=Depends(get_db)):
    b = db.execute("SELECT * FROM spj_bukti WHERE id=?", (bid,)).fetchone()
    if not b:
        raise Gagal("Bukti tidak ditemukan.", 404)
    _lihat(user, _ambil(db, b["spj_id"]))
    return Response(b["data"], media_type=b["tipe"], headers={"Content-Disposition": f'inline; filename="{b["nama"]}"', "Cache-Control": "private, max-age=3600"})


@router.delete("/bukti/{bid}")
def hapus_bukti(bid: int, user=Depends(auth), db=Depends(get_db)):
    b = db.execute("SELECT id, spj_id, nama FROM spj_bukti WHERE id=?", (bid,)).fetchone()
    if not b:
        raise Gagal("Bukti tidak ditemukan.", 404)
    r = _ambil(db, b["spj_id"])
    penuh = _lihat(user, r)
    if not _bisa_ubah(user, r, penuh):
        raise Gagal("Bukti tidak dapat dihapus pada status SPJ ini.", 403)
    db.execute("DELETE FROM spj_bukti WHERE id=?", (bid,))
    audit(db, user, "spj_bukti", bid, "HAPUS", {"spj_id": b["spj_id"], "nama": b["nama"]}, None, r["dana"])
    return {"ok": True}


@router.get("/{sid}")
def rinci(sid: int, user=Depends(auth), db=Depends(get_db)):
    r = _ambil(db, sid)
    penuh = _lihat(user, r)
    o = _bentuk(r, penuh, user)
    o["sisa_baris"] = r["pagu_baris"] - _dibayar_baris(db, r["baris_id"], sid)
    o["berkas"] = _daftar_bukti(db, sid)
    return o


@router.put("/{sid}")
def ubah(sid: int, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    r = _ambil(db, sid)
    penuh = _lihat(user, r)
    if not _bisa_ubah(user, r, penuh):
        raise Gagal("SPJ ini tidak dapat diubah (sudah diajukan/dibayar, atau Anda tidak berhak).", 403)
    lama = json.loads(r["rincian_json"])
    rincian, total = _hitung_rincian(lama, body.get("rincian"))
    f = {"catatan": str(body.get("catatan") if "catatan" in body else (r["catatan"] or "")).strip() or None}
    if r["jenis"] == "UMUM":
        uraian = str(body.get("uraian", r["uraian"]) or "").strip()
        if len(uraian) < 3:
            raise Gagal("Uraian belanja wajib diisi.")
        total = _int(body.get("jumlah", r["total"]))
        if total <= 0:
            raise Gagal("Jumlah harus lebih dari nol.")
        rincian = [{**lama[0], "uraian": uraian, "tarif": total, "rencana": total, "jumlah": total, "bukti": str(body.get("bukti", lama[0].get("bukti", "")) or "")[:200]}]
        f.update(uraian=uraian, penerima=str(body.get("penerima", r["penerima"]) or "").strip(), tanggal=_tgl(body.get("tanggal", r["tanggal"])), total_rencana=total)
    else:
        mulai, selesai = _tgl(body.get("mulai", r["mulai"]), "Tanggal berangkat"), _tgl(body.get("selesai", r["selesai"]), "Tanggal kembali")
        if selesai < mulai:
            raise Gagal("Tanggal kembali tidak boleh sebelum tanggal berangkat.")
        f.update(mulai=mulai, selesai=selesai, tanggal=selesai)
    f.update(rincian_json=json.dumps(rincian, ensure_ascii=False), total=total)
    f["alasan_kembali"] = None if r["status"] == "Dikembalikan" else r["alasan_kembali"]
    db.execute(f"UPDATE spj SET {','.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), sid))
    audit(db, user, "spj", sid, "UBAH", {"total": r["total"]}, {"total": total}, r["dana"])
    return {"ok": True, "total": total}


@router.delete("/{sid}")
def hapus(sid: int, user=Depends(auth), db=Depends(get_db)):
    r = _ambil(db, sid)
    penuh = _lihat(user, r)
    if not _bisa_ubah(user, r, penuh):
        raise Gagal("SPJ ini tidak dapat dihapus.", 403)
    db.execute("DELETE FROM spj WHERE id=?", (sid,))
    audit(db, user, "spj", sid, "HAPUS", {"uraian": r["uraian"], "total": r["total"]}, None, r["dana"])
    return {"ok": True}


def _sinkron_jadwal(db, st_id):
    """Semua SPJ petugas pada ST sudah dibayar -> jadwal 'Terlaksana'; selain itu kembali 'Disetujui'."""
    if not st_id:
        return
    j = db.execute("SELECT j.id, j.status FROM jadwal j JOIN surat_tugas s ON s.jadwal_id=j.id WHERE s.id=?", (st_id,)).fetchone()
    if not j or j["status"] not in ("Disetujui", "Terlaksana"):
        return
    tot = db.execute("SELECT COUNT(*) c FROM spd WHERE st_id=?", (st_id,)).fetchone()["c"]
    lunas = db.execute("SELECT COUNT(*) c FROM spj WHERE st_id=? AND status='Dibayar'", (st_id,)).fetchone()["c"]
    db.execute("UPDATE jadwal SET status=? WHERE id=?", ("Terlaksana" if tot and lunas >= tot else "Disetujui", j["id"]))


@router.post("/{sid}/status")
def ubah_status(sid: int, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    r = _ambil(db, sid)
    penuh = _lihat(user, r)
    ke, alasan = str(body.get("ke") or ""), str(body.get("alasan") or "").strip()
    dari = r["status"]
    pagu_ok = user["role"] != "pegawai" and akses_uang(user, r["dana"], "pagu")
    sekarang = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets: dict = {"status": ke}
    if ke == "Diajukan":
        if dari not in EDIT or not _bisa_ubah(user, r, penuh):
            raise Gagal("SPJ tidak dapat diajukan oleh Anda pada status ini.", 403)
        if r["total"] <= 0:
            raise Gagal("Total SPJ harus lebih dari nol.")
        if r["jenis"] == "SPD":
            if r["st_status"] != "Terbit":
                raise Gagal("ST sudah dibatalkan.")
            if _set(db, "spj_setelah_selesai", "1") == "1" and dt.date.today().isoformat() < (r["selesai"] or ""):
                raise Gagal(f"SPJ baru dapat diajukan setelah kegiatan selesai ({dk.tgl(r['selesai'])}).")
            if not any(x.get("bukti") for x in json.loads(r["rincian_json"])) and not _daftar_bukti(db, sid) and body.get("tanpa_bukti") is not True:
                raise Gagal("Isi nomor/keterangan bukti pada minimal satu komponen atau unggah foto bukti (atau ajukan dengan 'tanpa bukti').")
        sets.update(diajukan_pada=sekarang, alasan_kembali=None)
    elif ke == "Dikembalikan":
        if dari not in ("Diajukan", "Diverifikasi") or not pagu_ok:
            raise Gagal("Hanya bendahara/Kepala yang dapat mengembalikan SPJ yang diajukan.", 403)
        if len(alasan) < 5:
            raise Gagal("Alasan pengembalian wajib diisi (min. 5 huruf).")
        sets["alasan_kembali"] = alasan
    elif ke == "Diverifikasi":
        if dari != "Diajukan" or not pagu_ok:
            raise Gagal("Hanya bendahara/Kepala yang dapat memverifikasi SPJ yang diajukan.", 403)
        sets.update(diverifikasi_oleh=user["username"], diverifikasi_pada=sekarang)
    elif ke == "Dibayar":
        if dari != "Diverifikasi" or not pagu_ok:
            raise Gagal("SPJ harus terverifikasi dan dibayar oleh bendahara/Kepala.", 403)
        sisa = r["pagu_baris"] - _dibayar_baris(db, r["baris_id"], sid)
        if r["total"] > sisa:
            raise Gagal(f"Melebihi pagu baris RAB: sisa {dk.rp(max(sisa, 0))}, SPJ {dk.rp(r['total'])}.")
        tb = _tgl(body.get("tanggal_bayar") or dt.date.today().isoformat(), "Tanggal bayar")
        if r["jenis"] == "SPD" and r["selesai"] and tb < r["mulai"]:
            raise Gagal("Tanggal bayar tidak boleh sebelum kegiatan dimulai.")
        no = str(body.get("no_bukti") or "").strip()
        if not no:
            fmt = _set(db, "format_bukti_spj", "{urut}/PKM.M/{tahun}")
            bentuk = lambda n_: fmt.replace("{urut}", str(n_)).replace("{tahun}", str(r["tahun"])).replace("{sumber}", r["dana"])  # noqa: E731
            n = db.execute("SELECT COUNT(*) c FROM spj WHERE sumber_dana_id=? AND tahun=? AND no_bukti IS NOT NULL", (r["sumber_dana_id"], r["tahun"])).fetchone()["c"] + 1
            while db.execute("SELECT 1 FROM spj WHERE sumber_dana_id=? AND tahun=? AND no_bukti=?", (r["sumber_dana_id"], r["tahun"], bentuk(n))).fetchone():
                n += 1
            no = bentuk(n)
        sets.update(tanggal_bayar=tb, no_bukti=no, dibayar_oleh=user["username"], dibayar_pada=sekarang)
    else:
        raise Gagal("Status tujuan tidak valid.")
    db.execute(f"UPDATE spj SET {','.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), sid))
    if ke == "Dibayar":
        _sinkron_jadwal(db, r["st_id"])
        akuntansi.jurnal_spj_bayar(db, user, {**r, **sets})
    audit(db, user, "spj", sid, f"STATUS {dari}->{ke}", {"status": dari}, {"status": ke, "alasan": alasan or None, "total": r["total"]}, r["dana"])
    return {"ok": True, "status": ke, "no_bukti": sets.get("no_bukti")}


@router.post("/{sid}/koreksi")
def koreksi(sid: int, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    """Hanya Kepala: membatalkan pembayaran (mis. salah catat). SPJ kembali berstatus Diverifikasi; nomor bukti dilepas. Tercatat di audit."""
    r = _ambil(db, sid)
    _lihat(user, r)
    if user["role"] != "kepala":
        raise Gagal("Hanya Kepala Puskesmas yang dapat mengoreksi pembayaran.", 403)
    if r["status"] != "Dibayar":
        raise Gagal("SPJ belum dibayar.")
    alasan = str(body.get("alasan") or "").strip()
    if len(alasan) < 5:
        raise Gagal("Alasan koreksi wajib diisi (min. 5 huruf).")
    db.execute("UPDATE spj SET status='Diverifikasi', no_bukti=NULL, tanggal_bayar=NULL, dibayar_oleh=NULL, dibayar_pada=NULL WHERE id=?", (sid,))
    _sinkron_jadwal(db, r["st_id"])
    akuntansi.jurnal_spj_koreksi(db, user, r)
    audit(db, user, "spj", sid, "KOREKSI PEMBAYARAN", {"status": "Dibayar", "no_bukti": r["no_bukti"], "tanggal_bayar": r["tanggal_bayar"], "total": r["total"]}, {"status": "Diverifikasi", "alasan": alasan}, r["dana"])
    return {"ok": True}


@router.get("/{sid}/dok")
def dokumen(sid: int, format: str = "pdf", user=Depends(auth), db=Depends(get_db)):
    r = _ambil(db, sid)
    _lihat(user, r)
    rinci_ = json.loads(r["rincian_json"])
    kep, bend = _pejabat(db, "Kepala"), _pejabat(db, "Bendahara")
    kota = _set(db, "kota_surat", "Kuala Kapuas")
    nama = r["pegawai_nama"] or r["penerima"] or "-"
    head = [f"Sumber dana : <b>{r['dana']}</b>", f"Kode rekening : {dk.esc(r['kode_rekening'] or '-')}", f"Uraian : {dk.esc(r['uraian'])}", f"Penerima : <b>{dk.esc(nama)}</b>"]
    if r["jenis"] == "SPD":
        head += [f"Dasar : ST/SPD Nomor {dk.esc(r['st_srikandi'] or r['st_nomor'])}", f"Tanggal pelaksanaan : {dk.tgl(r['mulai'])}" + (f" s.d. {dk.tgl(r['selesai'])}" if r["selesai"] != r["mulai"] else "")]
    data = [["No", "Komponen biaya", "Tarif/Rencana", "Realisasi", "Bukti"]]
    for i, x in enumerate(rinci_, 1):
        data.append([str(i), dk.P(f"{dk.esc(x['uraian'])}<br/><font size=8>{x['volume']} {dk.esc(x['satuan'])} × {dk.rp(x['tarif'])}</font>", "kecil"), dk.P(dk.rp(x["rencana"]), "r"), dk.P(dk.rp(x["jumlah"]), "r"), dk.P(dk.esc(x.get("bukti")), "kecil")])
    data.append(["", dk.P("<b>Jumlah</b>", "n"), dk.P(dk.rp(r["total_rencana"]), "r"), dk.P(f"<b>{dk.rp(r['total'])}</b>", "r"), ""])
    tb = r["tanggal_bayar"] or dt.date.today().isoformat()
    ttd = dk.Table([[dk.P(f"<br/>Mengetahui,<br/>{dk.esc(kep['jabatan'] or 'Kepala')}<br/><br/><br/><br/><u>{dk.esc(kep['nama'])}</u><br/>NIP. {dk.esc(kep['nip'] or '-')}", "n"),
                     dk.P(f"<br/>Telah dibayar,<br/>{dk.esc(bend['jabatan'] or 'Bendahara')}<br/><br/><br/><br/><u>{dk.esc(bend['nama'])}</u><br/>NIP. {dk.esc(bend['nip'] or '-')}", "n"),
                     dk.P(f"{dk.esc(kota)}, {dk.tgl(tb)}<br/>Yang menerima,<br/><br/><br/><br/><u>{dk.esc(nama)}</u><br/>{('NIP. ' + dk.esc(r['pegawai_nip'])) if r['pegawai_nip'] else ''}", "n")]],
                   colWidths=[6.6 * dk.cm, 4.6 * dk.cm, 5.6 * dk.cm])
    story = dk.kop(_kop(db)) + [dk.P("<b>BUKTI PEMBAYARAN / SPJ</b>", "judul"), dk.Spacer(1, 2), dk.P(f"Nomor bukti : {dk.esc(r['no_bukti'] or '(belum dibayar)')}", "c"), dk.Spacer(1, 8),
                                dk.P("<br/>".join(head), "n"), dk.Spacer(1, 8), dk._tabel(data, [1.0 * dk.cm, 7.2 * dk.cm, 3.0 * dk.cm, 3.0 * dk.cm, 2.6 * dk.cm]), dk.Spacer(1, 6),
                                dk.P(f"Terbilang : <i>{dk.esc(dk.terbilang(r['total']))}</i>", "n"), dk.Spacer(1, 4)]
    if r["status"] != "Dibayar":
        story.append(dk.P(f"<font color='#b45309'><b>Status: {r['status']} — belum dibayar</b></font>", "n"))
    story += [dk.Spacer(1, 16), ttd]
    lamp = [b for b in db.execute("SELECT nama, tipe, data FROM spj_bukti WHERE spj_id=? ORDER BY id", (sid,)).fetchall() if b["tipe"].startswith("image/")]
    if lamp:
        import io as _io

        from PIL import Image as PILImage
        from reportlab.platypus import Image as RLImage
        story += [dk.PageBreak(), dk.P("<b>LAMPIRAN BUKTI</b>", "judul"), dk.Spacer(1, 6)]
        for i, b in enumerate(lamp, 1):
            try:
                w, h = PILImage.open(_io.BytesIO(b["data"])).size
            except Exception:  # noqa: BLE001
                continue
            esk = min(15.5 * dk.cm / w, 11.5 * dk.cm / h)
            story += [dk.KeepTogether([dk.P(f"Bukti {i}: {dk.esc(b['nama'])}", "kecil"), dk.Spacer(1, 3), RLImage(_io.BytesIO(b["data"]), width=w * esk, height=h * esk), dk.Spacer(1, 10)])]
    pdf = dk.build_pdf(story, f"SPJ {r['id']}")
    fn = f"SPJ_{r['id']}"
    if format == "docx":
        return Response(_pdf_ke_docx(pdf), media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{fn}.docx"', "Cache-Control": "no-store"})
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{fn}.pdf"', "Cache-Control": "no-store"})
