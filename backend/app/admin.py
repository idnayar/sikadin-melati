"""Perintah pengelola server SIKADIN (jalankan dari folder backend, venv aktif):

  python -m app.admin cek-sandi-demo          -> daftar akun yang masih memakai sandi demo (kode keluar 1 bila ada)
  python -m app.admin sandi-acak              -> ganti sandi demo semua akun dengan sandi acak kuat, dicetak SEKALI
  python -m app.admin atur-sandi USERNAME     -> ganti sandi satu akun (diminta tanpa tampil di layar)
  python -m app.admin backup [--dir D] [--keep N]  -> salinan konsisten database (aman saat aplikasi berjalan), simpan N terakhir
"""
import argparse
import datetime as dt
import getpass
import os
import secrets
import sqlite3
import sys
from pathlib import Path

from .db import DB_PATH, connect, hash_password, verify_password

SANDI_DEMO = {"sikadin2026"}


def akun_sandi_demo(con) -> list[str]:
    return [u["username"] for u in con.execute("SELECT username, password_hash FROM users WHERE aktif=1").fetchall() if any(verify_password(p, u["password_hash"]) for p in SANDI_DEMO)]


def amankan_sandi_demo(con) -> list[str]:
    """Bila SIKADIN_ADMIN_PASSWORD (>=10 karakter, bukan sandi demo) diatur, akun yang masih bersandi demo diganti dengan sandi itu.
    Dipakai saat start produksi dan setelah pemulihan database, agar server tidak pernah berjalan dengan sandi demo."""
    pw = os.environ.get("SIKADIN_ADMIN_PASSWORD") or ""
    if len(pw) < 10 or pw in SANDI_DEMO:
        return []
    ganti = akun_sandi_demo(con)
    for u in ganti:
        con.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(pw), u))
    con.commit()
    return ganti


def _acak() -> str:
    abjad = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(abjad) for _ in range(14))


def cek() -> int:
    con = connect()
    sisa = akun_sandi_demo(con)
    con.close()
    if sisa:
        print("Akun masih memakai sandi demo:", ", ".join(sisa))
        return 1
    print("OK: tidak ada akun aktif yang memakai sandi demo.")
    return 0


def acak() -> int:
    con = connect()
    sisa = akun_sandi_demo(con)
    for u in sisa:
        pw = _acak()
        con.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(pw), u))
        print(f"{u:<16} {pw}")
    con.commit()
    con.close()
    print("\nCatat sandi di atas sekarang — tidak ditampilkan lagi. Pengguna dapat menggantinya lewat tombol «Ganti password»." if sisa else "Tidak ada akun dengan sandi demo.")
    return 0


def atur(username: str) -> int:
    con = connect()
    if not con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        print("Pengguna tidak ditemukan.")
        return 1
    a, b = getpass.getpass("Sandi baru (min. 10 karakter): "), getpass.getpass("Ulangi sandi: ")
    if a != b or len(a) < 10:
        print("Sandi tidak sama atau kurang dari 10 karakter.")
        return 1
    con.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(a), username))
    con.commit()
    print("Sandi diganti.")
    return 0


def backup(folder: str, simpan: int) -> int:
    d = Path(folder)
    d.mkdir(parents=True, exist_ok=True)
    tujuan = d / f"sikadin-{dt.datetime.now():%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(tujuan)
    with dst:
        src.backup(dst)            # API backup SQLite: konsisten walau ada transaksi berjalan
    src.close()
    dst.close()
    lama = sorted(d.glob("sikadin-*.db"))[:-simpan] if simpan > 0 else []
    for f in lama:
        f.unlink()
    print(f"Backup: {tujuan} ({tujuan.stat().st_size // 1024} KB); dihapus {len(lama)} backup lama.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.admin")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("cek-sandi-demo")
    sp.add_parser("sandi-acak")
    a = sp.add_parser("atur-sandi")
    a.add_argument("username")
    b = sp.add_parser("backup")
    b.add_argument("--dir", default=str(DB_PATH.parent / "backup"))
    b.add_argument("--keep", type=int, default=30)
    n = ap.parse_args()
    return {"cek-sandi-demo": cek, "sandi-acak": acak}.get(n.cmd, lambda: atur(n.username) if n.cmd == "atur-sandi" else backup(n.dir, n.keep))()


if __name__ == "__main__":
    sys.exit(main())
