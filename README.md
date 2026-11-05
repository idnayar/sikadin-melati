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
- [x] 4. ST/SPD (templat Srikandi) + penomoran  - [ ] 5. Realisasi & SPJ (tanpa panjar — diputuskan pemilik)
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

## Surat Tugas & SPD (Tahap 4)
Dibuat dari **jadwal yang sudah disetujui** (menu Surat Tugas & SPD). Satu ST + satu SPD per jadwal; tarif per petugas dari Perbup (terkunci).
- **Ekspor Srikandi (.docx):** mengisi templat resmi *Surat Tugas dan SPD OPD (2 Tandatangan)* (`backend/app/assets/templat_st_spd_srikandi.docx`).
  Hanya titik-titik isian yang diisi; kode Srikandi dibiarkan utuh agar diisi saat TTE:
  `${nomor_naskah} ${tanggal_naskah} ${ttd_pengirim2} ${nama_pengirim2} ${pangkat_pengirim2} ${nip_pengirim2}` (Kepala) dan
  `${ttd_pengirim1} ${nama_pengirim1} ${nip_pengirim1}` (PPTK).
- **Satu halaman:** tanda tangan ST dan SPD tidak boleh pindah halaman. Ukuran font dipadatkan otomatis sesuai jumlah petugas; ST yang tak muat
  satu halaman (≈ >9 petugas) ditolak agar dipecah. Berlaku untuk DOCX dan PDF pratinjau.
- **Terkunci:** setelah terbit isi ST/SPD tidak bisa diubah (trigger database); perubahan hanya lewat **Batalkan** + terbit ulang (nomor baru, riwayat tersimpan).
- Dokumen PDF lain: rincian biaya, kuitansi, daftar hadir, daftar pengeluaran riil, surat pernyataan pembatalan & pengembalian biaya.
- Petugas melihat ST/SPD/rincian miliknya sendiri; dokumen BLUD mengikuti batas akses BLUD.

## Realisasi & SPJ (Tahap 5, tanpa panjar)
- Alur: **Draft → Diajukan → Diverifikasi → Dibayar** (atau *Dikembalikan* dengan alasan). Pembayaran dicatat setelah SPJ diverifikasi; hanya SPJ *Dibayar* dihitung sebagai realisasi.
- **SPJ perjalanan dinas** lahir dari SPD pada ST yang terbit (satu per petugas). Realisasi per komponen tidak boleh melebihi tarif SPD (Perbup); boleh lebih rendah. Pengajuan baru boleh setelah kegiatan selesai (pengaturan `spj_setelah_selesai`) dan perlu nomor bukti.
- **Belanja non-perjalanan** (jenis UMUM) dicatat per baris RAB oleh Kepala/Bendahara/Pengelola Program.
- Total dibayar per baris RAB tidak boleh melebihi pagu baris. Nomor bukti otomatis `BP/{SUMBER}/{tahun}/{urut}`.
- SPJ Dibayar terkunci (juga di database); hanya Kepala dapat mengoreksi pembayaran (alasan wajib, tercatat di audit).
- Petugas hanya melihat/mengisi SPJ miliknya. BLUD hanya Kepala + Bendahara BLUD. Menu **Realisasi & SPJ** memuat tab Realisasi anggaran (pagu, proses, realisasi, sisa, serapan per menu/rincian/baris).
- Ekspor: bukti SPJ (PDF/DOCX), rekap SPJ dibayar per sumber/bulan (PDF/DOCX/XLSX).

## Surat dalam satu modul, Kepala opsional (Tahap 4–5 disederhanakan)
- Menu **Surat** memuat tiga tab: *Surat Tugas & SPD*, *Siap diterbitkan* (dengan **terbit massal** berisian bawaan), dan *Nomor surat umum & kode*.
- **Persetujuan Kepala opsional** (pengaturan `kepala_wajib`, bawaan 0). Pembuat surat (Pengelola Program/Bendahara/Kepala; BLUD hanya Kepala + Bendahara BLUD) menyetujui rencana & jadwalnya sendiri dan mengotorisasi ST saat menerbitkan; semuanya tercatat di riwayat. Set `kepala_wajib` = 1 untuk mewajibkan persetujuan Kepala.
- **ST terbit → SPJ otomatis** (satu draft per petugas) dan tersambung ke realisasi belanja: daftar ST menampilkan status SPJ & nilai dibayar; pembatalan ST menghapus SPJ draft dan **ditolak** bila ada SPJ diajukan/dibayar.

## Rekap perjalanan dinas
Menu *Rekap Perjalanan Dinas*: per nama, tempat, waktu, tujuan, biaya (SPD) dan realisasi (SPJ dibayar) — setahun & per bulan; filter bulan/sumber/pegawai/tempat/teks; ekspor PDF/DOCX/XLSX. Pegawai hanya melihat miliknya; BLUD tetap terbatas.

## Akuntansi & Laporan Keuangan (Tahap 6, PSAP 13)
- Buku besar satu kesatuan (DAU, BOK, BLUD): bagan akun, jurnal (KAS/AKRUAL/AWAL), saldo awal, anggaran pendapatan. **Hanya Kepala + Bendahara BLUD.**
- SPJ dibayar otomatis menjadi jurnal kas (Dr belanja / Cr kas); koreksi pembayaran membuat jurnal balik. Penerimaan pendapatan dicatat lewat menu (Dr kas / Cr pendapatan).
- Tujuh laporan: LRA, L-SAL, Neraca, LO, LAK (metode langsung), LPE, CaLK, dengan kolom tahun lalu pada LRA/LO/Neraca; pemeriksaan integritas (jurnal seimbang, Neraca seimbang, LPE = Neraca). Ekspor PDF/DOCX/XLSX.
- LRA/LAK berbasis kas (jurnal KAS); LO/Neraca/LPE dari semua jurnal. Anggaran belanja LRA = total RAB per jenis belanja.

## Penomoran surat
Pola mengikuti contoh Srikandi: `klasifikasi/yymm-urut/unit/bulan-romawi/tahun`, mis. `000.1.2.3/2611-001/PKM.MELATI.BOK/XI/2026`.
Klasifikasi arsip: Permendagri 83/2022 (000.1.2.3 = Perjalanan Dinas Pegawai; 000 = Umum); tata naskah: Permendagri 1/2023.
**Seri terpisah** untuk `ST-BOK`, `ST-DAU`, `ST-BLUD`, dan `UMUM` (kode unit berbeda: `.BOK`, `.DAU`, `.BLUD`); nomor tak dipakai ulang.
Kode dapat diubah Kepala di menu Penomoran Surat. Nomor resmi ST diberikan Srikandi; nomor SIKADIN adalah nomor registri/internal
dan nomor Srikandi dicatat sekali setelah TTE.

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
