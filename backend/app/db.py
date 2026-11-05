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
  nama TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('kepala','bendahara','bendahara_blud','program','pembuat_surat','pegawai')),
  pegawai_id INTEGER REFERENCES pegawai(id), aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, waktu TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  user_id INTEGER, username TEXT, tabel TEXT NOT NULL, record_id INTEGER, aksi TEXT NOT NULL,
  data_lama TEXT, data_baru TEXT, sumber TEXT);
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
-- Pagu & RAB per sumber dana (BOK/DAU/BLUD). Nama tabel 'bok_*' dipertahankan dari versi awal (hanya BOK).
CREATE TABLE IF NOT EXISTS bok_pagu(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id),
  jenis TEXT NOT NULL DEFAULT 'Pagu Indikatif', pagu INTEGER NOT NULL DEFAULT 0 CHECK(pagu >= 0), keterangan TEXT,
  UNIQUE(tahun, sumber_dana_id));
CREATE TABLE IF NOT EXISTS bok_menu(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, sumber_dana_id INTEGER REFERENCES sumber_dana(id),
  no TEXT, nama TEXT NOT NULL, urut INTEGER NOT NULL DEFAULT 0);
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

-- Tahap 4: Surat Tugas (ST) & Surat Perjalanan Dinas (SPD). Setelah terbit, isi ST/SPD TERKUNCI (trigger);
-- perubahan hanya lewat pembatalan + terbit ulang dengan nomor baru. Nomor tidak pernah dipakai ulang.
CREATE TABLE IF NOT EXISTS surat_tugas(
  id INTEGER PRIMARY KEY, jadwal_id INTEGER NOT NULL REFERENCES jadwal(id), sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id),
  tahun INTEGER NOT NULL, jenis_nomor TEXT NOT NULL DEFAULT 'ST-BOK', nomor_urut INTEGER NOT NULL, nomor TEXT NOT NULL, tanggal_surat TEXT NOT NULL,
  dasar TEXT, maksud TEXT NOT NULL, penandatangan_id INTEGER REFERENCES pejabat(id), isi_json TEXT NOT NULL, nomor_srikandi TEXT,
  status TEXT NOT NULL DEFAULT 'Terbit' CHECK(status IN ('Terbit','Dibatalkan')),
  versi INTEGER NOT NULL DEFAULT 1, pengganti_dari INTEGER REFERENCES surat_tugas(id), alasan_batal TEXT, srikandi_diunggah_pada TEXT, srikandi_diunggah_oleh TEXT,
  dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')), dibatalkan_oleh TEXT, dibatalkan_pada TEXT,
  UNIQUE(tahun, jenis_nomor, nomor_urut), UNIQUE(nomor));
CREATE UNIQUE INDEX IF NOT EXISTS ux_st_aktif ON surat_tugas(jadwal_id) WHERE status='Terbit';
-- Kode penomoran naskah (klasifikasi arsip Permendagri 83/2022; tata naskah Permendagri 1/2023). Seri nomor terpisah per jenis.
CREATE TABLE IF NOT EXISTS jenis_nomor(
  kode TEXT PRIMARY KEY, nama TEXT NOT NULL, klasifikasi TEXT NOT NULL, unit TEXT NOT NULL,
  format TEXT NOT NULL DEFAULT '{klasifikasi}/{yymm}-{urut}/{unit}/{bulan_romawi}/{tahun}', keterangan TEXT, aktif INTEGER NOT NULL DEFAULT 1);
-- Register nomor surat umum / lainnya (selain Surat Tugas yang nomornya otomatis dari ST)
CREATE TABLE IF NOT EXISTS nomor_surat(
  id INTEGER PRIMARY KEY, jenis TEXT NOT NULL REFERENCES jenis_nomor(kode), tahun INTEGER NOT NULL, nomor_urut INTEGER NOT NULL,
  nomor TEXT NOT NULL UNIQUE, klasifikasi TEXT NOT NULL, tanggal TEXT NOT NULL, perihal TEXT NOT NULL, tujuan TEXT,
  status TEXT NOT NULL DEFAULT 'Terbit' CHECK(status IN ('Terbit','Dibatalkan')), alasan_batal TEXT,
  dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')), UNIQUE(jenis, tahun, nomor_urut));
-- Satu dokumen SPD per ST (nomor sama dengan ST). Baris tabel ini = rincian biaya per petugas (tarif Perbup, terkunci).
CREATE TABLE IF NOT EXISTS spd(
  id INTEGER PRIMARY KEY, st_id INTEGER NOT NULL REFERENCES surat_tugas(id), pegawai_id INTEGER NOT NULL REFERENCES pegawai(id),
  biaya_json TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0, UNIQUE(st_id, pegawai_id));
CREATE TRIGGER IF NOT EXISTS trg_st_kunci BEFORE UPDATE ON surat_tugas
WHEN OLD.status='Terbit' AND (NEW.nomor IS NOT OLD.nomor OR NEW.nomor_urut IS NOT OLD.nomor_urut OR NEW.isi_json IS NOT OLD.isi_json OR NEW.maksud IS NOT OLD.maksud
  OR NEW.dasar IS NOT OLD.dasar OR NEW.tanggal_surat IS NOT OLD.tanggal_surat OR NEW.jadwal_id IS NOT OLD.jadwal_id OR NEW.tahun IS NOT OLD.tahun)
BEGIN SELECT RAISE(ABORT, 'ST_TERKUNCI'); END;
-- nomor Srikandi diisi sekali (setelah ST ditandatangani elektronik), lalu terkunci
CREATE TRIGGER IF NOT EXISTS trg_st_noskd BEFORE UPDATE ON surat_tugas
WHEN OLD.nomor_srikandi IS NOT NULL AND NEW.nomor_srikandi IS NOT OLD.nomor_srikandi
BEGIN SELECT RAISE(ABORT, 'NOMOR_SRIKANDI_TERKUNCI'); END;
CREATE TRIGGER IF NOT EXISTS trg_st_final BEFORE UPDATE ON surat_tugas WHEN OLD.status='Dibatalkan'
BEGIN SELECT RAISE(ABORT, 'ST_DIBATALKAN'); END;
CREATE TRIGGER IF NOT EXISTS trg_st_nodel BEFORE DELETE ON surat_tugas BEGIN SELECT RAISE(ABORT, 'ST_TIDAK_BOLEH_DIHAPUS'); END;
CREATE TRIGGER IF NOT EXISTS trg_spd_kunci BEFORE UPDATE ON spd BEGIN SELECT RAISE(ABORT, 'SPD_TERKUNCI'); END;
CREATE TRIGGER IF NOT EXISTS trg_spd_nodel BEFORE DELETE ON spd BEGIN SELECT RAISE(ABORT, 'SPD_TIDAK_BOLEH_DIHAPUS'); END;
"""


SCHEMA_SPJ = """
-- Tahap 5: realisasi & SPJ (tanpa panjar; dibayar setelah SPJ diverifikasi). jenis SPD = perjalanan dinas (1 SPJ per petugas per SPD);
-- jenis UMUM = belanja lain pada baris RAB. Hanya SPJ berstatus Dibayar yang dihitung sebagai realisasi.
CREATE TABLE IF NOT EXISTS spj(
  id INTEGER PRIMARY KEY, jenis TEXT NOT NULL CHECK(jenis IN ('SPD','UMUM')), tahun INTEGER NOT NULL,
  sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id), baris_id INTEGER NOT NULL REFERENCES bok_baris(id),
  spd_id INTEGER UNIQUE REFERENCES spd(id), st_id INTEGER REFERENCES surat_tugas(id), pegawai_id INTEGER REFERENCES pegawai(id),
  tanggal TEXT NOT NULL, mulai TEXT, selesai TEXT, uraian TEXT NOT NULL, penerima TEXT,
  rincian_json TEXT NOT NULL DEFAULT '[]', total_rencana INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0 CHECK(total >= 0),
  status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft','Diajukan','Dikembalikan','Diverifikasi','Dibayar')),
  no_bukti TEXT, tanggal_bayar TEXT, catatan TEXT, alasan_kembali TEXT,
  dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')), diajukan_pada TEXT,
  diverifikasi_oleh TEXT, diverifikasi_pada TEXT, dibayar_oleh TEXT, dibayar_pada TEXT);
CREATE INDEX IF NOT EXISTS ix_spj_baris ON spj(baris_id, status);
CREATE INDEX IF NOT EXISTS ix_spj_sumber ON spj(tahun, sumber_dana_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_spj_bukti ON spj(sumber_dana_id, tahun, no_bukti) WHERE no_bukti IS NOT NULL;
-- SPJ yang sudah Dibayar tidak dapat diubah isinya (hanya status yang boleh dikoreksi Kepala lewat API) dan tidak dapat dihapus
CREATE TRIGGER IF NOT EXISTS trg_spj_kunci BEFORE UPDATE ON spj
WHEN OLD.status='Dibayar' AND NEW.status='Dibayar' BEGIN SELECT RAISE(ABORT, 'SPJ_TERKUNCI'); END;
CREATE TRIGGER IF NOT EXISTS trg_spj_nodel BEFORE DELETE ON spj WHEN OLD.status NOT IN ('Draft','Dikembalikan')
BEGIN SELECT RAISE(ABORT, 'SPJ_TIDAK_BOLEH_DIHAPUS'); END;
-- Foto/berkas bukti SPJ (disimpan di database agar ikut backup & pemulihan). Hanya boleh berubah saat SPJ Draft/Dikembalikan.
CREATE TABLE IF NOT EXISTS spj_bukti(
  id INTEGER PRIMARY KEY, spj_id INTEGER NOT NULL REFERENCES spj(id) ON DELETE CASCADE, nama TEXT NOT NULL, tipe TEXT NOT NULL,
  ukuran INTEGER NOT NULL, data BLOB NOT NULL, diunggah_oleh TEXT, diunggah_pada TEXT DEFAULT (datetime('now','localtime')));
CREATE INDEX IF NOT EXISTS ix_spj_bukti ON spj_bukti(spj_id);
CREATE TRIGGER IF NOT EXISTS trg_bukti_ins BEFORE INSERT ON spj_bukti
WHEN (SELECT status FROM spj WHERE id=NEW.spj_id) NOT IN ('Draft','Dikembalikan') BEGIN SELECT RAISE(ABORT, 'BUKTI_TERKUNCI'); END;
-- Dokumen FINAL hasil Srikandi (PDF bertanda tangan elektronik) per Surat Tugas; boleh diganti, selalu tercatat di audit.
CREATE TABLE IF NOT EXISTS st_final(
  id INTEGER PRIMARY KEY, st_id INTEGER NOT NULL UNIQUE REFERENCES surat_tugas(id), nama TEXT NOT NULL, ukuran INTEGER NOT NULL, data BLOB NOT NULL,
  nomor_terdeteksi TEXT, diunggah_oleh TEXT, diunggah_pada TEXT DEFAULT (datetime('now','localtime')));
CREATE TRIGGER IF NOT EXISTS trg_bukti_del BEFORE DELETE ON spj_bukti
WHEN (SELECT status FROM spj WHERE id=OLD.spj_id) NOT IN ('Draft','Dikembalikan') BEGIN SELECT RAISE(ABORT, 'BUKTI_TERKUNCI'); END;
"""


SCHEMA_AKUN = """
-- Tahap 6: akuntansi BLU (PSAP 13). Satu buku besar untuk semua sumber dana (laporan keuangan satu kesatuan).
-- lra: pemetaan akun non-beban/pendapatan ke LRA ('BELANJA_MODAL' = debit dihitung belanja modal; 'PEMBIAYAAN' = kredit penerimaan, debit pengeluaran pembiayaan).
CREATE TABLE IF NOT EXISTS akun(
  id INTEGER PRIMARY KEY, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL,
  jenis TEXT NOT NULL CHECK(jenis IN ('ASET','KEWAJIBAN','EKUITAS','PENDAPATAN','BEBAN')),
  normal TEXT NOT NULL CHECK(normal IN ('D','K')), kas INTEGER NOT NULL DEFAULT 0, arus TEXT NOT NULL DEFAULT 'OPERASI' CHECK(arus IN ('OPERASI','INVESTASI','PENDANAAN')),
  lra TEXT CHECK(lra IN ('BELANJA_MODAL','PEMBIAYAAN')), aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS jurnal(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, tanggal TEXT NOT NULL, no_bukti TEXT, uraian TEXT NOT NULL,
  basis TEXT NOT NULL CHECK(basis IN ('AWAL','KAS','AKRUAL')), sumber_dana_id INTEGER REFERENCES sumber_dana(id),
  ref_jenis TEXT, ref_id INTEGER, uraian_buku TEXT, dibuat_oleh TEXT, dibuat_pada TEXT DEFAULT (datetime('now','localtime')));
CREATE INDEX IF NOT EXISTS ix_jurnal_tahun ON jurnal(tahun, tanggal);
CREATE INDEX IF NOT EXISTS ix_jurnal_ref ON jurnal(ref_jenis, ref_id);
CREATE TABLE IF NOT EXISTS jurnal_baris(
  id INTEGER PRIMARY KEY, jurnal_id INTEGER NOT NULL REFERENCES jurnal(id) ON DELETE CASCADE, akun_id INTEGER NOT NULL REFERENCES akun(id), tempat TEXT, dana TEXT,
  debit INTEGER NOT NULL DEFAULT 0 CHECK(debit >= 0), kredit INTEGER NOT NULL DEFAULT 0 CHECK(kredit >= 0), CHECK(debit = 0 OR kredit = 0));
CREATE TABLE IF NOT EXISTS anggaran_pendapatan(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, akun_id INTEGER NOT NULL REFERENCES akun(id), jumlah INTEGER NOT NULL DEFAULT 0 CHECK(jumlah >= 0), UNIQUE(tahun, akun_id));
CREATE TABLE IF NOT EXISTS calk(tahun INTEGER NOT NULL, bagian TEXT NOT NULL, isi TEXT NOT NULL DEFAULT '', PRIMARY KEY(tahun, bagian));
"""

# (kode, nama, jenis, normal, kas, arus, lra)
AKUN_AWAL = [
    ("1.1.1.01", "Kas Bendahara Pengeluaran Pembantu — BOK", "ASET", "D", 1, "OPERASI", None),
    ("1.1.1.02", "Kas BLUD (Kas pada BLU)", "ASET", "D", 1, "OPERASI", None),
    ("1.1.1.03", "Kas Bendahara Penerimaan (Retribusi)", "ASET", "D", 1, "OPERASI", None),
    ("1.1.1.04", "Kas Bendahara Pengeluaran Pembantu — DAU", "ASET", "D", 1, "OPERASI", None),
    ("1.1.2.01", "Piutang Jasa Layanan", "ASET", "D", 0, "OPERASI", None),
    ("1.1.3.01", "Persediaan Obat dan BMHP", "ASET", "D", 0, "OPERASI", None),
    ("1.1.4.01", "Belanja Dibayar di Muka", "ASET", "D", 0, "OPERASI", None),
    ("1.3.2.01", "Peralatan dan Mesin", "ASET", "D", 0, "INVESTASI", "BELANJA_MODAL"),
    ("1.3.3.01", "Gedung dan Bangunan", "ASET", "D", 0, "INVESTASI", "BELANJA_MODAL"),
    ("1.3.9.01", "Akumulasi Penyusutan", "ASET", "K", 0, "OPERASI", None),
    ("2.1.1.01", "Utang Belanja", "KEWAJIBAN", "K", 0, "OPERASI", None),
    ("2.1.2.01", "Pendapatan Diterima di Muka", "KEWAJIBAN", "K", 0, "OPERASI", None),
    ("2.1.3.01", "Utang Jangka Pendek Lainnya", "KEWAJIBAN", "K", 0, "PENDANAAN", "PEMBIAYAAN"),
    ("3.1.1.01", "Ekuitas", "EKUITAS", "K", 0, "OPERASI", None),
    ("4.1.1.01", "Pendapatan Jasa Layanan dari Masyarakat", "PENDAPATAN", "K", 0, "OPERASI", None),
    ("4.1.1.02", "Pendapatan Jasa Layanan dari JKN (Kapitasi/Non-Kapitasi)", "PENDAPATAN", "K", 0, "OPERASI", None),
    ("4.2.1.01", "Pendapatan Transfer DAU", "PENDAPATAN", "K", 0, "OPERASI", None),
    ("4.2.2.01", "Pendapatan Transfer BOK (DAK Non Fisik)", "PENDAPATAN", "K", 0, "OPERASI", None),
    ("4.9.9.01", "Pendapatan Lain-lain", "PENDAPATAN", "K", 0, "OPERASI", None),
    ("5.1.1.01", "Belanja/Beban Pegawai dan Jasa Pelayanan", "BEBAN", "D", 0, "OPERASI", None),
    ("5.1.2.01", "Belanja/Beban Barang dan Jasa", "BEBAN", "D", 0, "OPERASI", None),
    ("5.1.2.02", "Belanja/Beban Perjalanan Dinas", "BEBAN", "D", 0, "OPERASI", None),
    ("5.1.2.03", "Belanja/Beban Obat dan BMHP", "BEBAN", "D", 0, "OPERASI", None),
    ("5.1.3.01", "Beban Penyusutan", "BEBAN", "D", 0, "OPERASI", None),
    ("5.1.9.01", "Beban Lain-lain", "BEBAN", "D", 0, "OPERASI", None),
]


PEJABAT_BKU = [
    ("Bendahara Pengeluaran Pembantu", "ANISA, A.Md.Kep", "199410102020122026", "", "Bendahara Pengeluaran Pembantu"),
    ("Bendahara Penerimaan", "SARI NINDIATI, Amd. Keb", "198910072011012004", "", "Bendahara Penerimaan"),
    ("Bendahara Dana Kapitasi/BLUD", "WARIE KRISTINA MIASIE, S.Kep.,Ns", "198601282011012008", "", "Bendahara Dana Kapitasi/BLUD"),
]


JENIS_NOMOR_AWAL = [
    ("ST-BOK", "Surat Tugas & SPD — BOK", "000.1.2.3", "PKM.MELATI.BOK", "000.1.2.3 = Perjalanan Dinas Pegawai (Permendagri 83/2022). Seri nomor khusus BOK."),
    ("ST-DAU", "Surat Tugas & SPD — DAU", "000.1.2.3", "PKM.MELATI.DAU", "Seri nomor khusus DAU."),
    ("ST-BLUD", "Surat Tugas & SPD — BLUD", "000.1.2.3", "PKM.MELATI.BLUD", "Seri nomor khusus BLUD (hanya Kepala & Bendahara BLUD)."),
    ("UMUM", "Surat Umum", "000", "PKM.MELATI", "000 = Umum. Klasifikasi rinci dapat diubah saat menerbitkan nomor."),
]

# Pengaturan yang ditambahkan setelah rilis awal (ditambahkan otomatis ke database lama)
PENGATURAN_BARU = [
    ("bku_skpd", "PUSKESMAS MELATI", "Nama SKPD pada Buku Kas Umum (BKU)"),
    ("format_bukti_spj", "{urut}/PKM.M/{tahun}", "Format nomor bukti pembayaran SPJ/BKU. Kode: {urut} {tahun} {sumber}"),
    ("kepala_wajib", "0", "1 = rencana/jadwal harus disetujui Kepala; 0 (bawaan) = persetujuan Kepala opsional, pembuat surat/penjadwalan dapat mengotorisasi sendiri (tercatat di riwayat)"),
    ("spj_setelah_selesai", "1", "1 = SPJ perjalanan dinas baru boleh diajukan setelah tanggal selesai kegiatan; 0 = boleh kapan saja"),
    ("batas_persen_ruangan", "50", "Maks. % pegawai satu ruangan yang boleh meninggalkan ruangan (dinas luar/cuti) pada hari yang sama"),
    ("ruangan_hitung_cuti", "1", "1 = pegawai cuti dihitung sebagai tidak berada di ruangan; 0 = hanya dinas luar yang dihitung"),
    ("format_nomor_spd", "{no}/SPD/PKM-MLT/{bulan_romawi}/{tahun}", "Format nomor Surat Perjalanan Dinas"),
    ("kota_surat", "Kuala Kapuas", "Kota pada penandatanganan surat"),
    ("tempat_berangkat", "UPT Puskesmas Melati", "Tempat berangkat pada SPD"),
    ("kop_jalan", "Melati No 18 Kecamatan Selat,", "Kop (template Srikandi): isian setelah 'Jalan'"),
    ("kop_kodepos", "73514", "Kop (template Srikandi): kode pos"),
    ("kop_laman", "pkmmelati.com", "Kop (template Srikandi): laman"),
    ("kop_email", "puskesmasmelati2016@gmail.com", "Kop (template Srikandi): pos-el"),
    ("dasar_st_default", "Peraturan Bupati Kapuas Nomor 8 Tahun 2026 Tanggal 30 April 2026 Tentang Perjalanan Dinas", "Dasar pada Surat Tugas"),
    ("nomor_dpa", "DPA/A.1/1.02.0.00.0.00.02.0000/001/2026", "Nomor DPA untuk 'Pembebanan Biaya' pada Surat Tugas"),
    ("anggaran_instansi", "1.02.0.00.0.00.02.0003|Puskesmas Melati", "SPD: kode|nama instansi"),
    ("anggaran_program", "1.02.02|Pemenuhan Upaya Kesehatan Perorangan dan Upaya Kesehatan Masyarakat\n1.02.02.2.02|Penyediaan Layanan Kesehatan Untuk UKM dan UKP Rujukan Tingkat Daerah Kabupaten/Kota", "SPD: program (satu baris 'kode|nama' per baris)"),
    ("anggaran_kegiatan", "1.02.02.2.02.0033|Operasional Pelayanan Puskesmas", "SPD: kode|nama kegiatan"),
    ("anggaran_rekening", "5.1.02.04.01.0001|Belanja Perjalanan Dinas Biasa", "SPD: kode|nama rekening belanja"),
]


SCHEMA_USERS = """CREATE TABLE users(
  id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  nama TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('kepala','bendahara','bendahara_blud','program','pembuat_surat','pegawai')),
  pegawai_id INTEGER REFERENCES pegawai(id), aktif INTEGER NOT NULL DEFAULT 1);"""
SCHEMA_BOK_PAGU = """CREATE TABLE bok_pagu(
  id INTEGER PRIMARY KEY, tahun INTEGER NOT NULL, sumber_dana_id INTEGER NOT NULL REFERENCES sumber_dana(id),
  jenis TEXT NOT NULL DEFAULT 'Pagu Indikatif', pagu INTEGER NOT NULL DEFAULT 0 CHECK(pagu >= 0), keterangan TEXT,
  UNIQUE(tahun, sumber_dana_id));"""


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
    con.executescript(SCHEMA_SPJ)
    con.executescript(SCHEMA_AKUN)
    for a in AKUN_AWAL:
        con.execute("INSERT OR IGNORE INTO akun(kode,nama,jenis,normal,kas,arus,lra) VALUES(?,?,?,?,?,?,?)", a)
    # Migrasi database lama: pagu & menu RAB kini per sumber dana (data lama = BOK)
    bok = (con.execute("SELECT id FROM sumber_dana WHERE kode='BOK'").fetchone() or {}).get("id")
    if "sumber_dana_id" not in {r["name"] for r in con.execute("PRAGMA table_info(bok_pagu)").fetchall()}:
        con.executescript("ALTER TABLE bok_pagu RENAME TO bok_pagu_lama;" + SCHEMA_BOK_PAGU)
        con.execute("INSERT INTO bok_pagu(id,tahun,sumber_dana_id,jenis,pagu,keterangan) SELECT id,tahun,?,jenis,pagu,keterangan FROM bok_pagu_lama", (bok or 2,))
        con.execute("DROP TABLE bok_pagu_lama")
    if "sumber_dana_id" not in {r["name"] for r in con.execute("PRAGMA table_info(bok_menu)").fetchall()}:
        con.execute("ALTER TABLE bok_menu ADD COLUMN sumber_dana_id INTEGER REFERENCES sumber_dana(id)")
    if bok:
        con.execute("UPDATE bok_menu SET sumber_dana_id=? WHERE sumber_dana_id IS NULL", (bok,))
    con.execute("CREATE INDEX IF NOT EXISTS ix_bok_menu_sumber ON bok_menu(tahun, sumber_dana_id)")
    # Migrasi: peran 'bendahara_blud' (tabel users dibuat ulang karena CHECK tidak bisa diubah) & kolom audit_log.sumber
    sql_users = (con.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone() or {}).get("sql") or ""
    if sql_users and "pembuat_surat" not in sql_users:
        con.execute("PRAGMA foreign_keys=OFF")
        con.executescript("ALTER TABLE users RENAME TO users_lama;" + SCHEMA_USERS)
        con.execute("INSERT INTO users(id,username,password_hash,nama,role,pegawai_id,aktif) SELECT id,username,password_hash,nama,role,pegawai_id,aktif FROM users_lama")
        con.execute("DROP TABLE users_lama")
        con.execute("PRAGMA foreign_keys=ON")
    if "sumber" not in {r["name"] for r in con.execute("PRAGMA table_info(audit_log)").fetchall()}:
        con.execute("ALTER TABLE audit_log ADD COLUMN sumber TEXT")
        con.execute("UPDATE audit_log SET sumber='BLUD' WHERE tabel IN ('bok_menu','bok_rincian','bok_baris','bok_pagu','rencana','jadwal') AND (data_lama LIKE '%BLUD%' OR data_baru LIKE '%BLUD%')")
    # Migrasi: seri nomor ST per jenis (tabel surat_tugas dibuat ulang bila masih kosong)
    st_sql = (con.execute("SELECT sql FROM sqlite_master WHERE name='surat_tugas'").fetchone() or {}).get("sql") or ""
    if st_sql and "jenis_nomor" not in st_sql:
        if con.execute("SELECT COUNT(*) c FROM surat_tugas").fetchone()["c"] == 0:
            con.executescript("DROP TRIGGER IF EXISTS trg_spd_kunci; DROP TRIGGER IF EXISTS trg_spd_nodel; DROP TABLE IF EXISTS spd; "
                              "DROP TRIGGER IF EXISTS trg_st_kunci; DROP TRIGGER IF EXISTS trg_st_noskd; DROP TRIGGER IF EXISTS trg_st_final; DROP TRIGGER IF EXISTS trg_st_nodel; DROP TABLE surat_tugas;")
            con.executescript(SCHEMA)
        else:
            raise RuntimeError("Tabel surat_tugas berisi data dengan skema lama; migrasi manual diperlukan.")
    for kode, nama, klas, unit, ket in JENIS_NOMOR_AWAL:
        con.execute("INSERT OR IGNORE INTO jenis_nomor(kode,nama,klasifikasi,unit,keterangan) VALUES(?,?,?,?,?)", (kode, nama, klas, unit, ket))
    # Migrasi Tahap 4 (spd versi awal per-petugas bernomor sendiri, belum berisi data): buat ulang bila masih kosong
    spd_sql = (con.execute("SELECT sql FROM sqlite_master WHERE name='spd'").fetchone() or {}).get("sql") or ""
    if "nomor_urut" in spd_sql and con.execute("SELECT COUNT(*) c FROM spd").fetchone()["c"] == 0:
        con.executescript("DROP TRIGGER IF EXISTS trg_spd_kunci; DROP TRIGGER IF EXISTS trg_spd_nodel; DROP TABLE spd;")
        con.executescript(SCHEMA)
    kolom_st = {r["name"] for r in con.execute("PRAGMA table_info(surat_tugas)").fetchall()}
    for kol in ("srikandi_diunggah_pada", "srikandi_diunggah_oleh"):
        if kol not in kolom_st:
            con.execute(f"ALTER TABLE surat_tugas ADD COLUMN {kol} TEXT")
    if con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] and not con.execute("SELECT 1 FROM users WHERE username='pembuat_surat'").fetchone():
        con.execute("INSERT INTO users(username,password_hash,nama,role,pegawai_id) VALUES(?,?,?,?,?)", ("pembuat_surat", hash_password(os.environ.get("SIKADIN_ADMIN_PASSWORD") or "sikadin2026"), "Pembuat Surat (ganti nama)", "pembuat_surat", None))
    if "nomor_srikandi" not in {r["name"] for r in con.execute("PRAGMA table_info(surat_tugas)").fetchall()}:
        con.execute("ALTER TABLE surat_tugas ADD COLUMN nomor_srikandi TEXT")
        con.executescript(SCHEMA)
    # Migrasi database lama: kolom baru pada tabel pegawai
    ada = {r["name"] for r in con.execute("PRAGMA table_info(pegawai)").fetchall()}
    for kol in ("ruangan", "telepon"):
        if kol not in ada:
            con.execute(f"ALTER TABLE pegawai ADD COLUMN {kol} TEXT")
    if con.execute("SELECT COUNT(*) c FROM pegawai").fetchone()["c"] == 0:
        _seed(con)
    kol_j = {r["name"] for r in con.execute("PRAGMA table_info(jurnal)").fetchall()}
    if kol_j and "uraian_buku" not in kol_j:
        con.execute("ALTER TABLE jurnal ADD COLUMN uraian_buku TEXT")
    kol_b = {r["name"] for r in con.execute("PRAGMA table_info(jurnal_baris)").fetchall()}
    for kol in ("tempat", "dana"):
        if kol_b and kol not in kol_b:
            con.execute(f"ALTER TABLE jurnal_baris ADD COLUMN {kol} TEXT")
    con.execute("UPDATE akun SET nama='Kas Bendahara Pengeluaran Pembantu — BOK' WHERE kode='1.1.1.01' AND nama LIKE 'Kas di Bendahara Pengeluaran%'")
    # Pejabat pembuat BKU (data dari contoh BKU Agustus 2026); ditambahkan bila belum ada
    for peran, nama, nip, pangkat, jabatan in PEJABAT_BKU:
        if con.execute("SELECT COUNT(*) c FROM pejabat").fetchone()["c"] and not con.execute("SELECT 1 FROM pejabat WHERE peran=?", (peran,)).fetchone():
            con.execute("INSERT INTO pejabat(peran,nama,nip,pangkat,jabatan) VALUES(?,?,?,?,?)", (peran, nama, nip, pangkat, jabatan))
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
        ("panjar_maks_persen", "80", "(Tidak dipakai: fitur panjar dibatalkan oleh pemilik)"),
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
                       ("bendahara_blud", "Bendahara BLUD (ganti nama)", "bendahara_blud", None),
                       ("program", "Agus Prasetyo, SKM", "program", 4), ("pembuat_surat", "Pembuat Surat (ganti nama)", "pembuat_surat", None),
                       ("pegawai", "Budi Santoso, S.Kep", "pegawai", 2)]:
        con.execute("INSERT INTO users(username,password_hash,nama,role,pegawai_id) VALUES(?,?,?,?,?)", (u, hash_password(pw), n, r, p))
