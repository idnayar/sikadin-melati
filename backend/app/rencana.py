"""Perencanaan (RPK/POA) — estimasi biaya dari tarif Perbup, kontrol pagu real-time, alur status."""
import json
import re

from fastapi import APIRouter, Body, Depends

from .calc import hitung
from .core import Gagal, akses_sumber, audit, cek_sumber, get_db, kode_sd, perlu_baca, sumber_boleh

router = APIRouter(prefix="/api/rencana")
ALUR = {"Draft→Diajukan": "tulis", "Diajukan→Disetujui": "kepala", "Diajukan→Ditolak": "kepala",
        "Diajukan→Draft": "tulis", "Ditolak→Draft": "tulis", "Disetujui→Draft": "kepala"}
KOL = ["tahun", "bulan", "sumber_dana_id", "baris_id", "kegiatan", "kode_rekening", "lokasi_id", "jenis_perjalanan", "durasi", "jumlah_petugas", "jumlah_hari",
       "frekuensi", "tingkat", "roda", "menginap", "pp", "transport_manual", "estimasi_manual", "estimasi", "catatan"]


def _int(v, label, minimum=1, default=None):
    if (v is None or v == "") and default is not None:
        return default
    try:
        x = float(v)
        if x != int(x) or x < minimum:
            raise ValueError
    except (TypeError, ValueError):
        raise Gagal(f"{label} harus bilangan bulat ≥ {minimum}.")
    return int(x)


def _rpt(n) -> str:
    return "Rp" + f"{int(n):,}".replace(",", ".")


def _info_baris(db, bid):
    return db.execute("""SELECT b.*, r.nama rincian, r.no rincian_no, r.id rincian_id, m.nama menu, m.no menu_no, m.tahun, m.sumber_dana_id sd_id
        FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id WHERE b.id=?""", (bid,)).fetchone()


def analisis(db, b: dict, excl: int = 0) -> dict:
    """Hitung estimasi + cek pagu. Dipakai oleh preview, simpan, dan perubahan status."""
    baris = _info_baris(db, _int(b.get("baris_id"), "Pos anggaran (baris RAB)"))
    if not baris:
        raise Gagal("Pos anggaran (baris RAB) tidak ditemukan.")
    tahun, sd, kode = baris["tahun"], baris["sd_id"], kode_sd(db, baris["sd_id"])
    d = {
        "tahun": tahun, "sumber_dana_id": sd, "bulan": _int(b.get("bulan"), "Bulan"), "baris_id": baris["id"], "kegiatan": str(b.get("kegiatan") or "").strip(),
        "kode_rekening": str(b.get("kode_rekening") or baris["kode_rekening"] or "").strip() or None,
        "lokasi_id": _int(b.get("lokasi_id"), "Lokasi") if b.get("lokasi_id") else None, "durasi": "le8" if b.get("durasi") == "le8" else "gt8",
        "jumlah_petugas": _int(b.get("jumlah_petugas"), "Jumlah petugas", 1, 1), "jumlah_hari": _int(b.get("jumlah_hari"), "Jumlah hari", 1, 1),
        "frekuensi": _int(b.get("frekuensi"), "Frekuensi pelaksanaan", 1, 1), "tingkat": "C" if b.get("tingkat") == "C" else "D",
        "roda": 4 if str(b.get("roda")) == "4" else 2, "menginap": b.get("menginap") if b.get("menginap") in ("hotel", "tidak_hotel") else "tidak",
        "pp": 0 if b.get("pp") in (False, 0, "0") else 1, "transport_manual": _int(b.get("transport_manual"), "Transport manual", 0, 0),
        "estimasi_manual": _int(b.get("estimasi_manual"), "Estimasi manual", 0, 0), "catatan": str(b.get("catatan") or "").strip() or None,
    }
    if d["bulan"] > 12:
        raise Gagal("Bulan harus 1–12.")
    if not d["kegiatan"]:
        d["kegiatan"] = baris["komponen"] or baris["rincian"]
    perjalanan = bool(re.search("perjalanan dinas", baris["jenis_belanja"], re.I))
    peringatan, galat_dasar = [], []
    if perjalanan:
        if not d["lokasi_id"]:
            raise Gagal("Lokasi tujuan wajib diisi untuk perjalanan dinas.")
        lok = db.execute("SELECT * FROM lokasi WHERE id=?", (d["lokasi_id"],)).fetchone()
        if not lok:
            raise Gagal("Lokasi tidak ditemukan.")
        d["jenis_perjalanan"] = lok["jenis"]
        h = hitung(db, {"tingkat": d["tingkat"], "lokasi_id": d["lokasi_id"], "tahun": tahun, "durasi": d["durasi"], "hari": d["jumlah_hari"],
                        "roda": d["roda"], "menginap": d["menginap"], "pp": bool(d["pp"]), "transport_manual": d["transport_manual"]})
        kali = d["jumlah_petugas"] * d["frekuensi"]
        estimasi = h["total"] * kali
        rincian = {"per_orang": h["baris"], "total_per_orang": h["total"], "pengali": kali, "tarif_tahun": h["tahun"]}
        peringatan += h["peringatan"]
        if h["total"] == 0:
            galat_dasar.append("Estimasi Rp0: periksa durasi (≤ 8 jam hanya transport lokal), lokasi, tarif master, atau isi transport manual.")
    else:
        d["jenis_perjalanan"] = None
        if not d["estimasi_manual"]:
            raise Gagal('Pos anggaran ini bukan perjalanan dinas: isi "Estimasi biaya (Rp)".')
        estimasi, rincian = d["estimasi_manual"], {"manual": True}
    d["estimasi"] = estimasi

    terpakai = db.execute("SELECT COALESCE(SUM(estimasi),0) s FROM rencana WHERE baris_id=? AND status!='Ditolak' AND id!=?", (baris["id"], excl)).fetchone()["s"]
    sisa_sebelum = baris["jumlah"] - terpakai
    sisa_sesudah = sisa_sebelum - estimasi
    pg = db.execute("SELECT pagu FROM bok_pagu WHERE tahun=? AND sumber_dana_id=?", (tahun, sd)).fetchone()
    pagu = pg["pagu"] if pg else None
    dipakai_bok = db.execute("SELECT COALESCE(SUM(estimasi),0) s FROM rencana WHERE tahun=? AND sumber_dana_id=? AND status!='Ditolak' AND id!=?", (tahun, sd, excl)).fetchone()["s"]
    sisa_bok = None if pagu is None else pagu - dipakai_bok - estimasi
    rinc_pagu = db.execute("SELECT COALESCE(SUM(jumlah),0) s FROM bok_baris WHERE rincian_id=?", (baris["rincian_id"],)).fetchone()["s"]
    rinc_terpakai = db.execute("""SELECT COALESCE(SUM(r.estimasi),0) s FROM rencana r JOIN bok_baris b ON b.id=r.baris_id
        WHERE b.rincian_id=? AND r.status!='Ditolak' AND r.id!=?""", (baris["rincian_id"], excl)).fetchone()["s"]
    galat = list(galat_dasar)
    if sisa_sesudah < 0:
        galat.append(f"Melebihi pagu pos anggaran: sisa {_rpt(sisa_sebelum)}, rencana {_rpt(estimasi)} (kurang {_rpt(-sisa_sesudah)}).")
    if sisa_bok is not None and sisa_bok < 0:
        galat.append(f"Melebihi pagu {kode} {tahun}: sisa {_rpt(pagu - dipakai_bok)}, rencana {_rpt(estimasi)}.")
    if pagu is None:
        peringatan.append(f"Pagu {kode} {tahun} belum diatur di menu Pagu Anggaran {kode}.")
    amb = db.execute("SELECT nilai FROM pengaturan WHERE kunci='ambang_pagu_peringatan'").fetchone()
    amb = float(amb["nilai"]) if amb else 10
    if not galat and baris["jumlah"] > 0 and sisa_sesudah / baris["jumlah"] * 100 < amb:
        peringatan.append(f"Sisa pagu pos anggaran tinggal {sisa_sesudah / baris['jumlah'] * 100:.1f}%.")
    return {
        "d": d, "sumber": kode, "perjalanan": perjalanan, "rincian": rincian, "estimasi": estimasi, "galat": galat, "peringatan": peringatan, "ok": not galat,
        "pos": {"baris_id": baris["id"], "label": f"{baris['rincian_no'] or ''}. {baris['rincian']}", "komponen": baris["komponen"], "jenis": baris["jenis_belanja"],
                "uraian": baris["uraian"], "pagu": baris["jumlah"], "terpakai": terpakai, "sisa_sebelum": sisa_sebelum, "sisa_sesudah": sisa_sesudah},
        "kegiatan": {"pagu": rinc_pagu, "terpakai": rinc_terpakai, "sisa_sesudah": rinc_pagu - rinc_terpakai - estimasi},
        "bok": {"pagu": pagu, "terpakai": dipakai_bok, "sisa_sesudah": sisa_bok},
    }


def bisa_ubah(db, u, r) -> bool:
    """Boleh mengubah rencana: harus berhak atas sumber dananya (BLUD: hanya Kepala & Bendahara BLUD); Pengelola Program hanya miliknya."""
    if not akses_sumber(u, kode_sd(db, r["sumber_dana_id"]), "rencana"):
        return False
    return u["role"] in ("kepala", "bendahara", "bendahara_blud") or (u["role"] == "program" and r["dibuat_oleh"] == u["username"])


@router.get("/opsi")
def opsi(tahun: int, sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "baca")
    rows = db.execute("""SELECT b.id, b.komponen, b.jenis_belanja, b.uraian, b.jumlah, b.kode_rekening, r.id rincian_id, r.no rincian_no, r.nama rincian, m.no menu_no, m.nama menu,
        b.jumlah - COALESCE((SELECT SUM(estimasi) FROM rencana x WHERE x.baris_id=b.id AND x.status!='Ditolak'),0) sisa
        FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id
        WHERE m.tahun=? AND m.sumber_dana_id=(SELECT id FROM sumber_dana WHERE kode=?) ORDER BY m.urut, r.urut, b.urut""", (tahun, sumber.upper())).fetchall()
    for x in rows:
        x["perjalanan"] = bool(re.search("perjalanan dinas", x["jenis_belanja"], re.I))
    return rows


@router.post("/preview")
def preview(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    try:
        a = analisis(db, body, int(body.get("id") or 0))
    except Gagal as e:
        return {"error": e.pesan, "galat": [e.pesan], "peringatan": [], "ok": False}
    cek_sumber(user, a["sumber"], "rencana")
    a.pop("d")
    return a


@router.get("/poa")
def poa(tahun: int, sumber: str = "BOK", user=Depends(perlu_baca), db=Depends(get_db)):
    cek_sumber(user, sumber, "baca")
    rows = db.execute("""SELECT m.no menu_no, m.nama menu, rc.id rincian_id, rc.no rincian_no, rc.nama rincian,
        (SELECT COALESCE(SUM(jumlah),0) FROM bok_baris WHERE rincian_id=rc.id) pagu FROM bok_rincian rc JOIN bok_menu m ON m.id=rc.menu_id
        WHERE m.tahun=? AND m.sumber_dana_id=(SELECT id FROM sumber_dana WHERE kode=?) ORDER BY m.urut, rc.urut""", (tahun, sumber.upper())).fetchall()
    sums = db.execute("""SELECT b.rincian_id, r.bulan, SUM(r.estimasi) s FROM rencana r JOIN bok_baris b ON b.id=r.baris_id
        WHERE r.tahun=? AND r.status!='Ditolak' GROUP BY b.rincian_id, r.bulan""", (tahun,)).fetchall()
    by = {x["rincian_id"]: x for x in rows}
    for x in rows:
        x["bulan"] = [0] * 12
    for s in sums:
        if s["rincian_id"] in by:
            by[s["rincian_id"]]["bulan"][s["bulan"] - 1] = s["s"]
    for x in rows:
        x["total"] = sum(x["bulan"])
        x["sisa"] = x["pagu"] - x["total"]
    return rows


@router.get("")
def daftar(tahun: int, bulan: int | None = None, status: str | None = None, sumber: str | None = None, user=Depends(perlu_baca), db=Depends(get_db)):
    q, a = ["m.tahun=?"], [tahun]
    if sumber:
        cek_sumber(user, sumber, "baca")
        q.append("m.sumber_dana_id=(SELECT id FROM sumber_dana WHERE kode=?)")
        a.append(sumber.upper())
    else:  # tanpa filter: hanya sumber yang boleh dilihat pengguna ini
        boleh = sumber_boleh(user, "baca")
        q.append("m.sumber_dana_id IN (SELECT id FROM sumber_dana WHERE kode IN (%s))" % ",".join("?" * len(boleh)))
        a += boleh
    if bulan:
        q.append("r.bulan=?")
        a.append(bulan)
    if status:
        q.append("r.status=?")
        a.append(status)
    rows = db.execute(f"""SELECT r.*, l.nama lokasi, b.komponen, b.jenis_belanja, b.uraian pos_uraian, rc.no rincian_no, rc.nama rincian, m.no menu_no
        FROM rencana r JOIN bok_baris b ON b.id=r.baris_id JOIN bok_rincian rc ON rc.id=b.rincian_id JOIN bok_menu m ON m.id=rc.menu_id
        LEFT JOIN lokasi l ON l.id=r.lokasi_id WHERE {' AND '.join(q)} ORDER BY r.bulan, r.id""", a).fetchall()
    for r in rows:
        r["rincian_biaya"] = json.loads(r["rincian_biaya"]) if r["rincian_biaya"] else None
        r["bisa_ubah"] = bisa_ubah(db, user, r)
    return rows


def _sd_bok(db):
    r = db.execute("SELECT id FROM sumber_dana WHERE kode='BOK'").fetchone()
    if not r:
        raise Gagal("Sumber dana BOK belum ada di master.")
    return r["id"]


@router.post("")
def tambah(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    a = analisis(db, body)
    cek_sumber(user, a["sumber"], "rencana")
    if not a["ok"]:
        raise Gagal(" ".join(a["galat"]))
    d = a["d"]
    rid = db.execute(f"INSERT INTO rencana({','.join(KOL)},rincian_biaya,dibuat_oleh) VALUES({','.join('?' * len(KOL))},?,?)",
                     (*[d.get(k) for k in KOL], json.dumps(a["rincian"], ensure_ascii=False), user["username"])).lastrowid
    audit(db, user, "rencana", rid, "TAMBAH", None, d, a["sumber"])
    return {"id": rid, "peringatan": a["peringatan"]}


@router.put("/{rid}")
def ubah(rid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    lama = db.execute("SELECT * FROM rencana WHERE id=?", (rid,)).fetchone()
    if not lama:
        raise Gagal("Rencana tidak ditemukan.")
    cek_sumber(user, kode_sd(db, lama["sumber_dana_id"]), "baca")
    if not bisa_ubah(db, user, lama):
        raise Gagal("Anda tidak berhak mengubah rencana ini.")
    if lama["status"] != "Draft":
        raise Gagal("Hanya rencana berstatus Draft yang dapat diubah. Tarik kembali ke Draft terlebih dahulu.")
    a = analisis(db, {**body, "id": rid}, rid)
    cek_sumber(user, a["sumber"], "rencana")
    if not a["ok"]:
        raise Gagal(" ".join(a["galat"]))
    d = a["d"]
    db.execute(f"UPDATE rencana SET {','.join(k + '=?' for k in KOL)}, rincian_biaya=? WHERE id=?",
               [*[d.get(k) for k in KOL], json.dumps(a["rincian"], ensure_ascii=False), rid])
    audit(db, user, "rencana", rid, "UBAH", lama, d, a["sumber"])
    return {"peringatan": a["peringatan"]}


@router.delete("/{rid}")
def hapus(rid: int, user=Depends(perlu_baca), db=Depends(get_db)):
    lama = db.execute("SELECT * FROM rencana WHERE id=?", (rid,)).fetchone()
    if not lama:
        raise Gagal("Rencana tidak ditemukan.")
    if not bisa_ubah(db, user, lama):
        raise Gagal("Anda tidak berhak menghapus rencana ini.")
    if lama["status"] != "Draft":
        raise Gagal("Hanya rencana Draft yang dapat dihapus.")
    db.execute("DELETE FROM rencana WHERE id=?", (rid,))
    audit(db, user, "rencana", rid, "HAPUS", lama, None, kode_sd(db, lama["sumber_dana_id"]))
    return {"ok": 1}


@router.post("/{rid}/status")
def ubah_status(rid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    lama = db.execute("SELECT * FROM rencana WHERE id=?", (rid,)).fetchone()
    if not lama:
        raise Gagal("Rencana tidak ditemukan.")
    cek_sumber(user, kode_sd(db, lama["sumber_dana_id"]), "rencana" if user["role"] != "kepala" else "baca")
    ke = str(body.get("ke") or "")
    syarat = ALUR.get(f"{lama['status']}→{ke}")
    if not syarat:
        raise Gagal(f"Perubahan status {lama['status']} → {ke} tidak diizinkan.")
    if syarat == "kepala" and user["role"] != "kepala":
        raise Gagal("Hanya Kepala Puskesmas yang dapat menyetujui/menolak.")
    if syarat == "tulis" and not bisa_ubah(db, user, lama):
        raise Gagal("Anda tidak berhak mengubah status rencana ini.")
    alasan = str(body.get("alasan") or "").strip()
    if ke == "Ditolak" and not alasan:
        raise Gagal("Alasan penolakan wajib diisi.")
    if ke in ("Diajukan", "Disetujui"):
        a = analisis(db, lama, rid)
        if not a["ok"]:
            raise Gagal(" ".join(a["galat"]))
    now = "datetime('now','localtime')"
    if ke == "Diajukan":
        db.execute(f"UPDATE rencana SET status=?, diajukan_pada={now}, alasan_tolak=NULL WHERE id=?", (ke, rid))
    elif ke in ("Disetujui", "Ditolak"):
        db.execute(f"UPDATE rencana SET status=?, diputuskan_oleh=?, diputuskan_pada={now}, alasan_tolak=? WHERE id=?",
                   (ke, user["username"], alasan if ke == "Ditolak" else None, rid))
    else:
        db.execute("UPDATE rencana SET status=? WHERE id=?", (ke, rid))
    audit(db, user, "rencana", rid, "STATUS", {"status": lama["status"]}, {"status": ke, **({"alasan": alasan} if alasan else {})}, kode_sd(db, lama["sumber_dana_id"]))
    return {"ok": 1}
