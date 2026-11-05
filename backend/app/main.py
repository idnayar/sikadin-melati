"""SIKADIN — backend FastAPI. Jalankan:  uvicorn app.main:app --port 8000   (dari folder backend)."""
import os
from pathlib import Path

from fastapi import Body, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import akuntansi, bku, dashboard, laporan, laporan_melati, rekap, bok, jadwal, kode_surat, master, penomoran, rencana, spj, surat
from .calc import hitung
from . import core
from .core import Gagal, get_db, perlu_baca
from .db import init_db

app = FastAPI(title="SIKADIN API", docs_url="/api/docs" if os.environ.get("SIKADIN_DOCS") else None, redoc_url=None, openapi_url="/api/openapi.json" if os.environ.get("SIKADIN_DOCS") else None)
init_db()

# Mode produksi (SIKADIN_ENV=production): cookie sesi hanya lewat HTTPS dan server menolak jalan bila masih ada akun bersandi demo.
if core.produksi() and not os.environ.get("SIKADIN_IZINKAN_SANDI_DEMO"):
    from .admin import akun_sandi_demo, amankan_sandi_demo
    _c = core.connect()
    amankan_sandi_demo(_c)   # bila SIKADIN_ADMIN_PASSWORD diatur: sandi demo diganti otomatis
    _sisa = akun_sandi_demo(_c)
    _c.close()
    if _sisa:
        raise RuntimeError("Akun masih memakai sandi demo: " + ", ".join(_sisa) + ". Jalankan «python -m app.admin sandi-acak» (atau atur-sandi USERNAME), atau atur variabel SIKADIN_ADMIN_PASSWORD (min. 10 karakter), lalu mulai ulang.")


@app.middleware("http")
async def _header_keamanan(request, call_next):
    r = await call_next(request)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "same-origin")
    r.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    r.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'self' blob:; frame-ancestors 'none'")
    if core.cookie_aman():
        r.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return r


@app.get("/api/health")
def _health():
    c = core.connect()
    try:
        c.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    finally:
        c.close()
    return {"ok": True}


@app.exception_handler(Gagal)
async def _gagal(_, e: Gagal):
    return JSONResponse({"error": e.pesan, **e.extra}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def _valid(_, e: RequestValidationError):
    return JSONResponse({"error": "Data yang dikirim tidak valid."}, status_code=422)


app.include_router(master.router)
app.include_router(bok.router)
app.include_router(rencana.router)
app.include_router(jadwal.router)
app.include_router(surat.router)
app.include_router(kode_surat.router)
app.include_router(penomoran.router)
app.include_router(spj.router)
app.include_router(akuntansi.router)
app.include_router(laporan.router)
app.include_router(rekap.router)
app.include_router(dashboard.router)
app.include_router(bku.router)
app.include_router(laporan_melati.router)


@app.post("/api/hitung-biaya")
def hitung_biaya(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    return hitung(db, body)


# Produksi: frontend hasil `npm run build` (frontend/dist) disajikan langsung oleh FastAPI.
DIST = Path(os.environ.get("SIKADIN_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist")
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
else:
    @app.get("/")
    def _info():
        return JSONResponse({"pesan": "API SIKADIN aktif. Jalankan frontend (npm run dev di folder frontend) atau npm run build."})
