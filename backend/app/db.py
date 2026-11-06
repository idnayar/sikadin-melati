"""
Skema & data SIKADIN.
Versi ini menggunakan Wrapper PyMySQL agar kode SQLite lama tetap berjalan
tanpa perlu mengubah parameter binding (?) di file lain.
"""
import hashlib
import hmac
import os
import re
import secrets
import pymysql
import pymysql.cursors
from urllib.parse import urlparse

# URL format dari Render environment, misal: mysql+pymysql://user_db:password_db@IP_CPANEL/nama_db
DB_URL_STR = os.environ.get("DATABASE_URL")

# =====================================================================
# WRAPPER / INTERCEPTOR UNTUK MENIRU SIFAT SQLITE DI MYSQL
# =====================================================================
class SQLiteAdapterCursor:
    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, query, args=()):
        # HACK: Otomatis ubah parameter SQLite (?) jadi MySQL (%s) pada saat runtime
        query = query.replace('?', '%s')
        self._cur.execute(query, args)
        return self

    def executemany(self, query, args=()):
        query = query.replace('?', '%s')
        self._cur.executemany(query, args)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def description(self):
        return self._cur.description

    def __getattr__(self, attr):
        return getattr(self._cur, attr)

    def __iter__(self):
        return iter(self._cur)

class SQLiteAdapterConnection:
    def __init__(self, **kwargs):
        self._conn = pymysql.connect(**kwargs)
        # Meniru atribut row_factory milik SQLite (PyMySQL DictCursor otomatis mengurus ini)
        self.row_factory = None 

    def cursor(self):
        return SQLiteAdapterCursor(self._conn.cursor())

    def execute(self, query, args=()):
        # Izinkan pemanggilan con.execute() langsung seperti di SQLite
        cur = self.cursor()
        cur.execute(query, args)
        return cur

    def executemany(self, query, args=()):
        cur = self.cursor()
        cur.executemany(query, args)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

def connect():
    if not DB_URL_STR:
        # Fallback sementara jika variabel belum ter-set di Render (mencegah crash instan)
        raise ValueError("DATABASE_URL environment variable belum diatur di Render!")
    
    parsed = urlparse(DB_URL_STR)
    
    return SQLiteAdapterConnection(
        host=parsed.hostname,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        port=parsed.port or 3306,
        cursorclass=pymysql.cursors.DictCursor, # Menggantikan _dict_factory bawaanmu
        autocommit=False # Biarkan manual commit seperti bawaan SQLite
    )

# =====================================================================
# FUNGSI-FUNGSI UTILITAS ASLI SIKADIN (DIBIARKAN UTUH)
# =====================================================================
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.scrypt(pw.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32).hex()

def verify_password(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":")
        calc = hashlib.scrypt(pw.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False

def hitung_tingkat(eselon, golongan, status) -> str:
    es = re.sub(r"[^IV]", "", str(eselon or "").upper())
    gol = str(golongan or "").upper().strip()
    if es == "I":
        return "A"
    if es == "II":
        return "B"
    if es == "III":
        return "C"
    if es == "IV":
        return "D"
    if status == "Non ASN":
        return "D"
    if re.match(r"^IV(\b|/|-|$)", gol):
        return "C"
    return "D"

def init_db() -> None:
    """
    Tabel dan data sudah dimigrasi sepenuhnya via DBeaver ke MySQL cPanel.
    Script pembuatan skema SQLite (SCHEMA, SCHEMA_SPJ, dll) dan _seed dihapus dari
    fungsi ini untuk mencegah bentrok/error syntax di MySQL saat aplikasi dijalankan.
    Fungsi ini dibiarkan kosong (pass) agar main.py tidak error saat memanggilnya.
    """
    pass
