"""Penjadwalan dinas luar + aturan anti-doubling.

Aturan divalidasi di sini (pesan jelas + saran pengganti) DAN dikunci oleh constraint database
(lihat tabel penugasan_hari / jadwal_hari + trigger libur/cuti di db.py), sehingga tetap aman
walau ada dua permintaan bersamaan atau data diubah lewat jalur lain.
"""
import datetime as dt
import sqlite3

from fastapi import APIRouter, Body, Depends

from .core import Gagal, audit, get_db, perlu_baca

router = APIRouter(prefix="/api/jadwal")
AKTIF = ("Diusulkan", "Disetujui", "Terlaksana")
HARI_MAKS = 31


def _tgl(s, label):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        raise Gagal(f"{label} tidak valid (format YYYY-MM-DD).")


def _fmt(d) -> str:
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d-%m-%Y")


def _rentang(mulai: dt.date, selesai: dt.date) -> list[str]:
    return [(mulai + dt.timedelta(days=i)).isoformat() for i in range((selesai - mulai).days + 1)]


def _setting(db, k, d):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    try:
        return float(r["nilai"]) if r else d
    except (TypeError, ValueError):
        return d


def _bisa_ubah(u, j) -> bool:
    return u["role"] in ("kepala", "bendahara") or (u["role"] == "program" and j["dibuat_oleh"] == u["username"])


def _beban_bulan(db, pegawai_id, ym, excl=0) -> int:
    return db.execute("SELECT COUNT(*) c FROM penugasan_hari WHERE pegawai_id=? AND tanggal LIKE ? AND jadwal_id!=?", (pegawai_id, ym + "%", excl)).fetchone()["c"]


def pegawai_bebas(db, hari: list[str], exclude: set[int], excl_jadwal=0, program=None) -> list[dict]:
    """Pegawai aktif yang kosong (tanpa jadwal/cuti) pada SEMUA tanggal di `hari`, diurut dari beban terendah."""
    ym = hari[0][:7]
    q = """SELECT p.id, p.nama, p.nip, p.tingkat, p.program, p.jabatan FROM pegawai p
        WHERE p.aktif=1 AND COALESCE(p.jabatan,'') NOT LIKE 'Kepala Puskesmas%'
        AND NOT EXISTS(SELECT 1 FROM penugasan_hari ph WHERE ph.pegawai_id=p.id AND ph.tanggal BETWEEN ? AND ? AND ph.jadwal_id!=?)
        AND NOT EXISTS(SELECT 1 FROM cuti c WHERE c.pegawai_id=p.id AND c.mulai<=? AND c.selesai>=?)"""
    a = [hari[0], hari[-1], excl_jadwal, hari[-1], hari[0]]
    if program:
        q += " AND (p.program=? OR p.ruangan=?)"
        a += [program, program]
    out = []
    for p in db.execute(q, a).fetchall():
        if p["id"] in exclude:
            continue
        p["beban_bulan"] = _beban_bulan(db, p["id"], ym, excl_jadwal)
        p["beban_tahun"] = db.execute("SELECT COUNT(*) c FROM penugasan_hari WHERE pegawai_id=? AND tanggal LIKE ?", (p["id"], ym[:4] + "%")).fetchone()["c"]
        out.append(p)
    out.sort(key=lambda p: (p["beban_bulan"], p["beban_tahun"], p["nama"]))
    return out


def periksa(db, b: dict, excl: int = 0) -> dict:
    """Validasi lengkap. Mengembalikan {ok, galat:[{jenis,pesan,pegawai_id,pengganti}], peringatan:[...], hari:[...]}."""
    galat, peringatan = [], []

    def G(jenis, pesan, pegawai_id=None, pengganti=None):
        galat.append({"jenis": jenis, "pesan": pesan, "pegawai_id": pegawai_id, "pengganti": pengganti or []})

    rid = int(b.get("rencana_id") or 0)
    r = db.execute("SELECT * FROM rencana WHERE id=?", (rid,)).fetchone()
    if not r:
        raise Gagal("Pilih rencana kegiatan yang sudah disetujui.")
    mulai, selesai = _tgl(b.get("mulai"), "Tanggal mulai"), _tgl(b.get("selesai"), "Tanggal selesai")
    if selesai < mulai:
        raise Gagal("Tanggal selesai tidak boleh sebelum tanggal mulai.")
    hari = _rentang(mulai, selesai)
    if len(hari) > HARI_MAKS:
        raise Gagal(f"Satu jadwal maksimal {HARI_MAKS} hari.")
    petugas = list(dict.fromkeys(int(x) for x in (b.get("petugas") or [])))
    if not petugas:
        raise Gagal("Pilih minimal satu petugas.")
    lokasi_id = int(b.get("lokasi_id") or r["lokasi_id"] or 0)
    lok = db.execute("SELECT * FROM lokasi WHERE id=?", (lokasi_id,)).fetchone()
    if not lok:
        raise Gagal("Lokasi tujuan wajib diisi.")
    durasi = "le8" if b.get("durasi") == "le8" else "gt8"

    # --- keterkaitan dengan rencana ---
    if not excl and r["status"] not in ("Disetujui", "Terjadwal"):
        G("rencana", f"Rencana berstatus {r['status']}; hanya rencana Disetujui yang dapat dijadwalkan.")
    if mulai.year != r["tahun"] or selesai.year != r["tahun"]:
        G("rencana", f"Tanggal harus berada di tahun anggaran rencana ({r['tahun']}).")
    if len(petugas) > r["jumlah_petugas"]:
        G("rencana", f"Petugas ({len(petugas)}) melebihi rencana ({r['jumlah_petugas']}) — estimasi biaya hanya mencukupi {r['jumlah_petugas']} orang.")
    elif len(petugas) < r["jumlah_petugas"]:
        peringatan.append(f"Petugas ({len(petugas)}) kurang dari rencana ({r['jumlah_petugas']}).")
    if len(hari) > r["jumlah_hari"]:
        G("rencana", f"Durasi ({len(hari)} hari) melebihi rencana ({r['jumlah_hari']} hari per pelaksanaan).")
    terjadwal = db.execute("SELECT COUNT(*) c FROM jadwal WHERE rencana_id=? AND status IN ('Diusulkan','Disetujui','Terlaksana') AND id!=?", (rid, excl)).fetchone()["c"]
    if terjadwal >= r["frekuensi"]:
        G("rencana", f"Seluruh {r['frekuensi']} pelaksanaan rencana ini sudah dijadwalkan.")
    if mulai.month != r["bulan"]:
        peringatan.append(f"Bulan jadwal berbeda dari bulan rencana ({r['bulan']:02d}).")
    if r["lokasi_id"] and r["lokasi_id"] != lokasi_id:
        peringatan.append("Lokasi berbeda dari rencana; estimasi biaya mengikuti lokasi pada rencana.")

    # --- (d) libur ---
    for tg, ket in [(x["tanggal"], x["keterangan"]) for x in db.execute("SELECT * FROM libur WHERE tanggal BETWEEN ? AND ?", (hari[0], hari[-1])).fetchall()]:
        G("libur", f"{_fmt(tg)} adalah hari libur ({ket or 'libur'}); jadwal tidak boleh jatuh pada tanggal libur.")
    for tg in hari:
        if dt.date.fromisoformat(tg).weekday() >= 5:
            peringatan.append(f"{_fmt(tg)} jatuh pada akhir pekan.")

    # --- per petugas ---
    ya_hari = set(hari)
    for pid in petugas:
        p = db.execute("SELECT * FROM pegawai WHERE id=?", (pid,)).fetchone()
        if not p or not p["aktif"]:
            G("pegawai", "Petugas tidak ditemukan atau nonaktif.", pid)
            continue
        nama = f"{p['nama']} (NIP {p['nip'] or '-'})"
        # (d) cuti
        for c in db.execute("SELECT * FROM cuti WHERE pegawai_id=? AND mulai<=? AND selesai>=?", (pid, hari[-1], hari[0])).fetchall():
            ov = [x for x in hari if c["mulai"] <= x <= c["selesai"]]
            G("cuti", f"{nama} sedang cuti pada {_fmt(ov[0])}" + (f" s.d. {_fmt(ov[-1])}" if len(ov) > 1 else "") + f" ({c['keterangan'] or 'cuti'}).", pid,
              [{"id": x["id"], "nama": x["nama"], "tingkat": x["tingkat"]} for x in pegawai_bebas(db, hari, set(petugas), excl)[:5]])
        # (a)(c) bentrok tanggal / uang harian ganda lintas sumber dana
        rows = db.execute("""SELECT ph.tanggal, ph.jadwal_id, ph.uang_harian, j.no_st, j.kegiatan, l.nama lokasi, sd.kode dana, j.sumber_dana_id
            FROM penugasan_hari ph JOIN jadwal j ON j.id=ph.jadwal_id JOIN lokasi l ON l.id=j.lokasi_id JOIN sumber_dana sd ON sd.id=j.sumber_dana_id
            WHERE ph.pegawai_id=? AND ph.tanggal BETWEEN ? AND ? AND ph.jadwal_id!=? ORDER BY ph.tanggal""", (pid, hari[0], hari[-1], excl)).fetchall()
        per_jadwal: dict[int, list] = {}
        for x in rows:
            per_jadwal.setdefault(x["jadwal_id"], []).append(x)
        for jid, xs in per_jadwal.items():
            tgs = [x["tanggal"] for x in xs]
            tgl_txt = ", ".join(_fmt(t) for t in tgs[:4]) + (f" (+{len(tgs) - 4} hari)" if len(tgs) > 4 else "")
            x0 = xs[0]
            pesan = f"{nama} sudah bertugas ke {x0['lokasi']} pada {tgl_txt}, ST No. {x0['no_st'] or 'belum terbit'}, dana {x0['dana']}."
            if x0["sumber_dana_id"] != r["sumber_dana_id"]:
                pesan += " Memberi tugas lagi berarti uang harian ganda lintas sumber dana."
            G("bentrok", pesan, pid, [{"id": x["id"], "nama": x["nama"], "tingkat": x["tingkat"], "beban_bulan": x["beban_bulan"]}
                                      for x in pegawai_bebas(db, hari, set(petugas), excl)[:5]])
        # (e) peringatan beban bulanan
        batas = _setting(db, "batas_hari_dinas_bulan", 10)
        per_bulan: dict[str, int] = {}
        for tg in hari:
            per_bulan[tg[:7]] = per_bulan.get(tg[:7], 0) + 1
        for ym, n in per_bulan.items():
            total = _beban_bulan(db, pid, ym, excl) + n
            if total > batas:
                peringatan.append(f"{p['nama']}: total {total} hari dinas luar pada bulan {ym[5:]}/{ym[:4]} melebihi batas {int(batas)} hari.")

    # --- (b) kegiatan sama di lokasi sama pada tanggal sama ---
    for x in db.execute("""SELECT jh.tanggal, jh.jadwal_id, j.no_st FROM jadwal_hari jh JOIN jadwal j ON j.id=jh.jadwal_id
        WHERE jh.baris_id=? AND jh.lokasi_id=? AND jh.tanggal BETWEEN ? AND ? AND jh.jadwal_id!=? ORDER BY jh.tanggal""", (r["baris_id"], lokasi_id, hari[0], hari[-1], excl)).fetchall():
        G("kegiatan", f"Kegiatan \"{r['kegiatan']}\" di {lok['nama']} sudah dijadwalkan pada {_fmt(x['tanggal'])} (jadwal #{x['jadwal_id']}"
          + (f", ST No. {x['no_st']}" if x["no_st"] else "") + "); tidak boleh dua kali pada tanggal yang sama.")
    return {"ok": not galat, "galat": galat, "peringatan": peringatan, "hari": hari, "jumlah_hari": len(hari),
            "_r": r, "_lok": lok, "_durasi": durasi, "_petugas": petugas, "_mulai": mulai, "_selesai": selesai}


def _bersih(a: dict) -> dict:
    return {k: v for k, v in a.items() if not k.startswith("_")}


def _tulis_hari(db, jid, a):
    r, lok = a["_r"], a["_lok"]
    uh = 1 if (a["_durasi"] == "gt8" or lok["jenis"] in ("LK_KALTENG", "LK_LUAR_PROV")) else 0
    db.execute("DELETE FROM jadwal_hari WHERE jadwal_id=?", (jid,))
    db.execute("DELETE FROM penugasan_hari WHERE jadwal_id=?", (jid,))
    for tg in a["hari"]:
        db.execute("INSERT INTO jadwal_hari(jadwal_id,tanggal,baris_id,lokasi_id) VALUES(?,?,?,?)", (jid, tg, r["baris_id"], lok["id"]))
        for pid in a["_petugas"]:
            db.execute("INSERT INTO penugasan_hari(jadwal_id,pegawai_id,tanggal,sumber_dana_id,uang_harian) VALUES(?,?,?,?,?)", (jid, pid, tg, r["sumber_dana_id"], uh))


def _simpan_petugas(db, jid, petugas):
    db.execute("DELETE FROM jadwal_petugas WHERE jadwal_id=?", (jid,))
    db.executemany("INSERT INTO jadwal_petugas(jadwal_id,pegawai_id) VALUES(?,?)", [(jid, p) for p in petugas])


def _sinkron_rencana(db, rid, user):
    r = db.execute("SELECT * FROM rencana WHERE id=?", (rid,)).fetchone()
    n = db.execute("SELECT COUNT(*) c FROM jadwal WHERE rencana_id=? AND status IN ('Diusulkan','Disetujui','Terlaksana')", (rid,)).fetchone()["c"]
    baru = "Terjadwal" if n else "Disetujui"
    if r["status"] in ("Disetujui", "Terjadwal") and r["status"] != baru:
        db.execute("UPDATE rencana SET status=? WHERE id=?", (baru, rid))
        audit(db, user, "rencana", rid, "STATUS", {"status": r["status"]}, {"status": baru, "alasan": "mengikuti jadwal"})


def _tambah_info(db, rows):
    for j in rows:
        j["petugas"] = db.execute("SELECT p.id, p.nama, p.nip, p.program, p.tingkat FROM jadwal_petugas jp JOIN pegawai p ON p.id=jp.pegawai_id WHERE jp.jadwal_id=? ORDER BY p.nama", (j["id"],)).fetchall()
    return rows


@router.get("/rencana-siap")
def rencana_siap(tahun: int, user=Depends(perlu_baca), db=Depends(get_db)):
    rows = db.execute("""SELECT r.id, r.bulan, r.kegiatan, r.lokasi_id, l.nama lokasi, r.durasi, r.jumlah_petugas, r.jumlah_hari, r.frekuensi, r.status, r.sumber_dana_id,
        (SELECT COUNT(*) FROM jadwal j WHERE j.rencana_id=r.id AND j.status IN ('Diusulkan','Disetujui','Terlaksana')) terjadwal
        FROM rencana r LEFT JOIN lokasi l ON l.id=r.lokasi_id WHERE r.tahun=? AND r.status IN ('Disetujui','Terjadwal') ORDER BY r.bulan, r.id""", (tahun,)).fetchall()
    return [x for x in rows if x["terjadwal"] < x["frekuensi"]]


@router.get("")
def daftar(dari: str, sampai: str, pegawai_id: int | None = None, lokasi_id: int | None = None, program: str | None = None,
           sumber_dana_id: int | None = None, status: str | None = None, user=Depends(perlu_baca), db=Depends(get_db)):
    q, a = ["j.mulai<=?", "j.selesai>=?"], [sampai, dari]
    if status:
        q.append("j.status=?")
        a.append(status)
    else:
        q.append("j.status NOT IN ('Dibatalkan','Ditolak')")
    if lokasi_id:
        q.append("j.lokasi_id=?")
        a.append(lokasi_id)
    if sumber_dana_id:
        q.append("j.sumber_dana_id=?")
        a.append(sumber_dana_id)
    if pegawai_id:
        q.append("EXISTS(SELECT 1 FROM jadwal_petugas x WHERE x.jadwal_id=j.id AND x.pegawai_id=?)")
        a.append(pegawai_id)
    if program:
        q.append("EXISTS(SELECT 1 FROM jadwal_petugas x JOIN pegawai pp ON pp.id=x.pegawai_id WHERE x.jadwal_id=j.id AND (pp.program=? OR pp.ruangan=?))")
        a += [program, program]
    rows = db.execute(f"""SELECT j.*, l.nama lokasi, sd.kode dana, r.jumlah_petugas rencana_petugas FROM jadwal j JOIN lokasi l ON l.id=j.lokasi_id
        JOIN sumber_dana sd ON sd.id=j.sumber_dana_id JOIN rencana r ON r.id=j.rencana_id WHERE {' AND '.join(q)} ORDER BY j.mulai, j.id""", a).fetchall()
    for j in _tambah_info(db, rows):
        j["bisa_ubah"] = _bisa_ubah(user, j)
    return rows


@router.post("/periksa")
def api_periksa(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    try:
        return _bersih(periksa(db, body, int(body.get("id") or 0)))
    except Gagal as e:
        return {"ok": False, "galat": [{"jenis": "isian", "pesan": e.pesan, "pegawai_id": None, "pengganti": []}], "peringatan": [], "hari": []}


@router.post("/saran")
def saran(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    """Bagi Petugas Otomatis: pilih `jumlah` pegawai yang kosong pada seluruh tanggal, beban bulan terendah dulu (pemerataan)."""
    mulai, selesai = _tgl(body.get("mulai"), "Tanggal mulai"), _tgl(body.get("selesai"), "Tanggal selesai")
    if selesai < mulai:
        raise Gagal("Tanggal selesai tidak boleh sebelum tanggal mulai.")
    hari = _rentang(mulai, selesai)
    libur = db.execute("SELECT tanggal, keterangan FROM libur WHERE tanggal BETWEEN ? AND ?", (hari[0], hari[-1])).fetchone()
    if libur:
        raise Gagal(f"{_fmt(libur['tanggal'])} adalah hari libur ({libur['keterangan'] or 'libur'}).")
    n = max(1, int(body.get("jumlah") or 1))
    ada = pegawai_bebas(db, hari, {int(x) for x in (body.get("kecuali") or [])}, int(body.get("id") or 0), body.get("program") or None)
    return {"dipilih": ada[:n], "cadangan": ada[n:n + 5], "kurang": max(0, n - len(ada)), "tersedia": len(ada)}


@router.post("")
def tambah(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    a = periksa(db, body)
    if not a["ok"]:
        raise Gagal(" ".join(g["pesan"] for g in a["galat"]), galat=[g["pesan"] for g in a["galat"]])
    r, lok = a["_r"], a["_lok"]
    try:
        jid = db.execute("""INSERT INTO jadwal(rencana_id,tahun,baris_id,kegiatan,lokasi_id,sumber_dana_id,mulai,selesai,durasi,catatan,dibuat_oleh) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                         (r["id"], r["tahun"], r["baris_id"], r["kegiatan"], lok["id"], r["sumber_dana_id"], a["hari"][0], a["hari"][-1], a["_durasi"],
                          str(body.get("catatan") or "").strip() or None, user["username"])).lastrowid
        _simpan_petugas(db, jid, a["_petugas"])
        _tulis_hari(db, jid, a)
    except sqlite3.IntegrityError as e:
        raise Gagal(_pesan_bentrok(e))
    _sinkron_rencana(db, r["id"], user)
    audit(db, user, "jadwal", jid, "TAMBAH", None, {"rencana_id": r["id"], "mulai": a["hari"][0], "selesai": a["hari"][-1], "lokasi_id": lok["id"], "petugas": a["_petugas"]})
    return {"id": jid, "peringatan": a["peringatan"]}


def _pesan_bentrok(e) -> str:
    m = str(e)
    if "LIBUR" in m:
        return "Tanggal libur ditolak oleh database."
    if "CUTI" in m:
        return "Pegawai sedang cuti pada tanggal tersebut (ditolak oleh database)."
    return "Bentrok terdeteksi oleh database (jadwal lain baru saja masuk). Periksa ulang jadwal Anda."


@router.put("/{jid}")
def ubah(jid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    j = db.execute("SELECT * FROM jadwal WHERE id=?", (jid,)).fetchone()
    if not j:
        raise Gagal("Jadwal tidak ditemukan.", 404)
    if not _bisa_ubah(user, j):
        raise Gagal("Anda tidak berhak mengubah jadwal ini.", 403)
    if j["status"] != "Diusulkan":
        raise Gagal("Hanya jadwal berstatus Diusulkan yang dapat diubah. Batalkan lalu buat ulang bila sudah disetujui.")
    a = periksa(db, {**body, "rencana_id": j["rencana_id"]}, jid)
    if not a["ok"]:
        raise Gagal(" ".join(g["pesan"] for g in a["galat"]), galat=[g["pesan"] for g in a["galat"]])
    lok = a["_lok"]
    try:
        db.execute("UPDATE jadwal SET lokasi_id=?, mulai=?, selesai=?, durasi=?, catatan=? WHERE id=?",
                   (lok["id"], a["hari"][0], a["hari"][-1], a["_durasi"], str(body.get("catatan") or "").strip() or None, jid))
        _simpan_petugas(db, jid, a["_petugas"])
        _tulis_hari(db, jid, a)
    except sqlite3.IntegrityError as e:
        raise Gagal(_pesan_bentrok(e))
    audit(db, user, "jadwal", jid, "UBAH", j, {"mulai": a["hari"][0], "selesai": a["hari"][-1], "lokasi_id": lok["id"], "petugas": a["_petugas"]})
    return {"peringatan": a["peringatan"]}


@router.post("/{jid}/status")
def ubah_status(jid: int, body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    j = db.execute("SELECT * FROM jadwal WHERE id=?", (jid,)).fetchone()
    if not j:
        raise Gagal("Jadwal tidak ditemukan.", 404)
    ke, alasan = str(body.get("ke") or ""), str(body.get("alasan") or "").strip()
    ok = {("Diusulkan", "Disetujui"): "kepala", ("Diusulkan", "Ditolak"): "kepala", ("Diusulkan", "Dibatalkan"): "tulis",
          ("Disetujui", "Dibatalkan"): "kepala", ("Disetujui", "Diusulkan"): "kepala"}.get((j["status"], ke))
    if not ok:
        raise Gagal(f"Perubahan status {j['status']} → {ke} tidak diizinkan.")
    if ok == "kepala" and user["role"] != "kepala":
        raise Gagal("Hanya Kepala Puskesmas yang dapat melakukan ini.", 403)
    if ok == "tulis" and not _bisa_ubah(user, j):
        raise Gagal("Anda tidak berhak mengubah jadwal ini.", 403)
    if ke in ("Ditolak", "Dibatalkan") and not alasan:
        raise Gagal("Alasan wajib diisi.")
    if j["no_st"] and ke in ("Dibatalkan", "Diusulkan"):
        raise Gagal("Surat Tugas sudah terbit. Perubahan hanya lewat pembatalan ST + terbit ulang.")
    now = "datetime('now','localtime')"
    db.execute(f"UPDATE jadwal SET status=?, alasan=?, diputuskan_oleh=?, diputuskan_pada={now} WHERE id=?", (ke, alasan or None, user["username"], jid))
    if ke in ("Ditolak", "Dibatalkan"):  # bebaskan tanggal & kuota
        db.execute("DELETE FROM jadwal_hari WHERE jadwal_id=?", (jid,))
        db.execute("DELETE FROM penugasan_hari WHERE jadwal_id=?", (jid,))
    _sinkron_rencana(db, j["rencana_id"], user)
    audit(db, user, "jadwal", jid, "STATUS", {"status": j["status"]}, {"status": ke, **({"alasan": alasan} if alasan else {})})
    return {"ok": 1}
