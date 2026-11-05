"""Membuat panduan & tutorial per peran (satu PDF per peran, sampul berlogo Kab. Kapuas + Puskesmas Melati).
Jalankan: backend/.venv/Scripts/python docs/buat_panduan_peran.py   -> docs/peran/Panduan-<peran>.pdf"""
from pathlib import Path

import buat_panduan as B
from buat_panduan import P, Spacer, Tag, bagian, callout, langkah, tabel, Alur, G7

MASUK = [("Buka alamat SIKADIN", "Ketik alamat dari admin di Chrome/Edge/Safari (laptop atau HP)."),
         ("Masukkan Username &amp; Password", "Dari admin. Salah lima kali berturut-turut, login dikunci 5 menit."),
         ("Ganti password", "Klik <b>Ganti password</b> di pojok kanan atas (min. 8 karakter). Lakukan segera pada login pertama."),
         ("Pilih menu di sisi kiri", "Di HP, ketuk ikon tiga garis di kiri atas. Menu yang tampil sudah disesuaikan dengan peran Anda.")]

TAHUN = callout("tip", "Ganti tahun anggaran", "Kolom <b>Tahun</b> ada di hampir setiap layar; mengubahnya berlaku untuk semua menu.")

SPJ_ALUR = [("Draft", "Pegawai mengisi realisasi & bukti"), ("Diajukan", "Menunggu bendahara"), ("Diverifikasi", "Bendahara memeriksa"), ("Dibayar", "Terhitung realisasi")]

ST_LANGKAH = [("Buka menu <b>Surat</b> → tab <b>Siap diterbitkan</b>", "Daftar jadwal yang belum punya Surat Tugas. Centang semuanya atau sebagian → <b>Terbitkan yang dipilih</b>."),
              ("Unduh dokumen", "Klik <b>Dokumen</b> pada ST: Surat Tugas, SPD, rincian biaya, kuitansi, daftar hadir, dll. — tiap dokumen punya tombol <b>PDF</b> dan <b>DOCX</b>."),
              ("Unggah ke Srikandi", "Pilih <b>DOCX Srikandi (ST + SPD)</b> atau <b>PDF Srikandi (ST + SPD)</b>. Kode tanda tangan elektronik di dalamnya jangan diubah."),
              ("Klik <b>Tandai sudah diunggah ke Srikandi</b>", "Supaya semua orang tahu surat sedang menunggu tanda tangan elektronik."),
              ("Setelah ditandatangani: <b>Unggah PDF hasil Srikandi</b>", "SIKADIN membaca nomor naskah dari PDF; konfirmasi untuk mencatatnya. Progres menjadi <b>Selesai di Srikandi</b> (3/3).")]

ROLES = {}


def peran(kode, nama, singkat, lead, ringkas, menu, tugas, rinci, aturan, faq, *, warna=None):
    ROLES[kode] = dict(nama=nama, singkat=singkat, lead=lead, ringkas=ringkas, menu=menu, tugas=tugas, rinci=rinci, aturan=aturan, faq=faq)


# ---------------------------------------------------------------- PEGAWAI
peran("pegawai", "Pegawai", "Melihat jadwal & Surat Tugas, mengisi SPJ",
      "Panduan untuk pegawai yang mendapat tugas dinas luar: lihat Surat Tugas, isi SPJ, pantau pembayaran.",
      [["Bisa", "Melihat jadwal, ST/SPD, dan rekap perjalanan <b>milik sendiri</b>; mengisi dan mengajukan SPJ perjalanannya; mengunggah foto bukti"],
       ["Tidak bisa", "Melihat data orang lain, mengubah ST/SPD, memverifikasi atau membayar SPJ, melihat data keuangan Puskesmas"]],
      [["Dashboard", "Status SPJ Anda dan jadwal terdekat"], ["Surat Tugas &amp; SPD Saya", "Daftar dan unduhan dokumen ST/SPD milik Anda"], ["Rekap Perjalanan Saya", "Riwayat perjalanan dinas setahun: tempat, waktu, tujuan, biaya"], ["Realisasi &amp; SPJ", "Mengisi realisasi biaya dan bukti"]],
      [("Cek jadwal &amp; Surat Tugas", "Menu <b>Surat Tugas &amp; SPD Saya</b> → klik <b>Dokumen</b> untuk mengunduh ST/SPD (PDF)."),
       ("Berangkat &amp; simpan semua bukti", "Tiket/karcis, kuitansi penginapan, nota. Foto langsung dengan HP lebih praktis."),
       ("Setelah kegiatan selesai, buka <b>Realisasi &amp; SPJ</b>", "SPJ Anda otomatis sudah disiapkan sejak ST terbit. Klik <b>Buka</b>."),
       ("Periksa &amp; isi", "Cek tanggal berangkat/kembali. Isi <b>Realisasi</b> tiap komponen (uang harian, transport, penginapan) — tidak boleh lebih dari tarif di SPD — dan <b>No. bukti</b>."),
       ("Unggah <b>foto bukti</b>", "Tombol <b>Ambil foto</b> (kamera HP) atau <b>Pilih foto / PDF</b>. Maks. 8 berkas, 4 MB per berkas. Foto dikecilkan otomatis."),
       ("Klik <b>Simpan &amp; ajukan</b>", "Bendahara akan memeriksa. Bila dikembalikan, alasannya tampil — perbaiki, lalu ajukan lagi.")],
      [P("Status SPJ", "h2"), Alur(SPJ_ALUR, warna=G7), Spacer(1, 6),
       tabel([["Status", "Artinya bagi Anda"], ["Draft", "Belum diajukan. Anda bebas mengubah angka dan bukti."], ["Diajukan", "Sudah masuk antrean bendahara. Tidak bisa diubah."], ["Dikembalikan", "Ada yang perlu diperbaiki; baca alasannya, edit, ajukan lagi."],
              ["Diverifikasi", "Sudah benar menurut bendahara; menunggu pembayaran."], ["Dibayar", "Selesai. Jumlah tercatat sebagai realisasi dan masuk BKU."]], [3.4, 13.6]),
       callout("tip", "Foto bukti yang baik", "Letakkan nota di permukaan rata, pastikan tulisan terbaca dan keempat sudutnya terlihat. Satu nota satu foto.")],
      [["Realisasi", "Tidak boleh melebihi tarif di SPD (Perbup Kapuas No. 8/2026)."], ["Bukti", "Diisi sebelum diajukan; bisa ditambah/dihapus hanya saat Draft atau Dikembalikan."], ["Waktu pengajuan", "SPJ baru bisa diajukan setelah kegiatan selesai."], ["Terkunci", "SPJ yang sudah dibayar tidak dapat diubah."]],
      [["Tombol Ajukan tidak aktif.", "Kegiatan belum selesai, belum ada nomor bukti, atau total masih nol."], ["Realisasi saya ditolak melebihi tarif.", "Aturan sistem. Isi sesuai bukti, maksimal sebesar tarif SPD."], ["SPJ saya tidak muncul.", "SPJ muncul setelah Surat Tugas diterbitkan. Hubungi pembuat surat bila ST belum ada."], ["Foto gagal diunggah.", "Pastikan JPG/PNG/WebP/PDF dan di bawah 4 MB; SPJ harus berstatus Draft/Dikembalikan."]])

# ---------------------------------------------------------------- PROGRAM
peran("program", "Pengelola Program", "Membuat rencana, jadwal, dan menerbitkan Surat Tugas (BOK/DAU)",
      "Panduan untuk pengelola program: dari rencana kegiatan sampai Surat Tugas terbit.",
      [["Bisa", "Membuat rencana (RPK/POA) dan jadwal dinas luar, menerbitkan ST/SPD, mengisi belanja non-perjalanan, melihat rekap — untuk BOK dan DAU"],
       ["Tidak bisa", "Mengubah pagu/RAB, memverifikasi/membayar SPJ, melihat data BLUD"]],
      [["Dashboard", "Pekerjaan menunggu, serapan, peringatan"], ["Perencanaan (RPK/POA)", "Rencana kegiatan dan matriks POA"], ["Jadwal Dinas Luar", "Kalender, tabel, dan generate jadwal bulanan"], ["Surat", "Menerbitkan ST/SPD, nomor surat"], ["Rekap Perjalanan Dinas", "Rekap per nama/tempat/bulan"], ["Realisasi &amp; SPJ", "Memantau SPJ; belanja non-perjalanan"], ["Pagu Anggaran BOK/DAU", "Hanya melihat"]],
      [("Buat <b>Rencana</b>", "Perencanaan → <b>+ Rencana</b>: pilih baris RAB, bulan, lokasi, durasi, jumlah petugas/hari/frekuensi. Biaya dihitung otomatis dari tarif Perbup."),
       ("Ajukan rencana", "Rencana diajukan kepada Pembuat Surat Tugas/Kepala (atau disetujui sendiri sesuai pengaturan)."),
       ("Buat <b>Jadwal</b>", "Jadwal Dinas Luar → pilih rencana yang disetujui, tanggal, petugas. Atau gunakan <b>Generate</b> untuk satu bulan penuh."),
       ("Terbitkan <b>Surat Tugas</b>", "Menu Surat → <b>Siap diterbitkan</b> → centang jadwal → <b>Terbitkan yang dipilih</b>."),
       ("Pantau SPJ petugas", "Menu Realisasi &amp; SPJ menampilkan status SPJ tiap petugas yang otomatis dibuat.")],
      [P("Rencana (RPK/POA)", "h2"),
       langkah([("<b>+ Rencana</b>", "Pilih sumber dana, baris RAB, bulan, lokasi tujuan, durasi (≤ 8 jam atau &gt; 8 jam), jumlah petugas, hari, dan frekuensi."),
                ("Lihat estimasi", "Biaya per orang dari tarif Perbup. Sistem memperingatkan bila melebihi sisa pagu baris."),
                ("Ajukan → Disetujui", "Status: Draft → Diajukan → Disetujui (atau Ditolak dengan alasan). Hanya rencana Disetujui yang bisa dijadwalkan."),
                ("Tab <b>Matriks POA</b>", "Ringkasan rencana per bulan untuk satu tahun.")]),
       P("Jadwal dinas luar", "h2"),
       langkah([("Tambah jadwal", "Pilih rencana, tanggal mulai/selesai, lokasi, petugas."),
                ("Sistem memeriksa otomatis", "Satu orang satu tugas per hari (lintas sumber dana); kegiatan + lokasi + tanggal tidak boleh ganda; tidak pada hari libur atau saat cuti; maks. <b>50%</b> pegawai satu ruangan keluar pada hari yang sama."),
                ("<b>Generate</b> bulanan", "Pilih bulan → <b>pratinjau</b> pembagian petugas yang adil → simpan bila sesuai.")]),
       callout("tip", "Bentrok? Baca saransnya", "Pesan merah menyebut siapa/hari apa yang bentrok dan menyarankan pengganti yang bebas."),
       P("Menerbitkan Surat Tugas", "h2"), langkah(ST_LANGKAH[:2] + [("Serahkan ke Pembuat Surat Tugas bila Anda tidak berhak mengunggah ke Srikandi", "Cukup beri tahu bahwa ST sudah terbit; unggah &amp; tanda tangan elektronik dikerjakan sesuai alur Puskesmas.")]),
       P("Belanja non-perjalanan", "h2"),
       langkah([("<b>+ Belanja non-perjalanan</b>", "Di Realisasi &amp; SPJ: pilih baris RAB, isi uraian, tanggal, jumlah, penerima, bukti. Alurnya sama dengan SPJ perjalanan.")])],
      [["Sumber dana", "Hanya BOK dan DAU. Data BLUD tidak terlihat."], ["ST terkunci", "Setelah terbit, ubah hanya dengan batal + terbit ulang. Batal ditolak bila ada SPJ yang sudah diajukan/dibayar."], ["Satu halaman", "ST harus muat satu halaman; lebih dari ± 9 petugas ditolak — pecah jadi dua ST."], ["Pagu", "Biaya rencana tidak boleh melebihi sisa pagu baris RAB."]],
      [["Tombol Terbitkan ST tidak muncul.", "Jadwal harus Disetujui dan Anda berhak atas sumber dananya (BOK/DAU)."], ["Jadwal ditolak “bentrok”.", "Baca pesan merahnya: ada petugas yang sudah bertugas, libur/cuti, atau ruangannya melebihi 50%."], ["Rencana tidak bisa diajukan.", "Periksa sisa pagu baris RAB dan kelengkapan lokasi/petugas."]])

# ---------------------------------------------------------------- PEMBUAT SURAT
peran("pembuat_surat", "Pembuat Surat Tugas", "Hak istimewa menyetujui & menerbitkan surat BOK/DAU/BLUD sampai Srikandi selesai",
      "Panduan untuk Pembuat Surat Tugas: dari usulan sampai PDF final Srikandi tercatat.",
      [["Bisa", "Membuat surat sesuai pagu <b>BOK, DAU, maupun BLUD</b> — dari rencana/jadwal sendiri atau <b>usulan Pengelola Program</b> — dan <b>menyetujuinya</b> (selalu, walau persetujuan Kepala diwajibkan); menerbitkan ST/SPD (terbit massal); mengelola alur Srikandi sampai selesai"],
       ["Tidak bisa", "Mengubah pagu/RAB; memverifikasi atau membayar SPJ; melihat <b>data uang BLUD</b> (SPJ, serapan, laporan keuangan)"]],
      [["Dashboard", "Pekerjaan menunggu: usulan, jadwal, ST menunggu Srikandi"], ["Perencanaan", "Meninjau/menyetujui usulan, atau membuat rencana sendiri"], ["Jadwal Dinas Luar", "Menyetujui jadwal usulan, atau membuat sendiri"], ["Surat", "Terbit massal, dokumen, alur Srikandi, nomor surat umum"], ["Rekap Perjalanan Dinas", "Rekap setahun/bulanan"], ["Kalkulator Biaya", "Menghitung perkiraan biaya"]],
      [("Tinjau usulan", "Menu <b>Perencanaan</b>: rencana Diajukan → <b>Setujui</b>/<b>Tolak</b> (alasan wajib). <b>Jadwal Dinas Luar</b>: jadwal Diusulkan → <b>Setujui</b>."),
       ("Atau buat sendiri", "Boleh membuat rencana &amp; jadwal sendiri lalu menyetujuinya, selama masih dalam pagu baris RAB.")] + [(a, b) for a, b in ST_LANGKAH],
      [P("Alur Srikandi (progres 0/3 → 3/3)", "h2"),
       Alur([("Diunggah", "Dokumen diunduh &amp; diunggah ke Srikandi"), ("Ditandai", "Tombol Tandai di SIKADIN"), ("Nomor dicatat", "Nomor naskah dari PDF"), ("PDF final", "Tersimpan di SIKADIN")], warna=G7), Spacer(1, 6),
       tabel([["Tahap", "Yang Anda lakukan"], ["0/3", "ST terbit di SIKADIN. Unduh DOCX/PDF Srikandi."], ["1/3", "Setelah mengunggah ke Srikandi → <b>Tandai sudah diunggah</b>."], ["2/3", "Nomor naskah tercatat (terbaca dari PDF, atau <b>Catat nomor Srikandi</b> manual — hanya sekali)."], ["3/3", "<b>Unggah PDF hasil Srikandi</b> → <b>Selesai di Srikandi</b>. PDF final dapat dilihat kembali dan boleh diganti; penggantian tercatat."]], [2.4, 14.6]),
       P("Terbit massal &amp; nomor umum", "h2"),
       langkah([("Terbit massal", "Tab <b>Siap diterbitkan</b>: centang beberapa jadwal → <b>Terbitkan yang dipilih</b>. Jadwal yang masih diusulkan otomatis disetujui atas nama Anda."),
                ("Nomor surat umum", "Tab <b>Nomor surat umum</b>: klik <b>⚡ Generate nomor otomatis</b> untuk mencadangkan nomor berikutnya; isi perihal belakangan lewat <b>Isi perihal</b>."),
                ("Salah? Batalkan &amp; terbitkan ulang", "<b>Batalkan ST</b> (alasan wajib), lalu terbitkan lagi. ST tidak bisa diedit setelah terbit.")]),
       callout("warn", "Pembatalan ditolak bila SPJ sudah berjalan", "Jika ada SPJ yang diajukan atau dibayar, minta bendahara mengembalikan SPJ atau Kepala mengoreksi pembayaran terlebih dahulu."),
       callout("info", "Surat BLUD", "Anda boleh membuat dan menerbitkan surat dengan sumber dana BLUD, tetapi rincian uang BLUD (SPJ, serapan) disembunyikan — itu wewenang Kepala dan Bendahara BLUD.")],
      [["Persetujuan", "Hak Anda berlaku untuk semua sumber dana, juga saat persetujuan Kepala diwajibkan (kepala_wajib = 1)."], ["Pagu", "Sistem tetap menolak bila melebihi sisa pagu baris RAB."], ["Satu halaman", "ST harus muat satu halaman; lebih dari ± 9 petugas — pecah jadi dua ST."], ["Riwayat", "Semua persetujuan dan penerbitan tercatat di Riwayat Perubahan atas nama Anda."]],
      [["Nomor Srikandi tidak terbaca.", "Pastikan PDF teks (bukan hasil foto). Atau gunakan <b>Catat nomor Srikandi</b> manual."], ["Ingin mengganti PDF final.", "Unggah ulang; versi lama tercatat di riwayat."], ["Ada ST salah tanggal.", "Batalkan (alasan wajib) lalu terbitkan ulang dengan nomor baru."]])

# ---------------------------------------------------------------- BENDAHARA
peran("bendahara", "Bendahara (BOK/DAU)", "Pagu & RAB, rencana, jadwal, verifikasi & pembayaran SPJ, BKU BOK/DAU",
      "Panduan untuk Bendahara Pengeluaran Pembantu: dari menyusun RAB sampai buku kas.",
      [["Bisa", "Mengisi pagu &amp; RAB BOK/DAU, rencana, jadwal, ST; memverifikasi dan membayar SPJ; mencatat BKU BOK &amp; DAU; rekap dan dashboard"],
       ["Tidak bisa", "Melihat/mengubah data BLUD; mengoreksi pembayaran (hanya Kepala)"]],
      [["Dashboard", "SPJ menunggu verifikasi/bayar, serapan, peringatan"], ["Pagu Anggaran BOK/DAU", "Menu → Rincian → Baris RAB; impor Excel"], ["Perencanaan, Jadwal, Surat", "Seperti Pengelola Program"], ["Realisasi &amp; SPJ", "Verifikasi, kembalikan, bayar; realisasi anggaran"], ["Buku Kas Umum", "BKU BOK dan DAU (bulanan &amp; tahunan)"], ["Rekap Perjalanan Dinas", "Rekap + ekspor"]],
      [("Susun pagu &amp; RAB", "Menu Pagu Anggaran BOK/DAU: impor Excel atau tambah <b>Menu → Rincian → Baris</b>."),
       ("Periksa SPJ yang masuk", "Realisasi &amp; SPJ → buka SPJ berstatus <b>Diajukan</b> → cek angka dan foto bukti → <b>Verifikasi</b> atau <b>Kembalikan</b> (alasan wajib)."),
       ("Catat pembayaran", "SPJ <b>Diverifikasi</b> → <b>Catat pembayaran</b> (tanggal bayar). Nomor bukti otomatis (mis. <b>122/PKM.M/2026</b>) dan baris BKU terbentuk sendiri."),
       ("Isi saldo awal BKU", "Menu Buku Kas Umum → pilih BOK/DAU → <b>Saldo awal</b> (sekali di awal tahun)."),
       ("Cetak BKU", "Pilih bulan atau Tahunan → <b>PDF / DOCX / XLSX</b>.")],
      [P("Pagu &amp; RAB", "h2"),
       langkah([("Impor dari Excel (disarankan)", "Klik tombol impor, pilih berkas RAB. <b>Ganti</b> menimpa RAB tahun itu. Angka yang tidak cocok volume × harga diberi tanda."),
                ("Atau tambah manual", "<b>+ Menu</b> → <b>+ Rincian</b> → <b>+ Baris</b>: jenis belanja, uraian, volume, harga satuan."),
                ("Cocokkan dengan pagu resmi", "Isi pagu tahun di bagian atas; selisih terhadap total RAB ditampilkan.")]),
       P("Memverifikasi &amp; membayar SPJ", "h2"), Alur(SPJ_ALUR, warna=G7), Spacer(1, 6),
       langkah([("Periksa", "Bandingkan realisasi dengan bukti foto. Realisasi tidak mungkin melebihi tarif SPD."),
                ("Kembalikan bila perlu", "Tulis alasan jelas; pegawai dapat mengedit lagi."),
                ("Bayar", "Tanggal bayar tidak boleh sebelum kegiatan dimulai. Total yang dibayar per baris RAB tidak boleh melebihi pagu baris."),
                ("Salah catat?", "Hanya <b>Kepala</b> yang bisa <b>Koreksi pembayaran</b>; Anda cukup melapor.")]),
       P("Buku Kas Umum (BOK &amp; DAU)", "h2"),
       langkah([("Pembayaran SPJ masuk otomatis", "Nomor bukti dan uraian mengikuti format Puskesmas (<b>Pembayaran … An. …</b>)."),
                ("<b>+ Catat transaksi</b>", "Penerimaan (dana masuk), pengeluaran lain, atau pindah antar buku. Transaksi manual dapat dihapus; yang dari SPJ dikoreksi lewat SPJ."),
                ("Cetak", "Bulanan: jumlah bulan ini, s.d. bulan lalu, sisa, tanda tangan. Tahunan: tiap bulan berurutan.")])],
      [["Tanpa panjar", "Pembayaran dilakukan <b>setelah</b> SPJ diverifikasi."], ["Terkunci", "SPJ dibayar tidak dapat diubah, juga di basis data."], ["Pagu", "Total dibayar per baris RAB ≤ pagu baris."], ["Data BLUD", "Tidak terlihat oleh Anda."]],
      [["SPJ tidak bisa diverifikasi.", "Pastikan statusnya Diajukan dan bukti sudah ada."], ["Saldo BKU tidak sesuai bank.", "Periksa saldo awal dan transaksi manual yang belum dicatat."], ["Impor RAB gagal.", "Periksa kolom volume, harga satuan, dan jenis belanja; lihat tanda di pratinjau."]])

# ---------------------------------------------------------------- BENDAHARA BLUD
peran("bendahara_blud", "Bendahara BLUD", "Pendapatan & belanja BLUD, BKU Retribusi/BLUD, laporan keuangan",
      "Panduan untuk Bendahara BLUD / Bendahara Penerimaan: BLUD, retribusi, jurnal, dan laporan keuangan resmi.",
      [["Bisa", "Semua urusan BLUD (pagu, rencana, ST, SPJ, pendapatan); BKU Retribusi &amp; BLUD; seluruh laporan keuangan gabungan; BOK/DAU hanya melihat"],
       ["Tidak bisa", "Mengubah BOK/DAU; mengoreksi pembayaran (hanya Kepala)"]],
      [["Dashboard", "Ringkasan keuangan: pendapatan, belanja, surplus, kas, aset"], ["Pagu Anggaran BLUD", "RAB BLUD"], ["Rencana, Jadwal, Surat", "Untuk sumber dana BLUD"], ["Realisasi &amp; SPJ", "Verifikasi dan bayar SPJ BLUD"], ["Buku Kas Umum", "BKU Retribusi dan BLUD"], ["Akuntansi &amp; Laporan Keuangan", "Jurnal, saldo awal, laporan format Melati"]],
      [("Isi <b>saldo awal kas</b>", "Menu Buku Kas Umum → buku BLUD/Retribusi → <b>Saldo awal</b>. Rinci per tempat (Bank/Kas) dan jenis dana."),
       ("Catat pendapatan &amp; transaksi", "BKU → <b>+ Catat transaksi</b>: penerimaan, pengeluaran (mis. jasa giro), <b>setor/pindah</b> retribusi → BLUD, atau <b>terima lalu teruskan</b> (Qris). Di Akuntansi → Jurnal: <b>+ Penerimaan pendapatan</b>."),
       ("Verifikasi &amp; bayar SPJ BLUD", "Realisasi &amp; SPJ → Verifikasi → Catat pembayaran; jurnal kas terbentuk otomatis."),
       ("Isi anggaran pendapatan &amp; data tahun lalu", "Akuntansi → Anggaran pendapatan; tab <b>Data tahun lalu</b> bila jurnal tahun lalu belum ada."),
       ("Susun laporan", "Akuntansi → <b>Laporan Puskesmas Melati</b>: pilih Semester 1/Tahunan, periksa LRA, LRA BLUD, Neraca, LO, LPE, sunting teks CaLK, lalu <b>PDF Laporan lengkap</b>.")],
      [P("Buku Kas Umum BLUD &amp; Retribusi", "h2"),
       langkah([("Pilih buku, tahun, bulan", "Atau <b>Tahunan</b> untuk seluruh tahun."), ("Saldo awal", "Sekali di awal tahun; rincian saldo di akhir BKU mengikutinya."),
                ("Transaksi", "Penerimaan, pengeluaran, setor/pindah antar buku, atau terima-lalu-teruskan."), ("Cetak", "<b>PDF / DOCX / XLSX</b> dalam tiga format cetak Puskesmas (pembantu, penerimaan, BLUD).")]),
       P("Akuntansi &amp; laporan", "h2"),
       langkah([("Saldo awal non-kas", "Tab Saldo awal: aset non-kas, kewajiban, ekuitas — Aset = Kewajiban + Ekuitas. (Kas lewat BKU.)"),
                ("Jurnal manual", "Piutang klaim (Akrual), penyusutan, pembelian aset. Debit total = kredit total."),
                ("Laporan Puskesmas Melati", "Sampul, pengantar, SPTJM, LRA (kode BAS), LRA BLUD, Neraca, LO, LPE, CaLK Bab I–VII. Ekspor PDF/DOCX/XLSX per bagian atau lengkap."),
                ("Tab <b>PSAP 13 (tambahan)</b>", "Tujuh laporan PSAP 13 termasuk LAK dan L-SAL, tersedia sebagai pelengkap.")]),
       callout("warn", "Pemetaan kode BAS", "Kode di luar contoh Puskesmas (mis. kas Bendahara Penerimaan, belanja modal non-BLUD) ditebak sistem. Minta akuntan memeriksa tabel akun sebelum laporan dipakai resmi."),
       callout("info", "Teks CaLK", "Teks bawaan diambil dari laporan semester 1 2026. Sunting narasi tahun/periode di tab <b>CaLK &amp; Pengantar</b>.")],
      [["Data BLUD", "Hanya Anda dan Kepala yang melihatnya."], ["Saldo awal kas", "Lewat BKU, bukan tab Saldo awal akuntansi."], ["Jurnal", "Debit = kredit; jurnal dari SPJ tidak diedit manual."], ["Tahun lalu", "Kolom pembanding otomatis dari jurnal tahun lalu atau diisi manual."]],
      [["Neraca tidak seimbang.", "Periksa saldo awal dan jurnal manual. RK PPKD menjadi penyeimbang ekuitas."], ["Kolom tahun lalu kosong.", "Belum ada jurnal tahun lalu: isi di tab Data tahun lalu."], ["Angka BKU berbeda dari laporan.", "Pastikan basis dan periode sama (s.d. bulan yang dipilih)."]])

# ---------------------------------------------------------------- KEPALA
peran("kepala", "Kepala Puskesmas", "Memantau, menyetujui, mengoreksi pembayaran, laporan, pengaturan",
      "Panduan untuk Kepala Puskesmas: memantau, menyetujui, mengoreksi, dan mengelola pengaturan sistem.",
      [["Bisa", "Melihat semua menu dan sumber dana; menyetujui rencana/jadwal/SPJ bila perlu; <b>mengoreksi pembayaran</b>; laporan keuangan gabungan; mengelola pengguna, pengaturan, backup &amp; pemulihan"],
       ["Catatan", "Persetujuan Kepala bersifat <b>opsional</b> (bawaan: pembuat dokumen mengotorisasi sendiri). Aktifkan <b>kepala_wajib</b> bila ingin persetujuan Kepala/Pembuat Surat"]],
      [["Dashboard", "Serapan, tugas menunggu, peringatan, ringkasan keuangan"], ["Pagu, Perencanaan, Jadwal, Surat", "Memantau dan menyetujui"], ["Realisasi &amp; SPJ", "Koreksi pembayaran"], ["Buku Kas Umum", "Keempat buku"], ["Akuntansi &amp; Laporan", "Laporan gabungan DAU + BOK + BLUD"], ["Master Data &amp; Pengaturan", "Pegawai, tarif, pejabat, kop, kepala_wajib"], ["Pengguna", "Akun, peran, aktif/nonaktif"], ["Riwayat Perubahan, Backup &amp; Ekspor", "Audit dan pemulihan"]],
      [("Mulai dari Dashboard", "Lihat serapan per sumber dana, tombol <b>Perlu tindakan</b>, dan peringatan."),
       ("Setujui bila diwajibkan", "Rencana, jadwal, dan SPJ yang menunggu muncul di <b>Perlu tindakan</b>."),
       ("Pantau laporan", "Akuntansi → <b>Laporan Puskesmas Melati</b> + kotak <b>Pemeriksaan integritas</b>."),
       ("Koreksi pembayaran bila salah catat", "Realisasi &amp; SPJ → SPJ Dibayar → <b>Koreksi pembayaran</b> (alasan wajib). Jurnal akuntansi dibalik otomatis."),
       ("Tinjau Riwayat Perubahan", "Menu Alat → Riwayat Perubahan: siapa mengubah apa dan kapan.")],
      [P("Pengaturan penting (Master Data → Pengaturan &amp; Kop)", "h2"),
       tabel([["Pengaturan", "Fungsi"], ["kepala_wajib", "0 (bawaan): pembuat dokumen mengotorisasi sendiri. 1: persetujuan hanya oleh Kepala dan Pembuat Surat Tugas."], ["spj_setelah_selesai", "1: SPJ baru dapat diajukan setelah kegiatan selesai."], ["Kop &amp; kota surat", "Dipakai pada ST, SPD, dan laporan."], ["format_bukti_spj", "Format nomor bukti, bawaan <b>{urut}/PKM.M/{tahun}</b>."], ["Kode penomoran", "Kode unit surat (tab Nomor surat umum)."]], [4.2, 12.8]),
       P("Pengguna &amp; keamanan", "h2"),
       langkah([("Kelola akun", "Menu <b>Pengguna</b>: tambah akun, tetapkan peran, nonaktifkan. Peran: Kepala, Bendahara, Bendahara BLUD, Pengelola Program, Pembuat Surat, Pegawai."),
                ("Ganti password demo", "Di server: <b>python -m app.admin sandi-acak</b>. Mode produksi menolak berjalan bila sandi demo masih ada."),
                ("Backup &amp; pulihkan", "Backup &amp; Ekspor → unduh database. <b>Pulihkan database</b> menimpa seluruh data (salinan otomatis disimpan; semua sesi dikeluarkan).")]),
       callout("stop", "Pulihkan database menghapus data saat ini", "Gunakan hanya dari backup yang dipercaya. Salinan <b>sebelum-pulih-*.db</b> disimpan otomatis sebagai pengaman.")],
      [["Koreksi", "Hanya Kepala yang boleh mengoreksi pembayaran; alasan wajib dan tercatat."], ["Laporan", "Laporan gabungan hanya Kepala + Bendahara BLUD."], ["BLUD", "Data uang BLUD hanya Kepala + Bendahara BLUD."], ["Riwayat", "Setiap perubahan penting tercatat dan tidak bisa dihapus."]],
      [["Dokumen menunggu persetujuan saya.", "Berarti kepala_wajib = 1 atau pembuat memilih menunggu; buka <b>Perlu tindakan</b>."], ["Lupa password pengguna.", "Admin menjalankan <b>python -m app.admin atur-sandi USERNAME</b>."], ["Sesi habis tiba-tiba.", "Server dimulai ulang atau lewat 12 jam; masuk lagi."]])


def story_peran(kode):
    r = ROLES[kode]

    def fn():
        s = [Spacer(1, 0), Tag("PANDUAN PERAN"), Spacer(1, 6), P(r["nama"], "h1"), P(r["lead"], "lead"),
             tabel([["", "Hak &amp; batas peran"]] + r["ringkas"], [3.0, 14.0]),
             P("Menu yang Anda gunakan", "h2"), tabel([["Menu", "Gunanya"]] + r["menu"], [5.4, 11.6]),
             P("Masuk pertama kali", "h2"), langkah(MASUK), TAHUN]
        s += bagian(1, "Jalur cepat", "Urutan kerja sehari-hari, dari awal sampai selesai.")
        s += [langkah(r["tugas"])]
        s += bagian(2, "Tutorial rinci")
        s += r["rinci"]
        s += bagian(3, "Aturan &amp; tanya jawab")
        s += [P("Aturan yang perlu diingat", "h2"), tabel([["Hal", "Aturan"]] + r["aturan"], [3.6, 13.4]),
              P("Pertanyaan yang sering muncul", "h2"), tabel([["Pertanyaan", "Jawaban"]] + r["faq"], [5.4, 11.6]), Spacer(1, 14),
              B.Table([[P("<b>Butuh bantuan?</b><br/>Hubungi admin SIKADIN Puskesmas Melati. Sertakan nama menu, tangkapan layar, dan pesan galat yang muncul.", "k")]], colWidths=[B.CW],
                      style=B.TableStyle([("BACKGROUND", (0, 0), (-1, -1), B.MINT), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))]
        return s
    return fn


def main():
    out = Path(__file__).resolve().parent / "peran"
    out.mkdir(exist_ok=True)
    for kode, r in ROLES.items():
        B.COVER.clear()
        B.COVER.update({"judul": "Panduan & Tutorial: " + r["nama"], "baris": [r["singkat"]], "fs": 13})
        B.halaman_judul = r["nama"]
        B.main(out / f"Panduan-SIKADIN-{kode}.pdf", story_peran(kode), f"Panduan SIKADIN — {r['nama']}")


if __name__ == "__main__":
    main()
