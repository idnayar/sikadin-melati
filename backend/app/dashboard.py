"""Tahap 7 — Dashboard per peran: serapan anggaran, tugas yang menunggu, jadwal terdekat, peringatan, ringkasan keuangan.
Setiap angka mengikuti hak akses sumber dana (BLUD hanya Kepala + Bendahara BLUD); pegawai hanya melihat data dirinya."""
import datetime as dt

from fastapi import APIRouter, Depends

from .core import akses_sumber, akses_uang, auth, boleh_setuju, get_db, kepala_wajib

router = APIRouter(prefix="/api/dashboard")
SUMBER = ("BOK", "DAU", "BLUD")


def _set(db, k, d):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    try:
        return int(r["nilai"]) if r else d
    except (TypeError, ValueError):
        return d


def _pegawai(db, user, tahun):
    pid = user.get("pegawai_id")
    hari = dt.date.today().isoformat()
    if not pid:
        return {"peran": "pegawai", "perjalanan": [], "spj": {}, "total": {"perjalanan": 0, "hari": 0, "biaya": 0}}
    rows = db.execute("""SELECT st.id st_id, st.nomor, st.maksud, j.mulai, j.selesai, l.nama tempat, d.total, x.id spj_id, x.status spj_status, x.total spj_total
        FROM spd d JOIN surat_tugas st ON st.id=d.st_id AND st.status='Terbit' JOIN jadwal j ON j.id=st.jadwal_id JOIN lokasi l ON l.id=j.lokasi_id
        LEFT JOIN spj x ON x.spd_id=d.id WHERE d.pegawai_id=? AND substr(j.mulai,1,4)=? ORDER BY j.mulai""", (pid, str(tahun))).fetchall()
    akan = [r for r in rows if r["selesai"] >= hari][:8]
    spj: dict = {}
    for r in rows:
        spj[r["spj_status"] or "Belum dibuat"] = spj.get(r["spj_status"] or "Belum dibuat", 0) + 1
    hari_tot = sum((dt.date.fromisoformat(r["selesai"]) - dt.date.fromisoformat(r["mulai"])).days + 1 for r in rows)
    return {"peran": "pegawai", "perjalanan": akan, "spj": spj, "perlu_tindakan": [r for r in rows if r["spj_status"] in ("Draft", "Dikembalikan")][:8],
            "total": {"perjalanan": len(rows), "hari": hari_tot, "biaya": sum(r["total"] for r in rows)}}


@router.get("")
def dashboard(tahun: int, user=Depends(auth), db=Depends(get_db)):
    if user["role"] == "pegawai":
        return _pegawai(db, user, tahun)
    ok = [k for k in SUMBER if akses_uang(user, k, "baca")]                 # sumber yang boleh dilihat UANG-nya
    srt = [k for k in SUMBER if akses_sumber(user, k, "baca")]              # sumber untuk alur surat (Pembuat Surat: termasuk BLUD)
    ph = ",".join("?" * len(ok)) or "''"
    hari = dt.date.today()
    bulan_ini = hari.month if hari.year == tahun else 12
    out: dict = {"peran": user["role"], "tahun": tahun, "kepala_wajib": kepala_wajib(db), "sumber": ok}

    # --- serapan per sumber & per bulan
    pagu = {r["kode"]: r["j"] for r in db.execute(f"""SELECT sd.kode, COALESCE(SUM(b.jumlah),0) j FROM sumber_dana sd LEFT JOIN bok_menu m ON m.sumber_dana_id=sd.id AND m.tahun=?
        LEFT JOIN bok_rincian r ON r.menu_id=m.id LEFT JOIN bok_baris b ON b.rincian_id=r.id WHERE sd.kode IN ({ph}) GROUP BY sd.kode""", (tahun, *ok)).fetchall()}
    spj = {}
    for r in db.execute(f"""SELECT sd.kode, s.status, COALESCE(SUM(s.total),0) j, COUNT(*) n FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id
        WHERE s.tahun=? AND sd.kode IN ({ph}) GROUP BY sd.kode, s.status""", (tahun, *ok)).fetchall():
        spj.setdefault(r["kode"], {})[r["status"]] = {"jml": r["j"], "n": r["n"]}
    rencana = {r["kode"]: r["j"] for r in db.execute(f"""SELECT sd.kode, COALESCE(SUM(r.estimasi),0) j FROM rencana r JOIN sumber_dana sd ON sd.id=r.sumber_dana_id
        WHERE r.tahun=? AND r.status IN ('Disetujui','Terjadwal','Terlaksana','SPJ Selesai') AND sd.kode IN ({ph}) GROUP BY sd.kode""", (tahun, *ok)).fetchall()}
    srp = []
    for k in ok:
        s = spj.get(k, {})
        real = s.get("Dibayar", {}).get("jml", 0)
        proses = sum(s.get(x, {}).get("jml", 0) for x in ("Diajukan", "Diverifikasi"))
        srp.append({"sumber": k, "pagu": pagu.get(k, 0), "rencana": rencana.get(k, 0), "proses": proses, "realisasi": real, "sisa": pagu.get(k, 0) - real,
                    "persen": round(100 * real / pagu[k], 1) if pagu.get(k) else 0})
    out["serapan"] = srp
    out["total"] = {x: sum(s[x] for s in srp) for x in ("pagu", "rencana", "proses", "realisasi", "sisa")}
    out["total"]["persen"] = round(100 * out["total"]["realisasi"] / out["total"]["pagu"], 1) if out["total"]["pagu"] else 0
    bul_real, bul_ren = [0] * 12, [0] * 12
    for r in db.execute(f"""SELECT CAST(substr(COALESCE(s.tanggal_bayar,s.tanggal),6,2) AS INTEGER) b, SUM(s.total) j FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id
        WHERE s.tahun=? AND s.status='Dibayar' AND sd.kode IN ({ph}) GROUP BY b""", (tahun, *ok)).fetchall():
        bul_real[r["b"] - 1] += r["j"]
    for r in db.execute(f"""SELECT r.bulan b, SUM(r.estimasi) j FROM rencana r JOIN sumber_dana sd ON sd.id=r.sumber_dana_id
        WHERE r.tahun=? AND r.status IN ('Disetujui','Terjadwal','Terlaksana','SPJ Selesai') AND sd.kode IN ({ph}) GROUP BY r.bulan""", (tahun, *ok)).fetchall():
        bul_ren[r["b"] - 1] += r["j"]
    out["bulanan"] = {"rencana": bul_ren, "realisasi": bul_real}

    # --- tugas yang menunggu
    can_rencana = [k for k in srt if akses_sumber(user, k, "rencana")]       # rencana/jadwal/ST
    can_rencana_uang = [k for k in ok if akses_uang(user, k, "rencana")]     # SPJ draft
    can_pagu = [k for k in ok if akses_uang(user, k, "pagu")]
    pr = ",".join("?" * len(can_rencana)) or "''"
    pu = ",".join("?" * len(can_rencana_uang)) or "''"
    pp = ",".join("?" * len(can_pagu)) or "''"
    c = lambda q, a: db.execute(q, a).fetchone()["c"]  # noqa: E731
    setuju = boleh_setuju(db, user)
    tugas = []
    n = c(f"SELECT COUNT(*) c FROM rencana r JOIN sumber_dana sd ON sd.id=r.sumber_dana_id WHERE r.tahun=? AND r.status='Diajukan' AND sd.kode IN ({pr})", (tahun, *can_rencana)) if setuju else 0
    tugas.append({"kunci": "rencana", "label": "Rencana menunggu persetujuan", "n": n, "tujuan": "rencana"})
    n = c(f"SELECT COUNT(*) c FROM jadwal j JOIN sumber_dana sd ON sd.id=j.sumber_dana_id WHERE j.tahun=? AND j.status='Diusulkan' AND sd.kode IN ({pr})", (tahun, *can_rencana)) if setuju else 0
    tugas.append({"kunci": "jadwal", "label": "Jadwal diusulkan (belum disetujui)", "n": n, "tujuan": "jadwal"})
    sts = "('Disetujui','Diusulkan')" if setuju else "('Disetujui')"
    n = c(f"""SELECT COUNT(*) c FROM jadwal j JOIN sumber_dana sd ON sd.id=j.sumber_dana_id WHERE j.tahun=? AND j.status IN {sts} AND sd.kode IN ({pr})
        AND NOT EXISTS(SELECT 1 FROM surat_tugas s WHERE s.jadwal_id=j.id AND s.status='Terbit')""", (tahun, *can_rencana))
    tugas.append({"kunci": "st", "label": "Jadwal siap dibuatkan Surat Tugas", "n": n, "tujuan": "st"})
    n = c(f"""SELECT COUNT(*) c FROM surat_tugas s JOIN jadwal jj ON jj.id=s.jadwal_id JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE jj.tahun=? AND s.status='Terbit'
        AND (s.nomor_srikandi IS NULL OR NOT EXISTS(SELECT 1 FROM st_final f WHERE f.st_id=s.id)) AND sd.kode IN ({pr})""", (tahun, *can_rencana))
    tugas.append({"kunci": "srikandi", "label": "ST belum selesai di Srikandi (nomor / PDF final)", "n": n, "tujuan": "st"})
    n = c(f"SELECT COUNT(*) c FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE s.tahun=? AND s.status IN ('Draft','Dikembalikan') AND sd.kode IN ({pu})", (tahun, *can_rencana_uang))
    tugas.append({"kunci": "spj_draft", "label": "SPJ belum diajukan / dikembalikan", "n": n, "tujuan": "spj"})
    n = c(f"SELECT COUNT(*) c FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE s.tahun=? AND s.status='Diajukan' AND sd.kode IN ({pp})", (tahun, *can_pagu))
    tugas.append({"kunci": "verifikasi", "label": "SPJ menunggu verifikasi", "n": n, "tujuan": "spj"})
    n = c(f"SELECT COUNT(*) c FROM spj s JOIN sumber_dana sd ON sd.id=s.sumber_dana_id WHERE s.tahun=? AND s.status='Diverifikasi' AND sd.kode IN ({pp})", (tahun, *can_pagu))
    tugas.append({"kunci": "bayar", "label": "SPJ terverifikasi menunggu pembayaran", "n": n, "tujuan": "spj"})
    out["tugas"] = [t for t in tugas if t["n"]]

    # --- jadwal 14 hari ke depan (BLUD tersamar bagi yang tak berhak)
    sd_, ed_ = hari.isoformat(), (hari + dt.timedelta(days=14)).isoformat()
    jw = db.execute("""SELECT j.id, j.mulai, j.selesai, j.kegiatan, j.status, sd.kode dana, l.nama lokasi, (SELECT COUNT(*) FROM jadwal_petugas p WHERE p.jadwal_id=j.id) petugas,
        EXISTS(SELECT 1 FROM surat_tugas s WHERE s.jadwal_id=j.id AND s.status='Terbit') punya_st
        FROM jadwal j JOIN sumber_dana sd ON sd.id=j.sumber_dana_id JOIN lokasi l ON l.id=j.lokasi_id
        WHERE j.status IN ('Diusulkan','Disetujui') AND j.selesai>=? AND j.mulai<=? ORDER BY j.mulai, j.id LIMIT 12""", (sd_, ed_)).fetchall()
    for j in jw:
        if j["dana"] not in srt:
            j["kegiatan"], j["lokasi"] = "Kegiatan BLUD (terbatas)", "-"
    out["jadwal_dekat"] = jw

    # --- peringatan
    pr_ = []
    for r in db.execute(f"""SELECT sd.kode, b.id, b.uraian, b.jumlah pagu, COALESCE((SELECT SUM(s.total) FROM spj s WHERE s.baris_id=b.id AND s.status='Dibayar'),0) real,
        COALESCE((SELECT SUM(s.total) FROM spj s WHERE s.baris_id=b.id AND s.status IN ('Diajukan','Diverifikasi')),0) proses
        FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id JOIN sumber_dana sd ON sd.id=m.sumber_dana_id
        WHERE m.tahun=? AND sd.kode IN ({ph}) AND b.jumlah>0""", (tahun, *ok)).fetchall():
        if r["real"] + r["proses"] > r["pagu"]:
            pr_.append({"level": "bad", "teks": f"{r['kode']}: «{r['uraian']}» melebihi pagu baris (realisasi+proses {r['real'] + r['proses']:,} > pagu {r['pagu']:,}).".replace(",", ".")})
        elif r["real"] >= 0.9 * r["pagu"]:
            pr_.append({"level": "warn", "teks": f"{r['kode']}: «{r['uraian']}» terserap {round(100 * r['real'] / r['pagu'])}% dari pagu baris."})
    batas = _set(db, "batas_hari_dinas_bulan", 10)
    for r in db.execute("""SELECT p.nama, COUNT(*) n FROM penugasan_hari h JOIN pegawai p ON p.id=h.pegawai_id
        WHERE substr(h.tanggal,1,7)=? GROUP BY h.pegawai_id HAVING n>?""", (hari.strftime("%Y-%m"), batas)).fetchall():
        pr_.append({"level": "warn", "teks": f"{r['nama']} dinas luar {r['n']} hari bulan ini (batas {batas})."})
    if tahun == hari.year and bulan_ini > 1 and out["total"]["pagu"] and out["total"]["persen"] < 100 * (bulan_ini - 1) / 12 * 0.5:
        pr_.append({"level": "info", "teks": f"Serapan {out['total']['persen']}% — jauh di bawah target linier bulan berjalan ({round(100 * (bulan_ini - 1) / 12)}%)."})
    out["peringatan"] = pr_[:12]

    # --- keuangan (Kepala + Bendahara BLUD saja)
    if user["role"] in ("kepala", "bendahara_blud"):
        from .laporan import susun
        d = susun(db, tahun, bulan_ini)
        g = lambda rep, kata, i=0: next((r["v"][i] for r in d[rep]["baris"] if r.get("u", "").startswith(kata) and r["v"]), 0)  # noqa: E731
        out["keuangan"] = {"bulan": bulan_ini, "pendapatan": g("lra", "JUMLAH PENDAPATAN", 1), "belanja": g("lra", "JUMLAH BELANJA", 1), "surplus_lra": g("lra", "SURPLUS", 1),
                           "surplus_lo": g("lo", "SURPLUS", 0), "kas": g("lak", "SALDO KAS AKHIR", 0), "aset": g("neraca", "JUMLAH ASET", 0), "ekuitas": g("neraca", "JUMLAH EKUITAS", 0),
                           "seimbang": not d["neraca"]["catatan"]}
    # --- ringkasan perjalanan dinas tahun ini
    rd = db.execute(f"""SELECT COUNT(DISTINCT st.id) st, COUNT(*) orang FROM spd d JOIN surat_tugas st ON st.id=d.st_id AND st.status='Terbit' JOIN jadwal j ON j.id=st.jadwal_id
        JOIN sumber_dana sd ON sd.id=st.sumber_dana_id WHERE substr(j.mulai,1,4)=? AND sd.kode IN ({",".join("?" * len(srt)) or "''"})""", (str(tahun), *srt)).fetchone()
    out["dinas"] = {"st": rd["st"], "orang": rd["orang"]}
    return out
