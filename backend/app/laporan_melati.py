"""Laporan Keuangan BLUD UPT Puskesmas Melati — FORMAT RESMI Puskesmas (sesuai contoh Semester 1 2026):
sampul · daftar isi · pengantar · SPTJM · LRA · Neraca · Laporan Operasional · LPE · CaLK Bab I–VII, plus LRA BLUD (F-07).
Kode rekening BAS bertingkat (akun.kode_bas), kolom pembanding tahun lalu, angka berformat 1.234.567,00.
Catatan format (mengikuti contoh): LRA SKPD & LO hanya memuat belanja/beban; RK PPKD adalah penyeimbang ekuitas.
Hanya Kepala dan Bendahara BLUD."""
import calendar
import datetime as dt
import io
import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response

from . import dokumen as dk
from .akuntansi import akses, peta_belanja
from .core import Gagal, audit, get_db
from .surat import DOCX, _pdf_ke_docx

router = APIRouter(prefix="/api/laporan-melati")
TEMPLAT = json.loads((Path(__file__).parent / "assets" / "calk_melati.json").read_text(encoding="utf-8"))
BAGIAN = ("lra", "lra_blud", "neraca", "lo", "lpe", "calk")
KODE_MODAL_BLUD, KODE_MODAL_LAIN = "5.2.02.99.099", "5.2.02.01.001"


# ---------------------------------------------------------------- format angka
def f2(n) -> str:
    n = int(round(n or 0))
    s = f"{abs(n):,}".replace(",", ".") + ",00"
    return f"({s})" if n < 0 else s


def fp(a, b) -> str:
    if not b:
        return "0,00"
    p = round(100 * a / b, 2)
    s = f"{abs(p):.2f}".replace(".", ",")
    return f"({s})" if p < 0 else s


def _set(db, k, d=""):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    return r["nilai"] if r and r["nilai"] is not None else d


def _akhir(tahun, bulan):
    return f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]:02d}"


def _tgl(s):
    d = dt.date.fromisoformat(s)
    return f"{d.day} {dk.BULAN[d.month - 1]} {d.year}"


def _periode(tahun, bulan):
    return f"1 Januari {tahun} Sampai {_tgl(_akhir(tahun, bulan))}"


# ---------------------------------------------------------------- data
def _muat(db, sampai):
    return db.execute("""SELECT j.id jid, j.tanggal, j.basis, sd.kode dana, a.id akun_id, a.kode, a.nama, a.jenis, a.normal, a.kas, a.lra, a.kode_bas, a.kode_lra, b.debit d, b.kredit k
        FROM jurnal_baris b JOIN jurnal j ON j.id=b.jurnal_id JOIN akun a ON a.id=b.akun_id LEFT JOIN sumber_dana sd ON sd.id=j.sumber_dana_id WHERE j.tanggal<=?""", (sampai,)).fetchall()


def _kb(x):
    return x["kode_bas"] or x["kode"]


def _nama_bas(db):
    return {r["kode"]: r["nama"] for r in db.execute("SELECT kode, nama FROM bas_nama").fetchall()}


def _ada_jurnal(db, tahun):
    return bool(db.execute("SELECT 1 FROM jurnal WHERE substr(tanggal,1,4)=? AND basis!='AWAL' LIMIT 1", (str(tahun),)).fetchone())


def _anggaran(db, tahun):
    bel, bel_blud, pend = {}, {}, {}
    for r in db.execute("""SELECT b.jenis_belanja, sd.kode dana, SUM(b.jumlah) j FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id
        JOIN sumber_dana sd ON sd.id=m.sumber_dana_id WHERE m.tahun=? GROUP BY b.jenis_belanja, sd.kode""", (tahun,)).fetchall():
        kode = peta_belanja(r["jenis_belanja"], r["dana"])
        a = db.execute("SELECT kode_bas, kode_lra, lra FROM akun WHERE kode=?", (kode,)).fetchone()
        if a and a["lra"] == "BELANJA_MODAL":
            kode = KODE_MODAL_BLUD if r["dana"] == "BLUD" else KODE_MODAL_LAIN
        else:
            kode = (a["kode_bas"] if a else None) or kode
        bel[kode] = bel.get(kode, 0) + r["j"]
        if r["dana"] == "BLUD":
            bel_blud[kode] = bel_blud.get(kode, 0) + r["j"]
    for r in db.execute("SELECT a.kode, a.kode_bas, p.jumlah FROM anggaran_pendapatan p JOIN akun a ON a.id=p.akun_id WHERE p.tahun=?", (tahun,)).fetchall():
        k = r["kode_bas"] or r["kode"]
        if k.startswith("4.1.04.16"):
            pend[k] = pend.get(k, 0) + r["jumlah"]
    return bel, bel_blud, pend


def _pembanding(db, tahun, laporan):
    return {r["kode"]: r["jumlah"] for r in db.execute("SELECT kode, jumlah FROM pembanding WHERE tahun=? AND laporan=?", (tahun, laporan)).fetchall()}


def hitung(db, tahun, bulan):
    """Agregat satu periode (1 Jan – akhir bulan) dan posisi neraca pada akhir periode."""
    dari, sampai = f"{tahun}-01-01", _akhir(tahun, bulan)
    L = _muat(db, sampai)
    bel, bel_blud, pend_blud, beban = {}, {}, {}, {}
    for x in L:
        if x["basis"] == "AWAL" or not (dari <= x["tanggal"] <= sampai):
            continue
        if x["jenis"] == "BEBAN":
            beban_k = _kb(x)
            beban_k = ("8." + beban_k[2:]) if beban_k.startswith("5.") else beban_k
            beban[beban_k] = beban.get(beban_k, 0) + x["d"] - x["k"]
        if x["basis"] != "KAS":
            continue
        if x["jenis"] == "BEBAN":
            kd = _kb(x)
            bel[kd] = bel.get(kd, 0) + x["d"] - x["k"]
            if x["dana"] == "BLUD":
                bel_blud[kd] = bel_blud.get(kd, 0) + x["d"] - x["k"]
        elif x["lra"] == "BELANJA_MODAL":
            kd = KODE_MODAL_BLUD if x["dana"] == "BLUD" else KODE_MODAL_LAIN
            bel[kd] = bel.get(kd, 0) + x["d"] - x["k"]
            if x["dana"] == "BLUD":
                bel_blud[kd] = bel_blud.get(kd, 0) + x["d"] - x["k"]
        elif x["jenis"] == "PENDAPATAN" and _kb(x).startswith("4.1.04.16"):
            pend_blud[_kb(x)] = pend_blud.get(_kb(x), 0) + x["k"] - x["d"]
    # neraca pada akhir periode
    aset, kew = {}, {}
    nama_akun = {}
    for x in L:
        k = _kb(x)
        nama_akun.setdefault(k, x["nama"])
        if x["jenis"] == "ASET":
            aset[k] = aset.get(k, 0) + ((x["d"] - x["k"]) if x["normal"] == "D" else -(x["k"] - x["d"]))
        elif x["jenis"] == "KEWAJIBAN":
            kew[k] = kew.get(k, 0) + x["k"] - x["d"]
    ek_awal = 0   # ekuitas pada awal periode = (aset − kewajiban) sebelum periode, termasuk saldo awal
    for x in L:
        if x["basis"] == "AWAL" or x["tanggal"] < dari:
            if x["jenis"] == "ASET":
                ek_awal += (x["d"] - x["k"]) if x["normal"] == "D" else -(x["k"] - x["d"])
            elif x["jenis"] == "KEWAJIBAN":
                ek_awal -= x["k"] - x["d"]
    return {"bel": bel, "bel_blud": bel_blud, "pend_blud": pend_blud, "beban": beban, "aset": aset, "kew": kew, "ek_awal": ek_awal, "nama": nama_akun, "sampai": sampai}


def _surplus_lo(db, h):
    pend = sum(h["pend_blud"].values()) if _set(db, "melati_lo_pendapatan", "0") == "1" else 0
    return pend - sum(h["beban"].values())


def _ek_tiga(db, h):
    """Tiga baris ekuitas pada Neraca: Ekuitas (awal), Surplus/Defisit-LO, RK PPKD (penyeimbang)."""
    ek_akhir = sum(h["aset"].values()) - sum(h["kew"].values())
    lo = _surplus_lo(db, h)
    return h["ek_awal"], lo, ek_akhir - h["ek_awal"] - lo, ek_akhir


# ---------------------------------------------------------------- pohon kode BAS
def _induk(kode):
    seg = kode.split(".")
    return [".".join(seg[:i]) for i in range(1, len(seg))]


def pohon(db, daun: dict, nama_daun: dict, kolom: int, awalan: tuple | None = None, akar: bool = False):
    """daun = {kode: [nilai_kolom...]} -> baris berurutan dengan induk teragregasi. Nama dari bas_nama (induk & daun), cadangan: nama akun."""
    bn = _nama_bas(db)
    nilai: dict = {}
    for k, v in daun.items():
        if (awalan and not k.startswith(awalan)) or not any(v):
            continue
        for kk in _induk(k) + [k]:
            cur = nilai.setdefault(kk, [0] * kolom)
            for i in range(kolom):
                cur[i] += v[i]
    rows = []
    for k in sorted(nilai, key=lambda c: [int(p) if p.isdigit() else 0 for p in c.split(".")]):
        if not akar and "." not in k:
            continue
        rows.append({"k": k, "u": bn.get(k) or nama_daun.get(k) or k, "v": nilai[k], "b": len(k) <= 3, "lv": len(k.split(".")) - 1})
    return rows


def _jumlah(u, kolom_vals, b=True):
    return {"k": "", "u": u, "v": kolom_vals, "b": b, "lv": 0}


def _tot(rows, depth=1):
    return [sum(r["v"][i] for r in rows if r["lv"] == depth) for i in range(len(rows[0]["v"]))] if rows else None


# ---------------------------------------------------------------- penyusun laporan
def _lra_rows(db, tahun, bulan, blud: bool):
    h = hitung(db, tahun, bulan)
    ada_lalu = _ada_jurnal(db, tahun - 1)
    hl = hitung(db, tahun - 1, 12) if ada_lalu else None
    bel_ang, bel_ang_blud, pend_ang = _anggaran(db, tahun)
    pb = _pembanding(db, tahun - 1, "lra")
    sumber_b, ang_b = (h["bel_blud"], bel_ang_blud) if blud else (h["bel"], bel_ang)
    lalu_b = (hl["bel_blud"] if blud else hl["bel"]) if hl else {}
    nama = {**h["nama"]}
    kodes = set(sumber_b) | set(ang_b) | set(lalu_b) | {k for k in pb if k.startswith("5.") and (not blud or ".99." in k)}
    daun = {k: [ang_b.get(k, 0), sumber_b.get(k, 0), lalu_b.get(k, pb.get(k, 0))] for k in kodes}
    rows = []
    jum = lambda r: [sum(x["v"][i] for x in r if x["lv"] == 1) for i in range(3)]  # noqa: E731
    if blud:
        pk = set(pend_ang) | set(h["pend_blud"]) | ({k for k in pb if k.startswith("4.")})
        dp = {k: [pend_ang.get(k, 0), h["pend_blud"].get(k, 0), (hitung(db, tahun - 1, 12)["pend_blud"].get(k, 0) if ada_lalu else pb.get(k, 0))] for k in pk}
        rp_ = pohon(db, dp, nama, 3, None, True)
        rows += rp_
        tot_p = [sum(v[i] for v in dp.values()) for i in range(3)]
        rows += [_jumlah("JUMLAH PENDAPATAN ASLI DAERAH", tot_p), _jumlah("JUMLAH PENDAPATAN", tot_p)]
    else:
        tot_p = [0, 0, 0]
    rop = pohon(db, daun, nama, 3, ("5.1",))
    rmo = pohon(db, daun, nama, 3, ("5.2",))
    rows += [{"k": "5", "u": "BELANJA DAERAH", "v": [sum(v[i] for v in daun.values()) for i in range(3)], "b": True, "lv": 0}]
    rows += rop
    top = [sum(v[i] for k, v in daun.items() if k.startswith("5.1")) for i in range(3)]
    tmo = [sum(v[i] for k, v in daun.items() if k.startswith("5.2")) for i in range(3)]
    if rop:
        rows.append(_jumlah("JUMLAH BELANJA OPERASI", top))
    rows += rmo
    if rmo:
        rows.append(_jumlah("JUMLAH BELANJA MODAL", tmo))
    tb = [top[i] + tmo[i] for i in range(3)]
    rows.append(_jumlah("JUMLAH BELANJA", tb))
    sur = [tot_p[i] - tb[i] for i in range(3)]
    rows += [_jumlah("SURPLUS/DEFISIT", sur), _jumlah("SISA LEBIH PEMBIAYAAN ANGGARAN", sur)]
    return rows, {"belanja": tb, "pendapatan": tot_p}


def _lalu_neraca(db, tahun):
    """Neraca akhir tahun lalu: dari jurnal bila ada, selain itu dari tabel pembanding."""
    if _ada_jurnal(db, tahun - 1):
        h = hitung(db, tahun - 1, 12)
        eka, lo, rk, ekt = _ek_tiga(db, h)
        return h["aset"], h["kew"], (eka, lo, rk), True
    pb = _pembanding(db, tahun - 1, "neraca")
    aset = {k: v for k, v in pb.items() if k.startswith("1.")}
    kew = {k: v for k, v in pb.items() if k.startswith("2.")}
    return aset, kew, (pb.get("3.1.01.01.001", 0), pb.get("3.1.01.02.01", 0), pb.get("3.1.03.01.001", 0)), bool(pb)


def _neraca_rows(db, tahun, bulan):
    h = hitung(db, tahun, bulan)
    la, lk, (leka, llo, lrk), ada = _lalu_neraca(db, tahun)
    nama = h["nama"]
    kode = set(h["aset"]) | set(la)
    daun = {k: [h["aset"].get(k, 0), la.get(k, 0)] for k in kode}
    rows = [{"k": "1", "u": "ASET", "v": [sum(v[0] for v in daun.values()), sum(v[1] for v in daun.values())], "b": True, "lv": 0}]
    for awalan, judul in (("1.1", "JUMLAH ASET LANCAR"), ("1.3", "JUMLAH ASET TETAP")):
        r = pohon(db, daun, nama, 2, (awalan,))
        rows += r
        if r:
            rows.append(_jumlah(judul, [sum(v[0] for k, v in daun.items() if k.startswith(awalan)), sum(v[1] for k, v in daun.items() if k.startswith(awalan))]))
    lain = {k: v for k, v in daun.items() if not k.startswith(("1.1", "1.3"))}
    rows += pohon(db, lain, nama, 2)
    ta = [sum(v[0] for v in daun.values()), sum(v[1] for v in daun.values())]
    rows.append(_jumlah("JUMLAH ASET", ta))
    dk_ = {k: [h["kew"].get(k, 0), lk.get(k, 0)] for k in set(h["kew"]) | set(lk)}
    tk = [sum(v[0] for v in dk_.values()), sum(v[1] for v in dk_.values())]
    if dk_ and any(tk):
        rows.append({"k": "2", "u": "KEWAJIBAN", "v": tk, "b": True, "lv": 0})
        rows += pohon(db, dk_, nama, 2)
        rows.append(_jumlah("JUMLAH KEWAJIBAN", tk))
    eka, lo, rk, ekt = _ek_tiga(db, h)
    ekt_l = leka + llo + lrk
    rows += [{"k": "3", "u": "EKUITAS", "v": [ekt, ekt_l], "b": True, "lv": 0}, {"k": "3.1", "u": "EKUITAS", "v": [ekt, ekt_l], "b": False, "lv": 1},
             {"k": "3.1.01", "u": "Ekuitas", "v": [eka + lo, leka + llo], "b": False, "lv": 2},
             {"k": "3.1.01.01", "u": "Ekuitas", "v": [eka, leka], "b": False, "lv": 3}, {"k": "3.1.01.01.001", "u": "Ekuitas", "v": [eka, leka], "b": False, "lv": 4},
             {"k": "3.1.01.02", "u": "Surplus/Defisit-LO", "v": [lo, llo], "b": False, "lv": 3}, {"k": "3.1.01.02.01", "u": "Surplus/Defisit-LO", "v": [lo, llo], "b": False, "lv": 4},
             {"k": "3.1.03", "u": "Ekuitas untuk Dikonsolidasikan", "v": [rk, lrk], "b": False, "lv": 2}, {"k": "3.1.03.01", "u": "RK PPKD", "v": [rk, lrk], "b": False, "lv": 3},
             {"k": "3.1.03.01.001", "u": "RK PPKD", "v": [rk, lrk], "b": False, "lv": 4},
             _jumlah("JUMLAH EKUITAS", [ekt, ekt_l]), _jumlah("JUMLAH KEWAJIBAN DAN EKUITAS", [tk[0] + ekt, tk[1] + ekt_l])]
    return rows, {"aset": ta, "ekuitas": [ekt, ekt_l], "ek_tiga": (eka, lo, rk), "lalu_ada": ada}


def _lo_rows(db, tahun, bulan):
    h = hitung(db, tahun, bulan)
    ada = _ada_jurnal(db, tahun - 1)
    hl = hitung(db, tahun - 1, 12) if ada else None
    pb = _pembanding(db, tahun - 1, "lo")
    kodes = set(h["beban"]) | set(hl["beban"] if hl else {}) | {k for k in pb if k.startswith("8.")}
    daun = {k: [h["beban"].get(k, 0), (hl["beban"].get(k, 0) if hl else pb.get(k, 0))] for k in kodes}
    r = pohon(db, daun, {**h["nama"]}, 2, ("8.1",))
    bn = _nama_bas(db)
    for x in r:   # nama baris beban = nama belanja dengan awalan Beban
        x["u"] = (bn.get("5." + x["k"][2:]) or x["u"]).replace("Belanja", "Beban", 1).replace("BELANJA", "BEBAN", 1)
    t = [sum(v[0] for v in daun.values()), sum(v[1] for v in daun.values())]
    rows = [{"k": "8", "u": "BEBAN", "v": t, "b": True, "lv": 0}] + r
    rows += [_jumlah("JUMLAH BEBAN OPERASI", t), _jumlah("JUMLAH BEBAN", t)]
    sur = [-t[0], -t[1]]
    if _set(db, "melati_lo_pendapatan", "0") == "1":
        sur = [sum(h["pend_blud"].values()) - t[0], (sum(hl["pend_blud"].values()) if hl else 0) - t[1]]
    rows.append(_jumlah("SURPLUS/DEFISIT-LO", sur))
    return rows, {"beban": t, "surplus": sur}


def _lpe_rows(db, tahun, bulan):
    h = hitung(db, tahun, bulan)
    la, lk, (leka, llo, lrk), ada = _lalu_neraca(db, tahun)
    eka, lo, rk, ekt = _ek_tiga(db, h)
    lal = leka + llo + lrk
    rows = [["EKUITAS AWAL", leka, eka], ["SURPLUS / (DEFISIT) - LO", llo, lo], ["RK PPKD", lrk, rk], ["DAMPAK KUMULATIF PERUBAHAN KEBIJAKAN/KESALAHAN MENDASAR", None, None],
            ["KOREKSI NILAI PERSEDIAAN", 0, 0], ["KOREKSI SELISIH REVALUASI ASET TETAP", 0, 0], ["LAIN-LAIN", 0, 0], ["EKUITAS AKHIR", lal, ekt]]
    return rows, {"awal": eka, "akhir": ekt}


# ---------------------------------------------------------------- tampilan JSON
def _pejabat(db):
    k = db.execute("SELECT nama, nip, jabatan FROM pejabat WHERE aktif=1 AND (peran LIKE '%Penandatangan%' OR jabatan LIKE 'Kepala%') ORDER BY id LIMIT 1").fetchone() or {"nama": "", "nip": "", "jabatan": "Kepala"}
    return k


def _nip(n):   # 19911123 202012 1 008
    n = "".join(ch for ch in str(n or "") if ch.isdigit())
    return f"{n[:8]} {n[8:14]} {n[14:15]} {n[15:]}".strip() if len(n) == 18 else n


def susun(db, tahun, bulan, bagian):
    if not 2000 < tahun < 2100 or not 1 <= bulan <= 12:
        raise Gagal("Tahun/bulan tidak valid.")
    judul_per = _periode(tahun, bulan)
    if bagian == "lra":
        rows, ang = _lra_rows(db, tahun, bulan, False)
        return {"jenis": "lra", "judul": ["PEMERINTAHAN KABUPATEN KAPUAS", _set(db, "bku_skpd", "PUSKESMAS MELATI").title().upper(), "LAPORAN REALISASI ANGGARAN PENDAPATAN DAN BELANJA DAERAH", f"TAHUN ANGGARAN {tahun}", judul_per],
                "kolom": ["Kode Rekening", "URAIAN", "ANGGARAN", f"REALISASI {tahun}", f"% {tahun}", f"REALISASI {tahun - 1}"], "angka": ["1", "2", "3", "4", "5 = (4/3)*100", "6"], "rows": rows, "ttd": "KEPALA PUSKESMAS MELATI"}
    if bagian == "lra_blud":
        rows, ang = _lra_rows(db, tahun, bulan, True)
        return {"jenis": "lra_blud", "judul": ["PEMERINTAHAN KAB. KAPUAS", "BLUD PUSKESMAS MELATI", "LAPORAN REALISASI ANGGARAN PENDAPATAN DAN BELANJA DAERAH", f"TAHUN ANGGARAN {tahun}", judul_per.replace("1 Januari", "01 Januari")],
                "kolom": ["Kode Rekening", "URAIAN", "ANGGARAN", f"REALISASI {tahun}", f"% {tahun}", f"REALISASI {tahun - 1}"], "angka": ["1", "2", "3", "4", "5 = (4/3)*100", "6"], "rows": rows, "ttd": "KEPALA BLUD PUSKESMAS MELATI"}
    if bagian == "neraca":
        rows, info = _neraca_rows(db, tahun, bulan)
        return {"jenis": "neraca", "judul": ["PEMERINTAHAN KABUPATEN KAPUAS", "PUSKESMAS MELATI", "NERACA", f"TAHUN ANGGARAN {tahun}", judul_per, "(Dalam Rupiah)"], "kolom": ["Kode Rekening", "Uraian", str(tahun), str(tahun - 1)], "rows": rows, "ttd": "KEPALA PUSKESMAS MELATI", "info": info}
    if bagian == "lo":
        rows, info = _lo_rows(db, tahun, bulan)
        return {"jenis": "lo", "judul": ["PEMERINTAHAN KABUPATEN KAPUAS", "Puskesmas Melati", "LAPORAN OPERASIONAL", f"TAHUN ANGGARAN {tahun}", judul_per, "Dalam Rupiah"], "kolom": ["Kode Rekening", "Uraian", str(tahun), str(tahun - 1), "Kenaikan / Penurunan", "%"], "rows": rows, "ttd": "KEPALA PUSKESMAS MELATI", "info": info, "bagian_judul": "KEGIATAN OPERASIONAL"}
    if bagian == "lpe":
        rows, info = _lpe_rows(db, tahun, bulan)
        return {"jenis": "lpe", "judul": ["PEMERINTAH KAB. KAPUAS", "PUSKESMAS MELATI", "LAPORAN PERUBAHAN EKUITAS", f"{_periode(tahun, bulan).upper()}", "(Dalam Rupiah)"], "kolom": ["URAIAN", str(tahun - 1), str(tahun)], "rows": rows, "ttd": "KEPALA PUSKESMAS MELATI", "info": info}
    raise Gagal("Bagian laporan tidak dikenal.", 404)


@router.get("")
def lihat(tahun: int, bulan: int = 6, bagian: str = "lra", user=Depends(akses), db=Depends(get_db)):
    d = susun(db, tahun, bulan, bagian)
    d["tanggal_ttd"] = _tgl(_akhir(tahun, bulan))
    d["pejabat"] = _pejabat(db)
    return d


@router.get("/pembanding")
def lihat_pembanding(tahun: int, user=Depends(akses), db=Depends(get_db)):
    """Data pembanding = angka TAHUN LALU (tahun-1) yang diinput manual bila jurnalnya belum ada di SIKADIN."""
    return {laporan: [{"kode": r["kode"], "jumlah": r["jumlah"]} for r in db.execute("SELECT kode, jumlah FROM pembanding WHERE tahun=? AND laporan=? ORDER BY kode", (tahun - 1, laporan)).fetchall()] for laporan in ("lra", "lo", "neraca")}


@router.put("/pembanding")
def simpan_pembanding(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    tahun, laporan = int(body.get("tahun") or 0), str(body.get("laporan") or "")
    if laporan not in ("lra", "lo", "neraca") or not 2000 < tahun < 2100:
        raise Gagal("Laporan/tahun tidak valid.")
    db.execute("DELETE FROM pembanding WHERE tahun=? AND laporan=?", (tahun - 1, laporan))
    n = 0
    for x in body.get("items") or []:
        kode = str(x.get("kode") or "").strip()
        if not kode or not all(p.isdigit() for p in kode.split(".")):
            raise Gagal(f"Kode rekening tidak valid: {kode!r}.")
        try:
            jml = int(round(float(str(x.get("jumlah")).replace(".", "").replace(",", ".") if isinstance(x.get("jumlah"), str) else x.get("jumlah"))))
        except (TypeError, ValueError):
            raise Gagal(f"Jumlah untuk {kode} tidak valid.")
        db.execute("INSERT INTO pembanding(tahun,laporan,kode,jumlah) VALUES(?,?,?,?)", (tahun - 1, laporan, kode, jml))
        n += 1
    audit(db, user, "pembanding", tahun, "UBAH", None, {"laporan": laporan, "baris": n}, "BLUD")
    return {"ok": True, "baris": n}


# ---------------------------------------------------------------- CaLK
NAMA_TEKS = {"pengantar": "Pengantar", "sptjm": "Pernyataan Tanggung Jawab", "bab1": "Bab I Pendahuluan", "bab2": "Bab II Tugas Pokok, Fungsi, Indikator Kinerja", "bab3": "Bab III Ikhtisar Pencapaian Kinerja (tambahan narasi)",
             "bab4": "Bab IV Kebijakan Akuntansi", "bab6": "Bab VI Informasi Non Keuangan", "bab7": "Bab VII Penutup"}


def _teks(db, tahun, kunci):
    r = db.execute("SELECT isi FROM calk WHERE tahun=? AND bagian=?", (tahun, "m_" + kunci)).fetchone()
    if r and r["isi"].strip():
        return r["isi"]
    t = TEMPLAT.get(kunci, "")
    if kunci in ("pengantar", "sptjm", "bab6", "bab7"):
        t = t.replace("2026", str(tahun)).replace("2025", str(tahun - 1))
    return t


@router.get("/teks")
def daftar_teks(tahun: int, user=Depends(akses), db=Depends(get_db)):
    return [{"kode": k, "judul": v, "isi": _teks(db, tahun, k)} for k, v in NAMA_TEKS.items()]


@router.put("/teks")
def simpan_teks(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    tahun = int(body.get("tahun") or 0)
    for k, isi in (body.get("teks") or {}).items():
        if k in NAMA_TEKS:
            db.execute("INSERT INTO calk(tahun,bagian,isi) VALUES(?,?,?) ON CONFLICT(tahun,bagian) DO UPDATE SET isi=excluded.isi", (tahun, "m_" + k, str(isi)[:60000]))
    audit(db, user, "calk", tahun, "UBAH-MELATI", None, {"bagian": list((body.get("teks") or {}).keys())}, "BLUD")
    return {"ok": True}


# ---------------------------------------------------------------- cetak PDF
def _p(t, rata="l", tebal=False, ukuran=7.8):
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    return Paragraph(str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;") if False else str(t if t is not None else ""),
                     ParagraphStyle("m", fontName=dk.FONTB if tebal else dk.FONT, fontSize=ukuran, leading=ukuran + 2, alignment={"l": TA_LEFT, "c": TA_CENTER, "r": TA_RIGHT}[rata]))


def _esc(t):
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _blok_judul(judul):
    from reportlab.platypus import Spacer
    out = []
    for i, j in enumerate(judul):
        out.append(_p(f"<b>{_esc(j)}</b>", "c", True, 10 if i in (1, 2) else 9))
    return out + [Spacer(1, 6)]


def _ttd(db, d, tanggal, jabatan):
    from reportlab.platypus import Spacer, Table, TableStyle
    k = _pejabat(db)
    kota = _set(db, "kota_surat", "Kuala Kapuas")
    t = Table([["", [_p(f"{_esc(kota)}, {tanggal}", "l", False, 9), _p(f"<b>{_esc(jabatan)}</b>", "l", True, 9), Spacer(1, 40), _p(f"<b>{_esc(k['nama'])}</b>", "l", True, 9), _p(f"NIP. {_nip(k['nip'])}", "l", False, 9)]]],
              colWidths=[9.5 * dk.cm, 7.5 * dk.cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [Spacer(1, 14), t]


def _tabel_statement(d):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    kol = d["kolom"]
    n_nilai = len(kol) - 2 if d["jenis"] != "lpe" else len(kol) - 1
    if d["jenis"] == "lpe":
        data = [[_p(f"<b>{_esc(kol[0])}</b>", "c", True), _p(f"<b>{kol[1]}</b>", "c", True), _p(f"<b>{kol[2]}</b>", "c", True)]]
        for u, a, b in d["rows"]:
            tebal = u in ("EKUITAS AWAL", "EKUITAS AKHIR")
            data.append([_p(f"<b>{u}</b>" if tebal else u, "l", tebal), _p("" if a is None else f2(a), "r", tebal), _p("" if b is None else f2(b), "r", tebal)])
        t = Table(data, colWidths=[9.2 * dk.cm, 3.9 * dk.cm, 3.9 * dk.cm])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), dk.FONT), ("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t
    lebar = {"lra": [2.4, 5.4, 2.7, 2.7, 1.8, 2.7], "lra_blud": [2.4, 5.4, 2.7, 2.7, 1.8, 2.7], "neraca": [3.0, 8.2, 3.0, 3.0], "lo": [2.3, 5.2, 2.5, 2.5, 2.5, 1.3]}[d["jenis"]]
    data = [[_p(f"<b>{_esc(x)}</b>", "c", True, 7.4) for x in kol]]
    if "angka" in d:
        data.append([_p(x, "c", False, 7) for x in d["angka"]])
    if d.get("bagian_judul"):
        data.append(["", _p(f"<b>{d['bagian_judul']}</b>", "l", True), "", "", "", ""])
    stil = []
    for r in d["rows"]:
        v = r["v"]
        tebal = r["b"]
        ind = "&nbsp;" * (2 * r["lv"] if d["jenis"] in ("neraca",) else 0)
        if d["jenis"] in ("lra", "lra_blud"):
            cells = [_p(r["k"], "l", tebal), _p(f"{'<b>' if tebal else ''}{_esc(r['u'])}{'</b>' if tebal else ''}", "l", tebal), _p(f2(v[0]), "r", tebal), _p(f2(v[1]), "r", tebal), _p(fp(v[1], v[0]) if r["k"] or True else "", "r", tebal), _p(f2(v[2]), "r", tebal)]
        elif d["jenis"] == "neraca":
            cells = [_p(r["k"], "l", tebal), _p(f"{ind}{'<b>' if tebal else ''}{_esc(r['u'])}{'</b>' if tebal else ''}", "l", tebal), _p(f2(v[0]), "r", tebal), _p(f2(v[1]), "r", tebal)]
        else:   # lo
            sel = v[0] - v[1]
            cells = [_p(r["k"], "l", tebal), _p(f"{'<b>' if tebal else ''}{_esc(r['u'])}{'</b>' if tebal else ''}", "l", tebal), _p(f2(v[0]), "r", tebal), _p(f2(v[1]), "r", tebal), _p(f2(sel), "r", tebal), _p(fp(sel, v[1]), "r", tebal)]
        data.append(cells)
        if r["u"].startswith(("JUMLAH", "SURPLUS", "SISA")):
            stil.append(("LINEABOVE", (0, len(data) - 1), (-1, len(data) - 1), 0.6, colors.black))
    t = Table(data, colWidths=[w * dk.cm for w in lebar], repeatRows=2 if "angka" in d else 1)
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), dk.FONT), ("FONTSIZE", (0, 0), (-1, -1), 7.8), ("GRID", (0, 0), (-1, 1 if "angka" in d else 0), 0.5, colors.black), ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                           ("LINEBEFORE", (2, 0), (-1, -1), 0.3, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)] + stil))
    return t


def _story_statement(db, tahun, bulan, bagian):
    d = susun(db, tahun, bulan, bagian)
    return _blok_judul(d["judul"]) + [_tabel_statement(d)] + _ttd(db, d, _tgl(_akhir(tahun, bulan)), d["ttd"]), d


def _para(teks, ukuran=10, rata="j"):
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer
    out = []
    st = ParagraphStyle("t", fontName=dk.FONT, fontSize=ukuran, leading=ukuran + 4, alignment=TA_JUSTIFY)
    for blok in str(teks).split("\n\n"):
        b = blok.strip()
        if b:
            out += [Paragraph(_esc(b).replace("\n", " "), st), Spacer(1, 5)]
    return out


def _calk(db, tahun, bulan):
    from reportlab.platypus import PageBreak, Spacer
    lra, a1 = _lra_rows(db, tahun, bulan, False)
    lrab, a2 = _lra_rows(db, tahun, bulan, True)
    ner, a3 = _neraca_rows(db, tahun, bulan)
    lo, a4 = _lo_rows(db, tahun, bulan)
    story = [_p("<b>CATATAN ATAS LAPORAN KEUANGAN</b>", "c", True, 12), _p(f"<b>Untuk Tahun yang Berakhir sampai dengan {_tgl(_akhir(tahun, bulan))}</b>", "c", True, 9), _p("<b>Puskesmas Melati BLUD</b>", "c", True, 9), Spacer(1, 10)]
    for kunci, judul in (("bab1", None), ("bab2", None)):
        story += _para(_teks(db, tahun, kunci))
        story.append(PageBreak())
    pend_blud = a2["pendapatan"][1]
    bel_b = a1["belanja"]
    p3 = (f"UPT Puskesmas Melati menganggarkan pendapatan BLUD sebesar Rp {f2(a2['pendapatan'][0])[:-3]},00 dan terealisasi sebesar Rp {f2(pend_blud)[:-3]},00 ({fp(pend_blud, a2['pendapatan'][0])}%). "
          f"Total belanja (seluruh sumber dana) terealisasi sebesar Rp {f2(bel_b[1])[:-3]},00 atau {fp(bel_b[1], bel_b[0])}% dari anggaran Rp {f2(bel_b[0])[:-3]},00.")
    story += [_p("<b>BAB III</b>", "c", True, 11), _p("<b>IKHTISAR PENCAPAIAN KINERJA KEUANGAN</b>", "c", True, 11), Spacer(1, 6)]
    story += _para("Pada bagian ini disajikan analisa capaian kinerja keuangan yang digambarkan dalam ringkasan realisasi anggaran pendapatan dan belanja UPT Puskesmas Melati secara keseluruhan sebagai akuntabilitas keuangan terhadap capaian indikator dalam mewujudkan tujuan yang ditetapkan.")
    story += [_p("<b>3.1 Ikhtisar Realisasi Pencapaian Target Kinerja Keuangan</b>"), Spacer(1, 3)] + _para(p3) + _para(_teks(db, tahun, "bab3")) + [PageBreak()]
    story += _para(_teks(db, tahun, "bab4")) + [PageBreak()]
    story += [_p("<b>BAB V</b>", "c", True, 11), _p("<b>PENJELASAN ATAS LAPORAN KEUANGAN</b>", "c", True, 11), Spacer(1, 6), _p("<b>5.1 PENJELASAN LAPORAN REALISASI ANGGARAN</b>"), Spacer(1, 3), _p("<b>5.1.1 Pendapatan</b>"), Spacer(1, 2)]
    story += _para(f"Realisasi pendapatan BLUD (jasa layanan) Tahun Anggaran {tahun - 1} dan {tahun} masing-masing sebesar Rp {f2(sum(r['v'][2] for r in lrab if r['lv'] == 1 and r['k'].startswith('4')))[:-3]},00 dan Rp {f2(pend_blud)[:-3]},00.")
    story += [_p("<b>5.1.2 Belanja</b>"), Spacer(1, 2)] + _para(f"Realisasi belanja Tahun Anggaran {tahun} sebesar Rp {f2(bel_b[1])[:-3]},00 dari anggaran Rp {f2(bel_b[0])[:-3]},00 ({fp(bel_b[1], bel_b[0])}%), dengan rincian sebagai berikut:")
    d = {"jenis": "lra", "kolom": ["Kode Rekening", "URAIAN", "ANGGARAN", f"REALISASI {tahun}", f"% {tahun}", f"REALISASI {tahun - 1}"], "rows": [r for r in lra if r["k"]], "angka": None}
    d.pop("angka")
    story.append(_tabel_statement(d))
    story += [Spacer(1, 6), _p("<b>5.2 PENJELASAN NERACA</b>"), Spacer(1, 3)] + _para(f"Posisi Neraca per {_tgl(_akhir(tahun, bulan))}: jumlah aset Rp {f2(a3['aset'][0])[:-3]},00 dan jumlah ekuitas Rp {f2(a3['ekuitas'][0])[:-3]},00; kas dan setara kas disajikan menurut buku kas (Bendahara Pengeluaran, BLUD, Dana BOK, Kas Lainnya) dan aset tetap menurut kelompok barang.")
    story += [_p("<b>5.3 PENJELASAN LAPORAN OPERASIONAL</b>"), Spacer(1, 3)] + _para(f"Beban operasi Tahun {tahun} sebesar Rp {f2(a4['beban'][0])[:-3]},00 dibandingkan Tahun {tahun - 1} sebesar Rp {f2(a4['beban'][1])[:-3]},00.")
    eka, lo_, rk, ekt = a3["ek_tiga"][0], a3["ek_tiga"][1], a3["ek_tiga"][2], a3["ekuitas"][0]
    story += [_p("<b>5.4 PENJELASAN LAPORAN PERUBAHAN EKUITAS</b>"), Spacer(1, 3)] + _para(f"Ekuitas awal Rp {f2(eka)[:-3]},00, surplus/(defisit)-LO Rp {f2(lo_)[:-3]},00, dan RK PPKD Rp {f2(rk)[:-3]},00 sehingga ekuitas akhir sebesar Rp {f2(ekt)[:-3]},00.")
    story += [PageBreak(), _p("<b>BAB VI</b>", "c", True, 11), _p("<b>PENJELASAN INFORMASI NON KEUANGAN</b>", "c", True, 11), Spacer(1, 6)] + _para(_teks(db, tahun, "bab6"))
    story += [Spacer(1, 6), _p("<b>BAB VII</b>", "c", True, 11), _p("<b>PENUTUP</b>", "c", True, 11), Spacer(1, 6)] + _para(_teks(db, tahun, "bab7"))
    k = _pejabat(db)
    story += [Spacer(1, 8), _p(f"Demikian Laporan Keuangan dan Catatan atas Laporan Keuangan UPT Puskesmas Melati Tahun {tahun} disusun untuk digunakan sebagaimana mestinya.", "l", False, 10), Spacer(1, 10),
              _p("<b>KEPALA UPT PUSKESMAS MELATI KABUPATEN KAPUAS</b>", "l", True, 10), Spacer(1, 40), _p(f"<b>{_esc(k['nama'])}</b>", "l", True, 10), _p(f"NIP. {_nip(k['nip'])}", "l", False, 10)]
    return story


def _sampul(c, d):
    from reportlab.lib.pagesizes import A4
    c.saveState()
    W, H = A4
    c.setFont(dk.FONTB, 17)
    for i, t in enumerate(d["sampul"][:3]):
        c.drawCentredString(W / 2, H - 6.0 * dk.cm - i * 0.9 * dk.cm, t)
    try:
        c.drawImage(str(dk.ASSETS / "lambang-kapuas.png"), W / 2 - 3.2 * dk.cm, H - 17.2 * dk.cm, width=6.4 * dk.cm, height=7.4 * dk.cm, mask="auto")
    except Exception:  # noqa: BLE001
        pass
    c.setFont(dk.FONTB, 12.5)
    for i, t in enumerate(d["sampul"][3:]):
        c.drawCentredString(W / 2, 7.0 * dk.cm - i * 0.75 * dk.cm, t)
    c.restoreState()


def _label_periode(bulan):
    return "SEMESTER 1" if bulan == 6 else "SEMESTER 2" if bulan == 12 else f"PERIODE S.D. {dk.BULAN[bulan - 1].upper()}"


def story_lengkap(db, tahun, bulan, bagian="semua"):
    from reportlab.platypus import PageBreak, Spacer
    st = []
    if bagian in ("semua",):
        st += [PageBreak(), _p("<b>DAFTAR ISI</b>", "c", True, 12), Spacer(1, 10)]
        for u, h in (("DAFTAR ISI", "I"), ("PENGANTAR", "III"), ("SURAT PERNYATAAN TANGGUNG JAWAB", "IV"), ("LAPORAN REALISASI ANGGARAN", "V"), ("NERACA", "VI"), ("LAPORAN OPERASIONAL", "VII"), ("LAPORAN PERUBAHAN EKUITAS (LPE)", "VIII"), ("CATATAN ATAS LAPORAN KEUANGAN (CaLK)", "1")):
            st.append(_p(f"{u} {'.' * (70 - len(u))} {h}", "l", False, 10))
        st += [Spacer(1, 4)]
        k = _pejabat(db)
        st += [PageBreak(), _p("<b>PENGANTAR</b>", "c", True, 12), Spacer(1, 8)] + _para(_teks(db, tahun, "pengantar")) + [Spacer(1, 6), _p("Kepala UPT Puskesmas Melati", "l", False, 10), Spacer(1, 40), _p(f"<b>{_esc(k['nama'])}</b>", "l", True, 10), _p(f"NIP. {_nip(k['nip'])}", "l", False, 10)]
        st += [PageBreak(), _p("<b>PERNYATAAN TANGGUNG JAWAB</b>", "c", True, 12), Spacer(1, 8)] + _para(_teks(db, tahun, "sptjm")) + [Spacer(1, 6), _p("Kepala UPT Puskesmas Melati", "l", False, 10), Spacer(1, 40), _p(f"<b>{_esc(k['nama'])}</b>", "l", True, 10), _p(f"NIP. {_nip(k['nip'])}", "l", False, 10)]
    for b in ("lra", "neraca", "lo", "lpe") if bagian == "semua" else ([bagian] if bagian in ("lra", "lra_blud", "neraca", "lo", "lpe") else []):
        s, _ = _story_statement(db, tahun, bulan, b)
        st += ([PageBreak()] if st else []) + s
    if bagian in ("semua", "calk"):
        st += ([PageBreak()] if st else []) + _calk(db, tahun, bulan)
    return st


@router.get("/dok")
def dokumen(tahun: int, bulan: int = 6, bagian: str = "semua", format: str = "pdf", user=Depends(akses), db=Depends(get_db)):
    if bagian != "semua" and bagian not in BAGIAN:
        raise Gagal("Bagian tidak dikenal.", 404)
    nama = f"Laporan_Keuangan_Melati_{tahun}_{bulan:02d}" + ("" if bagian == "semua" else f"_{bagian}")
    if format == "xlsx":
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for b in (("lra", "lra_blud", "neraca", "lo", "lpe") if bagian in ("semua", "calk") else (bagian,)):
            if b == "calk":
                continue
            d = susun(db, tahun, bulan, b)
            ws = wb.create_sheet(b.upper())
            for j in d["judul"]:
                ws.append([j])
            ws["A1"].font = Font(bold=True)
            ws.append([])
            ws.append(d["kolom"])
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
            if b == "lpe":
                for u, a, bb in d["rows"]:
                    ws.append([u, a, bb])
            else:
                for r in d["rows"]:
                    ws.append([r["k"], r["u"]] + r["v"])
                    if r["b"]:
                        for c in ws[ws.max_row]:
                            c.font = Font(bold=True)
            ws.column_dimensions["A"].width = 16 if b != "lpe" else 60
            ws.column_dimensions["B"].width = 55
            for col in "CDEF":
                ws.column_dimensions[col].width = 22
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{nama}.xlsx"', "Cache-Control": "no-store"})
    story = story_lengkap(db, tahun, bulan, bagian)
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.0 * dk.cm, rightMargin=2.0 * dk.cm, topMargin=1.6 * dk.cm, bottomMargin=1.8 * dk.cm, title="Laporan Keuangan BLUD Puskesmas Melati", author="SIKADIN")
    meta = {"sampul": ["LAPORAN KEUANGAN BLUD", "PUSKESMAS MELATI", _label_periode(bulan), "DINAS KESEHATAN KABUPATEN KAPUAS", "PUSKESMAS MELATI KECAMATAN SELAT", "KABUPATEN KAPUAS", f"TAHUN {tahun}"]}

    def kaki(c, _d):
        c.saveState()
        c.setFont(dk.FONT, 7.5)
        c.drawCentredString(A4[0] / 2, 1.0 * dk.cm, f"Laporan Keuangan BLUD Puskesmas Melati {tahun} — halaman {_d.page}")
        c.restoreState()
    if bagian == "semua":
        from reportlab.platypus import PageBreak
        doc.build(story, onFirstPage=lambda c, d_: _sampul(c, meta), onLaterPages=kaki)
    else:
        doc.build(story, onFirstPage=kaki, onLaterPages=kaki)
    pdf = buf.getvalue()
    if format == "docx":
        return Response(_pdf_ke_docx(pdf), media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{nama}.docx"', "Cache-Control": "no-store"})
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nama}.pdf"', "Cache-Control": "no-store"})
