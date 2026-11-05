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


def akses_sumber(u: dict, kode: str, aksi: str = "baca") -> bool:
    """Izin per sumber dana. aksi: 'baca' (lihat pagu/RAB/rencana), 'pagu' (ubah pagu & RAB), 'rencana' (buat/ubah rencana).
    BLUD: HANYA Kepala Puskesmas dan Bendahara BLUD. BOK/DAU: Kepala, Bendahara (pagu+rencana), Pengelola Program (rencana);
    Bendahara BLUD hanya boleh melihat BOK/DAU."""
    role, kode = u["role"], str(kode or "").upper()
    if role == "kepala":
        return True
    if kode == "BLUD":
        return role == "bendahara_blud"
    if role == "bendahara":
        return True
    if role == "program":
        return aksi in ("baca", "rencana")
    if role == "bendahara_blud":
        return aksi == "baca"
    return False


def cek_sumber(u: dict, kode: str, aksi: str = "baca") -> None:
    if not akses_sumber(u, kode, aksi):
        raise Gagal("Data sumber dana " + str(kode) + " hanya dapat diakses oleh Kepala Puskesmas" + (" dan Bendahara BLUD." if str(kode).upper() == "BLUD" else " dan bendahara yang berwenang."), 403)


def sumber_boleh(u: dict, aksi: str = "baca") -> list[str]:
    return [k for k in ("BOK", "DAU", "BLUD") if akses_sumber(u, k, aksi)]


def kode_sd(db, sd_id) -> str:
    r = db.execute("SELECT kode FROM sumber_dana WHERE id=?", (sd_id,)).fetchone()
    return r["kode"] if r else ""


def kepala_wajib(db) -> bool:
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci='kepala_wajib'").fetchone()
    return bool(r) and str(r["nilai"]).strip() == "1"


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


def audit(db, user: dict, tabel: str, rid, aksi: str, lama=None, baru=None, sumber: str | None = None) -> None:
    """Catat perubahan. `sumber` (BOK/DAU/BLUD) menandai catatan keuangan agar riwayat BLUD tidak terlihat pihak yang tak berwenang."""
    dump = lambda o: json.dumps(o, ensure_ascii=False, default=str) if o else None  # noqa: E731
    db.execute("INSERT INTO audit_log(user_id,username,tabel,record_id,aksi,data_lama,data_baru,sumber) VALUES(?,?,?,?,?,?,?,?)",
               (user["id"], user["username"], tabel, rid, aksi, dump(lama), dump(baru), (sumber or None)))


def pesan_db(e: Exception) -> str:
    m = str(e)
    if "SPJ_TERKUNCI" in m:
        return "SPJ yang sudah dibayar terkunci."
    if "SPJ_TIDAK_BOLEH_DIHAPUS" in m:
        return "SPJ yang sudah diajukan tidak boleh dihapus."
    if "UNIQUE" in m:
        return "Data dengan nilai kunci yang sama sudah ada (duplikat)."
    if "FOREIGN KEY" in m:
        return "Data masih dipakai data lain. Nonaktifkan saja, jangan dihapus."
    if "CHECK" in m:
        return "Nilai tidak memenuhi aturan (cek tanggal/jenis/pagu)."
    return m
