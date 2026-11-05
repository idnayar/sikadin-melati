"""Login, hak akses, CRUD master generik, impor/ekspor Excel, backup, riwayat."""
import datetime as dt
import io
import os
import tempfile
import time

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from openpyxl import Workbook, load_workbook
from starlette.background import BackgroundTask

from . import core
from .core import Gagal, audit, auth, bisa_baca, bisa_tulis, get_db, pesan_db
from .db import DB_PATH, hash_password, hitung_tingkat, verify_password

router = APIRouter(prefix="/api")


# ---------------- Definisi sumber daya master (satu sumber kebenaran untuk server & UI) ----------------
def F(k, label, type="text", **o):
    return {"k": k, "label": label, "type": type, **o}


AKTIF = F("aktif", "Aktif", "bool", **{"def": 1})
RES = {
    "pegawai": {
        "judul": "Pegawai", "tabel": "pegawai", "urut": "aktif DESC, nama", "unik": ["nip"],
        "fields": [F("nama", "Nama", req=1), F("nip", "NIP"), F("pangkat", "Pangkat"),
                   F("golongan", "Golongan (mis. III/b, IV/a)"), F("jabatan", "Jabatan"), F("eselon", "Eselon (III/IV/kosong)"),
                   F("status", "Status", "select", req=1, opts=["ASN", "PPPK", "Non ASN"], **{"def": "ASN"}),
                   F("program", "Program"), F("tingkat", "Tingkat biaya (otomatis)", ro=1), AKTIF],
        "list": ["nama", "nip", "golongan", "jabatan", "status", "program", "tingkat", "aktif"],
    },
    "sumber_dana": {
        "judul": "Sumber Dana", "tabel": "sumber_dana", "urut": "kode", "unik": ["kode"],
        "fields": [F("kode", "Kode", req=1), F("nama", "Nama", req=1)], "list": ["kode", "nama"],
    },
    "pagu": {
        "judul": "Pagu per Rekening", "tabel": "pagu", "urut": "tahun DESC, sumber_dana_id, kode_rekening", "tahunFilter": "tahun",
        "unik": ["tahun", "sumber_dana_id", "program", "kegiatan", "sub_kegiatan", "kode_rekening"],
        "imp": {"sumber_dana_id": ["sumber_dana", "sumber_dana", "kode"]},
        "fields": [F("tahun", "Tahun", "number", req=1), F("sumber_dana_id", "Sumber dana", "ref", req=1, ref="sumber_dana", refLabel="kode"),
                   F("program", "Program"), F("kegiatan", "Kegiatan"), F("sub_kegiatan", "Sub kegiatan"),
                   F("kode_rekening", "Kode rekening belanja", req=1), F("uraian", "Uraian rekening"),
                   F("pagu", "Pagu (Rp)", "rupiah", req=1)],
        "list": ["tahun", "sumber_dana_id", "kegiatan", "kode_rekening", "uraian", "pagu"],
    },
    "lokasi": {
        "judul": "Lokasi Tujuan", "tabel": "lokasi", "urut": "jenis, nama", "unik": ["nama", "jenis"],
        "fields": [F("nama", "Nama lokasi", req=1),
                   F("jenis", "Jenis", "select", req=1, opts=[["DK_WILAYAH", "Dalam kota – wilayah kerja"], ["DK_ANTAR", "Dalam kota – antar kecamatan/desa"],
                                                              ["LK_KALTENG", "Luar kota – Kalteng"], ["LK_LUAR_PROV", "Luar kota – luar provinsi"]]),
                   F("kecamatan", "Kecamatan"), F("provinsi", "Provinsi"),
                   F("induk_id", "Berada di (induk)", "ref", ref="lokasi", refLabel="nama"),
                   F("kunci_tarif", 'Kunci tarif (cocok dgn "Tujuan" di tabel tarif)'), AKTIF],
        "list": ["nama", "jenis", "kecamatan", "provinsi", "kunci_tarif", "aktif"],
    },
    "tarif": {
        "judul": "Tarif Perbup", "tabel": "tarif", "urut": "kategori, tujuan, tingkat", "tahunFilter": "tahun_berlaku",
        "unik": ["tahun_berlaku", "kategori", "tujuan", "tingkat"],
        "fields": [F("tahun_berlaku", "Tahun berlaku", "number", req=1), F("dasar_hukum", "Dasar hukum", req=1),
                   F("kategori", "Kategori", "select", req=1, opts=[
                       ["UH_DK", "Uang harian dalam kota"], ["UH_DIKLAT_DK", "Uang harian diklat dalam kota"], ["UH_LK_KALTENG", "Uang harian luar kota Kalteng"],
                       ["UH_LUAR_PROV", "Uang harian luar provinsi"], ["TR_DK", "Transport dalam kota (R2/R4)"], ["TR_DARAT_LK", "Transport darat luar kota"],
                       ["INAP_DK", "Penginapan dalam kota"], ["INAP_KALTENG", "Penginapan Kalteng"], ["INAP_LUAR_PROV", "Penginapan luar provinsi"],
                       ["TIKET_PESAWAT", "Tiket pesawat"], ["TAKSI", "Taksi"]]),
                   F("tujuan", "Tujuan / wilayah"), F("tingkat", "Tingkat (C/D, kosong = semua)"),
                   F("nilai", "Nilai (Rp) / Roda 2", "rupiah"), F("nilai2", "Nilai 2 (Rp) / Roda 4", "rupiah"),
                   F("satuan", "Satuan"), F("lampiran", "Lampiran Perbup"), F("keterangan", "Keterangan")],
        "list": ["kategori", "tujuan", "tingkat", "nilai", "nilai2", "satuan", "lampiran"],
    },
    "pejabat": {
        "judul": "Pejabat Penandatangan", "tabel": "pejabat", "urut": "peran",
        "fields": [F("peran", "Peran", req=1), F("nama", "Nama", req=1), F("nip", "NIP"), F("pangkat", "Pangkat/Gol"), F("jabatan", "Jabatan"), AKTIF],
        "list": ["peran", "nama", "nip", "jabatan", "aktif"],
    },
    "pengaturan": {
        "judul": "Pengaturan & Kop Surat", "tabel": "pengaturan", "urut": "id", "noCreate": 1, "noDelete": 1,
        "fields": [F("kunci", "Kunci", ro=1), F("nilai", "Nilai"), F("keterangan", "Keterangan", ro=1)],
        "list": ["kunci", "nilai", "keterangan"],
    },
    "libur": {
        "judul": "Hari Libur", "tabel": "libur", "urut": "tanggal", "unik": ["tanggal"],
        "fields": [F("tanggal", "Tanggal", "date", req=1), F("keterangan", "Keterangan")], "list": ["tanggal", "keterangan"],
    },
    "cuti": {
        "judul": "Cuti Pegawai", "tabel": "cuti", "urut": "mulai DESC",
        "imp": {"pegawai_id": ["pegawai", "nip", "nip"]},
        "fields": [F("pegawai_id", "Pegawai", "ref", req=1, ref="pegawai", refLabel="nama"), F("mulai", "Mulai", "date", req=1),
                   F("selesai", "Selesai", "date", req=1), F("keterangan", "Keterangan")],
        "list": ["pegawai_id", "mulai", "selesai", "keterangan"],
    },
    "users": {
        "judul": "Pengguna", "tabel": "users", "urut": "username", "onlyKepala": 1, "unik": ["username"],
        "fields": [F("username", "Username", req=1), F("nama", "Nama", req=1),
                   F("role", "Hak akses", "select", req=1, opts=[["kepala", "Kepala Puskesmas"], ["bendahara", "Bendahara"], ["program", "Pengelola Program"], ["pegawai", "Pegawai"]]),
                   F("pegawai_id", "Terkait pegawai", "ref", ref="pegawai", refLabel="nama"),
                   F("password", "Password (isi untuk mengubah)", "password", virtual=1), AKTIF],
        "list": ["username", "nama", "role", "aktif"],
    },
}
_MISSING = object()


def db_fields(r):
    return [f for f in r["fields"] if not f.get("virtual")]


# ---------------- Login ----------------
@router.post("/login")
def login(request: Request, response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    ip = request.client.host if request.client else "?"
    n, t = core.GAGAL_LOGIN.get(ip, (0, 0.0))
    if n >= 5 and time.time() - t < 300:
        raise Gagal("Terlalu banyak percobaan. Coba lagi 5 menit.", 429)
    u = db.execute("SELECT * FROM users WHERE username=? AND aktif=1", (str(body.get("username", "")),)).fetchone()
    if not u or not verify_password(str(body.get("password", "")), u["password_hash"]):
        core.GAGAL_LOGIN[ip] = (n + 1, time.time())
        raise Gagal("Username atau password salah.", 401)
    core.GAGAL_LOGIN.pop(ip, None)
    info = {"id": u["id"], "username": u["username"], "nama": u["nama"], "role": u["role"], "pegawai_id": u["pegawai_id"]}
    sid = core.new_session(info)
    response.set_cookie("sid", sid, httponly=True, samesite="strict", max_age=43200, path="/",
                        secure=os.environ.get("SIKADIN_COOKIE_SECURE") == "1")
    return info


@router.post("/logout")
def logout(request: Request, response: Response):
    core.SESSIONS.pop(request.cookies.get("sid"), None)
    response.delete_cookie("sid", path="/")
    return {"ok": 1}


@router.get("/me")
def me(user=Depends(auth)):
    return user


@router.post("/ganti-password")
def ganti_password(body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    u = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    if not verify_password(str(body.get("lama", "")), u["password_hash"]):
        raise Gagal("Password lama salah.")
    if len(str(body.get("baru", ""))) < 8:
        raise Gagal("Password baru minimal 8 karakter.")
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(str(body["baru"])), u["id"]))
    audit(db, user, "users", u["id"], "UBAH", {"password": "***"}, {"password": "*** (diganti)"})
    return {"ok": 1}


# ---------------- CRUD generik ----------------
def cek_hak(user, key, tulis):
    r = RES.get(key)
    if not r:
        raise Gagal("Sumber daya tidak dikenal.", 404)
    if r.get("onlyKepala") and user["role"] != "kepala":
        raise Gagal("Hanya Kepala Puskesmas yang dapat mengelola pengguna.", 403)
    if (not bisa_tulis(user)) if tulis else (not bisa_baca(user)):
        raise Gagal("Anda tidak memiliki hak akses untuk tindakan ini.", 403)
    return r


def _angka(v, label):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Gagal(f"{label} harus berupa angka.")
    if x != x:
        raise Gagal(f"{label} harus berupa angka.")
    return int(x) if x == int(x) else x


def normalisasi(r, body, lama=None):
    out = {}
    for f in db_fields(r):
        if f.get("ro"):
            continue
        k, t = f["k"], f["type"]
        v = body.get(k, _MISSING)
        if v is _MISSING:
            if lama is not None:
                continue
            v = f.get("def")
        if t == "bool":
            v = 1 if v else 0
        elif t in ("number", "rupiah", "ref"):
            v = None if v in ("", None) else _angka(v, f["label"])
        elif isinstance(v, str):
            v = v.strip()
        if (v == "" or v is None) and k in ("tujuan", "tingkat"):
            v = ""
        elif v == "":
            v = None
        if f.get("req") and v is None:
            raise Gagal(f"{f['label']} wajib diisi.")
        if t == "rupiah" and v is not None and v < 0:
            raise Gagal(f"{f['label']} tidak boleh negatif.")
        if t == "select" and v is not None:
            ok = [o[0] if isinstance(o, list) else o for o in f["opts"]]
            if v not in ok:
                raise Gagal(f"{f['label']} tidak valid.")
        out[k] = v
    if r["tabel"] == "pegawai":
        m = {**(lama or {}), **out}
        out["tingkat"] = hitung_tingkat(m.get("eselon"), m.get("golongan"), m.get("status"))
    return out


def bersih(row):
    if row and "password_hash" in row:
        row = {k: v for k, v in row.items() if k != "password_hash"}
    return row


def _insert(db, tabel, d):
    cols = list(d)
    cur = db.execute(f"INSERT INTO {tabel}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [d[c] for c in cols])
    return cur.lastrowid


@router.get("/meta")
def meta(user=Depends(auth)):
    m = {}
    for k, r in RES.items():
        if r.get("onlyKepala") and user["role"] != "kepala":
            continue
        m[k] = {"judul": r["judul"], "fields": r["fields"], "list": r["list"], "tahunFilter": r.get("tahunFilter"),
                "noCreate": r.get("noCreate"), "noDelete": r.get("noDelete")}
    return {"user": user, "meta": m, "bisaTulis": bisa_tulis(user), "bisaBaca": bisa_baca(user)}


@router.get("/data/{res}")
def data_list(res: str, tahun: int | None = None, user=Depends(auth), db=Depends(get_db)):
    r = cek_hak(user, res, False)
    sql, args = f"SELECT * FROM {r['tabel']}", []
    if r.get("tahunFilter") and tahun:
        sql += f" WHERE {r['tahunFilter']}=?"
        args.append(tahun)
    sql += f" ORDER BY {r['urut']}"
    return [bersih(x) for x in db.execute(sql, args).fetchall()]


@router.post("/data/{res}")
def data_tambah(res: str, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    r = cek_hak(user, res, True)
    if r.get("noCreate"):
        raise Gagal("Data ini tidak bisa ditambah.")
    try:
        d = normalisasi(r, body)
        if r["tabel"] == "users":
            pw = str(body.get("password") or "")
            if len(pw) < 8:
                raise Gagal("Password minimal 8 karakter.")
            d["password_hash"] = hash_password(pw)
        rid = _insert(db, r["tabel"], d)
    except Gagal:
        raise
    except Exception as e:
        raise Gagal(pesan_db(e))
    audit(db, user, r["tabel"], rid, "TAMBAH", None, bersih(d))
    return {"id": rid}


@router.put("/data/{res}/{rid}")
def data_ubah(res: str, rid: int, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    r = cek_hak(user, res, True)
    lama = db.execute(f"SELECT * FROM {r['tabel']} WHERE id=?", (rid,)).fetchone()
    if not lama:
        raise Gagal("Data tidak ditemukan.", 404)
    try:
        d = normalisasi(r, body, lama)
        if r["tabel"] == "users" and body.get("password"):
            if len(str(body["password"])) < 8:
                raise Gagal("Password minimal 8 karakter.")
            d["password_hash"] = hash_password(str(body["password"]))
        if d:
            db.execute(f"UPDATE {r['tabel']} SET {','.join(c + '=?' for c in d)} WHERE id=?", [*d.values(), rid])
    except Gagal:
        raise
    except Exception as e:
        raise Gagal(pesan_db(e))
    if d:
        baru = db.execute(f"SELECT * FROM {r['tabel']} WHERE id=?", (rid,)).fetchone()
        audit(db, user, r["tabel"], rid, "UBAH", bersih(lama), bersih(baru))
    return {"ok": 1}


@router.delete("/data/{res}/{rid}")
def data_hapus(res: str, rid: int, user=Depends(auth), db=Depends(get_db)):
    r = cek_hak(user, res, True)
    if r.get("noDelete"):
        raise Gagal("Data ini tidak bisa dihapus.")
    lama = db.execute(f"SELECT * FROM {r['tabel']} WHERE id=?", (rid,)).fetchone()
    if not lama:
        raise Gagal("Data tidak ditemukan.", 404)
    if r["tabel"] == "users" and lama["id"] == user["id"]:
        raise Gagal("Tidak dapat menghapus akun sendiri.")
    try:
        db.execute(f"DELETE FROM {r['tabel']} WHERE id=?", (rid,))
    except Exception as e:
        raise Gagal(pesan_db(e))
    audit(db, user, r["tabel"], rid, "HAPUS", bersih(lama), None)
    return {"ok": 1}


# ---------------- Impor / ekspor Excel ----------------
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_resp(wb: Workbook, nama: str) -> Response:
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nama}"'})


def kolom_excel(r):
    imp = r.get("imp") or {}
    return [f["k"] for f in db_fields(r) if not f.get("ro") and f["k"] not in imp] + [a[1] for a in imp.values()]


@router.get("/template/{res}")
def template(res: str, user=Depends(auth)):
    r = cek_hak(user, res, True)
    wb = Workbook()
    wb.active.title = r["tabel"]
    wb.active.append(kolom_excel(r))
    return _xlsx_resp(wb, f"template_{r['tabel']}.xlsx")


def baca_xlsx(data: bytes) -> list[dict]:
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    rows = list(wb[wb.sheetnames[0]].iter_rows(values_only=True))
    if not rows:
        return []
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for row in rows[1:]:
        if all(c is None or c == "" for c in row):
            continue
        d = {}
        for h, c in zip(head, row):
            if not h:
                continue
            d[h] = c.date().isoformat() if isinstance(c, (dt.datetime, dt.date)) and hasattr(c, "date") else ("" if c is None else c)
        out.append(d)
    return out


@router.post("/import/{res}")
def impor(res: str, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    import base64
    r = cek_hak(user, res, True)
    if r.get("onlyKepala") or r.get("noCreate"):
        raise Gagal("Data ini tidak dapat diimpor.")
    try:
        rows = baca_xlsx(base64.b64decode(str(body.get("file") or "")))
    except Exception:
        raise Gagal("Berkas tidak dapat dibaca. Gunakan .xlsx dari Template.")
    if not rows:
        raise Gagal("File kosong.")
    tambah = ubah = 0
    galat = []
    db.execute("SAVEPOINT impor")
    for i, row in enumerate(rows):
        try:
            b = dict(row)
            for fk, (tbl, col, by) in (r.get("imp") or {}).items():
                val = str(row.get(col, "")).strip()
                rec = db.execute(f"SELECT id FROM {tbl} WHERE {by}=?", (val,)).fetchone() if val else None
                if not rec:
                    raise Gagal(f'"{val}" tidak ditemukan di {tbl}.')
                b[fk] = rec["id"]
            d = normalisasi(r, b)
            uk, ada = r.get("unik"), None
            if uk and not (r["tabel"] == "pegawai" and not d.get("nip")):
                ada = db.execute(f"SELECT * FROM {r['tabel']} WHERE {' AND '.join(c + ' IS ?' for c in uk)}", [d.get(c) for c in uk]).fetchone()
            if ada:
                db.execute(f"UPDATE {r['tabel']} SET {','.join(c + '=?' for c in d)} WHERE id=?", [*d.values(), ada["id"]])
                audit(db, user, r["tabel"], ada["id"], "IMPOR-UBAH", ada, d)
                ubah += 1
            else:
                rid = _insert(db, r["tabel"], d)
                audit(db, user, r["tabel"], rid, "IMPOR-TAMBAH", None, d)
                tambah += 1
        except Gagal as e:
            galat.append(f"Baris {i + 2}: {e.pesan}")
        except Exception as e:
            galat.append(f"Baris {i + 2}: {pesan_db(e)}")
    if galat:
        db.execute("ROLLBACK TO impor")
        db.execute("RELEASE impor")
        raise Gagal("Impor dibatalkan, tidak ada data tersimpan.", galat=galat[:20])
    db.execute("RELEASE impor")
    return {"tambah": tambah, "ubah": ubah}


@router.get("/export/xlsx")
def export_xlsx(user=Depends(auth), db=Depends(get_db)):
    if not bisa_baca(user):
        raise Gagal("Tidak ada akses.", 403)
    wb = Workbook()
    wb.remove(wb.active)

    def sheet(nama, rows):
        ws = wb.create_sheet(nama[:31])
        if rows:
            ws.append(list(rows[0].keys()))
            for x in rows:
                ws.append([str(v) if isinstance(v, (bytes,)) else v for v in x.values()])
    for k, r in RES.items():
        if not r.get("onlyKepala"):
            sheet(k, db.execute(f"SELECT * FROM {r['tabel']} ORDER BY id").fetchall())
    if bisa_tulis(user):
        sheet("riwayat", db.execute("SELECT * FROM audit_log ORDER BY id").fetchall())
    return _xlsx_resp(wb, f"sikadin_data_{dt.date.today().isoformat()}.xlsx")


@router.get("/backup")
def backup(user=Depends(auth), db=Depends(get_db)):
    if not bisa_tulis(user):
        raise Gagal("Tidak ada akses.", 403)
    tmp = os.path.join(tempfile.gettempdir(), f"sikadin_backup_{int(time.time())}.db")
    db.commit()
    db.execute(f"VACUUM INTO '{tmp.replace(chr(39), chr(39) * 2)}'")
    audit(db, user, "sistem", None, "BACKUP", None, None)
    return FileResponse(tmp, filename=f"sikadin_backup_{dt.date.today().isoformat()}.db", background=BackgroundTask(os.unlink, tmp))


@router.get("/riwayat")
def riwayat(tabel: str | None = None, user=Depends(auth), db=Depends(get_db)):
    if not bisa_tulis(user):
        raise Gagal("Hanya Kepala/Bendahara.", 403)
    sql, a = "SELECT * FROM audit_log" + (" WHERE tabel=?" if tabel else "") + " ORDER BY id DESC LIMIT 300", ([tabel] if tabel else [])
    return db.execute(sql, a).fetchall()
