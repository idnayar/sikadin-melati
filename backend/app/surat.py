"""Surat Tugas (ST) & Surat Perjalanan Dinas (SPD): terbit dari jadwal yang disetujui, nomor berurutan, terkunci, batal + terbit ulang."""
import datetime as dt
import json
import re
import sqlite3

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response

from . import dokumen as dk
from .calc import hitung
from .core import Gagal, akses_sumber, audit, auth, cek_sumber, get_db, kode_sd, perlu_baca
from .docx_srikandi import isi_templat
from .penomoran import bentuk_nomor, nomor_berikut, pasang_nomor
from .docx_srikandi import cek_muat

router = APIRouter(prefix="/api/st")


def _set(db, k, d=""):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    return r["nilai"] if r and r["nilai"] is not None else d


def _petugas_ids(db, jadwal_id) -> set:
    return {r["pegawai_id"] for r in db.execute("SELECT pegawai_id FROM jadwal_petugas WHERE jadwal_id=?", (jadwal_id,)).fetchall()}


def _boleh_lihat(db, user, st) -> tuple[bool, bool]:
    """(boleh, penuh): penuh = berhak atas sumber dananya (lihat semua dokumen & biaya); selain itu hanya petugas yang bersangkutan."""
    if akses_sumber(user, kode_sd(db, st["sumber_dana_id"]), "baca") and user["role"] != "pegawai":
        return True, True
    own = user.get("pegawai_id")
    return (bool(own) and own in {x["pegawai_id"] for x in db.execute("SELECT pegawai_id FROM spd WHERE st_id=?", (st["id"],)).fetchall()}), False


def _jadwal_info(db, jid):
    j = db.execute("""SELECT j.*, r.roda, r.menginap, r.pp, r.transport_manual, r.jumlah_petugas, sd.kode dana, l.nama lokasi, b.kode_rekening
        FROM jadwal j JOIN rencana r ON r.id=j.rencana_id JOIN sumber_dana sd ON sd.id=j.sumber_dana_id JOIN lokasi l ON l.id=j.lokasi_id JOIN bok_baris b ON b.id=j.baris_id WHERE j.id=?""", (jid,)).fetchone()
    if not j:
        raise Gagal("Jadwal tidak ditemukan.", 404)
    return j


def _hari(j) -> int:
    return (dt.date.fromisoformat(j["selesai"]) - dt.date.fromisoformat(j["mulai"])).days + 1


def _alat(j) -> str:
    return "Angkutan darat"


def _rank_gol(g) -> int:
    """Golongan lebih tinggi lebih dulu (IV/b > III/d); tidak ada golongan = paling akhir."""
    m = re.match(r"^\s*(IV|III|II|I)\s*[/ -]?\s*([a-eA-E])?", str(g or ""))
    return (({"I": 1, "II": 2, "III": 3, "IV": 4}[m.group(1)] * 10 + (ord(m.group(2).lower()) - 96 if m.group(2) else 0)) if m else 0)


def _urut_petugas(rows):
    return sorted(rows, key=lambda p: (p["status"] == "Non ASN", -_rank_gol(p["golongan"]), p["nama"]))


def _default_maksud(j) -> str:
    return f"{j['kegiatan']} di {j['lokasi']}"


def _pejabat_aktif(db):
    return db.execute("SELECT * FROM pejabat WHERE aktif=1 ORDER BY (peran LIKE '%Penandatangan%') DESC, id").fetchall()


def _jenis_st(dana: str) -> str:
    return "ST-" + str(dana).upper()


@router.get("/siap")
def siap(tahun: int, user=Depends(perlu_baca), db=Depends(get_db)):
    """Jadwal Disetujui yang belum punya ST aktif. Hanya yang boleh diterbitkan pengguna (Kepala; bendahara sesuai sumber dana)."""
    rows = db.execute("""SELECT j.id, j.rencana_id, j.kegiatan, j.mulai, j.selesai, j.lokasi_id, l.nama lokasi, sd.kode dana
        FROM jadwal j JOIN lokasi l ON l.id=j.lokasi_id JOIN sumber_dana sd ON sd.id=j.sumber_dana_id
        WHERE j.tahun=? AND j.status='Disetujui' AND NOT EXISTS(SELECT 1 FROM surat_tugas s WHERE s.jadwal_id=j.id AND s.status='Terbit') ORDER BY j.mulai, j.id""", (tahun,)).fetchall()
    rows = [r for r in rows if akses_sumber(user, r["dana"], "pagu")]
    for r in rows:
        r["petugas"] = [x["nama"] for x in db.execute("SELECT p.nama FROM jadwal_petugas jp JOIN pegawai p ON p.id=jp.pegawai_id WHERE jp.jadwal_id=? ORDER BY p.nama", (r["id"],)).fetchall()]
    return rows


@router.get("/draft/{jid}")
def draft(jid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    j = _jadwal_info(db, jid)
    cek_sumber(user, j["dana"], "pagu")
    tanggal = dt.date.today().isoformat()
    if tanggal > j["mulai"]:
        tanggal = j["mulai"]
    dasar = _set(db, "dasar_st_default")
    nomor = bentuk_nomor(db, _jenis_st(j["dana"]), tanggal)[0]
    return {"jadwal_id": jid, "nomor_pratinjau": nomor, "tanggal_surat": tanggal, "dasar": dasar, "maksud": _default_maksud(j), "kegiatan": j["kegiatan"], "lokasi": j["lokasi"],
            "mulai": j["mulai"], "selesai": j["selesai"], "dana": j["dana"],
            "pejabat": [{"id": p["id"], "label": f"{p['nama']} — {p['jabatan'] or p['peran']}"} for p in _pejabat_aktif(db)],
            "dpa": _set(db, "nomor_dpa"), "petugas": [x["nama"] for x in db.execute("SELECT p.nama FROM jadwal_petugas jp JOIN pegawai p ON p.id=jp.pegawai_id WHERE jp.jadwal_id=? ORDER BY p.nama", (jid,)).fetchall()]}


@router.post("/terbit")
def terbit(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    j = _jadwal_info(db, int(body.get("jadwal_id") or 0))
    cek_sumber(user, j["dana"], "pagu")
    if j["status"] != "Disetujui":
        raise Gagal(f"Jadwal berstatus {j['status']}; hanya jadwal Disetujui yang dapat diterbitkan Surat Tugasnya.")
    if db.execute("SELECT 1 FROM surat_tugas WHERE jadwal_id=? AND status='Terbit'", (j["id"],)).fetchone():
        raise Gagal("Jadwal ini sudah punya Surat Tugas aktif. Batalkan dulu bila perlu terbit ulang.")
    try:
        tanggal = dt.date.fromisoformat(str(body.get("tanggal_surat") or "")[:10]).isoformat()
    except ValueError:
        raise Gagal("Tanggal surat tidak valid.")
    maksud = str(body.get("maksud") or "").strip()
    if not maksud:
        raise Gagal("Maksud/uraian tugas wajib diisi.")
    pj = db.execute("SELECT * FROM pejabat WHERE id=? AND aktif=1", (int(body.get("penandatangan_id") or 0),)).fetchone()
    if not pj:
        raise Gagal("Pilih pejabat penandatangan.")
    petugas = _urut_petugas(db.execute("SELECT p.* FROM jadwal_petugas jp JOIN pegawai p ON p.id=jp.pegawai_id WHERE jp.jadwal_id=?", (j["id"],)).fetchall())
    if not petugas:
        raise Gagal("Jadwal tidak memiliki petugas.")
    tahun = int(tanggal[:4])
    hari = _hari(j)
    isi = {
        "kop": {"baris1": _set(db, "kop_baris1"), "baris2": _set(db, "kop_baris2"), "baris3": _set(db, "kop_baris3"), "alamat": _set(db, "kop_alamat"),
                "jalan": _set(db, "kop_jalan"), "kodepos": _set(db, "kop_kodepos"), "laman": _set(db, "kop_laman"), "email": _set(db, "kop_email")},
        "dpa": str(body.get("dpa") or _set(db, "nomor_dpa")).strip(),
        "anggaran": {"instansi": _set(db, "anggaran_instansi"), "program": _set(db, "anggaran_program"), "kegiatan": _set(db, "anggaran_kegiatan"),
                     "rekening": (f"{j['kode_rekening']}|" + _set(db, "anggaran_rekening").partition("|")[2]) if j["kode_rekening"] else _set(db, "anggaran_rekening")},
        "instansi": _set(db, "instansi", "UPT Puskesmas Melati"), "kota": _set(db, "kota_surat", "Kuala Kapuas"), "tempat_berangkat": _set(db, "tempat_berangkat", "Kec. Selat"),
        "kegiatan": j["kegiatan"], "lokasi": j["lokasi"], "mulai": j["mulai"], "selesai": j["selesai"], "hari": hari, "durasi": j["durasi"], "sumber": j["dana"],
        "kode_rekening": j["kode_rekening"], "alat_angkutan": _alat(j), "tahun": j["tahun"],
        "pptk": (lambda r: {"nama": r["nama"], "nip": r["nip"]} if r else {})(db.execute("SELECT nama, nip FROM pejabat WHERE aktif=1 AND peran LIKE '%PPTK%' ORDER BY id LIMIT 1").fetchone()),
        "ttd": {"peran": pj["peran"], "nama": pj["nama"], "nip": pj["nip"], "pangkat": pj["pangkat"], "jabatan": pj["jabatan"] or pj["peran"]},
        "petugas": [{"id": p["id"], "nama": p["nama"], "nip": p["nip"], "pangkat": p["pangkat"], "golongan": p["golongan"], "jabatan": p["jabatan"], "tingkat": p["tingkat"], "ruangan": p["ruangan"], "status": p["status"]} for p in petugas],
    }
    muat = cek_muat(isi, str(body.get("dasar") or ""), maksud)
    if not muat["ok"]:
        raise Gagal(f"Surat Tugas dengan {len(petugas)} petugas tidak muat dalam SATU halaman (tanda tangan harus satu halaman dengan isinya). "
                    f"Pecah menjadi dua jadwal/ST (maksimal sekitar {muat['maks_petugas']} petugas per ST), atau persingkat uraian tugas.")
    prev = db.execute("SELECT id, versi FROM surat_tugas WHERE jadwal_id=? AND status='Dibatalkan' ORDER BY id DESC LIMIT 1", (j["id"],)).fetchone()
    try:
        jenis = _jenis_st(j["dana"])
        nomor, urut = bentuk_nomor(db, jenis, tanggal)
        sid = db.execute("""INSERT INTO surat_tugas(jadwal_id,sumber_dana_id,tahun,jenis_nomor,nomor_urut,nomor,tanggal_surat,dasar,maksud,penandatangan_id,isi_json,versi,pengganti_dari,dibuat_oleh)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (j["id"], j["sumber_dana_id"], tahun, jenis, urut, nomor, tanggal, str(body.get("dasar") or "").strip() or None, maksud, pj["id"],
                                                   json.dumps(isi, ensure_ascii=False), (prev["versi"] + 1) if prev else 1, prev["id"] if prev else None, user["username"])).lastrowid
        spd_ids = []
        for p in petugas:
            h = hitung(db, {"pegawai_id": p["id"], "lokasi_id": j["lokasi_id"], "tahun": j["tahun"], "durasi": j["durasi"], "hari": hari, "roda": j["roda"],
                            "menginap": j["menginap"], "pp": bool(j["pp"]), "transport_manual": j["transport_manual"]})
            spd_ids.append(db.execute("INSERT INTO spd(st_id,pegawai_id,biaya_json,total) VALUES(?,?,?,?)", (sid, p["id"], json.dumps(h, ensure_ascii=False), h["total"])).lastrowid)
        db.execute("UPDATE jadwal SET no_st=? WHERE id=?", (nomor, j["id"]))
    except sqlite3.IntegrityError:
        raise Gagal("Nomor surat bentrok dengan penerbitan lain yang bersamaan. Silakan coba lagi.")
    audit(db, user, "surat_tugas", sid, "TERBIT", None, {"nomor": nomor, "jadwal_id": j["id"], "petugas": len(petugas), "versi": (prev["versi"] + 1) if prev else 1}, j["dana"])
    return {"id": sid, "nomor": nomor, "spd": len(spd_ids)}


@router.get("")
def daftar(tahun: int, status: str | None = None, user=Depends(auth), db=Depends(get_db)):
    q, a = ["s.tahun=?"], [tahun]
    if status:
        q.append("s.status=?")
        a.append(status)
    rows = db.execute(f"""SELECT s.id, s.jadwal_id, s.sumber_dana_id, s.tahun, s.nomor, s.nomor_urut, s.tanggal_surat, s.maksud, s.status, s.versi, s.pengganti_dari, s.alasan_batal,
        s.nomor_srikandi, s.jenis_nomor, s.dibuat_oleh, s.dibuat_pada, s.dibatalkan_oleh, s.dibatalkan_pada, sd.kode dana, j.mulai, j.selesai, l.nama lokasi
        FROM surat_tugas s JOIN jadwal j ON j.id=s.jadwal_id JOIN lokasi l ON l.id=j.lokasi_id JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE {' AND '.join(q)} ORDER BY s.nomor_urut DESC""", a).fetchall()
    out = []
    for s in rows:
        boleh, penuh = _boleh_lihat(db, user, s)
        if not boleh:
            continue
        sp = db.execute("SELECT d.id, d.pegawai_id, d.total, p.nama FROM spd d JOIN pegawai p ON p.id=d.pegawai_id WHERE d.st_id=? ORDER BY p.nama", (s["id"],)).fetchall()
        if not penuh:   # petugas biasa: hanya SPD miliknya, tanpa biaya orang lain
            sp = [x for x in sp if x["pegawai_id"] == user.get("pegawai_id")]
        s["spd"] = sp
        s["penuh"] = penuh
        s["bisa_batal"] = penuh and s["status"] == "Terbit" and akses_sumber(user, s["dana"], "pagu")
        out.append(s)
    return out


@router.post("/{sid}/batal")
def batal(sid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    s = db.execute("SELECT * FROM surat_tugas WHERE id=?", (sid,)).fetchone()
    if not s:
        raise Gagal("Surat Tugas tidak ditemukan.", 404)
    kode = kode_sd(db, s["sumber_dana_id"])
    cek_sumber(user, kode, "pagu")
    if s["status"] != "Terbit":
        raise Gagal("Surat Tugas ini sudah dibatalkan.")
    alasan = str(body.get("alasan") or "").strip()
    if len(alasan) < 5:
        raise Gagal("Alasan pembatalan wajib diisi (min. 5 karakter).")
    db.execute("UPDATE surat_tugas SET status='Dibatalkan', alasan_batal=?, dibatalkan_oleh=?, dibatalkan_pada=datetime('now','localtime') WHERE id=?", (alasan, user["username"], sid))
    db.execute("UPDATE jadwal SET no_st=NULL WHERE id=?", (s["jadwal_id"],))
    audit(db, user, "surat_tugas", sid, "BATAL", {"nomor": s["nomor"], "status": "Terbit"}, {"status": "Dibatalkan", "alasan": alasan}, kode)
    return {"ok": 1}


@router.put("/{sid}/nomor-srikandi")
def nomor_srikandi(sid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    """Catat nomor naskah yang diberikan Srikandi setelah ST ditandatangani elektronik (sekali isi, lalu terkunci)."""
    s = db.execute("SELECT * FROM surat_tugas WHERE id=?", (sid,)).fetchone()
    if not s:
        raise Gagal("Surat Tugas tidak ditemukan.", 404)
    kode = kode_sd(db, s["sumber_dana_id"])
    cek_sumber(user, kode, "pagu")
    if s["status"] != "Terbit":
        raise Gagal("Surat Tugas sudah dibatalkan.")
    if s["nomor_srikandi"]:
        raise Gagal("Nomor Srikandi sudah dicatat dan tidak dapat diubah.")
    n = " ".join(str(body.get("nomor") or "").split())
    if len(n) < 5 or len(n) > 120:
        raise Gagal("Isi nomor naskah dari Srikandi (contoh: 000.1.2.3/2611-1179/PKM.MELATI/XI/2026).")
    db.execute("UPDATE surat_tugas SET nomor_srikandi=? WHERE id=?", (n, sid))
    db.execute("UPDATE jadwal SET no_st=? WHERE id=?", (n, s["jadwal_id"]))
    audit(db, user, "surat_tugas", sid, "NOMOR-SRIKANDI", {"nomor_internal": s["nomor"]}, {"nomor_srikandi": n}, kode)
    return {"ok": 1}


DOK_PENUH = {"st", "spd", "rincian", "riil", "batal", "kembali", "hadir", "kuitansi", "paket", "lengkap", "srikandi"}
DOK_PETUGAS = {"st", "spd", "rincian", "paket"}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/{sid}/dok")
def dokumen(sid: int, dok: str = "st", pegawai_id: int | None = None, mode: str = "cetak", user=Depends(auth), db=Depends(get_db)):
    """dok=srikandi -> berkas .docx (templat resmi Srikandi, kode TTE dibiarkan) untuk diunggah ke Srikandi.
    Lainnya -> PDF. mode='cetak' (nama tercetak) atau 'srikandi' (memuat kode ${...}) untuk ST/SPD PDF."""
    s = db.execute("SELECT * FROM surat_tugas WHERE id=?", (sid,)).fetchone()
    if not s:
        raise Gagal("Surat Tugas tidak ditemukan.", 404)
    boleh, penuh = _boleh_lihat(db, user, s)
    if not boleh:
        raise Gagal("Anda tidak berhak atas dokumen ini.", 403)
    if dok not in DOK_PENUH or (not penuh and dok not in DOK_PETUGAS):
        raise Gagal("Jenis dokumen tidak tersedia untuk Anda.", 403)
    isi = json.loads(s["isi_json"])
    stx = {"nomor": s["nomor"], "nomor_tampil": s["nomor_srikandi"] or s["nomor"], "nomor_srikandi": s["nomor_srikandi"], "tanggal_surat": s["tanggal_surat"], "dasar": s["dasar"], "maksud": s["maksud"]}
    nama_berkas = f"{s['nomor_urut']:03d}_{s['tanggal_surat']}"
    if dok == "srikandi":
        if s["status"] != "Terbit":
            raise Gagal("Surat Tugas yang dibatalkan tidak dapat diekspor ke Srikandi.")
        data, ringkas = isi_templat(isi, stx)
        hdr = {"Content-Disposition": f'attachment; filename="ST_SPD_Srikandi_{nama_berkas}.docx"', "Cache-Control": "no-store",
               "X-Pemadatan": f"ST=L{ringkas['st'][0]}(~{ringkas['st'][1]}pt);SPD=L{ringkas['spd'][0]}(~{ringkas['spd'][1]}pt)"}
        return Response(data, media_type=DOCX, headers=hdr)
    spds = db.execute("SELECT * FROM spd WHERE st_id=? ORDER BY id", (sid,)).fetchall()
    if not penuh:
        spds = [x for x in spds if x["pegawai_id"] == user.get("pegawai_id")]
    elif pegawai_id:
        spds = [x for x in spds if x["pegawai_id"] == pegawai_id]
    mode = "srikandi" if mode == "srikandi" else "cetak"
    if dok not in ("st", "spd", "hadir", "paket", "lengkap") and not spds:
        raise Gagal("Petugas tidak ditemukan pada Surat Tugas ini.", 404)
    B = lambda x: json.loads(x["biaya_json"])  # noqa: E731
    parts: list[list] = []
    ft = mode == "srikandi"
    if dok in ("st", "paket", "lengkap"):
        parts.append(dk.muat_halaman(lambda: dk.d_st(isi, stx, mode), 1, footer=ft))        # ST: satu halaman, tanda tangan ikut
    if dok in ("spd", "paket", "lengkap"):
        parts.append(dk.muat_halaman(lambda: dk.d_spd(isi, stx, spds, mode), 2, footer=ft))  # SPD: depan + belakang
    if dok == "hadir" or dok == "lengkap":
        parts.append(dk.d_hadir(isi, stx))
    for x in spds:
        if dok in ("rincian", "paket", "lengkap"):
            parts.append(dk.d_rincian(isi, stx, x, B(x)))
        if dok in ("riil", "lengkap"):
            parts.append(dk.d_riil(isi, stx, x))
        if dok in ("kuitansi", "lengkap"):
            parts.append(dk.d_kuitansi(isi, stx, x, B(x)))
        if dok == "batal":
            parts.append(dk.d_batal(isi, stx, x))
        if dok == "kembali":
            parts.append(dk.d_kembali(isi, stx, x))
    if s["status"] == "Dibatalkan":   # penanda pada setiap dokumen yang dicetak dari ST batal
        from reportlab.platypus import Paragraph
        from .dokumen import S as GAYA
        tanda = Paragraph(f'<font color="#b91c1c"><b>*** DIBATALKAN — {dk.esc(s["alasan_batal"])} ***</b></font>', GAYA["c"])
        parts = [[tanda, *p] for p in parts]
    pdf = dk.build_pdf(dk.gabung(*parts), f"{dok.upper()} {stx['nomor_tampil']}", footer_srikandi=(mode == "srikandi" and dok in ("st", "spd")))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{dok.upper()}_{nama_berkas}.pdf"', "Cache-Control": "no-store"})
