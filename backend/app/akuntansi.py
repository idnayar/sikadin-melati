"""Tahap 6 — modul akuntansi BLU (PSAP 13): bagan akun, jurnal, saldo awal, pendapatan, anggaran pendapatan.
Laporan keuangan SATU KESATUAN (semua sumber dana) → seluruh modul ini hanya untuk Kepala dan Bendahara BLUD.
SPJ yang dibayar otomatis menjadi jurnal kas (Dr belanja / Cr kas); koreksi pembayaran membuat jurnal balik."""
import datetime as dt

from fastapi import APIRouter, Body, Depends

from .core import Gagal, audit, auth, get_db

router = APIRouter(prefix="/api/akun")
KAS_BLUD, KAS_BOK = "1.1.1.02", "1.1.1.01"


def pastikan(user: dict) -> dict:
    if user["role"] not in ("kepala", "bendahara_blud"):
        raise Gagal("Akuntansi dan laporan keuangan gabungan hanya untuk Kepala dan Bendahara BLUD.", 403)
    return user


def akses(user=Depends(auth)):
    return pastikan(user)


def _akun(db, kode):
    a = db.execute("SELECT * FROM akun WHERE kode=?", (kode,)).fetchone()
    if not a:
        raise Gagal(f"Akun {kode} tidak ada.", 500)
    return a


def kode_kas(dana: str) -> str:
    return KAS_BLUD if str(dana).upper() == "BLUD" else KAS_BOK


def peta_belanja(jenis_belanja: str) -> str:
    """Jenis belanja pada RAB -> kode akun. Dipakai jurnal otomatis SPJ dan anggaran belanja pada LRA."""
    j = str(jenis_belanja or "").lower()
    if "perjalanan" in j:
        return "5.1.2.02"
    if any(k in j for k in ("insentif", "honor", "gaji", "jasa pelayanan", "pegawai")):
        return "5.1.1.01"
    if any(k in j for k in ("obat", "bmhp", "alkes")):
        return "5.1.2.03"
    if any(k in j for k in ("modal", "peralatan", "mesin", "laptop", "komputer", "printer")):
        return "1.3.2.01"
    return "5.1.2.01"


def _tgl(v, nama="Tanggal") -> str:
    try:
        return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise Gagal(f"{nama} tidak valid (format TTTT-BB-HH).")


def _int(v, nama="Jumlah") -> int:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        raise Gagal(f"{nama} harus berupa angka.")
    if n < 0:
        raise Gagal(f"{nama} tidak boleh negatif.")
    return n


def buat_jurnal(db, user, tanggal, uraian, basis, baris, sumber_id=None, no_bukti=None, ref=(None, None)) -> int:
    """baris = [(akun_id, debit, kredit)]. Wajib seimbang dan minimal dua baris."""
    baris = [(a, int(d or 0), int(k or 0)) for a, d, k in baris if int(d or 0) or int(k or 0)]
    if len(baris) < 2:
        raise Gagal("Jurnal minimal memuat dua baris bernilai.")
    td, tk = sum(b[1] for b in baris), sum(b[2] for b in baris)
    if td != tk:
        raise Gagal(f"Jurnal tidak seimbang: debit {td:,} ≠ kredit {tk:,}.".replace(",", "."))
    jid = db.execute("INSERT INTO jurnal(tahun,tanggal,no_bukti,uraian,basis,sumber_dana_id,ref_jenis,ref_id,dibuat_oleh) VALUES(?,?,?,?,?,?,?,?,?)",
                     (int(tanggal[:4]), tanggal, no_bukti, uraian, basis, sumber_id, ref[0], ref[1], user["username"])).lastrowid
    for a, d, k in baris:
        db.execute("INSERT INTO jurnal_baris(jurnal_id,akun_id,debit,kredit) VALUES(?,?,?,?)", (jid, a, d, k))
    return jid


# ---- dipanggil modul SPJ (tanpa pembatasan peran: pencatatan otomatis oleh sistem) ----
def jurnal_spj_bayar(db, user, spj: dict) -> None:
    n = lambda j: db.execute("SELECT COUNT(*) c FROM jurnal WHERE ref_jenis=? AND ref_id=?", (j, spj["id"])).fetchone()["c"]  # noqa: E731
    if n("SPJ") > n("SPJ_BALIK"):
        return
    b = db.execute("SELECT jenis_belanja FROM bok_baris WHERE id=?", (spj["baris_id"],)).fetchone()
    beban = _akun(db, peta_belanja(b["jenis_belanja"] if b else ""))
    kas = _akun(db, kode_kas(spj["dana"]))
    buat_jurnal(db, user, spj["tanggal_bayar"], f"SPJ {spj['uraian']}", "KAS", [(beban["id"], spj["total"], 0), (kas["id"], 0, spj["total"])],
                spj["sumber_dana_id"], spj.get("no_bukti"), ("SPJ", spj["id"]))


def jurnal_spj_koreksi(db, user, spj: dict) -> None:
    j = db.execute("SELECT * FROM jurnal WHERE ref_jenis='SPJ' AND ref_id=? ORDER BY id DESC LIMIT 1", (spj["id"],)).fetchone()
    if not j or db.execute("SELECT COUNT(*) c FROM jurnal WHERE ref_jenis='SPJ_BALIK' AND ref_id=?", (spj["id"],)).fetchone()["c"] >= db.execute(
            "SELECT COUNT(*) c FROM jurnal WHERE ref_jenis='SPJ' AND ref_id=?", (spj["id"],)).fetchone()["c"]:
        return
    ls = db.execute("SELECT akun_id, debit, kredit FROM jurnal_baris WHERE jurnal_id=?", (j["id"],)).fetchall()
    buat_jurnal(db, user, dt.date.today().isoformat() if dt.date.today().isoformat() >= j["tanggal"] else j["tanggal"], f"Koreksi pembayaran: {j['uraian']}", "KAS",
                [(x["akun_id"], x["kredit"], x["debit"]) for x in ls], j["sumber_dana_id"], j["no_bukti"], ("SPJ_BALIK", spj["id"]))


# ---------------------------------------------------------------- bagan akun
@router.get("")
def daftar_akun(user=Depends(akses), db=Depends(get_db)):
    return db.execute("SELECT a.*, (SELECT COUNT(*) FROM jurnal_baris b WHERE b.akun_id=a.id) dipakai FROM akun a ORDER BY kode").fetchall()


@router.post("")
def tambah_akun(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    kode, nama, jenis = str(body.get("kode") or "").strip(), str(body.get("nama") or "").strip(), str(body.get("jenis") or "")
    if not kode or not nama or jenis not in ("ASET", "KEWAJIBAN", "EKUITAS", "PENDAPATAN", "BEBAN"):
        raise Gagal("Kode, nama, dan jenis akun wajib diisi dengan benar.")
    normal = "K" if (jenis in ("KEWAJIBAN", "EKUITAS", "PENDAPATAN") or body.get("normal") == "K") else "D"
    lra = body.get("lra") if body.get("lra") in ("BELANJA_MODAL", "PEMBIAYAAN") else None
    arus = body.get("arus") if body.get("arus") in ("OPERASI", "INVESTASI", "PENDANAAN") else "OPERASI"
    kas = 1 if (jenis == "ASET" and body.get("kas")) else 0
    aid = db.execute("INSERT INTO akun(kode,nama,jenis,normal,kas,arus,lra) VALUES(?,?,?,?,?,?,?)", (kode, nama, jenis, normal, kas, arus, lra)).lastrowid
    audit(db, user, "akun", aid, "BUAT", None, {"kode": kode, "nama": nama, "jenis": jenis}, "BLUD")
    return {"id": aid}


@router.put("/{aid:int}")
def ubah_akun(aid: int, body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    a = db.execute("SELECT * FROM akun WHERE id=?", (aid,)).fetchone()
    if not a:
        raise Gagal("Akun tidak ditemukan.", 404)
    pakai = db.execute("SELECT COUNT(*) c FROM jurnal_baris WHERE akun_id=?", (aid,)).fetchone()["c"]
    nama = str(body.get("nama", a["nama"]) or "").strip() or a["nama"]
    aktif = 1 if body.get("aktif", a["aktif"]) else 0
    if pakai and ("jenis" in body and body["jenis"] != a["jenis"] or "kas" in body and int(bool(body["kas"])) != a["kas"]):
        raise Gagal("Jenis/kas akun tidak dapat diubah karena sudah dipakai jurnal.")
    db.execute("UPDATE akun SET nama=?, aktif=? WHERE id=?", (nama, aktif, aid))
    audit(db, user, "akun", aid, "UBAH", {"nama": a["nama"], "aktif": a["aktif"]}, {"nama": nama, "aktif": aktif}, "BLUD")
    return {"ok": True}


# ---------------------------------------------------------------- jurnal
def _jurnal_rows(db, where, args):
    js = db.execute(f"SELECT j.*, sd.kode dana FROM jurnal j LEFT JOIN sumber_dana sd ON sd.id=j.sumber_dana_id WHERE {where} ORDER BY j.tanggal DESC, j.id DESC", args).fetchall()
    for j in js:
        j["baris"] = db.execute("SELECT b.akun_id, a.kode, a.nama, b.debit, b.kredit FROM jurnal_baris b JOIN akun a ON a.id=b.akun_id WHERE b.jurnal_id=? ORDER BY b.id", (j["id"],)).fetchall()
        j["total"] = sum(x["debit"] for x in j["baris"])
    return js


@router.get("/jurnal")
def daftar_jurnal(tahun: int, basis: str = "", user=Depends(akses), db=Depends(get_db)):
    return _jurnal_rows(db, "j.tahun=? AND (?='' OR j.basis=?)", (tahun, basis, basis))


def _baris_input(db, baris):
    out = []
    for x in baris or []:
        a = db.execute("SELECT id, aktif FROM akun WHERE id=?", (x.get("akun_id"),)).fetchone()
        if not a or not a["aktif"]:
            raise Gagal("Akun pada jurnal tidak ditemukan atau nonaktif.")
        out.append((a["id"], _int(x.get("debit") or 0, "Debit"), _int(x.get("kredit") or 0, "Kredit")))
    for _, d, k in out:
        if d and k:
            raise Gagal("Satu baris jurnal tidak boleh berisi debit sekaligus kredit.")
    return out


@router.post("/jurnal")
def tambah_jurnal(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    basis = body.get("basis") if body.get("basis") in ("KAS", "AKRUAL") else "AKRUAL"
    uraian = str(body.get("uraian") or "").strip()
    if len(uraian) < 3:
        raise Gagal("Uraian jurnal wajib diisi.")
    sd = body.get("sumber_dana_id") or None
    jid = buat_jurnal(db, user, _tgl(body.get("tanggal")), uraian, basis, _baris_input(db, body.get("baris")), sd, str(body.get("no_bukti") or "").strip() or None)
    audit(db, user, "jurnal", jid, "BUAT", None, {"uraian": uraian, "basis": basis}, "BLUD")
    return {"id": jid}


@router.delete("/jurnal/{jid}")
def hapus_jurnal(jid: int, user=Depends(akses), db=Depends(get_db)):
    j = db.execute("SELECT * FROM jurnal WHERE id=?", (jid,)).fetchone()
    if not j:
        raise Gagal("Jurnal tidak ditemukan.", 404)
    if j["ref_jenis"]:
        raise Gagal("Jurnal otomatis dari SPJ tidak dapat dihapus; koreksi lewat SPJ (Kepala).", 403)
    if j["basis"] == "AWAL":
        raise Gagal("Saldo awal diubah lewat menu Saldo Awal.", 403)
    db.execute("DELETE FROM jurnal WHERE id=?", (jid,))
    audit(db, user, "jurnal", jid, "HAPUS", {"uraian": j["uraian"], "tanggal": j["tanggal"]}, None, "BLUD")
    return {"ok": True}


@router.post("/pendapatan")
def catat_pendapatan(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    """Penerimaan pendapatan tunai: Dr Kas (sesuai sumber dana) / Cr Akun pendapatan."""
    a = db.execute("SELECT * FROM akun WHERE id=? AND jenis='PENDAPATAN' AND aktif=1", (body.get("akun_id"),)).fetchone()
    if not a:
        raise Gagal("Pilih akun pendapatan.")
    sd = db.execute("SELECT id, kode FROM sumber_dana WHERE kode=?", (str(body.get("sumber") or "").upper(),)).fetchone()
    if not sd:
        raise Gagal("Pilih sumber dana.")
    jml = _int(body.get("jumlah"))
    if jml <= 0:
        raise Gagal("Jumlah harus lebih dari nol.")
    kas = _akun(db, kode_kas(sd["kode"]))
    uraian = str(body.get("uraian") or "").strip() or a["nama"]
    jid = buat_jurnal(db, user, _tgl(body.get("tanggal")), uraian, "KAS", [(kas["id"], jml, 0), (a["id"], 0, jml)], sd["id"], str(body.get("no_bukti") or "").strip() or None, ("PENDAPATAN", None))
    audit(db, user, "jurnal", jid, "PENDAPATAN", None, {"akun": a["kode"], "sumber": sd["kode"], "jumlah": jml}, "BLUD")
    return {"id": jid}


# ---------------------------------------------------------------- saldo awal & anggaran pendapatan
@router.get("/saldo-awal")
def lihat_saldo_awal(tahun: int, user=Depends(akses), db=Depends(get_db)):
    ada = {r["akun_id"]: r for r in db.execute("SELECT b.akun_id, SUM(b.debit) debit, SUM(b.kredit) kredit FROM jurnal_baris b JOIN jurnal j ON j.id=b.jurnal_id WHERE j.basis='AWAL' AND j.tahun=? GROUP BY b.akun_id", (tahun,)).fetchall()}
    return [{**a, "debit": ada.get(a["id"], {}).get("debit", 0), "kredit": ada.get(a["id"], {}).get("kredit", 0)}
            for a in db.execute("SELECT id, kode, nama, jenis, normal FROM akun WHERE jenis IN ('ASET','KEWAJIBAN','EKUITAS') AND aktif=1 ORDER BY kode").fetchall()]


@router.put("/saldo-awal")
def simpan_saldo_awal(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    """Mengganti seluruh saldo awal tahun tersebut (Neraca awal). Aset harus = Kewajiban + Ekuitas."""
    tahun = int(body.get("tahun") or 0)
    if not 2000 < tahun < 2100:
        raise Gagal("Tahun tidak valid.")
    nilai = []
    for x in body.get("saldo") or []:
        a = db.execute("SELECT * FROM akun WHERE id=? AND jenis IN ('ASET','KEWAJIBAN','EKUITAS')", (x.get("akun_id"),)).fetchone()
        if not a:
            raise Gagal("Saldo awal hanya untuk akun Aset, Kewajiban, dan Ekuitas.")
        v = _int(x.get("saldo") or 0, f"Saldo {a['nama']}")
        if v:
            nilai.append((a, v))
    aset = sum(v if a["normal"] == "D" else -v for a, v in nilai if a["jenis"] == "ASET")
    pasiva = sum(v for a, v in nilai if a["jenis"] != "ASET")
    if aset != pasiva:
        raise Gagal(f"Saldo awal tidak seimbang: Aset {aset:,} ≠ Kewajiban + Ekuitas {pasiva:,}.".replace(",", "."))
    lama = db.execute("SELECT id FROM jurnal WHERE basis='AWAL' AND tahun=?", (tahun,)).fetchall()
    for j in lama:
        db.execute("DELETE FROM jurnal WHERE id=?", (j["id"],))
    if nilai:
        baris = [(a["id"], v if a["normal"] == "D" else 0, v if a["normal"] == "K" else 0) for a, v in nilai]
        buat_jurnal(db, user, f"{tahun}-01-01", f"Saldo awal {tahun}", "AWAL", baris)
    audit(db, user, "jurnal", tahun, "SALDO-AWAL", {"jurnal_lama": len(lama)}, {"akun": len(nilai), "aset": aset}, "BLUD")
    return {"ok": True, "aset": aset}


@router.get("/anggaran-pendapatan")
def lihat_anggaran(tahun: int, user=Depends(akses), db=Depends(get_db)):
    ada = {r["akun_id"]: r["jumlah"] for r in db.execute("SELECT akun_id, jumlah FROM anggaran_pendapatan WHERE tahun=?", (tahun,)).fetchall()}
    return [{**a, "jumlah": ada.get(a["id"], 0)} for a in db.execute("SELECT id, kode, nama FROM akun WHERE jenis='PENDAPATAN' AND aktif=1 ORDER BY kode").fetchall()]


@router.put("/anggaran-pendapatan")
def simpan_anggaran(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    tahun = int(body.get("tahun") or 0)
    for x in body.get("anggaran") or []:
        if not db.execute("SELECT 1 FROM akun WHERE id=? AND jenis='PENDAPATAN'", (x.get("akun_id"),)).fetchone():
            raise Gagal("Akun anggaran harus akun pendapatan.")
        db.execute("INSERT INTO anggaran_pendapatan(tahun,akun_id,jumlah) VALUES(?,?,?) ON CONFLICT(tahun,akun_id) DO UPDATE SET jumlah=excluded.jumlah", (tahun, x["akun_id"], _int(x.get("jumlah") or 0)))
    audit(db, user, "anggaran_pendapatan", tahun, "UBAH", None, {"akun": len(body.get("anggaran") or [])}, "BLUD")
    return {"ok": True}
