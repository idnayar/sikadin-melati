"""Utilitas bersama: koneksi per-permintaan, sesi/login, hak akses, audit, galat."""
import json
import secrets
import time

from fastapi import Depends, Request

from .db import connect


class Gagal(Exception):
    """Galat yang pesannya aman ditampilkan ke pengguna (dikirim sebagai {"error": pesan})."""

    def __init__(self, pesan: str, status: int = 400, **extra):
        super().__init__(pesan)
        self.pesan, self.status, self.extra = pesan, status, extra


def get_db():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


SESSIONS: dict[str, dict] = {}
GAGAL_LOGIN: dict[str, tuple[int, float]] = {}
SESSION_TTL = 12 * 3600


def new_session(user: dict) -> str:
    sid = secrets.token_hex(24)
    SESSIONS[sid] = {**user, "_exp": time.time() + SESSION_TTL}
    return sid


def auth(request: Request) -> dict:
    sid = request.cookies.get("sid")
    u = SESSIONS.get(sid) if sid else None
    if not u or u["_exp"] < time.time():
        SESSIONS.pop(sid, None)
        raise Gagal("Silakan login terlebih dahulu.", 401)
    return {k: v for k, v in u.items() if k != "_exp"}


def bisa_tulis(u: dict) -> bool:
    return u["role"] in ("kepala", "bendahara")


def bisa_baca(u: dict) -> bool:
    return u["role"] != "pegawai"


def perlu_baca(user: dict = Depends(auth)) -> dict:
    if not bisa_baca(user):
        raise Gagal("Tidak ada akses.", 403)
    return user


def perlu_tulis(user: dict = Depends(auth)) -> dict:
    if not bisa_tulis(user):
        raise Gagal("Hanya Kepala/Bendahara yang dapat mengubah data ini.", 403)
    return user


def audit(db, user: dict, tabel: str, rid, aksi: str, lama=None, baru=None) -> None:
    dump = lambda o: json.dumps(o, ensure_ascii=False, default=str) if o else None  # noqa: E731
    db.execute("INSERT INTO audit_log(user_id,username,tabel,record_id,aksi,data_lama,data_baru) VALUES(?,?,?,?,?,?,?)",
               (user["id"], user["username"], tabel, rid, aksi, dump(lama), dump(baru)))


def pesan_db(e: Exception) -> str:
    m = str(e)
    if "UNIQUE" in m:
        return "Data dengan nilai kunci yang sama sudah ada (duplikat)."
    if "FOREIGN KEY" in m:
        return "Data masih dipakai data lain. Nonaktifkan saja, jangan dihapus."
    if "CHECK" in m:
        return "Nilai tidak memenuhi aturan (cek tanggal/jenis/pagu)."
    return m
