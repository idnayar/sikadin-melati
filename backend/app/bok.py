"""Pagu & RAB BOK: Menu → Rincian Menu → baris biaya. Tambah / ubah / hapus di tiap tingkat."""
import base64
import datetime as dt
import math

from fastapi import APIRouter, Body, Depends
from openpyxl import Workbook

from .core import Gagal, audit, cek_sumber, get_db, kode_sd, perlu_baca
from .master import _xlsx_resp
from .rab import parse_rab

router = APIRouter(prefix="/api/bok")
KOL = ["komponen", "jenis_belanja", "kode_rekening", "uraian", "satuan", "vol1", "sat1", "vol2", "sat2", "vol3", "sat3", "unit_cost", "jumlah"]


def _t(v):
    return None if v is None or str(v).strip() == "" else str(v).strip()


def _n(v, label, default=None):
    if v is None or v == "":
        if default is not None:
            return default
        raise Gagal(f"{label} wajib diisi.")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Gagal(f"{label} harus angka ≥ 0.")
    if not math.isfinite(x) or x < 0:
        raise Gagal(f"{label} harus angka ≥ 0.")
    return int(x) if x == int(x) else x


def _bulat(x) -> int:
    return int(math.floor(x + 0.5))


def sd_id(db, kode) -> int:
    """Kode sumber dana (BOK/DAU/BLUD) -> id. Hanya sumber dana yang ada di master."""
    r = db.execute("SELECT id FROM sumber_dana WHERE kode=?", (str(kode or "BOK").upper(),)).fetchone()
    if not r:
        raise Gagal(f"Sumber dana {kode} tidak ada di master.")
    return r["id"]


def tree(db, tahun: int, sumber_id: int) -> dict:
    menus = db.execute("SELECT * FROM bok_menu WHERE tahun=? AND sumber_dana_id=? ORDER BY urut,id", (tahun, sumber_id)).fetchall()
    for m in menus:
        m["rincian"] = db.execute("SELECT * FROM bok_rincian WHERE menu_id=? ORDER BY urut,id", (m["id"],)).fetchall()
        m["total"] = 0
        for r in m["rincian"]:
            r["baris"] = db.execute("SELECT * FROM bok_baris WHERE rincian_id=? ORDER BY urut,id", (r["id"],)).fetchall()
            r["total"] = sum(b["jumlah"] for b in r["baris"])
            for b in r["baris"]:
                b["beda"] = b["jenis_belanja"] != "Pembulatan" and _bulat(b["vol1"] * b["vol2"] * b["vol3"] * b["unit_cost"]) != b["jumlah"]
            m["total"] += r["total"]
    p = db.execute("SELECT * FROM bok_pagu WHERE tahun=? AND sumber_dana_id=?", (tahun, sumber_id)).fetchone()
    return {"tahun": tahun, "sumber_dana_id": sumber_id, "pagu": p, "total": sum(m["total"] for m in menus), "menu": menus}


def _urut_baru(db, tbl, where, *arg) -> int:
    return db.execute(f"SELECT COALESCE(MAX(urut),0)+1 u FROM {tbl} WHERE {where}", arg).fetchone()["u"]


@router.get("/tahun")
def daftar_tahun(sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "baca")
    sid = sd_id(db, sumber)
    return [r["tahun"] for r in db.execute("SELECT tahun FROM (SELECT tahun FROM bok_pagu WHERE sumber_dana_id=? UNION SELECT tahun FROM bok_menu WHERE sumber_dana_id=?) ORDER BY tahun DESC", (sid, sid)).fetchall()]


@router.get("/{tahun}")
def lihat(tahun: int, sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "baca")
    return tree(db, tahun, sd_id(db, sumber))


@router.put("/{tahun}/pagu")
def set_pagu(tahun: int, body: dict = Body(default={}), sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "pagu")
    if not tahun:
        raise Gagal("Tahun tidak valid.")
    sid = sd_id(db, sumber)
    lama = db.execute("SELECT * FROM bok_pagu WHERE tahun=? AND sumber_dana_id=?", (tahun, sid)).fetchone()
    d = {"jenis": _t(body.get("jenis")) or "Pagu Indikatif", "pagu": _n(body.get("pagu"), "Pagu"), "keterangan": _t(body.get("keterangan"))}
    if lama:
        db.execute("UPDATE bok_pagu SET jenis=?,pagu=?,keterangan=? WHERE tahun=? AND sumber_dana_id=?", (d["jenis"], d["pagu"], d["keterangan"], tahun, sid))
    else:
        db.execute("INSERT INTO bok_pagu(tahun,sumber_dana_id,jenis,pagu,keterangan) VALUES(?,?,?,?,?)", (tahun, sid, d["jenis"], d["pagu"], d["keterangan"]))
    audit(db, user, "bok_pagu", tahun, "UBAH" if lama else "TAMBAH", lama, {"tahun": tahun, "sumber": sumber, **d}, sumber.upper())
    return {"ok": 1}


# ---- Penentu sumber dana dari id (izin dicek per sumber: BLUD hanya Kepala & Bendahara BLUD) ----
def _kode_menu(db, menu_id) -> str:
    r = db.execute("SELECT sumber_dana_id FROM bok_menu WHERE id=?", (menu_id,)).fetchone()
    if not r:
        raise Gagal("Menu tidak ditemukan.", 404)
    return kode_sd(db, r["sumber_dana_id"])


def _kode_rincian(db, rid) -> str:
    r = db.execute("SELECT menu_id FROM bok_rincian WHERE id=?", (rid,)).fetchone()
    if not r:
        raise Gagal("Rincian tidak ditemukan.", 404)
    return _kode_menu(db, r["menu_id"])


def _kode_baris(db, bid) -> str:
    r = db.execute("SELECT rincian_id FROM bok_baris WHERE id=?", (bid,)).fetchone()
    if not r:
        raise Gagal("Baris tidak ditemukan.", 404)
    return _kode_rincian(db, r["rincian_id"])


def _hapus(db, sql, *a):
    try:
        db.execute(sql, a)
    except Exception as e:
        raise Gagal("Data masih dipakai data lain (mis. rencana kegiatan)." if "FOREIGN KEY" in str(e) else str(e))


# ---- Menu ----
@router.post("/menu")
def tambah_menu(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    kode = str(body.get("sumber") or "BOK").upper()
    cek_sumber(user, kode, "pagu")
    tahun, nama, sid = _n(body.get("tahun"), "Tahun"), _t(body.get("nama")), sd_id(db, kode)
    if not nama:
        raise Gagal("Nama menu wajib diisi.")
    rid = db.execute("INSERT INTO bok_menu(tahun,sumber_dana_id,no,nama,urut) VALUES(?,?,?,?,?)",
                     (tahun, sid, _t(body.get("no")), nama, _urut_baru(db, "bok_menu", "tahun=? AND sumber_dana_id=?", tahun, sid))).lastrowid
    audit(db, user, "bok_menu", rid, "TAMBAH", None, {"tahun": tahun, "sumber": kode, "no": _t(body.get("no")), "nama": nama}, kode)
    return {"id": rid}


@router.put("/menu/{rid}")
def ubah_menu(rid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_menu(db, rid)
    cek_sumber(user, kode, "pagu")
    lama = db.execute("SELECT * FROM bok_menu WHERE id=?", (rid,)).fetchone()
    nama = _t(body.get("nama"))
    if not nama:
        raise Gagal("Nama menu wajib diisi.")
    db.execute("UPDATE bok_menu SET no=?,nama=? WHERE id=?", (_t(body.get("no")), nama, rid))
    audit(db, user, "bok_menu", rid, "UBAH", lama, {**lama, "no": _t(body.get("no")), "nama": nama}, kode)
    return {"ok": 1}


@router.delete("/menu/{rid}")
def hapus_menu(rid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_menu(db, rid)
    cek_sumber(user, kode, "pagu")
    lama = db.execute("SELECT * FROM bok_menu WHERE id=?", (rid,)).fetchone()
    snap = next((m for m in tree(db, lama["tahun"], lama["sumber_dana_id"])["menu"] if m["id"] == rid), None)
    _hapus(db, "DELETE FROM bok_menu WHERE id=?", rid)
    audit(db, user, "bok_menu", rid, "HAPUS", snap, None, kode)
    return {"ok": 1}


# ---- Rincian ----
@router.post("/rincian")
def tambah_rincian(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    menu_id, nama = _n(body.get("menu_id"), "Menu"), _t(body.get("nama"))
    kode = _kode_menu(db, menu_id)
    cek_sumber(user, kode, "pagu")
    if not nama:
        raise Gagal("Nama rincian wajib diisi.")
    rid = db.execute("INSERT INTO bok_rincian(menu_id,no,nama,urut) VALUES(?,?,?,?)",
                     (menu_id, _t(body.get("no")), nama, _urut_baru(db, "bok_rincian", "menu_id=?", menu_id))).lastrowid
    audit(db, user, "bok_rincian", rid, "TAMBAH", None, {"menu_id": menu_id, "no": _t(body.get("no")), "nama": nama}, kode)
    return {"id": rid}


@router.put("/rincian/{rid}")
def ubah_rincian(rid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_rincian(db, rid)
    cek_sumber(user, kode, "pagu")
    lama = db.execute("SELECT * FROM bok_rincian WHERE id=?", (rid,)).fetchone()
    nama = _t(body.get("nama"))
    if not nama:
        raise Gagal("Nama rincian wajib diisi.")
    db.execute("UPDATE bok_rincian SET no=?,nama=? WHERE id=?", (_t(body.get("no")), nama, rid))
    audit(db, user, "bok_rincian", rid, "UBAH", lama, {**lama, "no": _t(body.get("no")), "nama": nama}, kode)
    return {"ok": 1}


@router.delete("/rincian/{rid}")
def hapus_rincian(rid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_rincian(db, rid)
    cek_sumber(user, kode, "pagu")
    lama = db.execute("SELECT * FROM bok_rincian WHERE id=?", (rid,)).fetchone()
    baris = db.execute("SELECT * FROM bok_baris WHERE rincian_id=?", (rid,)).fetchall()
    _hapus(db, "DELETE FROM bok_rincian WHERE id=?", rid)
    audit(db, user, "bok_rincian", rid, "HAPUS", {**lama, "baris": baris}, None, kode)
    return {"ok": 1}


# ---- Baris biaya ----
def baca_baris(b: dict, lama: dict | None = None) -> dict:
    def g(k):
        return b[k] if k in b else (lama.get(k) if lama else None)
    jenis = _t(g("jenis_belanja"))
    if not jenis:
        raise Gagal("Jenis belanja wajib diisi.")
    d = {"komponen": _t(g("komponen")), "jenis_belanja": jenis, "kode_rekening": _t(g("kode_rekening")), "uraian": _t(g("uraian")), "satuan": _t(g("satuan")),
         "vol1": _n(g("vol1"), "Volume 1", 1), "sat1": _t(g("sat1")), "vol2": _n(g("vol2"), "Volume 2", 1), "sat2": _t(g("sat2")),
         "vol3": _n(g("vol3"), "Volume 3", 1), "sat3": _t(g("sat3")), "unit_cost": _bulat(_n(g("unit_cost"), "Tarif/unit cost", 0))}
    berubah = lama is None or any(float(lama[k]) != float(d[k]) for k in ("vol1", "vol2", "vol3", "unit_cost"))
    d["jumlah"] = _bulat(d["vol1"] * d["vol2"] * d["vol3"] * d["unit_cost"]) if berubah else lama["jumlah"]
    return d


def _ins_baris(db, rid, d):
    return db.execute(f"INSERT INTO bok_baris(rincian_id,{','.join(KOL)},urut) VALUES(?,{','.join('?' * len(KOL))},?)",
                      (rid, *[d.get(k) for k in KOL], _urut_baru(db, "bok_baris", "rincian_id=?", rid))).lastrowid


@router.post("/baris")
def tambah_baris(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    rid = _n(body.get("rincian_id"), "Rincian")
    kode = _kode_rincian(db, rid)
    cek_sumber(user, kode, "pagu")
    d = baca_baris(body)
    bid = _ins_baris(db, rid, d)
    audit(db, user, "bok_baris", bid, "TAMBAH", None, {"rincian_id": rid, **d}, kode)
    return {"id": bid}


@router.put("/baris/{bid}")
def ubah_baris(bid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_baris(db, bid)
    cek_sumber(user, kode, "pagu")
    lama = db.execute("SELECT * FROM bok_baris WHERE id=?", (bid,)).fetchone()
    d = baca_baris(body, lama)
    db.execute(f"UPDATE bok_baris SET {','.join(k + '=?' for k in KOL)} WHERE id=?", [*[d[k] for k in KOL], bid])
    audit(db, user, "bok_baris", bid, "UBAH", lama, {**lama, **d}, kode)
    return {"ok": 1}


@router.post("/baris/{bid}/duplikat")
def duplikat_baris(bid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_baris(db, bid)
    cek_sumber(user, kode, "pagu")
    s_ = db.execute("SELECT * FROM bok_baris WHERE id=?", (bid,)).fetchone()
    nid = _ins_baris(db, s_["rincian_id"], s_)
    audit(db, user, "bok_baris", nid, "TAMBAH", None, {"dari": bid, **s_}, kode)
    return {"id": nid}


@router.delete("/baris/{bid}")
def hapus_baris(bid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    kode = _kode_baris(db, bid)
    cek_sumber(user, kode, "pagu")
    lama = db.execute("SELECT * FROM bok_baris WHERE id=?", (bid,)).fetchone()
    _hapus(db, "DELETE FROM bok_baris WHERE id=?", bid)
    audit(db, user, "bok_baris", bid, "HAPUS", lama, None, kode)
    return {"ok": 1}


# ---- Impor RAB (mengganti seluruh RAB BOK tahun tsb) & hapus semua ----
@router.post("/import")
def impor_rab(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, body.get("sumber") or "BOK", "pagu")
    try:
        p = parse_rab(base64.b64decode(str(body.get("file") or "")))
    except Exception:
        raise Gagal("Berkas tidak dapat dibaca. Gunakan berkas RAB BOK (.xlsx).")
    tahun = int(body.get("tahun") or 0) or p["tahun"]
    if not tahun:
        raise Gagal("Tahun tidak terbaca, isi tahun.")
    if not p["menus"]:
        raise Gagal("Tidak ada menu terbaca. Pastikan format RAB BOK.")
    sid = sd_id(db, body.get("sumber"))
    ada = db.execute("SELECT COUNT(*) c FROM bok_menu WHERE tahun=? AND sumber_dana_id=?", (tahun, sid)).fetchone()["c"]
    if ada and not body.get("ganti"):
        raise Gagal(f'RAB {body.get("sumber") or "BOK"} {tahun} sudah berisi {ada} menu. Centang "ganti" untuk menimpa.')
    snap = tree(db, tahun, sid) if ada else None
    db.execute("SAVEPOINT impor_rab")
    try:
        db.execute("DELETE FROM bok_menu WHERE tahun=? AND sumber_dana_id=?", (tahun, sid))
        nb = 0
        for i, m in enumerate(p["menus"]):
            mid = db.execute("INSERT INTO bok_menu(tahun,sumber_dana_id,no,nama,urut) VALUES(?,?,?,?,?)", (tahun, sid, m["no"], m["nama"], i + 1)).lastrowid
            for j, r in enumerate(m["rincian"]):
                rid = db.execute("INSERT INTO bok_rincian(menu_id,no,nama,urut) VALUES(?,?,?,?)", (mid, r["no"], r["nama"], j + 1)).lastrowid
                for k, b in enumerate(r["baris"]):
                    db.execute(f"INSERT INTO bok_baris(rincian_id,{','.join(KOL)},urut) VALUES(?,{','.join('?' * len(KOL))},?)",
                               (rid, *[b.get(c) for c in KOL], k + 1))
                    nb += 1
        if not db.execute("SELECT 1 FROM bok_pagu WHERE tahun=? AND sumber_dana_id=?", (tahun, sid)).fetchone():
            pagu = p["pagu"] if p["pagu"] is not None else p["total"]
            db.execute("INSERT INTO bok_pagu(tahun,sumber_dana_id,jenis,pagu,keterangan) VALUES(?,?,?,?,?)", (tahun, sid, "Pagu Indikatif", pagu, "Diimpor dari berkas RAB"))
        db.execute("RELEASE impor_rab")
    except Exception as e:
        db.execute("ROLLBACK TO impor_rab")
        db.execute("RELEASE impor_rab")
        raise Gagal("Data masih dipakai rencana kegiatan; RAB tidak bisa diganti." if "FOREIGN KEY" in str(e) else str(e))
    audit(db, user, "bok_menu", None, "IMPOR-RAB", snap, {"tahun": tahun, "sumber": body.get("sumber") or "BOK", "menu": len(p["menus"]), "baris": nb, "total": p["total"]}, str(body.get("sumber") or "BOK").upper())
    return {"tahun": tahun, "menu": len(p["menus"]), "baris": nb, "total": p["total"], "pagu": p["pagu"], "peringatan": p["peringatan"]}


@router.delete("/{tahun}")
def kosongkan(tahun: int, sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "pagu")
    sid = sd_id(db, sumber)
    snap = tree(db, tahun, sid)
    _hapus(db, "DELETE FROM bok_menu WHERE tahun=? AND sumber_dana_id=?", tahun, sid)
    audit(db, user, "bok_menu", None, "HAPUS-SEMUA", snap, None, sumber.upper())
    return {"ok": 1}


@router.get("/{tahun}/export.xlsx")
def ekspor(tahun: int, sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "baca")
    tr = tree(db, tahun, sd_id(db, sumber))
    wb = Workbook()
    ws = wb.active
    ws.title = f"RAB {sumber.upper()} {tahun}"
    ws.append(["Menu_No", "Menu", "Rincian_No", "Rincian", "Komponen", "Jenis_Belanja", "Kode_Rekening", "Uraian", "Satuan",
               "Vol1", "Sat1", "Vol2", "Sat2", "Vol3", "Sat3", "Unit_Cost", "Jumlah"])
    for m in tr["menu"]:
        for r in m["rincian"]:
            for b in r["baris"]:
                ws.append([m["no"], m["nama"], r["no"], r["nama"], b["komponen"], b["jenis_belanja"], b["kode_rekening"], b["uraian"], b["satuan"],
                           b["vol1"], b["sat1"], b["vol2"], b["sat2"], b["vol3"], b["sat3"], b["unit_cost"], b["jumlah"]])
    return _xlsx_resp(wb, f"RAB_{sumber.upper()}_{tahun}.xlsx")
