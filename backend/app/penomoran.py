"""Penomoran naskah dinas: kode klasifikasi arsip (Permendagri 83/2022) + tata naskah dinas (Permendagri 1/2023).

Pola nomor mengikuti contoh Srikandi Puskesmas Melati:  {klasifikasi}/{yymm}-{urut}/{unit}/{bulan_romawi}/{tahun}
mis. 000.1.2.3/2611-001/PKM.MELATI.BOK/XI/2026
  - klasifikasi : 000.1.2.3 = Perjalanan Dinas Pegawai; 000 = Umum (dapat dirinci saat menerbitkan nomor)
  - seri nomor  : TERPISAH per jenis (ST-BOK, ST-DAU, ST-BLUD, UMUM) dan per tahun; nomor tidak pernah dipakai ulang
Catatan: nomor RESMI Surat Tugas diberikan Srikandi saat TTE (${nomor_naskah}); nomor di sini adalah nomor internal/registri.
"""
import datetime as dt

from fastapi import APIRouter, Body, Depends

from .core import Gagal, audit, auth, get_db, perlu_baca

router = APIRouter(prefix="/api/nomor")
ROMAWI = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _jenis(db, kode: str) -> dict:
    j = db.execute("SELECT * FROM jenis_nomor WHERE kode=? AND aktif=1", (kode,)).fetchone()
    if not j:
        raise Gagal(f"Jenis penomoran {kode} tidak ada/nonaktif. Atur di menu Penomoran Surat.")
    return j


def _urut_berikut(db, jenis: str, tahun: int) -> int:
    a = db.execute("SELECT COALESCE(MAX(nomor_urut),0) m FROM surat_tugas WHERE jenis_nomor=? AND tahun=?", (jenis, tahun)).fetchone()["m"]
    b = db.execute("SELECT COALESCE(MAX(nomor_urut),0) m FROM nomor_surat WHERE jenis=? AND tahun=?", (jenis, tahun)).fetchone()["m"]
    return max(a, b) + 1


def bentuk_nomor(db, jenis: str, tanggal: str, klasifikasi: str | None = None) -> tuple[str, int]:
    """Nomor berikut untuk `jenis` pada tahun `tanggal` -> (nomor_terformat, nomor_urut)."""
    j = _jenis(db, jenis)
    d = dt.date.fromisoformat(tanggal[:10])
    urut = _urut_berikut(db, jenis, d.year)
    nomor = (j["format"].replace("{klasifikasi}", (klasifikasi or j["klasifikasi"]).strip()).replace("{yymm}", f"{d.year % 100:02d}{d.month:02d}")
             .replace("{urut}", f"{urut:03d}").replace("{unit}", j["unit"]).replace("{bulan_romawi}", ROMAWI[d.month - 1]).replace("{tahun}", str(d.year)))
    return nomor, urut


nomor_berikut = _urut_berikut
pasang_nomor = bentuk_nomor


@router.get("/jenis")
def daftar_jenis(user=Depends(perlu_baca), db=Depends(get_db)):
    return db.execute("SELECT * FROM jenis_nomor ORDER BY kode").fetchall()


@router.put("/jenis/{kode}")
def ubah_jenis(kode: str, body: dict = Body(default={}), user=Depends(auth), db=Depends(get_db)):
    if user["role"] != "kepala":
        raise Gagal("Hanya Kepala Puskesmas yang dapat mengubah kode penomoran.", 403)
    j = db.execute("SELECT * FROM jenis_nomor WHERE kode=?", (kode,)).fetchone()
    if not j:
        raise Gagal("Jenis tidak ditemukan.", 404)
    klas, unit = str(body.get("klasifikasi") or j["klasifikasi"]).strip(), str(body.get("unit") or j["unit"]).strip()
    fmt = str(body.get("format") or j["format"]).strip()
    if not klas or not unit or "{urut}" not in fmt:
        raise Gagal("Klasifikasi & unit wajib diisi; format harus memuat {urut}.")
    db.execute("UPDATE jenis_nomor SET klasifikasi=?, unit=?, format=?, keterangan=?, aktif=? WHERE kode=?",
               (klas, unit, fmt, body.get("keterangan", j["keterangan"]), 0 if body.get("aktif") in (False, 0, "0") else 1, kode))
    audit(db, user, "jenis_nomor", None, "UBAH", j, {"kode": kode, "klasifikasi": klas, "unit": unit, "format": fmt})
    return {"ok": 1}


@router.get("")
def daftar(tahun: int, jenis: str | None = None, user=Depends(perlu_baca), db=Depends(get_db)):
    q, a = ["n.tahun=?"], [tahun]
    if jenis:
        q.append("n.jenis=?")
        a.append(jenis)
    return db.execute(f"SELECT n.* FROM nomor_surat n WHERE {' AND '.join(q)} ORDER BY n.id DESC", a).fetchall()


@router.get("/pratinjau")
def pratinjau(jenis: str = "UMUM", tanggal: str | None = None, klasifikasi: str | None = None, user=Depends(perlu_baca), db=Depends(get_db)):
    return {"nomor": bentuk_nomor(db, jenis, tanggal or dt.date.today().isoformat(), klasifikasi)[0]}


CADANGAN = "(nomor dicadangkan — perihal belum diisi)"


@router.put("/{nid}/perihal")
def isi_perihal(nid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    """Mengisi perihal/tujuan nomor yang dicadangkan (generate otomatis). Nomor tidak berubah."""
    n = db.execute("SELECT * FROM nomor_surat WHERE id=?", (nid,)).fetchone()
    if not n:
        raise Gagal("Nomor tidak ditemukan.", 404)
    if user["role"] not in ("kepala", "bendahara", "bendahara_blud") and n["dibuat_oleh"] != user["username"]:
        raise Gagal("Hanya pembuat nomor atau pengelola yang dapat mengisi perihal.", 403)
    if n["status"] != "Terbit":
        raise Gagal("Nomor sudah dibatalkan.")
    perihal = str(body.get("perihal") or "").strip()
    if len(perihal) < 3:
        raise Gagal("Perihal wajib diisi.")
    db.execute("UPDATE nomor_surat SET perihal=?, tujuan=? WHERE id=?", (perihal, str(body.get("tujuan") or n["tujuan"] or "").strip() or None, nid))
    audit(db, user, "nomor_surat", nid, "ISI-PERIHAL", {"perihal": n["perihal"]}, {"perihal": perihal})
    return {"ok": True}


@router.post("")
def terbit(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    """Terbitkan nomor untuk surat umum/lainnya. Jenis ST-* otomatis lewat Surat Tugas, bukan di sini."""
    jenis = str(body.get("jenis") or "UMUM")
    if jenis.startswith("ST-"):
        raise Gagal("Nomor Surat Tugas diterbitkan otomatis dari menu Surat Tugas & SPD.")
    j = _jenis(db, jenis)
    try:
        tanggal = dt.date.fromisoformat(str(body.get("tanggal") or dt.date.today().isoformat())[:10]).isoformat()
    except ValueError:
        raise Gagal("Tanggal tidak valid.")
    perihal = str(body.get("perihal") or "").strip() or CADANGAN   # generate otomatis: perihal boleh diisi nanti
    klas = str(body.get("klasifikasi") or j["klasifikasi"]).strip()
    nomor, urut = bentuk_nomor(db, jenis, tanggal, klas)
    nid = db.execute("INSERT INTO nomor_surat(jenis,tahun,nomor_urut,nomor,klasifikasi,tanggal,perihal,tujuan,dibuat_oleh) VALUES(?,?,?,?,?,?,?,?,?)",
                     (jenis, int(tanggal[:4]), urut, nomor, klas, tanggal, perihal, str(body.get("tujuan") or "").strip() or None, user["username"])).lastrowid
    audit(db, user, "nomor_surat", nid, "TERBIT", None, {"nomor": nomor, "perihal": perihal})
    return {"id": nid, "nomor": nomor}


@router.post("/{nid}/batal")
def batal(nid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    n = db.execute("SELECT * FROM nomor_surat WHERE id=?", (nid,)).fetchone()
    if not n:
        raise Gagal("Nomor tidak ditemukan.", 404)
    if user["role"] not in ("kepala", "bendahara", "bendahara_blud") and n["dibuat_oleh"] != user["username"]:
        raise Gagal("Anda tidak berhak membatalkan nomor ini.", 403)
    if n["status"] != "Terbit":
        raise Gagal("Nomor sudah dibatalkan.")
    alasan = str(body.get("alasan") or "").strip()
    if len(alasan) < 5:
        raise Gagal("Alasan pembatalan wajib diisi (min. 5 karakter).")
    db.execute("UPDATE nomor_surat SET status='Dibatalkan', alasan_batal=? WHERE id=?", (alasan, nid))   # nomor tidak dipakai ulang
    audit(db, user, "nomor_surat", nid, "BATAL", {"nomor": n["nomor"]}, {"alasan": alasan})
    return {"ok": 1}
