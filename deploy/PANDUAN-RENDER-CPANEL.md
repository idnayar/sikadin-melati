# SIKADIN di Render + cPanel pkmmelati.com

**Rancangan:** Render menjalankan SIKADIN (API *dan* tampilan dalam satu layanan). cPanel hanya dipakai untuk **DNS subdomain** dan **halaman utama** (tautan).
Tampilan sengaja *tidak* dipisah ke cPanel: login memakai cookie `SameSite=Strict`, sehingga halaman dan API harus satu alamat; memisahkannya menuntut CORS dan melemahkan keamanan.

```
pengguna → https://sikadin.pkmmelati.com ──(CNAME di cPanel)──► Render (SIKADIN + disk /data)
pengguna → https://pkmmelati.com  (cPanel, halaman statis) ── tombol "Masuk SIKADIN" ──► di atas
```

## ⚠ Wajib paket berbayar + disk
Data SIKADIN disimpan di berkas SQLite. Layanan **gratis** Render tidak punya disk persisten (data hilang tiap restart/deploy) dan tertidur saat sepi.
Pakai **Starter** (atau lebih) dengan **Disk** (`render.yaml` sudah memintanya: 1 GB di `/data`). Cek harga terbaru di dashboard Render.

## Langkah
1. **Repo di GitHub** (sudah ada: `tiofansha-bit/sikadin-melati`). Pastikan commit terbaru ter-push.
2. **Render → New + → Blueprint →** pilih repo → Render membaca `render.yaml`.
   Saat diminta, isi **SIKADIN_ADMIN_PASSWORD** (min. 10 karakter, mis. 14 acak). Ini sandi awal semua akun; segera diganti pengguna.
   Tunggu build selesai (±5–10 menit); `https://<nama>.onrender.com/api/health` harus menjawab `{"ok":true}`.
3. **Pindahkan data asli:** buka alamat `.onrender.com` → masuk sebagai `kepala` + sandi di atas → menu **Backup & Ekspor → Pulihkan database dari backup** →
   pilih `data/sikadin.db` (ada di zip proyek) → Pulihkan → masuk lagi (sandi yang sama; akun bersandi demo otomatis diganti dengannya).
   Salinan data lama disimpan di disk (`sebelum-pulih-….db`).
4. **Domain khusus:** Render → layanan → *Settings → Custom Domains → Add* `sikadin.pkmmelati.com` → Render menampilkan target CNAME.
   Di **cPanel → Domains → Zone Editor → Manage (pkmmelati.com) → Add Record**: Type **CNAME**, Name `sikadin`, Record/Target = nilai dari Render. Tunggu verifikasi (menit–jam); Render menerbitkan HTTPS otomatis.
   (Bila DNS domain dikelola di tempat lain mis. Cloudflare, buat CNAME di sana; matikan proxy oranye sampai terverifikasi.)
5. **Halaman utama (cPanel → File Manager → public_html):** tempel isi `deploy/landing-page-snippet.html` ke `index.html` situs Anda.
6. **Setelah tayang:** ubah nama akun `bendahara_blud`, minta tiap pengguna mengganti sandi (tombol *Ganti password*), lengkapi kode unit penomoran, saldo awal, dan pejabat asli.

## Perawatan
- **Backup:** Render membuat snapshot harian disk (periksa masa simpannya di dashboard), **tetapi** unduh backup sendiri berkala: menu *Backup & Ekspor → Unduh backup* (Kepala). Simpan di Drive/komputer.
- **Memulihkan:** menu yang sama (*Pulihkan database*). Aman dipakai juga untuk pindah server.
- **Update aplikasi:** `git push` ke repo → Render otomatis build & deploy ulang. Data di disk tetap; semua pengguna masuk ulang (sesi di memori).
- **Memori:** Starter 512 MB. Bila ekspor DOCX/PDF besar gagal karena memori, naikkan paket.
- **Satu instance saja:** jangan skala ke >1 instance (sesi & SQLite tidak dirancang untuk itu).

## Yang belum diuji
Berkas Docker/Render belum dijalankan di Render sungguhan. Yang sudah diuji lokal: mode produksi, penggantian sandi demo lewat `SIKADIN_ADMIN_PASSWORD`, dan pemulihan database lewat API.
