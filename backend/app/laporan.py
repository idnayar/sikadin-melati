"""Tahap 6 — Laporan keuangan BLU menurut PSAP 13: LRA, L-SAL, Neraca, LO, LAK, LPE, CaLK.
Satu kesatuan (semua sumber dana: DAU, BOK, BLUD) — hanya Kepala dan Bendahara BLUD.
Dasar: LRA & LAK berbasis kas (jurnal basis KAS); LO, Neraca, LPE dari seluruh jurnal (KAS + AKRUAL). Saldo awal = jurnal basis AWAL."""
import calendar
import datetime as dt
import io

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response

from . import dokumen as dk
from .akuntansi import akses, peta_belanja
from .core import Gagal, audit, get_db
from .surat import DOCX, _pdf_ke_docx

router = APIRouter(prefix="/api/laporan")
JENIS = ("lra", "lsal", "neraca", "lo", "lak", "lpe", "calk")
NAMA = {"lra": "LAPORAN REALISASI ANGGARAN", "lsal": "LAPORAN PERUBAHAN SALDO ANGGARAN LEBIH", "neraca": "NERACA", "lo": "LAPORAN OPERASIONAL",
        "lak": "LAPORAN ARUS KAS", "lpe": "LAPORAN PERUBAHAN EKUITAS", "calk": "CATATAN ATAS LAPORAN KEUANGAN"}
CALK_DEFAULT = {
    "umum": "UPT Puskesmas Melati adalah unit pelaksana teknis Dinas Kesehatan Kabupaten Kapuas (Kecamatan Selat, Kuala Kapuas, Kalimantan Tengah) yang menyelenggarakan pelayanan kesehatan tingkat pertama dan mengelola keuangan sebagai Badan Layanan Umum Daerah (BLUD). Sumber dana: Dana Alokasi Umum (DAU), Bantuan Operasional Kesehatan (BOK), dan pendapatan BLUD.",
    "dasar": "Laporan keuangan disusun menurut Pernyataan Standar Akuntansi Pemerintahan Nomor 13 tentang Penyajian Laporan Keuangan Badan Layanan Umum, dan terdiri atas Laporan Realisasi Anggaran, Laporan Perubahan Saldo Anggaran Lebih, Neraca, Laporan Operasional, Laporan Arus Kas, Laporan Perubahan Ekuitas, dan Catatan atas Laporan Keuangan. Laporan ini menggabungkan seluruh sumber dana (DAU, BOK, BLUD) dalam satu kesatuan pelaporan.",
    "kebijakan": "Laporan Realisasi Anggaran dan Laporan Arus Kas disusun berbasis kas: pendapatan diakui saat kas diterima dan belanja diakui saat kas dibayarkan (SPJ yang telah dibayar). Neraca, Laporan Operasional, dan Laporan Perubahan Ekuitas disusun berbasis akrual dari seluruh jurnal. Mata uang pelaporan Rupiah penuh.",
    "lainnya": "",
}
BAGIAN_CALK = (("umum", "Informasi Umum Entitas"), ("dasar", "Dasar Penyusunan Laporan Keuangan"), ("kebijakan", "Kebijakan Akuntansi"), ("lainnya", "Penjelasan Lainnya"))


def _set(db, k, d=""):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    return r["nilai"] if r and r["nilai"] is not None else d


def _batas(tahun: int, bulan: int):
    if not 2000 < tahun < 2100 or not 1 <= bulan <= 12:
        raise Gagal("Tahun/bulan tidak valid.")
    return f"{tahun}-01-01", f"{tahun}-{bulan:02d}-{calendar.monthrange(tahun, bulan)[1]:02d}"


def _muat(db, sampai: str) -> list:
    return db.execute("""SELECT j.id jid, j.tanggal, j.basis, j.sumber_dana_id, sd.kode dana, a.id akun_id, a.kode, a.nama, a.jenis, a.normal, a.kas, a.arus, a.lra, b.debit d, b.kredit k
        FROM jurnal_baris b JOIN jurnal j ON j.id=b.jurnal_id JOIN akun a ON a.id=b.akun_id LEFT JOIN sumber_dana sd ON sd.id=j.sumber_dana_id
        WHERE j.tanggal<=? ORDER BY j.tanggal, j.id, b.id""", (sampai,)).fetchall()


def _tambah(d: dict, key, v):
    d[key] = d.get(key, 0) + v


class Hitung:
    """Agregat satu periode [dari, sampai] dari baris jurnal."""

    def __init__(self, baris: list, dari: str, sampai: str):
        self.dari, self.sampai = dari, sampai
        self.pend_lra, self.bel_lra, self.po, self.lo_pend, self.lo_beban, self.ekuitas_gerak = {}, {}, {}, {}, {}, {}
        self.nama: dict = {}
        self.pembiayaan = {"terima": 0, "keluar": 0}
        self.lak: dict = {"OPERASI": {}, "INVESTASI": {}, "PENDANAAN": {}}
        self.per_dana_pend, self.per_dana_bel = {}, {}
        self.kas_awal = sum(x["d"] - x["k"] for x in baris if x["kas"] and (x["basis"] == "AWAL" or x["tanggal"] < dari))
        self.kas_akhir = sum(x["d"] - x["k"] for x in baris if x["kas"] and x["tanggal"] <= sampai)
        # ekuitas & surplus sebelum periode
        self.ekuitas_awal = sum(x["k"] - x["d"] for x in baris if x["jenis"] == "EKUITAS" and (x["basis"] == "AWAL" or x["tanggal"] < dari))
        self.pl_awal = sum((x["k"] - x["d"]) if x["jenis"] == "PENDAPATAN" else -(x["d"] - x["k"]) for x in baris if x["jenis"] in ("PENDAPATAN", "BEBAN") and x["basis"] != "AWAL" and x["tanggal"] < dari)
        jurnal: dict = {}
        for x in baris:
            if x["basis"] == "AWAL" or not (dari <= x["tanggal"] <= sampai):
                continue
            self.nama[x["kode"]] = x["nama"]
            jurnal.setdefault(x["jid"], []).append(x)
            if x["jenis"] == "PENDAPATAN":
                _tambah(self.lo_pend, x["kode"], x["k"] - x["d"])
            elif x["jenis"] == "BEBAN":
                _tambah(self.lo_beban, x["kode"], x["d"] - x["k"])
            elif x["jenis"] == "EKUITAS":
                _tambah(self.ekuitas_gerak, x["kode"], x["k"] - x["d"])
            if x["basis"] == "KAS":
                if x["jenis"] == "PENDAPATAN":
                    _tambah(self.pend_lra, x["kode"], x["k"] - x["d"])
                    _tambah(self.per_dana_pend, x["dana"] or "-", x["k"] - x["d"])
                elif x["jenis"] == "BEBAN":
                    _tambah(self.bel_lra, x["kode"], x["d"] - x["k"])
                    _tambah(self.per_dana_bel, x["dana"] or "-", x["d"] - x["k"])
                elif x["lra"] == "BELANJA_MODAL":
                    _tambah(self.bel_lra, x["kode"], x["d"] - x["k"])
                    _tambah(self.per_dana_bel, x["dana"] or "-", x["d"] - x["k"])
                elif x["lra"] == "PEMBIAYAAN":
                    self.pembiayaan["terima"] += x["k"]
                    self.pembiayaan["keluar"] += x["d"]
        for baris_j in jurnal.values():   # arus kas: alokasikan perubahan kas ke lawan transaksi
            if not any(x["kas"] for x in baris_j) or baris_j[0]["basis"] != "KAS":
                continue
            for x in baris_j:
                if x["kas"]:
                    continue
                efek = x["k"] - x["d"]
                if x["jenis"] == "PENDAPATAN":
                    label = "Penerimaan " + x["nama"]
                elif x["jenis"] == "BEBAN":
                    label = "Pembayaran " + x["nama"]
                else:
                    label = ("Penerimaan " if efek >= 0 else "Pembayaran ") + x["nama"]
                bagian = "INVESTASI" if (x["lra"] == "BELANJA_MODAL" or x["arus"] == "INVESTASI") else "PENDANAAN" if (x["lra"] == "PEMBIAYAAN" or x["arus"] == "PENDANAAN") else "OPERASI"
                _tambah(self.lak[bagian], label, efek)

    @property
    def surplus_lo(self):
        return sum(self.lo_pend.values()) - sum(self.lo_beban.values())

    @property
    def surplus_lra(self):
        return sum(self.pend_lra.values()) - sum(self.bel_lra.values())


def _anggaran(db, tahun):
    pend = {r["kode"]: r["jumlah"] for r in db.execute("SELECT a.kode, p.jumlah FROM anggaran_pendapatan p JOIN akun a ON a.id=p.akun_id WHERE p.tahun=?", (tahun,)).fetchall()}
    bel: dict = {}
    for r in db.execute("""SELECT b.jenis_belanja, sd.kode dana, SUM(b.jumlah) j FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id
        JOIN sumber_dana sd ON sd.id=m.sumber_dana_id WHERE m.tahun=? GROUP BY b.jenis_belanja, sd.kode""", (tahun,)).fetchall():
        _tambah(bel, peta_belanja(r["jenis_belanja"], r["dana"]), r["j"])
    return pend, bel


def _akun_nama(db):
    return {a["kode"]: a["nama"] for a in db.execute("SELECT kode, nama FROM akun").fetchall()}


def _R(u, v=None, b=False, lv=0, t=False):
    return {"u": u, "v": v if v is not None else [], "b": b, "lv": lv, "t": t}


def _pct(real, ang):
    return round(100 * real / ang, 1) if ang else None


# ---------------------------------------------------------------- penyusun tiap laporan
def _lra(db, h: Hitung, hp: Hitung, tahun):
    nm = _akun_nama(db)
    angp, angb = _anggaran(db, tahun)
    r = []
    kp = sorted(set(angp) | set(h.pend_lra) | set(hp.pend_lra))
    r.append(_R("PENDAPATAN", t=True, b=True))
    tp = [0, 0, 0]
    for k in kp:
        a, x, y = angp.get(k, 0), h.pend_lra.get(k, 0), hp.pend_lra.get(k, 0)
        r.append(_R(nm.get(k, k), [a, x, x - a, _pct(x, a), y], lv=1))
        tp = [tp[0] + a, tp[1] + x, tp[2] + y]
    r.append(_R("JUMLAH PENDAPATAN", [tp[0], tp[1], tp[1] - tp[0], _pct(tp[1], tp[0]), tp[2]], b=True))
    r.append(_R("BELANJA", t=True, b=True))
    kb = sorted(set(angb) | set(h.bel_lra) | set(hp.bel_lra))
    tb = [0, 0, 0]
    for k in kb:
        a, x, y = angb.get(k, 0), h.bel_lra.get(k, 0), hp.bel_lra.get(k, 0)
        etiket = ("Belanja Modal — " + nm.get(k, k)) if k.startswith("1.") else nm.get(k, k)
        r.append(_R(etiket, [a, x, a - x, _pct(x, a), y], lv=1))
        tb = [tb[0] + a, tb[1] + x, tb[2] + y]
    r.append(_R("JUMLAH BELANJA", [tb[0], tb[1], tb[0] - tb[1], _pct(tb[1], tb[0]), tb[2]], b=True))
    sa, sx, sy = tp[0] - tb[0], tp[1] - tb[1], tp[2] - tb[2]
    r.append(_R("SURPLUS/(DEFISIT)", [sa, sx, sx - sa, None, sy], b=True))
    r.append(_R("PEMBIAYAAN", t=True, b=True))
    r.append(_R("Penerimaan Pembiayaan", [None, h.pembiayaan["terima"], None, None, hp.pembiayaan["terima"]], lv=1))
    r.append(_R("Pengeluaran Pembiayaan", [None, h.pembiayaan["keluar"], None, None, hp.pembiayaan["keluar"]], lv=1))
    nb, nbp = h.pembiayaan["terima"] - h.pembiayaan["keluar"], hp.pembiayaan["terima"] - hp.pembiayaan["keluar"]
    r.append(_R("PEMBIAYAAN NETTO", [None, nb, None, None, nbp], b=True))
    r.append(_R("SISA LEBIH/KURANG PEMBIAYAAN ANGGARAN (SiLPA/SiKPA)", [None, sx + nb, None, None, sy + nbp], b=True))
    return {"kolom": ["Anggaran", "Realisasi", "Selisih", "%", "Realisasi tahun lalu"], "baris": r,
            "catatan": ["Selisih pendapatan = realisasi − anggaran; selisih belanja = anggaran − realisasi (sisa anggaran).", "Anggaran belanja = total RAB semua sumber dana tahun ini; anggaran pendapatan diisi di menu Akuntansi."],
            "angka": {"surplus": sx, "silpa": sx + nb}}


def _lsal(db, h: Hitung, lra):
    sal_awal = h.kas_awal
    silpa = lra["angka"]["silpa"]
    akhir = sal_awal + silpa
    r = [_R("Saldo Anggaran Lebih (SAL) awal", [sal_awal], b=True),
         _R("Penggunaan SAL sebagai penerimaan pembiayaan tahun berjalan", [0], lv=1),
         _R("Subtotal", [sal_awal], b=True),
         _R("Sisa Lebih/Kurang Pembiayaan Anggaran (SiLPA/SiKPA) tahun berjalan", [silpa], lv=1),
         _R("Koreksi kesalahan pembukuan tahun sebelumnya", [0], lv=1),
         _R("Lain-lain", [0], lv=1),
         _R("SALDO ANGGARAN LEBIH (SAL) AKHIR", [akhir], b=True)]
    cat = ["SAL awal disetarakan dengan saldo kas awal tahun (saldo awal jurnal)."]
    if akhir != h.kas_akhir:
        cat.append(f"Perhatian: SAL akhir ({_fmt(akhir)}) berbeda dari saldo kas akhir ({_fmt(h.kas_akhir)}); selisih {_fmt(h.kas_akhir - akhir)} — periksa jurnal kas manual atau jurnal berbasis akrual yang mengubah kas.")
    return {"kolom": ["Jumlah"], "baris": r, "catatan": cat}


def _saldo_akun(baris, sampai):
    s: dict = {}
    for x in baris:
        if x["tanggal"] <= sampai and x["jenis"] in ("ASET", "KEWAJIBAN", "EKUITAS"):
            e = s.setdefault(x["kode"], {"nama": x["nama"], "jenis": x["jenis"], "nilai": 0})
            e["nilai"] += (x["d"] - x["k"]) if x["normal"] == "D" else (x["k"] - x["d"])
    return s


def _pl_kum(baris, dari, sampai):
    return sum((x["k"] - x["d"]) if x["jenis"] == "PENDAPATAN" else (x["k"] - x["d"]) for x in baris if x["jenis"] in ("PENDAPATAN", "BEBAN") and x["basis"] != "AWAL" and dari <= x["tanggal"] <= sampai)


def _neraca(db, baris, tahun, sampai, sampai_lalu):
    s, sp = _saldo_akun(baris, sampai), _saldo_akun(baris, sampai_lalu)
    pl_lalu = _pl_kum(baris, "0000-01-01", f"{tahun}-01-01")  # < tahun berjalan (tanggal 01-01 diikutkan ke berjalan di bawah)
    pl_lalu = sum((x["k"] - x["d"]) for x in baris if x["jenis"] in ("PENDAPATAN", "BEBAN") and x["basis"] != "AWAL" and x["tanggal"] < f"{tahun}-01-01")
    pl_ini = sum((x["k"] - x["d"]) for x in baris if x["jenis"] in ("PENDAPATAN", "BEBAN") and x["basis"] != "AWAL" and f"{tahun}-01-01" <= x["tanggal"] <= sampai)
    pl_lalu_p = sum((x["k"] - x["d"]) for x in baris if x["jenis"] in ("PENDAPATAN", "BEBAN") and x["basis"] != "AWAL" and x["tanggal"] < f"{tahun - 1}-01-01")
    pl_ini_p = sum((x["k"] - x["d"]) for x in baris if x["jenis"] in ("PENDAPATAN", "BEBAN") and x["basis"] != "AWAL" and f"{tahun - 1}-01-01" <= x["tanggal"] <= sampai_lalu)
    kode = sorted(set(s) | set(sp))
    v = lambda d, k: d.get(k, {"nilai": 0})["nilai"]  # noqa: E731
    r: list = []

    def grup(judul, jenis, prefix=None, sign=1):
        ks = [k for k in kode if (s.get(k) or sp.get(k))["jenis"] == jenis and (prefix is None or k.startswith(prefix))]
        r.append(_R(judul, t=True, b=True))
        a = b = 0
        for k in ks:
            nm = (s.get(k) or sp.get(k))["nama"]
            x, y = v(s, k), v(sp, k)
            sg = -1 if (jenis == "ASET" and (s.get(k) or sp.get(k)) and k.startswith("1.3.9")) else 1
            r.append(_R(nm, [sg * x, sg * y], lv=1))
            a += sg * x
            b += sg * y
        return a, b
    a1 = grup("ASET LANCAR", "ASET", "1.1")
    a2 = grup("ASET TETAP", "ASET", "1.3")
    jaset = (a1[0] + a2[0], a1[1] + a2[1])
    lain = [k for k in kode if (s.get(k) or sp.get(k))["jenis"] == "ASET" and not k.startswith(("1.1", "1.3"))]
    for k in lain:
        r.append(_R((s.get(k) or sp.get(k))["nama"], [v(s, k), v(sp, k)], lv=1))
        jaset = (jaset[0] + v(s, k), jaset[1] + v(sp, k))
    r.append(_R("JUMLAH ASET", list(jaset), b=True))
    kw = grup("KEWAJIBAN", "KEWAJIBAN")
    r.append(_R("JUMLAH KEWAJIBAN", list(kw), b=True))
    r.append(_R("EKUITAS", t=True, b=True))
    eq = [0, 0]
    for k in [k for k in kode if (s.get(k) or sp.get(k))["jenis"] == "EKUITAS"]:
        r.append(_R((s.get(k) or sp.get(k))["nama"], [v(s, k), v(sp, k)], lv=1))
        eq = [eq[0] + v(s, k), eq[1] + v(sp, k)]
    r.append(_R("Surplus/(Defisit) LO tahun lalu (diakumulasi)", [pl_lalu, pl_lalu_p], lv=1))
    r.append(_R("Surplus/(Defisit) LO tahun berjalan", [pl_ini, pl_ini_p], lv=1))
    eq_t = [eq[0] + pl_lalu + pl_ini, eq[1] + pl_lalu_p + pl_ini_p]
    r.append(_R("JUMLAH EKUITAS", eq_t, b=True))
    pas = [kw[0] + eq_t[0], kw[1] + eq_t[1]]
    r.append(_R("JUMLAH KEWAJIBAN DAN EKUITAS", pas, b=True))
    cat = [] if (jaset[0] == pas[0] and jaset[1] == pas[1]) else [f"PERHATIAN: Neraca tidak seimbang (aset {_fmt(jaset[0])} ≠ kewajiban + ekuitas {_fmt(pas[0])}). Periksa saldo awal dan jurnal."]
    return {"kolom": ["Tahun berjalan", "Tahun lalu"], "baris": r, "catatan": cat, "angka": {"aset": jaset[0], "pasiva": pas[0], "ekuitas": eq_t[0]}}


def _lo(db, h: Hitung, hp: Hitung):
    nm = _akun_nama(db)
    r = [_R("PENDAPATAN-LO", t=True, b=True)]
    kp = sorted(set(h.lo_pend) | set(hp.lo_pend))
    for k in kp:
        r.append(_R(nm.get(k, k), [h.lo_pend.get(k, 0), hp.lo_pend.get(k, 0)], lv=1))
    tp, tpp = sum(h.lo_pend.values()), sum(hp.lo_pend.values())
    r.append(_R("JUMLAH PENDAPATAN", [tp, tpp], b=True))
    r.append(_R("BEBAN", t=True, b=True))
    for k in sorted(set(h.lo_beban) | set(hp.lo_beban)):
        r.append(_R(nm.get(k, k), [h.lo_beban.get(k, 0), hp.lo_beban.get(k, 0)], lv=1))
    tb, tbp = sum(h.lo_beban.values()), sum(hp.lo_beban.values())
    r.append(_R("JUMLAH BEBAN", [tb, tbp], b=True))
    r.append(_R("SURPLUS/(DEFISIT) LO", [tp - tb, tpp - tbp], b=True))
    return {"kolom": ["Tahun berjalan", "Tahun lalu"], "baris": r, "catatan": [], "angka": {"surplus": tp - tb}}


def _lak(h: Hitung):
    r, total = [], 0
    nama = {"OPERASI": "ARUS KAS DARI AKTIVITAS OPERASI", "INVESTASI": "ARUS KAS DARI AKTIVITAS INVESTASI", "PENDANAAN": "ARUS KAS DARI AKTIVITAS PENDANAAN"}
    for sek in ("OPERASI", "INVESTASI", "PENDANAAN"):
        r.append(_R(nama[sek], t=True, b=True))
        masuk = {k: v for k, v in h.lak[sek].items() if v > 0}
        keluar = {k: v for k, v in h.lak[sek].items() if v < 0}
        r.append(_R("Arus kas masuk", t=True, lv=1))
        for k, v in sorted(masuk.items()):
            r.append(_R(k, [v], lv=2))
        r.append(_R("Jumlah arus kas masuk", [sum(masuk.values())], lv=1, b=True))
        r.append(_R("Arus kas keluar", t=True, lv=1))
        for k, v in sorted(keluar.items()):
            r.append(_R(k, [v], lv=2))
        r.append(_R("Jumlah arus kas keluar", [sum(keluar.values())], lv=1, b=True))
        net = sum(h.lak[sek].values())
        total += net
        r.append(_R(f"ARUS KAS BERSIH DARI AKTIVITAS {sek}", [net], b=True))
    r.append(_R("KENAIKAN/(PENURUNAN) KAS", [total], b=True))
    r.append(_R("Saldo kas awal periode", [h.kas_awal], lv=1))
    r.append(_R("SALDO KAS AKHIR PERIODE", [h.kas_awal + total], b=True))
    cat = ["Metode langsung. Arus kas dari jurnal berbasis KAS (SPJ dibayar, penerimaan pendapatan, dan jurnal kas manual)."]
    if h.kas_awal + total != h.kas_akhir:
        cat.append("PERHATIAN: saldo kas akhir LAK berbeda dari saldo buku besar kas — ada jurnal akrual yang menyentuh akun kas.")
    return {"kolom": ["Jumlah"], "baris": r, "catatan": cat}


def _lpe(h: Hitung, neraca):
    koreksi = sum(h.ekuitas_gerak.values())
    awal = h.ekuitas_awal + h.pl_awal
    akhir = awal + h.surplus_lo + koreksi
    r = [_R("EKUITAS AWAL", [awal], b=True), _R("Surplus/(Defisit) LO", [h.surplus_lo], lv=1),
         _R("Koreksi dan perubahan ekuitas lainnya (jurnal akun ekuitas)", [koreksi], lv=1), _R("EKUITAS AKHIR", [akhir], b=True)]
    cat = [] if akhir == neraca["angka"]["ekuitas"] else [f"PERHATIAN: ekuitas akhir LPE ({_fmt(akhir)}) berbeda dari Neraca ({_fmt(neraca['angka']['ekuitas'])})."]
    return {"kolom": ["Jumlah"], "baris": r, "catatan": cat}


def _fmt(n):
    if n is None:
        return ""
    if isinstance(n, float):
        return f"{n:.1f}".replace(".", ",")
    return f"({abs(n):,})".replace(",", ".") if n < 0 else f"{n:,}".replace(",", ".")


def _calk(db, tahun, h: Hitung, lra, neraca, lo, awal_calk):
    r = []
    ada = {x["bagian"]: x["isi"] for x in db.execute("SELECT bagian, isi FROM calk WHERE tahun=?", (tahun,)).fetchall()}
    for i, (kode, judul) in enumerate(BAGIAN_CALK, 1):
        teks = ada.get(kode) or CALK_DEFAULT[kode]
        if teks:
            r.append(_R(f"{i}. {judul}", t=True, b=True))
            r.append({"teks": teks})
    n = len(BAGIAN_CALK) + 1
    r.append(_R(f"{n}. Rincian Pos Laporan", t=True, b=True))
    r.append(_R("Pendapatan (LRA) menurut sumber dana", t=True, lv=1))
    for d, v in sorted(h.per_dana_pend.items()):
        r.append(_R(d, [v], lv=2))
    r.append(_R("Belanja (LRA) menurut sumber dana", t=True, lv=1))
    for d, v in sorted(h.per_dana_bel.items()):
        r.append(_R(d, [v], lv=2))
    r.append(_R("Saldo kas", t=True, lv=1))
    r.append(_R("Saldo kas awal", [h.kas_awal], lv=2))
    r.append(_R("Saldo kas akhir", [h.kas_akhir], lv=2))
    r.append(_R("Ikhtisar", t=True, lv=1))
    r.append(_R("Surplus/(Defisit) LRA", [lra["angka"]["surplus"]], lv=2))
    r.append(_R("Surplus/(Defisit) LO", [lo["angka"]["surplus"]], lv=2))
    r.append(_R("Jumlah aset", [neraca["angka"]["aset"]], lv=2))
    r.append(_R("Jumlah ekuitas", [neraca["angka"]["ekuitas"]], lv=2))
    pem = []
    if neraca["catatan"]:
        pem += neraca["catatan"]
    if pem:
        r.append(_R(f"{n + 1}. Hal yang perlu diperhatikan", t=True, b=True))
        r += [{"teks": x} for x in pem]
    return {"kolom": ["Jumlah"], "baris": r, "catatan": []}


def susun(db, tahun: int, bulan: int = 12) -> dict:
    dari, sampai = _batas(tahun, bulan)
    dari_p, sampai_p = f"{tahun - 1}-01-01", f"{tahun - 1}-{bulan:02d}-{calendar.monthrange(tahun - 1, bulan)[1]:02d}"
    baris = _muat(db, sampai)
    h, hp = Hitung(baris, dari, sampai), Hitung(baris, dari_p, sampai_p)
    lra = _lra(db, h, hp, tahun)
    lo = _lo(db, h, hp)
    nr = _neraca(db, baris, tahun, sampai, sampai_p)
    out = {"lra": lra, "lsal": _lsal(db, h, lra), "neraca": nr, "lo": lo, "lak": _lak(h), "lpe": _lpe(h, nr), "calk": _calk(db, tahun, h, lra, nr, lo, None)}
    akhir = dt.date.fromisoformat(sampai)
    periode = f"{akhir.day} {dk.BULAN[akhir.month - 1]} {akhir.year}"
    for k, v in out.items():
        v["jenis"] = k
        v["judul"] = NAMA[k]
        v["periode"] = (f"Per {periode}" if k == "neraca" else f"Untuk periode yang berakhir pada {periode}") if k != "calk" else f"Tahun {tahun}"
    return out


@router.get("")
def lihat(tahun: int, bulan: int = 12, jenis: str = "", user=Depends(akses), db=Depends(get_db)):
    d = susun(db, tahun, bulan)
    if jenis:
        if jenis not in JENIS:
            raise Gagal("Jenis laporan tidak dikenal.", 404)
        return d[jenis]
    return d


@router.get("/periksa")
def periksa(tahun: int, bulan: int = 12, user=Depends(akses), db=Depends(get_db)):
    """Uji integritas: semua jurnal seimbang; Neraca seimbang; LRA/LAK konsisten dengan buku besar."""
    tdk = db.execute("""SELECT j.id, j.uraian, SUM(b.debit) d, SUM(b.kredit) k FROM jurnal j JOIN jurnal_baris b ON b.jurnal_id=j.id GROUP BY j.id HAVING d != k""").fetchall()
    d = susun(db, tahun, bulan)
    peringatan = [c for k in ("lra", "lsal", "neraca", "lak", "lpe") for c in d[k]["catatan"] if c.startswith(("PERHATIAN", "Perhatian"))]
    return {"jurnal_tidak_seimbang": tdk, "peringatan": peringatan, "ok": not tdk and not peringatan}


@router.put("/calk")
def simpan_calk(body: dict = Body(default={}), user=Depends(akses), db=Depends(get_db)):
    tahun = int(body.get("tahun") or 0)
    for kode, _ in BAGIAN_CALK:
        if kode in (body.get("bagian") or {}):
            isi = str(body["bagian"][kode] or "")[:6000]
            db.execute("INSERT INTO calk(tahun,bagian,isi) VALUES(?,?,?) ON CONFLICT(tahun,bagian) DO UPDATE SET isi=excluded.isi", (tahun, kode, isi))
    audit(db, user, "calk", tahun, "UBAH", None, {"bagian": list((body.get("bagian") or {}).keys())}, "BLUD")
    return {"ok": True}


@router.get("/calk-teks")
def calk_teks(tahun: int, user=Depends(akses), db=Depends(get_db)):
    ada = {x["bagian"]: x["isi"] for x in db.execute("SELECT bagian, isi FROM calk WHERE tahun=?", (tahun,)).fetchall()}
    return [{"kode": k, "judul": j, "isi": ada.get(k) or CALK_DEFAULT[k]} for k, j in BAGIAN_CALK]


# ---------------------------------------------------------------- ekspor
def _kop(db):
    return {"baris1": _set(db, "kop_baris1"), "baris2": _set(db, "kop_baris2"), "baris3": _set(db, "kop_baris3"), "alamat": _set(db, "kop_alamat"),
            "jalan": _set(db, "kop_jalan"), "kodepos": _set(db, "kop_kodepos"), "laman": _set(db, "kop_laman"), "email": _set(db, "kop_email")}


def _pj(db):
    k = db.execute("SELECT nama, nip, jabatan FROM pejabat WHERE aktif=1 AND (peran LIKE '%Penandatangan%' OR jabatan LIKE 'Kepala%') ORDER BY id LIMIT 1").fetchone() or {"nama": "", "nip": "", "jabatan": "Kepala"}
    b = db.execute("SELECT nama, nip, jabatan FROM pejabat WHERE aktif=1 AND peran LIKE '%Bendahara%' ORDER BY id LIMIT 1").fetchone() or {"nama": "", "nip": "", "jabatan": "Bendahara"}
    return k, b


def _story(db, rep, tahun, halaman_baru=True):
    P, esc = dk.P, dk.esc
    judul = [dk.P(f"<b>{esc(_set(db, 'kop_baris2') or 'DINAS KESEHATAN')}</b>", "c"), dk.P(f"<b>{esc(_set(db, 'kop_baris3') or 'UPT PUSKESMAS MELATI')}</b>", "c"),
             dk.P(f"<b>{rep['judul']}</b>", "c"), dk.P(esc(rep["periode"]), "c"), dk.P("(Dalam Rupiah)" if rep["jenis"] != "calk" else "", "c"), dk.Spacer(1, 8)]
    story = list(judul)
    kol = rep["kolom"]
    n = len(kol)
    if rep["jenis"] == "calk":
        for r in rep["baris"]:
            if "teks" in r:
                story += [P(esc(r["teks"]), "n"), dk.Spacer(1, 4)]
            elif r["t"]:
                story += [dk.Spacer(1, 4), P(f"<b>{esc(r['u'])}</b>" if r["lv"] == 0 else f"<i>{esc(r['u'])}</i>", "n")]
            else:
                story.append(dk._tabel([[P(esc(r["u"]), "n"), P(_fmt(r["v"][0]), "r")]], [10.5 * dk.cm, 5.5 * dk.cm], header=False, grid=False, pad=1))
    else:
        w0 = 16.4 - (n * (2.9 if n <= 2 else 2.5 if n <= 3 else 2.1 if n <= 4 else 1.9))
        wc = [w0 * dk.cm] + [(2.9 if n <= 2 else 2.5 if n <= 3 else 2.1 if n <= 4 else 1.9) * dk.cm] * n
        data = [[P("<b>Uraian</b>", "n")] + [P(f"<b>{esc(c)}</b>", "c") for c in kol]]
        for r in rep["baris"]:
            ind = "&nbsp;" * (r["lv"] * 4)
            u = P((f"<b>{ind}{esc(r['u'])}</b>" if r["b"] else f"{ind}{esc(r['u'])}"), "kecil")
            data.append([u] + [P((f"<b>{_fmt(x)}</b>" if r["b"] else _fmt(x)) if x is not None else "", "r") for x in (r["v"] + [None] * n)[:n]])
        story.append(dk._tabel(data, wc))
    for c in rep.get("catatan", []):
        story += [dk.Spacer(1, 3), P(f"<font size=8>* {esc(c)}</font>", "n")]
    return story


def _ttd(db, tahun, bulan):
    k, b = _pj(db)
    akhir = dt.date.fromisoformat(_batas(tahun, bulan)[1])
    t = dk.Table([[dk.P(f"<br/>Mengetahui,<br/>{dk.esc(k['jabatan'])}<br/><br/><br/><br/><u>{dk.esc(k['nama'])}</u><br/>NIP. {dk.esc(k['nip'] or '-')}", "n"),
                   dk.P(f"{dk.esc(_set(db, 'kota_surat', 'Kuala Kapuas'))}, {dk.tgl(akhir.isoformat())}<br/>{dk.esc(b['jabatan'])}<br/><br/><br/><br/><u>{dk.esc(b['nama'])}</u><br/>NIP. {dk.esc(b['nip'] or '-')}", "n")]],
                 colWidths=[8.2 * dk.cm, 8.2 * dk.cm])
    return [dk.Spacer(1, 18), t]


@router.get("/dok")
def dokumen(tahun: int, bulan: int = 12, format: str = "pdf", jenis: str = "", user=Depends(akses), db=Depends(get_db)):
    d = susun(db, tahun, bulan)
    pilih = [jenis] if jenis in JENIS else list(JENIS)
    nama = f"Laporan_Keuangan_{tahun}_{bulan:02d}" + (f"_{jenis}" if jenis in JENIS else "")
    if format == "xlsx":
        import openpyxl
        from openpyxl.styles import Alignment, Font
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for k in pilih:
            rep = d[k]
            ws = wb.create_sheet(k.upper())
            ws.append([rep["judul"]]); ws.append([rep["periode"]]); ws.append([])
            ws["A1"].font = Font(bold=True, size=13)
            if k == "calk":
                for r in rep["baris"]:
                    ws.append([r["teks"]] if "teks" in r else [("  " * r["lv"]) + r["u"]] + [x for x in r["v"]])
                    if "teks" in r:
                        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
                ws.column_dimensions["A"].width = 110
                continue
            ws.append(["Uraian"] + rep["kolom"])
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
            for r in rep["baris"]:
                ws.append([("  " * r["lv"]) + r["u"]] + [x for x in r["v"]])
                if r["b"]:
                    for c in ws[ws.max_row]:
                        c.font = Font(bold=True)
                for c in ws[ws.max_row][1:]:
                    c.number_format = '#,##0;(#,##0)' if True else 'General'
            ws.column_dimensions["A"].width = 62
            for i in range(len(rep["kolom"])):
                ws.column_dimensions[chr(66 + i)].width = 20
            for c in rep["catatan"]:
                ws.append([]); ws.append(["* " + c])
        buf = io.BytesIO(); wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nama}.xlsx"', "Cache-Control": "no-store"})
    story = dk.kop(_kop(db))
    for i, k in enumerate(pilih):
        if i:
            story.append(dk.PageBreak())
        story += _story(db, d[k], tahun) + (_ttd(db, tahun, bulan) if k in ("lra", "neraca", "calk") or len(pilih) == 1 else [])
    pdf = dk.build_pdf(story, f"Laporan Keuangan {tahun}")
    if format == "docx":
        return Response(_pdf_ke_docx(pdf), media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{nama}.docx"', "Cache-Control": "no-store"})
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nama}.pdf"', "Cache-Control": "no-store"})
