# Panduan Penayangan SIKADIN di pkmmelati.com

Alamat yang disarankan: **https://sikadin.pkmmelati.com** (subdomain). Halaman utama `pkmmelati.com` cukup diberi tautan
(`landing-page-snippet.html`). SIKADIN tidak bisa berjalan di hosting statis biasa karena butuh Python (FastAPI) + basis data SQLite.

## 0. Pilih tempat menjalankan
| Pilihan | Cocok bila | Catatan |
|---|---|---|
| **VPS Linux** (Ubuntu 22.04/24.04, 1 vCPU, 1–2 GB RAM) | Disarankan | Dua jalur di bawah: Docker (A) atau langsung (B). |
| Shared hosting/cPanel | Hanya bila ada «Setup Python App» | Tidak dicoba; HTTPS & proses panjang bergantung penyedia. |
| Komputer kantor + tunnel | Uji coba | Jangan untuk produksi jangka panjang. |

Hal yang perlu disiapkan: akses ke DNS `pkmmelati.com` (membuat record **A**: `sikadin` → IP server), port 80/443 terbuka.

## 1. Bawa data yang sudah ada
Data asli (pegawai, RAB, pejabat, dll.) ada di `data/sikadin.db` pada komputer pengembangan. Salin berkas itu ke server
(volume `/data` untuk Docker, atau `/var/lib/sikadin/sikadin.db` untuk jalur B). **Berkas ini berisi data pegawai — kirim lewat `scp`/SFTP, jangan lewat email/chat.**
Bila memulai dari nol, aplikasi membuat data contoh sendiri.

## A. Jalur Docker
```
git clone https://github.com/tiofansha-bit/sikadin-melati.git && cd sikadin-melati/deploy
docker compose build
# salin sikadin.db ke volume (sekali saja):
docker compose run --rm --no-deps -v $PWD/../data:/src:ro --entrypoint cp sikadin /src/sikadin.db /data/sikadin.db
docker compose run --rm --entrypoint python sikadin -m app.admin sandi-acak     # catat sandi baru yang dicetak!
docker compose up -d
```
Ubah `sikadin.pkmmelati.com` di `Caddyfile` bila domainnya lain. Caddy mengurus sertifikat HTTPS otomatis.

## B. Jalur langsung (tanpa Docker)
```
sudo apt install python3-venv nodejs npm caddy
sudo useradd -r -m sikadin && sudo mkdir -p /opt/sikadin /var/lib/sikadin /var/backups/sikadin
# letakkan kode di /opt/sikadin, lalu:
cd /opt/sikadin/frontend && npm ci && npm run build
cd ../backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo cp deploy/sikadin.service /etc/systemd/system/ && sudo chown -R sikadin /var/lib/sikadin /var/backups/sikadin
SIKADIN_DB=/var/lib/sikadin/sikadin.db .venv/bin/python -m app.admin sandi-acak
sudo systemctl daemon-reload && sudo systemctl enable --now sikadin
sudo cp deploy/Caddyfile.langsung /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
(Alternatif Caddy: `nginx-sikadin.conf` + certbot.)

## 2. Pengaman otomatis pada mode produksi (`SIKADIN_ENV=production`)
- Server **menolak start** bila masih ada akun bersandi demo → jalankan `python -m app.admin sandi-acak` atau `atur-sandi USERNAME`.
- Cookie sesi hanya lewat HTTPS; header keamanan (CSP, HSTS, anti-bingkai) aktif; dokumentasi API dimatikan.
- Batas percobaan login 5×/5 menit per alamat IP (alamat asli dibaca dari proxy).
- Hanya **satu proses** (jangan tambah `--workers`): sesi login ada di memori. Memulai ulang aplikasi = semua pengguna masuk lagi.

## 3. Setelah tayang
1. Masuk dengan sandi yang dicetak, ganti nama akun `bendahara_blud`, dan minta tiap pengguna mengganti sandinya.
2. Lengkapi: kode unit penomoran (menu Surat), saldo awal & anggaran pendapatan (menu Akuntansi), Bendahara/PPTK asli (menu Pejabat).
3. Pasang backup harian: `deploy/backup-harian.sh` (cron) → `python -m app.admin backup`. Simpan salinan di luar server dan **uji pulihkan** sesekali
   (hentikan aplikasi, ganti `sikadin.db` dengan berkas backup, jalankan lagi).
4. Pantau: `https://sikadin.pkmmelati.com/api/health` harus menjawab `{"ok":true}`.
5. Perbarui aplikasi: `git pull` → (Docker) `docker compose up -d --build` / (langsung) build frontend + `systemctl restart sikadin`. Basis data dimigrasi otomatis.

## 4. Tautan di halaman utama
Tempel `landing-page-snippet.html` pada `pkmmelati.com` (hanya tautan; iframe sengaja tidak didukung demi keamanan).

## 5. Yang belum diuji
Berkas Docker/Caddy/systemd/nginx ditulis menurut praktik umum tetapi **belum dijalankan** di server sungguhan (mesin pengembang tanpa Docker/Linux).
Yang sudah diuji: mode produksi lokal (penolakan sandi demo, `sandi-acak`, `backup`, `/api/health`, header keamanan).
