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
- [ ] 3. Jadwal + anti-doubling  - [ ] 4. ST/SPD (format Srikandi)  - [ ] 5. Panjar & SPJ
- [ ] 6. Rekap & laporan  - [ ] 7. Dashboard  - [ ] DAU/BLUD

## Catatan teknis
- Semua tarif ada di tabel `tarif` (`tahun_berlaku`, `dasar_hukum`); tidak ada angka tarif di kode.
- Skema SQL standar; pindah ke PostgreSQL/Supabase cukup mengganti `INTEGER PRIMARY KEY` → `bigserial` dan fungsi tanggal.
  Constraint anti-doubling (tahap 3): `UNIQUE(pegawai_id, tanggal)` pada tabel rincian harian penugasan.
- Kontrak API (`/api/...`) sama dengan versi Node sebelumnya, jadi UI tidak berubah.
