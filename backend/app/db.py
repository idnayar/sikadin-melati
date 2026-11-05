"""Skema & data contoh SIKADIN (SQLite). Skema memakai SQL standar sehingga mudah dipindah ke PostgreSQL."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("SIKADIN_DB") or Path(__file__).resolve().parents[2] / "data" / "sikadin.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  nama TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('kepala','bendahara','program','pegawai')),
  pegawai_id INTEGER REFERENCES pegawai(id), aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, waktu TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  user_id INTEGER, username TEXT, tabel TEXT NOT NULL, record_id INTEGER, aksi TEXT NOT NULL,
  data_lama TEXT, data_baru TEXT);
CREATE TABLE IF NOT EXISTS pegawai(
  id INTEGER PRIMARY KEY, nama TEXT NOT NULL, nip TEXT UNIQUE, pangkat TEXT, golongan TEXT,
  jabatan TEXT, eselon TEXT, status TEXT NOT NULL DEFAULT 'ASN' CHECK(status IN ('ASN','PPPK','Non ASN')),
  program TEXT, tingkat TEXT NOT NULL DEFAULT 'D' CHECK(tingkat IN ('A','B','C','D')),
  aktif INTEGER NOT NULL DEFAULT 1, ruangan TEXT, telepon TEXT);
CREATE TABLE IF NOT EXISTS sumber_dana(
  id INTEGER PRIMARY KEY, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pagu(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id),
  program TEXT, kegiatan TEXT, sub_kegiatan TEXT, kode_rekening TEXT NOT NULL, uraian TEXT,
  pagu INTEGER NOT NULL DEFAULT 0 CHECK(pagu >= 0),
  UNIQUE(tahun, sumber_dana_id, program, kegiatan, sub_kegiatan, kode_rekening));
CREATE TABLE IF NOT EXISTS lokasi(
  id INTEGER PRIMARY KEY, nama TEXT NOT NULL,
  jenis TEXT NOT NULL CHECK(jenis IN ('DK_WILAYAH','DK_ANTAR','LK_KALTENG','LK_LUAR_PROV')),
  kecamatan TEXT, provinsi TEXT, induk_id INTEGER REFERENCES lokasi(id),
  kunci_tarif TEXT, aktif INTEGER NOT NULL DEFAULT 1, UNIQUE(nama, jenis));
CREATE TABLE IF NOT EXISTS tarif(
  id INTEGER PRIMARY KEY, tahun_berlaku INTEGER NOT NULL, dasar_hukum TEXT NOT NULL,
  kategori TEXT NOT NULL CHECK(kategori IN ('UH_DK','UH_DIKLAT_DK','UH_LK_KALTENG','UH_LUAR_PROV',
    'TR_DK','TR_DARAT_LK','INAP_DK','INAP_KALTENG','INAP_LUAR_PROV','TIKET_PESAWAT','TAKSI')),
  tujuan TEXT NOT NULL DEFAULT '', tingkat TEXT NOT NULL DEFAULT '',
  nilai INTEGER, nilai2 INTEGER, satuan TEXT, lampiran TEXT, keterangan TEXT,
  UNIQUE(tahun_berlaku, kategori, tujuan, tingkat));
CREATE TABLE IF NOT EXISTS pejabat(
  id INTEGER PRIMARY KEY, peran TEXT NOT NULL, nama TEXT NOT NULL, nip TEXT, pangkat TEXT, jabatan TEXT,
  aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS pengaturan(
  id INTEGER PRIMARY KEY, kunci TEXT NOT NULL UNIQUE, nilai TEXT, keterangan TEXT);
CREATE TABLE IF NOT EXISTS libur(
  id INTEGER PRIMARY KEY, tanggal TEXT NOT NULL UNIQUE, keterangan TEXT);
CREATE TABLE IF NOT EXISTS bok_pagu(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL UNIQUE, jenis TEXT NOT NULL DEFAULT 'Pagu Indikatif',
  pagu INTEGER NOT NULL DEFAULT 0 CHECK(pagu >= 0), keterangan TEXT);
CREATE TABLE IF NOT EXISTS bok_menu(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, no TEXT, nama TEXT NOT NULL, urut INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS bok_rincian(
  id INTEGER PRIMARY KEY, menu_id INTEGER NOT NULL REFERENCES bok_menu(id) ON DELETE CASCADE,
  no TEXT, nama TEXT NOT NULL, urut INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS bok_baris(
  id INTEGER PRIMARY KEY, rincian_id INTEGER NOT NULL REFERENCES bok_rincian(id) ON DELETE CASCADE,
  komponen TEXT, jenis_belanja TEXT NOT NULL, kode_rekening TEXT, uraian TEXT, satuan TEXT,
  vol1 REAL NOT NULL DEFAULT 1, sat1 TEXT, vol2 REAL NOT NULL DEFAULT 1, sat2 TEXT, vol3 REAL NOT NULL DEFAULT 1, sat3 TEXT,
  unit_cost INTEGER NOT NULL DEFAULT 0 CHECK(unit_cost >= 0), jumlah INTEGER NOT NULL DEFAULT 0 CHECK(jumlah >= 0),
  urut INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_bok_menu_tahun ON bok_menu(tahun);
CREATE TABLE IF NOT EXISTS rencana(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, bulan INTEGER NOT NULL CHECK(bulan BETWEEN 1 AND 12),
  sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id), baris_id INTEGER NOT NULL REFERENCES bok_baris(id),
  kegiatan TEXT NOT NULL, kode_rekening TEXT, lokasi_id INTEGER REFERENCES lokasi(id),
  jenis_perjalanan TEXT, durasi TEXT CHECK(durasi IN ('gt8','le8')), jumlah_petugas INTEGER NOT NULL DEFAULT 1 CHECK(jumlah_petugas >= 1),
  jumlah_hari INTEGER NOT NULL DEFAULT 1 CHECK(jumlah_hari >= 1), frekuensi INTEGER NOT NULL DEFAULT 1 CHECK(frekuensi >= 1),
  tingkat TEXT NOT NULL DEFAULT 'D', roda INTEGER NOT NULL DEFAULT 2, menginap TEXT NOT NULL DEFAULT 'tidak',
  pp INTEGER NOT NULL DEFAULT 1, transport_manual INTEGER NOT NULL DEFAULT 0, estimasi_manual INTEGER NOT NULL DEFAULT 0,
  estimasi INTEGER NOT NULL DEFAULT 0 CHECK(estimasi >= 0), rincian_biaya TEXT,
  status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft','Diajukan','Ditolak','Disetujui','Terjadwal','Terlaksana','SPJ Selesai')),
  catatan TEXT, alasan_tolak TEXT, dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')),
  diajukan_pada TEXT, diputuskan_oleh TEXT, diputuskan_pada TEXT);
CREATE INDEX IF NOT EXISTS ix_rencana_baris ON rencana(baris_id);
CREATE TABLE IF NOT EXISTS cuti(
  id INTEGER PRIMARY KEY, pegawai_id INTEGER NOT NULL REFERENCES pegawai(id),
  mulai TEXT NOT NULL, selesai TEXT NOT NULL, keterangan TEXT, CHECK(selesai >= mulai));

-- Tahap 3: Jadwal dinas luar. Satu jadwal = satu pelaksanaan (mulai–selesai) dari satu rencana yang disetujui.
CREATE TABLE IF NOT EXISTS jadwal(
  id INTEGER PRIMARY KEY, rencana_id INTEGER NOT NULL REFERENCES rencana(id), tahun INTEGER NOT NULL,
  baris_id INTEGER NOT NULL REFERENCES bok_baris(id), kegiatan TEXT NOT NULL,
  lokasi_id INTEGER NOT NULL REFERENCES lokasi(id), sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id),
  mulai TEXT NOT NULL, selesai TEXT NOT NULL, durasi TEXT NOT NULL DEFAULT 'gt8' CHECK(durasi IN ('gt8','le8')),
  status TEXT NOT NULL DEFAULT 'Diusulkan' CHECK(status IN ('Diusulkan','Disetujui','Ditolak','Dibatalkan','Terlaksana')),
  no_st TEXT, catatan TEXT, alasan TEXT, dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')),
  diputuskan_oleh TEXT, diputuskan_pada TEXT, CHECK(selesai >= mulai));
CREATE INDEX IF NOT EXISTS ix_jadwal_rencana ON jadwal(rencana_id);
CREATE INDEX IF NOT EXISTS ix_jadwal_mulai ON jadwal(mulai, selesai);
CREATE TABLE IF NOT EXISTS jadwal_petugas(
  id INTEGER PRIMARY KEY, jadwal_id INTEGER NOT NULL REFERENCES jadwal(id) ON DELETE CASCADE,
  pegawai_id INTEGER NOT NULL REFERENCES pegawai(id), UNIQUE(jadwal_id, pegawai_id));
-- Baris-baris di bawah HANYA berisi jadwal aktif (Diusulkan/Disetujui/Terlaksana); dihapus saat Ditolak/Dibatalkan.
-- (b) kegiatan yang sama di lokasi yang sama tidak boleh dua kali pada tanggal yang sama
CREATE TABLE IF NOT EXISTS jadwal_hari(
  id INTEGER PRIMARY KEY, jadwal_id INTEGER NOT NULL REFERENCES jadwal(id) ON DELETE CASCADE, tanggal TEXT NOT NULL,
  baris_id INTEGER NOT NULL, lokasi_id INTEGER NOT NULL,
  UNIQUE(baris_id, lokasi_id, tanggal));
-- (a)+(c) satu pegawai tidak boleh punya dua penugasan pada tanggal yang sama, apa pun sumber dananya
-- (sehingga uang harian ganda lintas DAU/BOK/BLUD mustahil)
CREATE TABLE IF NOT EXISTS penugasan_hari(
  id INTEGER PRIMARY KEY, jadwal_id INTEGER NOT NULL REFERENCES jadwal(id) ON DELETE CASCADE,
  pegawai_id INTEGER NOT NULL REFERENCES pegawai(id), tanggal TEXT NOT NULL,
  sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id), uang_harian INTEGER NOT NULL DEFAULT 1,
  UNIQUE(pegawai_id, tanggal));
-- (d) tanggal libur / cuti pegawai ditolak juga oleh database
CREATE TRIGGER IF NOT EXISTS trg_penugasan_libur BEFORE INSERT ON penugasan_hari
WHEN EXISTS(SELECT 1 FROM libur WHERE tanggal = NEW.tanggal)
BEGIN SELECT RAISE(ABORT, 'LIBUR'); END;
CREATE TRIGGER IF NOT EXISTS trg_penugasan_cuti BEFORE INSERT ON penugasan_hari
WHEN EXISTS(SELECT 1 FROM cuti WHERE pegawai_id = NEW.pegawai_id AND NEW.tanggal BETWEEN mulai AND selesai)
BEGIN SELECT RAISE(ABORT, 'CUTI'); END;
"""


# Pengaturan yang ditambahkan setelah rilis awal (ditambahkan otomatis ke database lama)
PENGATURAN_BARU = [
    ("batas_persen_ruangan", "50", "Maks. % pegawai satu ruangan yang boleh meninggalkan ruangan (dinas luar/cuti) pada hari yang sama"),
    ("ruangan_hitung_cuti", "1", "1 = pegawai cuti dihitung sebagai tidak berada di ruangan; 0 = hanya dinas luar yang dihitung"),
]


def _dict_factory(cur, row):
    return {c[0]: row[i] for i, c in enumerate(cur.description)}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    con.row_factory = _dict_factory
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


# ---- kata sandi: scrypt (N=16384, r=8, p=1) — format "salt:hash" sama dengan versi Node lama ----
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
    """Perbup Pasal 7: C = Eselon III / Gol IV; D = Eselon IV / Gol III, II, I & Non ASN. A/B tidak dipakai di Puskesmas."""
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
    con = connect()
    con.executescript(SCHEMA)
    # Migrasi database lama: kolom baru pada tabel pegawai
    ada = {r["name"] for r in con.execute("PRAGMA table_info(pegawai)").fetchall()}
    for kol in ("ruangan", "telepon"):
        if kol not in ada:
            con.execute(f"ALTER TABLE pegawai ADD COLUMN {kol} TEXT")
    if con.execute("SELECT COUNT(*) c FROM pegawai").fetchone()["c"] == 0:
        _seed(con)
    for k, v, ket in PENGATURAN_BARU:  # database lama: tambahkan pengaturan baru bila belum ada
        con.execute("INSERT OR IGNORE INTO pengaturan(kunci,nilai,keterangan) VALUES(?,?,?)", (k, v, ket))
    con.commit()
    con.close()


def _seed(con: sqlite3.Connection) -> None:
    DH = "Perbup Kapuas No. 8 Tahun 2026"
    many = lambda sql, rows: con.executemany(sql, rows)  # noqa: E731
    peg = [
        ("dr. Rina Marlina", "198005122008012001", "Pembina", "IV/a", "Kepala Puskesmas", "III", "ASN", "Manajemen"),
        ("Budi Santoso, S.Kep", "198203152006041002", "Penata Tk.I", "III/d", "Perawat Ahli Muda", "", "ASN", "P2P"),
        ("Siti Aminah, Amd.Keb", "198507202009042001", "Penata Muda Tk.I", "III/b", "Bidan Penyelia", "", "ASN", "KIA"),
        ("Agus Prasetyo, SKM", "198811102011011003", "Penata", "III/c", "Epidemiolog Kesehatan", "", "ASN", "Promkes"),
        ("Dewi Lestari, A.Md.Gz", "199001252012052002", "Penata Muda", "III/a", "Nutrisionis", "", "ASN", "Gizi"),
        ("Hendra Wijaya, S.Kom", "198306062007031004", "Pembina", "IV/a", "Pranata Komputer / Kasubbag TU", "IV", "ASN", "Tata Usaha"),
        ("Maria Ulfa, Amd.Kes", "199203032020122003", "IX", "IX", "Sanitarian Terampil", "", "PPPK", "Kesling"),
        ("Rudi Hartono, Amd.Kep", "199105172021041001", "VII", "VII", "Perawat Terampil", "", "PPPK", "PTM"),
        ("Nina Safitri", "", "-", "-", "Tenaga Kesehatan Kontrak", "", "Non ASN", "KIA"),
        ("Joko Susilo", "", "-", "-", "Pengemudi Ambulans", "", "Non ASN", "Tata Usaha"),
    ]
    many("INSERT INTO pegawai(nama,nip,pangkat,golongan,jabatan,eselon,status,program,tingkat) VALUES(?,?,?,?,?,?,?,?,?)",
         [(p[0], p[1] or None, p[2], p[3], p[4], p[5], p[6], p[7], hitung_tingkat(p[5], p[3], p[6])) for p in peg])
    many("INSERT INTO sumber_dana(kode,nama) VALUES(?,?)",
         [("DAU", "Dana Alokasi Umum"), ("BOK", "Bantuan Operasional Kesehatan"), ("BLUD", "Badan Layanan Umum Daerah")])
    # Pagu contoh DAU/BLUD — angka ilustrasi. Pagu & RAB BOK diimpor dari berkas RAB (menu Pagu Anggaran BOK).
    many("INSERT INTO pagu(tahun,sumber_dana_id,program,kegiatan,sub_kegiatan,kode_rekening,uraian,pagu) VALUES(?,?,?,?,?,?,?,?)", [
        (2026, 1, "Program Pemenuhan UKP/UKM", "Penyediaan Layanan Kesehatan UKM", "Pelayanan Kesehatan Masyarakat", "5.1.02.04.01.0001", "Perjalanan Dinas Biasa", 30000000),
        (2026, 1, "Program Pemenuhan UKP/UKM", "Penyediaan Layanan Kesehatan UKM", "Pelayanan Kesehatan Masyarakat", "5.1.02.04.01.0003", "Perjalanan Dinas Dalam Kota", 20000000),
        (2026, 3, "Program BLUD", "Pelayanan dan Penunjang Pelayanan BLUD", "Pelayanan dan Penunjang Pelayanan BLUD", "5.1.02.04.01.0001", "Perjalanan Dinas Biasa", 25000000),
        (2026, 3, "Program BLUD", "Pelayanan dan Penunjang Pelayanan BLUD", "Pelayanan dan Penunjang Pelayanan BLUD", "5.1.02.04.01.0003", "Perjalanan Dinas Dalam Kota", 15000000),
    ])
    lk = "INSERT INTO lokasi(nama,jenis,kecamatan,provinsi,induk_id,kunci_tarif) VALUES(?,?,?,?,?,?)"
    for n in ["Kelurahan Selat Tengah", "Kelurahan Selat Dalam", "Kelurahan Selat Hulu", "Kelurahan Selat Utara"]:
        con.execute(lk, (n, "DK_WILAYAH", "Selat", "Kalimantan Tengah", None, None))
    con.execute(lk, ("Posyandu (contoh) — Selat Hulu", "DK_WILAYAH", "Selat", "Kalimantan Tengah", 3, None))
    for n in ["Kapuas Hilir", "Basarang", "Bataguh", "Kapuas Timur", "Pulau Petak", "Kapuas Barat", "Kapuas Murung", "Mantangai", "Timpah"]:
        con.execute(lk, ("Kec. " + n, "DK_ANTAR", n, "Kalimantan Tengah", None, "Kec. " + n))
    for n in ["Pulang Pisau", "Palangka Raya", "Katingan", "Kotawaringin Timur", "Gunung Mas", "Barito Selatan", "Seruyan",
              "Barito Timur", "Kotawaringin Barat", "Barito Utara", "Murung Raya", "Lamandau", "Sukamara"]:
        con.execute(lk, (n, "LK_KALTENG", n, "Kalimantan Tengah", None, n))
    for n in ["Kalimantan Selatan", "DKI Jakarta"]:
        con.execute(lk, (n, "LK_LUAR_PROV", n, n, None, n))

    tr = "INSERT INTO tarif(tahun_berlaku,dasar_hukum,kategori,tujuan,tingkat,nilai,nilai2,satuan,lampiran,keterangan) VALUES(2026,?,?,?,?,?,?,?,?,?)"

    def T(kat, tuj, ting, n1, n2, sat, lamp, ket=None):
        con.execute(tr, (DH, kat, tuj, ting, n1, n2, sat, lamp, ket))

    T("UH_DK", "Kab. Kapuas", "", 140000, None, "OH", "I.II", "Dalam kota > 8 jam, wilayah Kab. Kapuas")
    T("UH_DIKLAT_DK", "Kab. Kapuas", "", 110000, None, "OH", "I.II", "Diklat dalam kota > 8 jam")
    T("UH_LK_KALTENG", "Kalimantan Tengah", "", 360000, None, "OH", "I.I", "Luar kota dalam Provinsi Kalteng")
    T("UH_LUAR_PROV", "Kalimantan Selatan", "", 380000, None, "OH", "I.I", "Contoh — impor tabel lengkap per provinsi")
    T("UH_LUAR_PROV", "DKI Jakarta", "", 530000, None, "OH", "I.I", "Contoh — impor tabel lengkap per provinsi")
    for t, a, b in [("Kec. Kapuas Hilir", 50000, 250000), ("Kec. Basarang", 100000, 250000), ("Kec. Bataguh", 100000, 350000),
                    ("Kec. Kapuas Timur", 100000, 400000), ("Kec. Pulau Petak", 100000, 350000), ("Kec. Kapuas Barat", 200000, 450000),
                    ("Kec. Kapuas Murung", 250000, 450000), ("Kec. Mantangai", 350000, 1000000), ("Kec. Timpah", None, 2500000)]:
        T("TR_DK", t, "", a, b, "orang/kali", "I.XI.A", "Dari Kec. Selat; nilai=Roda 2, nilai2=Roda 4")
    for t, v in [("Pulang Pisau", 250000), ("Palangka Raya", 275000), ("Katingan", 525000), ("Kotawaringin Timur", 575000),
                 ("Gunung Mas", 575000), ("Barito Selatan", 565000), ("Seruyan", 603000), ("Barito Timur", 608000),
                 ("Kotawaringin Barat", 700000), ("Barito Utara", 700000), ("Murung Raya", 723000), ("Lamandau", 800000), ("Sukamara", 800000)]:
        T("TR_DARAT_LK", t, "", v, None, "orang/kali", "I.X", "Dari Kab. Kapuas; PP dihitung 2 kali")
    for t in ["Kec. Kapuas Hilir", "Kec. Bataguh", "Kec. Basarang", "Kec. Kapuas Timur", "Kec. Pulau Petak", "Kec. Kapuas Barat"]:
        T("INAP_DK", t, "", 300000, None, "OH", "I.VI", "Biaya riil maksimal tarif")
    T("INAP_DK", "Kec. Selat", "", 400000, None, "OH", "I.VI", "Biaya riil maksimal tarif")
    T("INAP_KALTENG", "Palangka Raya", "C", 1160000, None, "OH", "I.V", "Biaya riil maksimal tarif")
    T("INAP_KALTENG", "Palangka Raya", "D", 659000, None, "OH", "I.V", "Biaya riil maksimal tarif")
    T("INAP_KALTENG", "Kabupaten lain", "C", 600000, None, "OH", "I.V", "Biaya riil maksimal tarif")
    T("INAP_KALTENG", "Kabupaten lain", "D", 400000, None, "OH", "I.V", "Biaya riil maksimal tarif")

    many("INSERT INTO pengaturan(kunci,nilai,keterangan) VALUES(?,?,?)", [
        ("tahun_anggaran", "2027", "Tahun anggaran aktif"),
        ("dasar_hukum", DH, "Dasar hukum tarif aktif (menggantikan Perbup No. 11 Tahun 2024)"),
        ("instansi", "UPT Puskesmas Melati", "Nama instansi pada kop surat"),
        ("kop_baris1", "PEMERINTAH KABUPATEN KAPUAS", "Kop surat baris 1"),
        ("kop_baris2", "DINAS KESEHATAN", "Kop surat baris 2"),
        ("kop_baris3", "UPT PUSKESMAS MELATI", "Kop surat baris 3"),
        ("kop_alamat", "Kecamatan Selat, Kuala Kapuas, Kabupaten Kapuas, Kalimantan Tengah", "Alamat pada kop"),
        ("format_nomor_st", "{no}/ST/PKM-MLT/{bulan_romawi}/{tahun}", "Format nomor Surat Tugas"),
        ("panjar_maks_persen", "80", "Panjar maksimal % dari perkiraan biaya (Pasal 12 ayat 4)"),
        ("lumpsum_inap_persen", "30", "Lumpsum maks. % tarif penginapan bila tidak menginap di hotel (Pasal 6 ayat 6)"),
        ("batas_hari_dinas_bulan", "10", "Peringatan bila total hari dinas luar seorang pegawai per bulan melebihi nilai ini (nilai awal — sesuaikan)"),
        ("batas_jam_dalam_kota", "8", "Dalam kota ≤ batas jam hanya uang transport lokal (Pasal 6 ayat 3)"),
        ("min_rombongan_sewa", "3", "Minimal rombongan untuk sewa kendaraan (Pasal 6 ayat 5)"),
        ("ambang_pagu_peringatan", "10", "Peringatan bila sisa pagu < % ini"),
        *PENGATURAN_BARU,
    ])
    many("INSERT INTO pejabat(peran,nama,nip,pangkat,jabatan) VALUES(?,?,?,?,?)", [
        ("Penandatangan ST / KPA", "dr. Rina Marlina", "198005122008012001", "Pembina (IV/a)", "Kepala UPT Puskesmas Melati"),
        ("Bendahara Pengeluaran", "Dewi Lestari, A.Md.Gz", "199001252012052002", "Penata Muda (III/a)", "Bendahara Pengeluaran"),
        ("PPTK", "Agus Prasetyo, SKM", "198811102011011003", "Penata (III/c)", "PPTK"),
    ])
    many("INSERT INTO libur(tanggal,keterangan) VALUES(?,?)", [
        ("2026-11-09", "Contoh — perbarui sesuai SKB Libur Nasional & Cuti Bersama"), ("2026-12-25", "Hari Raya Natal")])
    con.execute("INSERT INTO cuti(pegawai_id,mulai,selesai,keterangan) VALUES(?,?,?,?)", (5, "2026-11-16", "2026-11-18", "Cuti tahunan (contoh)"))
    # Akun demo — GANTI setelah login pertama. Di produksi atur SIKADIN_ADMIN_PASSWORD sebelum jalan pertama.
    pw = os.environ.get("SIKADIN_ADMIN_PASSWORD") or "sikadin2026"
    for u, n, r, p in [("kepala", "dr. Rina Marlina", "kepala", 1), ("bendahara", "Dewi Lestari, A.Md.Gz", "bendahara", 5),
                       ("program", "Agus Prasetyo, SKM", "program", 4), ("pegawai", "Budi Santoso, S.Kep", "pegawai", 2)]:
        con.execute("INSERT INTO users(username,password_hash,nama,role,pegawai_id) VALUES(?,?,?,?,?)", (u, hash_password(pw), n, r, p))
