# SIKADIN — Sistem Informasi Keuangan & Dinas Luar
UPT Puskesmas Melati, Kec. Selat, Kab. Kapuas, Kalteng. Dasar biaya: Perbup Kapuas No. 8 Tahun 2026.

## Menjalankan
Butuh Node.js >= 22.5 (memakai `node:sqlite` bawaan, tanpa instalasi database).
```
cd sikadin
npm install
npm start          # http://localhost:3100  (ubah dengan PORT=...)
```
Database: `data/sikadin.db` (dibuat & diisi data contoh otomatis saat pertama jalan).
Untuk mengulang dari awal: hentikan server, hapus folder `data/`.

## Akun contoh (GANTI lewat tombol "Ganti password")
Username: `kepala`, `bendahara`, `program`, `pegawai` — password awal tertulis di `server/db.js` (bagian "Akun demo").

## Status tahap
- [x] 1. Master data & tarif Perbup (pegawai + tingkat otomatis, sumber dana, pagu, lokasi, tarif, pejabat,
      pengaturan/kop, libur, cuti, pengguna, riwayat perubahan, impor/ekspor Excel, backup, kalkulator biaya)
- [x] 2. Perencanaan BOK (RPK/POA)  - [ ] 3. Jadwal + anti-doubling  - [ ] 4. ST/SPD
- [ ] 5. Panjar & SPJ  - [ ] 6. Rekap & laporan  - [ ] 7. Dashboard

## Catatan teknis
- Semua tarif ada di tabel `tarif` (kolom `tahun_berlaku`, `dasar_hukum`); tidak ada angka tarif di kode.
- Skema memakai SQL standar; pindah ke PostgreSQL/Supabase cukup mengganti tipe `INTEGER PRIMARY KEY` → `bigserial`
  dan fungsi tanggal. Constraint anti-doubling (tahap 3) ditulis sebagai `UNIQUE(pegawai_id, tanggal)` di
  tabel rincian harian penugasan.
