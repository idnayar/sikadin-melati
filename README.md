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

## Produksi (sikadin.pkmmelati.com)
Render + cPanel: [`deploy/PANDUAN-RENDER-CPANEL.md`](deploy/PANDUAN-RENDER-CPANEL.md) (`render.yaml`, `Dockerfile.render`; wajib paket berbayar + disk). Server sendiri (VPS): [`deploy/PANDUAN-PENAYANGAN.md`](deploy/PANDUAN-PENAYANGAN.md) (Docker + Caddy, atau systemd; backup harian; tautan landing page).
Ringkas: `SIKADIN_ENV=production` mewajibkan sandi demo diganti (`python -m app.admin sandi-acak`), mengaktifkan cookie HTTPS & header keamanan.
Perintah admin: `python -m app.admin cek-sandi-demo | sandi-acak | atur-sandi USER | backup`. `SIKADIN_ADMIN_PASSWORD` (≥10 karakter) di mode produksi otomatis mengganti sandi demo pada akun mana pun, termasuk setelah pemulihan database (menu Backup & Ekspor → Pulihkan, hanya Kepala). Variabel: `SIKADIN_DB`, `SIKADIN_DIST`, `SIKADIN_ENV`, `SIKADIN_ADMIN_PASSWORD` (sandi awal hanya untuk database baru).

## Akun contoh (GANTI lewat tombol "Ganti password")
`kepala`, `bendahara`, `program`, `pegawai` — password awal ada di `backend/app/db.py` (bagian akun demo).

## Status tahap
- [x] 1. Master data & tarif Perbup
- [x] 2. Pagu & RAB BOK 2027, Perencanaan BOK (RPK/POA)
- [x] 3. Jadwal dinas luar + anti-doubling (kalender, bagi petugas otomatis, constraint DB)
- [x] 4. ST/SPD (templat Srikandi) + penomoran  - [x] 5. Realisasi & SPJ (tanpa panjar)
- [x] 6. Rekap perjalanan dinas & laporan keuangan PSAP 13  - [x] 7. Dashboard  - [x] DAU/BLUD per sumber dana

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
- **Persetujuan Kepala opsional** (pengaturan `kepala_wajib`, bawaan 0; bila 1, penyetuju = Kepala + Pembuat Surat). Pembuat surat (Pengelola Program/Bendahara/Kepala; BLUD hanya Kepala + Bendahara BLUD) menyetujui rencana & jadwalnya sendiri dan mengotorisasi ST saat menerbitkan; semuanya tercatat di riwayat. Set `kepala_wajib` = 1 untuk mewajibkan persetujuan Kepala.
- **ST terbit → SPJ otomatis** (satu draft per petugas) dan tersambung ke realisasi belanja: daftar ST menampilkan status SPJ & nilai dibayar; pembatalan ST menghapus SPJ draft dan **ditolak** bila ada SPJ diajukan/dibayar.

## Rekap perjalanan dinas
Menu *Rekap Perjalanan Dinas*: per nama, tempat, waktu, tujuan, biaya (SPD) dan realisasi (SPJ dibayar) — setahun & per bulan; filter bulan/sumber/pegawai/tempat/teks; ekspor PDF/DOCX/XLSX. Pegawai hanya melihat miliknya; BLUD tetap terbatas.

## Pembuat Surat Tugas, foto bukti SPJ, penyelesaian di Srikandi
- Peran **pembuat_surat** (hak istimewa): membuat surat sesuai pagu **BOK, DAU, dan BLUD**, dari rencana/jadwal sendiri atau **usulan Pengelola Program**, dan **menyetujuinya** (selalu boleh, termasuk saat `kepala_wajib`=1; jadwal Diusulkan otomatis disetujui saat ST terbit). Hak BLUD dibatasi pada alur surat (RAB baca, rencana, jadwal, ST): **tanpa data uang BLUD** (SPJ, realisasi, serapan, riwayat, laporan) — lihat `akses_uang` di `core.py`. Tidak dapat mengubah RAB/pagu atau memverifikasi/membayar SPJ. Menu: Dashboard, Perencanaan, Jadwal, Surat, Rekap, Kalkulator. Akun `pembuat_surat` ditambahkan otomatis (ganti nama & sandi).
- **Alur ST sampai selesai:** terbit → unduh DOCX → *Tandai sudah diunggah ke Srikandi* → *Unggah PDF hasil Srikandi* (nomor naskah dibaca otomatis dari PDF; pengguna mengonfirmasi) → progres **Selesai di Srikandi** (3/3). PDF final disimpan di database (`st_final`), boleh diganti (tercatat di riwayat).
- **Foto bukti SPJ:** unggah dari kamera/galeri (dikecilkan di browser), maks. 8 berkas × 4 MB per SPJ, hanya JPG/PNG/WebP/PDF (diperiksa isinya), terkunci setelah diajukan (juga di DB), ikut sebagai lampiran PDF SPJ, ikut backup & pemulihan.

## Buku Kas Umum (BKU) — format Puskesmas Melati
Menu *Buku Kas Umum*: empat buku, **bulanan dan tahunan**, ekspor PDF/DOCX/XLSX, formatnya mengikuti contoh BKU Agustus 2026:
- **BOK** dan **DAU** — BKU Bendahara Pengeluaran Pembantu (No Urut · Tanggal · Kode Rekening/Bukti · Uraian · Penerimaan · Pengeluaran; Saldo Awal; jumlah bulan ini / s.d. bulan lalu / sisa; tanda tangan KPA + Bendahara Pembantu).
- **Retribusi** — BKU Bendahara Penerimaan (judul Pemerintah Kabupaten, kolom bernomor, sisa kas NIHIL, baris Qris dengan penerimaan = pengeluaran, setor ke BLUD).
- **BLUD** — Buku Kas Bendahara Dana BLUD (Pendapatan · Belanja · Saldo; no. bukti `n/BKU/D|K`; rincian saldo: Bank per JKN Kapitasi/Non Kapitasi/Pelayanan Umum, Kas JKN, Kas Lain-lain, Panjar).
Setiap baris = satu jurnal kas. **Pembayaran SPJ otomatis masuk** (bukti `{urut}/PKM.M/{tahun}`, uraian "Pembayaran … An. …"; format di pengaturan `format_bukti_spj`). Transaksi lain dicatat lewat *+ Catat transaksi* (penerimaan, pengeluaran, setor/pindah antar buku, terima-lalu-teruskan seperti Qris). Saldo awal kas diisi per buku (BLUD dapat dirinci). Akses: Kepala semua; Bendahara BOK/DAU; Bendahara BLUD BLUD & Retribusi (BOK/DAU hanya baca). Akun kas: 1.1.1.01 BOK, 1.1.1.04 DAU, 1.1.1.02 BLUD, 1.1.1.03 Retribusi. Pejabat BKU di menu Pejabat.
- **Ekspor Srikandi**: DOCX (templat resmi) **dan PDF** (ST + SPD memuat kode `${nomor_naskah}`, `${ttd_pengirim}`, `${nama_pengirim}` (satu kode QR di kolom kanan, diberi ruang kosong agar QR Srikandi tidak menimpa teks)).

## Laporan Keuangan — format resmi Puskesmas Melati (menggantikan 7 komponen sebagai laporan utama)
Menu *Akuntansi & Laporan Keuangan → Laporan Puskesmas Melati* mengikuti **Laporan Keuangan BLUD Semester 1 2026** Puskesmas Melati: sampul, daftar isi, pengantar, SPTJM, **LRA** (kode rekening BAS, kolom Anggaran · Realisasi · % · Realisasi tahun lalu), **Neraca**, **Laporan Operasional**, **LPE**, dan **CaLK Bab I–VII**; plus **LRA BLUD** (F-07). Periode: Semester 1, tahunan, atau s.d. bulan apa pun. Ekspor PDF/DOCX/XLSX.
- Mengikuti contoh: LRA SKPD dan LO memuat belanja/beban saja; Surplus/Defisit = −belanja; **RK PPKD** = penyeimbang ekuitas (Aset − Kewajiban − Ekuitas awal − Surplus/Defisit-LO). Angka berformat `1.234.567,00`, negatif `( … )`.
- Kode rekening BAS dipetakan per akun (`kode_bas`) dan ditebak dari jenis belanja RAB + sumber dana: BLUD → `5.1.02.99.099`; perjalanan dinas → `5.1.02.04.001`; barang pakai habis → `5.1.02.01.001`; jasa kantor → `5.1.02.02.001`; pemeliharaan → `5.1.02.03.003`; modal BLUD → `5.2.02.99.099`; kas: BOK `1.1.01.11.001`, DAU `1.1.01.03.001`, BLUD `1.1.01.04.001`, Retribusi `1.1.01.02.001`, Lainnya `1.1.01.07.001`. **Kode di luar contoh Anda belum terverifikasi** — periksa tabel akun.
- Kolom tahun lalu: otomatis dari jurnal SIKADIN tahun lalu; bila belum ada, isi di tab *Data tahun lalu*. Teks Pengantar/SPTJM/CaLK diambil dari contoh dan dapat disunting (tab *CaLK & Pengantar*); angka Bab III dan Bab V dihitung otomatis.
- LAK dan L-SAL **tidak ada** dalam laporan resmi Puskesmas Melati; tetap tersedia di tab *Laporan PSAP 13 (tambahan)*.

## Dashboard (Tahap 7)
Beranda per peran (`/api/dashboard`): kartu pagu/realisasi/proses/sisa/serapan, daftar **pekerjaan yang menunggu** (rencana & jadwal belum disetujui, jadwal siap ST, ST belum bernomor Srikandi, SPJ untuk dilengkapi/diverifikasi/dibayar — tiap tombol langsung membuka menunya), peringatan (baris RAB ≥ 90% atau melebihi pagu, pegawai melebihi batas hari dinas, serapan jauh di bawah target), serapan per sumber, grafik rencana vs realisasi per bulan, jadwal 14 hari ke depan, ringkasan keuangan (hanya Kepala + Bendahara BLUD). Pegawai melihat perjalanan mendatang dan status SPJ miliknya. Semua angka mengikuti hak akses sumber dana (BLUD terisolasi). Tahun ST/SPJ mengikuti **tahun anggaran jadwal**, bukan tahun tanggal surat.

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

## Database kode surat (klasifikasi arsip)
Menu *Surat → Nomor surat umum & kode* memuat **Database kode surat**: daftar kode klasifikasi (mis. `000.1.2.3` = Perjalanan Dinas Pegawai). Tambah/ubah/nonaktifkan/hapus **manual**, atau **impor Excel/CSV** (kolom Kode, Uraian; kode yang ada diperbarui; satu baris salah = seluruh impor batal; gunakan Template agar Excel tidak mengubah `000.1.2.3` menjadi angka). Ekspor Excel tersedia. Kode aktif menjadi pilihan (datalist) pada kolom Klasifikasi saat menerbitkan nomor dan mengubah kode penomoran. Pengelola: Kepala, Bendahara, Bendahara BLUD, Pembuat Surat; Pengelola Program hanya melihat. API: `/api/kode-surat`.
