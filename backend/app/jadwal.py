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


def peta_ruangan(db, dari: str, sampai: str, excl: int = 0, hitung_cuti: bool | None = None):
    """Keadaan ruangan: jumlah pegawai aktif, batas maks. yang boleh keluar (cap), dan siapa yang sedang keluar per tanggal.
    'Keluar' = dinas luar (penugasan_hari) + (opsional) cuti. Batas = floor(jumlah pegawai × persen)."""
    if hitung_cuti is None:
        hitung_cuti = _setting(db, "ruangan_hitung_cuti", 1) >= 1
    persen = _setting(db, "batas_persen_ruangan", 50)
    room_of = {p["id"]: p["ruangan"] for p in db.execute("SELECT id, ruangan FROM pegawai WHERE aktif=1 AND ruangan IS NOT NULL AND ruangan!=''").fetchall()}
    size: dict[str, int] = {}
    for r in room_of.values():
        size[r] = size.get(r, 0) + 1
    cap = {r: int(n * persen / 100 + 1e-9) for r, n in size.items()}
    away: dict[str, dict[str, set]] = {r: {} for r in size}
    for x in db.execute("SELECT pegawai_id, tanggal FROM penugasan_hari WHERE tanggal BETWEEN ? AND ? AND jadwal_id!=?", (dari, sampai, excl)).fetchall():
        if x["pegawai_id"] in room_of:
            away[room_of[x["pegawai_id"]]].setdefault(x["tanggal"], set()).add(x["pegawai_id"])
    if hitung_cuti:
        for c in db.execute("SELECT pegawai_id, mulai, selesai FROM cuti WHERE mulai<=? AND selesai>=?", (sampai, dari)).fetchall():
            if c["pegawai_id"] in room_of:
                for tg in _rentang(_tgl(max(c["mulai"], dari), "t"), _tgl(min(c["selesai"], sampai), "t")):
                    away[room_of[c["pegawai_id"]]].setdefault(tg, set()).add(c["pegawai_id"])
    return {"room_of": room_of, "size": size, "cap": cap, "away": away, "persen": persen}


def _muat(peta, pid, hari) -> bool:
    """Apakah ruangan `pid` masih sanggup ditinggal pada seluruh `hari` bila `pid` ikut pergi?"""
    r = peta["room_of"].get(pid)
    if r is None:
        return True
    return all(len(peta["away"][r].get(tg, set()) | {pid}) <= peta["cap"][r] for tg in hari)


def _tandai(peta, pids, hari) -> None:
    for pid in pids:
        r = peta["room_of"].get(pid)
        if r is not None:
            for tg in hari:
                peta["away"][r].setdefault(tg, set()).add(pid)


def pegawai_bebas(db, hari: list[str], exclude: set[int], excl_jadwal=0, program=None, sudah: set[int] | None = None) -> list[dict]:
    """Pegawai aktif yang kosong (tanpa jadwal/cuti) pada SEMUA tanggal di `hari` DAN yang ruangannya masih sanggup ditinggal
    (batas % ruangan). `sudah` = petugas yang sudah dipilih (dihitung sebagai keluar). Diurut dari beban terendah."""
    ym = hari[0][:7]
    peta = peta_ruangan(db, hari[0], hari[-1], excl_jadwal)
    _tandai(peta, sudah if sudah is not None else exclude, hari)
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
        if p["id"] in exclude or not _muat(peta, p["id"], hari):
            continue
        r = peta["room_of"].get(p["id"])
        p["ruangan"] = r
        p["rasio"] = round(max(len(peta["away"][r].get(tg, ())) + 1 for tg in hari) / peta["size"][r], 3) if r else 0
        p["beban_bulan"] = _beban_bulan(db, p["id"], ym, excl_jadwal)
        p["beban_tahun"] = db.execute("SELECT COUNT(*) c FROM penugasan_hari WHERE pegawai_id=? AND tanggal LIKE ?", (p["id"], ym[:4] + "%")).fetchone()["c"]
        out.append(p)
    out.sort(key=lambda p: (p["beban_bulan"], p["rasio"], p["beban_tahun"], p["nama"]))
    return out


def pilih_otomatis(db, hari, jumlah, jangan: set[int], excl=0, program=None) -> tuple[list[dict], list[dict]]:
    """Pilih `jumlah` petugas satu per satu; tiap pilihan dihitung ke batas ruangan pilihan berikutnya."""
    dipilih: list[dict] = []
    for _ in range(jumlah):
        ada = pegawai_bebas(db, hari, jangan | {x["id"] for x in dipilih}, excl, program, sudah={x["id"] for x in dipilih})
        if not ada:
            break
        dipilih.append(ada[0])
    sisa = pegawai_bebas(db, hari, jangan | {x["id"] for x in dipilih}, excl, program, sudah={x["id"] for x in dipilih})
    return dipilih, sisa[:5]


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

    # --- (f) satu ruangan tidak boleh ditinggal lebih dari batas % pegawainya pada hari yang sama ---
    peta = peta_ruangan(db, hari[0], hari[-1], excl)
    per_ruang: dict[str, list[int]] = {}
    for pid in petugas:
        if pid in peta["room_of"]:
            per_ruang.setdefault(peta["room_of"][pid], []).append(pid)
    for room, pids in per_ruang.items():
        lewat = [tg for tg in hari if len(peta["away"][room].get(tg, set()) | set(pids)) > peta["cap"][room]]
        if not lewat:
            continue
        n, cap, persen = peta["size"][room], peta["cap"][room], int(peta["persen"])
        tg0 = lewat[0]
        keluar = peta["away"][room].get(tg0, set()) | set(pids)
        if cap == 0:
            pesan = f"Ruangan {room} hanya berisi {n} pegawai sehingga tidak boleh ditinggal (batas {persen}% = 0 orang)."
        else:
            pesan = (f"Ruangan {room} ({n} pegawai) akan ditinggal {len(keluar)} orang pada {_fmt(tg0)}"
                     + (f" dan {len(lewat) - 1} hari lain" if len(lewat) > 1 else "") + f"; batas maksimal {cap} orang ({persen}%).")
        G("ruangan", pesan, pids[0],
          [{"id": x["id"], "nama": x["nama"], "tingkat": x["tingkat"], "beban_bulan": x["beban_bulan"]}
           for x in pegawai_bebas(db, hari, set(petugas), excl)[:5]])

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
    dipilih, cadangan = pilih_otomatis(db, hari, n, {int(x) for x in (body.get("kecuali") or [])}, int(body.get("id") or 0), body.get("program") or None)
    return {"dipilih": dipilih, "cadangan": cadangan, "kurang": max(0, n - len(dipilih)), "tersedia": len(dipilih) + len(cadangan)}


def buat_jadwal(db, user, body: dict, catatan_otomatis: str | None = None) -> dict:
    """Validasi lengkap lalu simpan sebagai jadwal 'Diusulkan'. Dipakai oleh input manual dan hasil generate otomatis."""
    a = periksa(db, body)
    if not a["ok"]:
        raise Gagal(" ".join(g["pesan"] for g in a["galat"]), galat=[g["pesan"] for g in a["galat"]])
    r, lok = a["_r"], a["_lok"]
    db.execute("SAVEPOINT buat_jadwal")
    try:
        jid = db.execute("""INSERT INTO jadwal(rencana_id,tahun,baris_id,kegiatan,lokasi_id,sumber_dana_id,mulai,selesai,durasi,catatan,dibuat_oleh) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                         (r["id"], r["tahun"], r["baris_id"], r["kegiatan"], lok["id"], r["sumber_dana_id"], a["hari"][0], a["hari"][-1], a["_durasi"],
                          str(body.get("catatan") or "").strip() or catatan_otomatis, user["username"])).lastrowid
        _simpan_petugas(db, jid, a["_petugas"])
        _tulis_hari(db, jid, a)
        db.execute("RELEASE buat_jadwal")
    except sqlite3.IntegrityError as e:
        db.execute("ROLLBACK TO buat_jadwal")
        db.execute("RELEASE buat_jadwal")
        raise Gagal(_pesan_bentrok(e))
    _sinkron_rencana(db, r["id"], user)
    audit(db, user, "jadwal", jid, "TAMBAH", None, {"rencana_id": r["id"], "mulai": a["hari"][0], "selesai": a["hari"][-1], "lokasi_id": lok["id"], "petugas": a["_petugas"],
                                                    **({"sumber": "generate otomatis"} if catatan_otomatis else {})})
    return {"id": jid, "peringatan": a["peringatan"]}


@router.post("")
def tambah(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    return buat_jadwal(db, user, body)


# ======================================================================================
#  GENERATE JADWAL BULANAN
#  Menyusun usulan jadwal satu bulan untuk semua rencana yang sudah disetujui, dengan syarat:
#   - hanya hari kerja & bukan libur; satu pelaksanaan = hari berurutan sebanyak jumlah_hari rencana
#   - pegawai tidak bentrok (tanggal), tidak cuti; kegiatan+lokasi+tanggal tidak dobel
#   - satu ruangan tidak ditinggal > batas % pegawainya pada hari yang sama (default 50%)
#   - beban dibagi merata (pegawai dengan hari dinas paling sedikit dipilih dulu) & tanggal disebar
# ======================================================================================
def _hari_kerja(d: dt.date, hk: int) -> bool:
    return d.weekday() < hk


def generate(db, tahun: int, bulan: int, rencana_ids=None, hari_kerja=5, hitung_cuti=True, ruangan=None) -> dict:
    awal = dt.date(tahun, bulan, 1)
    akhir = (dt.date(tahun + (bulan == 12), bulan % 12 + 1, 1) - dt.timedelta(days=1))
    semua = _rentang(awal, akhir)
    libur = {x["tanggal"] for x in db.execute("SELECT tanggal FROM libur WHERE tanggal BETWEEN ? AND ?", (semua[0], semua[-1])).fetchall()}
    peta = peta_ruangan(db, semua[0], semua[-1], 0, hitung_cuti)
    busy: dict[int, set] = {}
    beban: dict[int, int] = {}
    for x in db.execute("SELECT pegawai_id, tanggal FROM penugasan_hari WHERE tanggal BETWEEN ? AND ?", (semua[0], semua[-1])).fetchall():
        busy.setdefault(x["pegawai_id"], set()).add(x["tanggal"])
        beban[x["pegawai_id"]] = beban.get(x["pegawai_id"], 0) + 1
    cuti: dict[int, set] = {}
    for c in db.execute("SELECT pegawai_id, mulai, selesai FROM cuti WHERE mulai<=? AND selesai>=?", (semua[-1], semua[0])).fetchall():
        cuti.setdefault(c["pegawai_id"], set()).update(tg for tg in semua if c["mulai"] <= tg <= c["selesai"])
    kl = {(x["baris_id"], x["lokasi_id"], x["tanggal"]) for x in db.execute("SELECT baris_id, lokasi_id, tanggal FROM jadwal_hari WHERE tanggal BETWEEN ? AND ?", (semua[0], semua[-1])).fetchall()}
    harian = {tg: sum(len(peta["away"][r].get(tg, ())) for r in peta["away"]) for tg in semua}   # orang yang sedang keluar per hari
    batas_bulan = _setting(db, "batas_hari_dinas_bulan", 10)
    pool = [p for p in db.execute("SELECT id, nama, ruangan, tingkat FROM pegawai WHERE aktif=1 AND COALESCE(jabatan,'') NOT LIKE 'Kepala Puskesmas%'").fetchall()
            if not ruangan or p["ruangan"] in ruangan]

    q = """SELECT r.*, l.nama lokasi_nama, (SELECT COUNT(*) FROM jadwal j WHERE j.rencana_id=r.id AND j.status IN ('Diusulkan','Disetujui','Terlaksana')) terjadwal
           FROM rencana r LEFT JOIN lokasi l ON l.id=r.lokasi_id WHERE r.tahun=? AND r.bulan=? AND r.status IN ('Disetujui','Terjadwal')"""
    daftar = db.execute(q, (tahun, bulan)).fetchall()
    if rencana_ids:
        daftar = [r for r in daftar if r["id"] in set(rencana_ids)]
    daftar.sort(key=lambda r: (-(r["jumlah_petugas"] * r["jumlah_hari"]), r["id"]))

    usulan, gagal = [], []
    for r in daftar:
        sisa = r["frekuensi"] - r["terjadwal"]
        if sisa <= 0:
            continue
        if not r["lokasi_id"]:
            gagal.append({"rencana_id": r["id"], "kegiatan": r["kegiatan"], "jumlah": sisa, "alasan": "Rencana tidak punya lokasi tujuan (bukan perjalanan dinas) — jadwalkan manual."})
            continue
        h, n = r["jumlah_hari"], r["jumlah_petugas"]
        mulai_sebelumnya: list[dt.date] = []
        for ke in range(1, sisa + 1):
            jendela = []
            for i in range(len(semua) - h + 1):
                w = semua[i:i + h]
                if all(_hari_kerja(dt.date.fromisoformat(tg), hari_kerja) and tg not in libur and (r["baris_id"], r["lokasi_id"], tg) not in kl for tg in w):
                    skor = sum(harian[tg] for tg in w) * 100 + i
                    d0 = dt.date.fromisoformat(w[0])
                    if any(abs((d0 - s).days) <= h + 1 for s in mulai_sebelumnya):
                        skor += 500          # sebar pelaksanaan rencana yang sama
                    jendela.append((skor, w))
            jendela.sort(key=lambda x: x[0])
            sebab = {"tanpa_jendela": not jendela, "ruangan": False, "petugas": False}
            hasil = None
            for keras in (True, False):       # putaran 1: hormati batas hari dinas/bulan; putaran 2: boleh melebihi (diberi peringatan)
                for _, w in jendela:
                    pilih: list[dict] = []
                    bebas_tanpa_cap = 0
                    for p in sorted(pool, key=lambda p: (beban.get(p["id"], 0), p["nama"])):
                        pid = p["id"]
                        if busy.get(pid, set()) & set(w) or cuti.get(pid, set()) & set(w):
                            continue
                        if keras and beban.get(pid, 0) + h > batas_bulan:
                            continue
                        bebas_tanpa_cap += 1
                        if not _muat(peta, pid, w):
                            continue
                        pilih.append(p)
                        _tandai(peta, [pid], w)        # hitung sementara agar petugas berikutnya satu ruangan ikut dibatasi
                        if len(pilih) == n:
                            break
                    if len(pilih) == n:
                        hasil = (w, pilih, not keras)
                        break
                    for p in pilih:                    # batal: kembalikan penandaan sementara
                        rr = peta["room_of"].get(p["id"])
                        if rr:
                            for tg in w:
                                peta["away"][rr].get(tg, set()).discard(p["id"])
                    if bebas_tanpa_cap >= n:
                        sebab["ruangan"] = True
                    else:
                        sebab["petugas"] = True
                if hasil:
                    break
            if not hasil:
                alasan = ("Tidak ada hari kerja yang cocok (libur/akhir pekan/kegiatan sudah terjadwal)." if sebab["tanpa_jendela"] else
                          f"Batas {int(peta['persen'])}% pegawai per ruangan membuat {n} petugas tidak bisa dipenuhi." if sebab["ruangan"] else
                          f"Petugas yang kosong kurang dari {n} orang pada hari-hari yang tersedia.")
                gagal.append({"rencana_id": r["id"], "kegiatan": r["kegiatan"], "jumlah": sisa - ke + 1, "alasan": alasan})
                break
            w, pilih, lewat = hasil
            for p in pilih:
                busy.setdefault(p["id"], set()).update(w)
                beban[p["id"]] = beban.get(p["id"], 0) + h
            for tg in w:
                harian[tg] += len(pilih)
                kl.add((r["baris_id"], r["lokasi_id"], tg))
            mulai_sebelumnya.append(dt.date.fromisoformat(w[0]))
            usulan.append({"rencana_id": r["id"], "kegiatan": r["kegiatan"], "ke": r["terjadwal"] + ke, "dari": r["frekuensi"], "lokasi_id": r["lokasi_id"], "lokasi": r["lokasi_nama"],
                           "mulai": w[0], "selesai": w[-1], "durasi": r["durasi"] or "gt8", "petugas": [{"id": p["id"], "nama": p["nama"], "ruangan": p["ruangan"]} for p in pilih],
                           "peringatan": ["Beban petugas melebihi batas hari dinas bulanan."] if lewat else []})
    usulan.sort(key=lambda u: (u["mulai"], u["rencana_id"]))
    dampak = []
    for room, n in sorted(peta["size"].items()):
        puncak = max(((len(s), tg) for tg, s in peta["away"][room].items()), default=(0, None))
        dampak.append({"ruangan": room, "pegawai": n, "batas": peta["cap"][room], "puncak": puncak[0], "tanggal": puncak[1],
                       "persen": round(puncak[0] / n * 100) if n else 0})
    dampak.sort(key=lambda d: (-d["persen"], d["ruangan"]))
    petugas_hari = {}
    for u in usulan:
        for p in u["petugas"]:
            petugas_hari[p["id"]] = petugas_hari.get(p["id"], 0) + (dt.date.fromisoformat(u["selesai"]) - dt.date.fromisoformat(u["mulai"])).days + 1
    nama = {p["id"]: p["nama"] for p in pool}
    return {"tahun": tahun, "bulan": bulan, "usulan": usulan, "gagal": gagal, "dampak": dampak, "persen": peta["persen"],
            "sebaran": sorted(({"id": i, "nama": nama.get(i, "?"), "hari": n} for i, n in petugas_hari.items()), key=lambda x: -x["hari"])[:8],
            "ringkas": {"jadwal": len(usulan), "gagal": sum(g["jumlah"] for g in gagal), "petugas": len(petugas_hari)}}


@router.post("/generate")
def api_generate(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    tahun, bulan = int(body.get("tahun") or 0), int(body.get("bulan") or 0)
    if not (tahun and 1 <= bulan <= 12):
        raise Gagal("Pilih bulan dan tahun.")
    return generate(db, tahun, bulan, [int(x) for x in body.get("rencana_ids") or []] or None, 6 if int(body.get("hari_kerja") or 5) == 6 else 5,
                    None, body.get("ruangan") or None)


@router.post("/generate/simpan")
def api_generate_simpan(body: dict = Body(default={}), user=Depends(perlu_baca), db=Depends(get_db)):
    """Simpan hasil pratinjau sebagai jadwal 'Diusulkan'. Tiap item divalidasi ulang (aturan sama dengan input manual)."""
    if user["role"] == "pegawai":
        raise Gagal("Tidak ada akses.", 403)
    ok, gagal = [], []
    for it in body.get("items") or []:
        try:
            res = buat_jadwal(db, user, {"rencana_id": it["rencana_id"], "mulai": it["mulai"], "selesai": it["selesai"], "lokasi_id": it["lokasi_id"],
                                         "durasi": it.get("durasi"), "petugas": [p["id"] if isinstance(p, dict) else p for p in it["petugas"]]}, "Dibuat otomatis (generate bulanan)")
            ok.append(res["id"])
        except Gagal as e:
            gagal.append({"kegiatan": it.get("kegiatan"), "mulai": it.get("mulai"), "alasan": e.pesan})
    return {"tersimpan": len(ok), "gagal": gagal}


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
