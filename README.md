# SIKADIN — Sistem Informasi Keuangan & Dinas Luar
UPT Puskesmas Melati, Kec. Selat, Kab. Kapuas, Kalteng. Dasar biaya: Perbup Kapuas No. 8 Tahun 2026.

**Arsitektur:** backend **Python (FastAPI + SQLite)** di `backend/`, frontend **Node.js (Vite)** di `frontend/`.

## Menjalankan (pengembangan)
Butuh Python >= 3.11 dan Node.js >= 20.
```
# 1) Backend — terminal pertama
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Linux/Mac: .venv/bin/pip
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 2) Frontend — terminal kedua
cd frontend
npm install
npm run dev                                          # buka http://localhost:5173
```
Database `data/sikadin.db` dibuat & diisi data contoh otomatis saat backend pertama jalan
(hapus folder `data/` untuk mengulang dari awal).

## Produksi (satu alamat, mis. sikadin.pkmmelati.com)
```
cd frontend && npm run build        # menghasilkan frontend/dist
cd ../backend
set SIKADIN_COOKIE_SECURE=1         # wajib bila lewat HTTPS
set SIKADIN_ADMIN_PASSWORD=...      # password awal akun (hanya berlaku saat database baru dibuat)
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
FastAPI otomatis menyajikan `frontend/dist`. Pasang di belakang reverse proxy HTTPS (Nginx/Caddy).
Variabel lain: `SIKADIN_DB` (lokasi file database), `SIKADIN_DIST` (lokasi build frontend).

## Akun contoh (GANTI lewat tombol "Ganti password")
`kepala`, `bendahara`, `program`, `pegawai` — password awal ada di `backend/app/db.py` (bagian akun demo).

## Status tahap
- [x] 1. Master data & tarif Perbup
- [x] 2. Pagu & RAB BOK 2027, Perencanaan BOK (RPK/POA)
- [x] 3. Jadwal dinas luar + anti-doubling (kalender, bagi petugas otomatis, constraint DB)
- [ ] 4. ST/SPD (format Srikandi)  - [ ] 5. Panjar & SPJ
- [ ] 6. Rekap & laporan  - [ ] 7. Dashboard  - [ ] DAU/BLUD

## Catatan teknis
- Semua tarif ada di tabel `tarif` (`tahun_berlaku`, `dasar_hukum`); tidak ada angka tarif di kode.
- Skema SQL standar; pindah ke PostgreSQL/Supabase cukup mengganti `INTEGER PRIMARY KEY` → `bigserial` dan fungsi tanggal.
  Constraint anti-doubling (tahap 3): `UNIQUE(pegawai_id, tanggal)` pada tabel rincian harian penugasan.
- Kontrak API (`/api/...`) sama dengan versi Node sebelumnya, jadi UI tidak berubah.

## Sumber dana & hak akses (BOK / DAU / BLUD)
Pagu, RAB (menu → rincian → baris), perencanaan, dan jadwal disusun **per sumber dana**; menunya sama untuk BOK, DAU, dan BLUD.

| Peran | BOK / DAU | BLUD |
|---|---|---|
| Kepala Puskesmas | semua | semua |
| Bendahara (BOK/DAU) | pagu, RAB, rencana | **tidak ada akses** |
| Bendahara BLUD | hanya lihat | pagu, RAB, rencana |
| Pengelola Program | rencana & jadwal | **tidak ada akses** |
| Pegawai | jadwal sendiri | jadwal sendiri |

Pembatasan BLUD dijaga di server (bukan hanya menyembunyikan menu): pagu/RAB/rencana BLUD, riwayat perubahan BLUD, dan
ekspor riwayat tidak terlihat oleh yang tak berwenang. Backup database hanya untuk Kepala. Pada **jadwal**, kegiatan BLUD tetap
muncul di kalender sebagai "Kegiatan BLUD (terbatas)" (tanggal, lokasi, petugas terlihat agar tidak bentrok; isi/anggaran tersembunyi).
Aturan anti-doubling berlaku **lintas sumber dana** (satu pegawai tidak bisa ditugaskan dua kali pada tanggal sama).

**Laporan keuangan tetap satu kesatuan** (semua sumber dana dalam satu laporan, ketujuh komponen PSAP 13). Siapa yang boleh melihat laporan
gabungan yang memuat angka BLUD: **keputusan pemilik — hanya Kepala Puskesmas dan Bendahara BLUD**; peran lain tidak mengakses laporan gabungan (diterapkan di Tahap 6).

## Catatan standar akuntansi (Tahap 6)
Laporan keuangan harus mengikuti **PSAP Nomor 13 — Penyajian Laporan Keuangan Badan Layanan Umum**
(PMK 217/PMK.05/2015). Komponennya ada tujuh: Laporan Realisasi Anggaran, Laporan Perubahan Saldo Anggaran Lebih,
Neraca, Laporan Operasional, Laporan Arus Kas, Laporan Perubahan Ekuitas, dan Catatan atas Laporan Keuangan.
Neraca/LO/LAK/LPE memerlukan data di luar perjalanan dinas (kas, pendapatan BLUD, persediaan, aset tetap, utang).
**Keputusan pemilik (2026-11-05): laporan mencakup ketujuh komponen dan semua sumber anggaran (DAU, BOK, BLUD).**
Dikerjakan setelah penjadwalan/ST/SPJ; perlu saldo awal dari bendahara/akuntan.

## Aturan penjadwalan (Tahap 3)
Divalidasi di server dan dikunci constraint database: (a) satu pegawai satu penugasan per tanggal (juga mencegah uang harian ganda
lintas sumber dana), (b) kegiatan + lokasi + tanggal tidak boleh dobel, (c) bukan hari libur/cuti, (d) satu ruangan tidak
ditinggal lebih dari 50% pegawainya per hari (`batas_persen_ruangan` di Pengaturan; cuti ikut dihitung bila `ruangan_hitung_cuti`=1),
(e) peringatan bila hari dinas luar sebulan melebihi batas. **Generate jadwal bulanan** menyusun usulan untuk semua rencana
yang disetujui pada bulan itu dengan aturan yang sama + pemerataan beban; hasilnya pratinjau dulu, lalu disimpan sebagai usulan.

## Identitas visual
Lambang Kabupaten Kapuas dan logo UPT Puskesmas Melati ada di `frontend/public/brand/` (berkas milik Puskesmas).
