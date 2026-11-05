"""Database kode klasifikasi surat (Permendagri 83/2022): tambah/ubah/hapus manual, impor Excel/CSV, ekspor.
Kode dipakai sebagai pilihan 'Klasifikasi' saat menerbitkan nomor surat dan pada pengaturan kode penomoran."""
import base64
import csv
import io
import re

from fastapi import APIRouter, Body, Depends
from openpyxl import Workbook, load_workbook

from .core import Gagal, audit, get_db, perlu_baca
from .master import _xlsx_resp

router = APIRouter(prefix="/api/kode-surat")
PENGELOLA = ("kepala", "bendahara", "bendahara_blud", "pembuat_surat")
POLA = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-/ ]{0,39}$")

SKEMA = """CREATE TABLE IF NOT EXISTS kode_surat(
  id INTEGER PRIMARY KEY, kode TEXT NOT NULL UNIQUE, uraian TEXT NOT NULL, aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')))"""
AWAL = [("000", "Umum"), ("000.1.2.3", "Perjalanan Dinas Pegawai")]


def pasang(con) -> None:
    con.execute(SKEMA)
    for k, u in AWAL:
        con.execute("INSERT OR IGNORE INTO kode_surat(kode,uraian,dibuat_oleh) VALUES(?,?,'sistem')", (k, u))


def _izin(user):
    if user["role"] not in PENGELOLA:
        raise Gagal("Hanya Kepala, Bendahara, dan Pembuat Surat yang dapat mengelola database kode surat.", 403)


def _bersih(kode, uraian) -> tuple[str, str]:
    if isinstance(kode, float):
        raise Gagal(f"Kode «{kode}» terbaca sebagai angka desimal oleh Excel. Format kolom Kode sebagai Teks, lalu ketik ulang (mis. 000.1.2.3).")
    kode, uraian = re.sub(r"\s+", " ", str(kode if kode is not None else "")).strip(), re.sub(r"\s+", " ", str(uraian if uraian is not None else "")).strip()
    if not POLA.match(kode):
        raise Gagal(f"Kode «{kode}» tidak valid (huruf/angka/titik/garis, maks. 40 karakter).")
    if len(uraian) < 2 or len(uraian) > 300:
        raise Gagal(f"Uraian untuk kode {kode} wajib diisi (2–300 karakter).")
    return kode, uraian


@router.get("")
def daftar(q: str = "", semua: int = 0, user=Depends(perlu_baca), db=Depends(get_db)):
    sql, a = "SELECT id,kode,uraian,aktif FROM kode_surat WHERE 1=1", []
    if not semua:
        sql += " AND aktif=1"
    if q.strip():
        sql += " AND (kode LIKE ? OR uraian LIKE ?)"
        a += [f"%{q.strip()}%"] * 2
    return db.execute(sql + " ORDER BY kode", a).fetchall()


@router.post("")
def tambah(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    _izin(user)
    kode, uraian = _bersih(body.get("kode"), body.get("uraian"))
    if db.execute("SELECT 1 FROM kode_surat WHERE kode=?", (kode,)).fetchone():
        raise Gagal(f"Kode {kode} sudah ada.")
    kid = db.execute("INSERT INTO kode_surat(kode,uraian,dibuat_oleh) VALUES(?,?,?)", (kode, uraian, user["username"])).lastrowid
    audit(db, user, "kode_surat", kid, "TAMBAH", None, {"kode": kode, "uraian": uraian})
    return {"id": kid}


@router.put("/{kid:int}")
def ubah(kid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    _izin(user)
    lama = db.execute("SELECT * FROM kode_surat WHERE id=?", (kid,)).fetchone()
    if not lama:
        raise Gagal("Kode tidak ditemukan.", 404)
    kode, uraian = _bersih(body.get("kode", lama["kode"]), body.get("uraian", lama["uraian"]))
    if db.execute("SELECT 1 FROM kode_surat WHERE kode=? AND id!=?", (kode, kid)).fetchone():
        raise Gagal(f"Kode {kode} sudah ada.")
    aktif = 0 if body.get("aktif") in (False, 0, "0") else 1
    db.execute("UPDATE kode_surat SET kode=?, uraian=?, aktif=? WHERE id=?", (kode, uraian, aktif, kid))
    audit(db, user, "kode_surat", kid, "UBAH", {"kode": lama["kode"], "uraian": lama["uraian"], "aktif": lama["aktif"]}, {"kode": kode, "uraian": uraian, "aktif": aktif})
    return {"ok": 1}


@router.delete("/{kid:int}")
def hapus(kid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    _izin(user)
    lama = db.execute("SELECT * FROM kode_surat WHERE id=?", (kid,)).fetchone()
    if not lama:
        raise Gagal("Kode tidak ditemukan.", 404)
    db.execute("DELETE FROM kode_surat WHERE id=?", (kid,))
    audit(db, user, "kode_surat", kid, "HAPUS", {"kode": lama["kode"], "uraian": lama["uraian"]}, None)
    return {"ok": 1}


def _baca(data: bytes) -> list[tuple]:
    """Baris (kode, uraian) dari .xlsx atau CSV/TSV. Baris judul (mengandung kata 'kode') dilewati."""
    if data[:2] == b"PK":
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        rows = [tuple(r) for r in wb[wb.sheetnames[0]].iter_rows(values_only=True)]
    else:
        teks = data.decode("utf-8-sig", errors="replace")
        try:
            sep = csv.Sniffer().sniff(teks[:2000], delimiters=",;\t").delimiter
        except csv.Error:
            sep = ";" if teks.count(";") > teks.count(",") else ","
        rows = [tuple(r) for r in csv.reader(io.StringIO(teks), delimiter=sep)]
    out = []
    for i, r in enumerate(rows):
        if not r or all(c is None or str(c).strip() == "" for c in r):
            continue
        r = list(r) + [None, None]
        if i == 0 and "kode" in str(r[0]).lower():
            continue
        out.append((r[0], r[1]))
    return out


@router.post("/import")
def impor(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    """Impor Excel/CSV: kolom 1 = Kode, kolom 2 = Uraian. Kode yang sudah ada diperbarui uraiannya. Satu baris salah = seluruh impor dibatalkan."""
    _izin(user)
    try:
        baris = _baca(base64.b64decode(str(body.get("file") or "")))
    except Exception:
        raise Gagal("Berkas tidak dapat dibaca. Gunakan .xlsx atau .csv (kolom: Kode, Uraian).")
    if not baris:
        raise Gagal("Berkas kosong.")
    if len(baris) > 5000:
        raise Gagal("Maksimal 5.000 baris per impor.")
    bersih, galat, lihat = [], [], set()
    for n, (k, u) in enumerate(baris, 1):
        try:
            kode, uraian = _bersih(k, u)
        except Gagal as e:
            galat.append(f"Baris {n}: {e.pesan if hasattr(e, 'pesan') else e}")
            continue
        if kode in lihat:
            galat.append(f"Baris {n}: kode {kode} ganda di dalam berkas.")
            continue
        lihat.add(kode)
        bersih.append((kode, uraian))
    if galat:
        raise Gagal("Impor dibatalkan. " + " ".join(galat[:5]) + (f" (+{len(galat) - 5} kesalahan lain)" if len(galat) > 5 else ""))
    tambah_n = ubah_n = 0
    for kode, uraian in bersih:
        ada = db.execute("SELECT id FROM kode_surat WHERE kode=?", (kode,)).fetchone()
        if ada:
            db.execute("UPDATE kode_surat SET uraian=?, aktif=1 WHERE id=?", (uraian, ada["id"]))
            ubah_n += 1
        else:
            db.execute("INSERT INTO kode_surat(kode,uraian,dibuat_oleh) VALUES(?,?,?)", (kode, uraian, user["username"]))
            tambah_n += 1
    audit(db, user, "kode_surat", None, "IMPOR", None, {"tambah": tambah_n, "ubah": ubah_n})
    return {"tambah": tambah_n, "ubah": ubah_n}


@router.get("/template")
def template(user=Depends(perlu_baca)):
    wb = Workbook()
    ws = wb.active
    ws.title = "kode_surat"
    ws.append(["Kode", "Uraian"])
    ws.append(["000", "Umum"])
    ws.append(["000.1.2.3", "Perjalanan Dinas Pegawai"])
    for r in range(2, 1000):
        ws.cell(r, 1).number_format = "@"   # kolom kode sebagai teks agar 000.1.2.3 tidak diubah Excel
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 18, 70
    return _xlsx_resp(wb, "template_kode_surat.xlsx")


@router.get("/ekspor")
def ekspor(user=Depends(perlu_baca), db=Depends(get_db)):
    wb = Workbook()
    ws = wb.active
    ws.title = "kode_surat"
    ws.append(["Kode", "Uraian", "Aktif"])
    for r in db.execute("SELECT kode,uraian,aktif FROM kode_surat ORDER BY kode").fetchall():
        ws.append([r["kode"], r["uraian"], "Ya" if r["aktif"] else "Tidak"])
        ws.cell(ws.max_row, 1).number_format = "@"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 18, 70
    return _xlsx_resp(wb, "kode_surat.xlsx")
