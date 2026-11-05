"""SIKADIN — backend FastAPI. Jalankan:  uvicorn app.main:app --port 8000   (dari folder backend)."""
import os
from pathlib import Path

from fastapi import Body, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import bok, master, rencana
from .calc import hitung
from .core import Gagal, get_db, perlu_baca
from .db import init_db

app = FastAPI(title="SIKADIN API", docs_url="/api/docs" if os.environ.get("SIKADIN_DOCS") else None, redoc_url=None, openapi_url="/api/openapi.json" if os.environ.get("SIKADIN_DOCS") else None)
init_db()


@app.exception_handler(Gagal)
async def _gagal(_, e: Gagal):
    return JSONResponse({"error": e.pesan, **e.extra}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def _valid(_, e: RequestValidationError):
    return JSONResponse({"error": "Data yang dikirim tidak valid."}, status_code=422)


app.include_router(master.router)
app.include_router(bok.router)
app.include_router(rencana.router)


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
