"""Pembuat dokumen PDF perjalanan dinas (ST, SPD, Rincian Biaya, Daftar Pengeluaran Riil, Surat Pernyataan,
Daftar Hadir, Kuitansi) dengan kop Kabupaten Kapuas / UPT Puskesmas Melati. Semua dokumen dibuat dari SNAPSHOT yang
disimpan saat Surat Tugas terbit, sehingga cetak ulang selalu identik walau data master berubah.

Format ST mengikuti naskah dinas Surat Tugas (untuk diunggah & ditandatangani elektronik di Srikandi): area tanda tangan
dibiarkan kosong untuk pembubuhan TTE oleh Srikandi.
"""
import datetime as dt
import io
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ASSETS = Path(__file__).parent / "assets"
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
ROMAWI = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


# ---------------- util teks ----------------
def tgl(s) -> str:
    d = dt.date.fromisoformat(str(s)[:10])
    return f"{d.day:02d} {BULAN[d.month - 1]} {d.year}"


def tgl_hari(s) -> str:
    d = dt.date.fromisoformat(str(s)[:10])
    return f"{HARI[d.weekday()]}, {d.day:02d} {BULAN[d.month - 1]} {d.year}"


def rp(n) -> str:
    return "Rp" + f"{int(round(n or 0)):,}".replace(",", ".")


def terbilang(n: int) -> str:
    sat = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"]

    def t(x: int) -> str:
        if x < 12:
            return sat[x]
        if x < 20:
            return t(x - 10) + " belas"
        if x < 100:
            return t(x // 10) + " puluh" + (" " + t(x % 10) if x % 10 else "")
        if x < 200:
            return "seratus" + (" " + t(x - 100) if x > 100 else "")
        if x < 1000:
            return t(x // 100) + " ratus" + (" " + t(x % 100) if x % 100 else "")
        if x < 2000:
            return "seribu" + (" " + t(x - 1000) if x > 1000 else "")
        if x < 1_000_000:
            return t(x // 1000) + " ribu" + (" " + t(x % 1000) if x % 1000 else "")
        if x < 1_000_000_000:
            return t(x // 1_000_000) + " juta" + (" " + t(x % 1_000_000) if x % 1_000_000 else "")
        if x < 1_000_000_000_000:
            return t(x // 1_000_000_000) + " miliar" + (" " + t(x % 1_000_000_000) if x % 1_000_000_000 else "")
        return str(x)
    n = int(round(n or 0))
    return ("nol" if n == 0 else t(n)).capitalize() + " rupiah"


def nomor_dari_format(fmt: str, urut: int, tanggal: str) -> str:
    d = dt.date.fromisoformat(tanggal[:10])
    return (fmt.replace("{no}", f"{urut:03d}").replace("{bulan_romawi}", ROMAWI[d.month - 1]).replace("{tahun}", str(d.year)).replace("{bulan}", f"{d.month:02d}"))


# ---------------- gaya ----------------
FONT, FONTB = "Helvetica", "Helvetica-Bold"
S = {
    "n": ParagraphStyle("n", fontName=FONT, fontSize=10.5, leading=12.8),
    "j": ParagraphStyle("j", fontName=FONT, fontSize=10.5, leading=13, alignment=TA_JUSTIFY),
    "c": ParagraphStyle("c", fontName=FONT, fontSize=11, leading=14, alignment=TA_CENTER),
    "r": ParagraphStyle("r", fontName=FONT, fontSize=11, leading=14, alignment=TA_RIGHT),
    "b": ParagraphStyle("b", fontName=FONTB, fontSize=11, leading=14),
    "judul": ParagraphStyle("judul", fontName=FONTB, fontSize=13, leading=16, alignment=TA_CENTER),
    "kecil": ParagraphStyle("kecil", fontName=FONT, fontSize=9.5, leading=12),
    "kop0": ParagraphStyle("kop0", fontName=FONT, fontSize=12.5, leading=15, alignment=TA_CENTER),
    "kop1": ParagraphStyle("kop1", fontName=FONTB, fontSize=13, leading=15.5, alignment=TA_CENTER),
    "kop2": ParagraphStyle("kop2", fontName=FONTB, fontSize=14.5, leading=17, alignment=TA_CENTER),
    "kopa": ParagraphStyle("kopa", fontName=FONT, fontSize=9, leading=11, alignment=TA_CENTER),
    "judulr": ParagraphStyle("judulr", fontName=FONT, fontSize=13, leading=16, alignment=TA_CENTER),
    "tiny": ParagraphStyle("tiny", fontName=FONT, fontSize=8.5, leading=10.5),
    "s": ParagraphStyle("s", fontName=FONT, fontSize=9.6, leading=11.4),
}


from contextvars import ContextVar  # noqa: E402

_SKALA: ContextVar = ContextVar("skala", default=1.0)
_GAYA_CACHE: dict = {}


def _gaya(nama: str):
    k = _SKALA.get()
    if k == 1.0:
        return S[nama]
    if (nama, k) not in _GAYA_CACHE:
        _GAYA_CACHE[(nama, k)] = ParagraphStyle(f"{nama}_{k}", parent=S[nama], fontSize=S[nama].fontSize * k, leading=S[nama].leading * k)
    return _GAYA_CACHE[(nama, k)]


def P(t, st="n"):
    return Paragraph(str(t if t is not None else "").replace("\n", "<br/>"), _gaya(st))


def muat_halaman(builder, target_halaman: int, footer: bool = False):
    """Bangun dokumen dengan ukuran font terbesar yang masih muat `target_halaman` (tanda tangan tidak boleh pindah halaman)."""
    import re as _re
    k = 1.0
    for k in (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55):
        tok = _SKALA.set(k)
        try:
            pdf = build_pdf(builder(), "uji", footer_srikandi=footer)
        finally:
            _SKALA.reset(tok)
        if len(_re.findall(rb"/Type /Page(?!s)", pdf)) <= target_halaman:
            break
    tok = _SKALA.set(k)
    try:
        return builder()
    finally:
        _SKALA.reset(tok)


def esc(t) -> str:
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- kop ----------------
def _logo_bulat() -> str:
    """Logo Puskesmas berbentuk lingkaran (menghilangkan sudut hitam pada JPG)."""
    out = Path(tempfile.gettempdir()) / "sikadin_logo_pkm_bulat.png"
    if not out.exists():
        im = Image.open(ASSETS / "logo-puskesmas.jpg").convert("RGBA")
        w, h = im.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).ellipse((2, 2, w - 2, h - 2), fill=255)
        im.putalpha(mask)
        im.resize((400, 400)).save(out)
    return str(out)


def kop(k: dict) -> list:
    """Kop mengikuti contoh Srikandi: lambang Kabupaten di kiri; baris 1 reguler, 2-3 tebal, alamat kecil."""
    ks = 0.55 + 0.45 * _SKALA.get()
    lam = RLImage(str(ASSETS / "lambang-kapuas.png"), width=2.1 * cm * ks, height=2.4 * cm * ks)
    tengah = [P(esc(k.get("baris1")), "kop0"), P(esc(k.get("baris2")), "kop1"), P(esc(k.get("baris3")), "kop2")]
    tengah += [P(esc(x), "kopa") for x in str(k.get("alamat") or "").split("\n") if x.strip()]
    t = Table([[lam, tengah, ""]], colWidths=[2.8 * cm, 11.4 * cm, 2.5 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, 3), HRFlowable(width="100%", thickness=1.6, color=colors.black, spaceAfter=8)]


def ttd(jabatan: str, nama: str, pangkat: str | None, nip: str | None, kota: str | None = None, tanggal: str | None = None, tinggi: float = 2.4, tte: bool = False) -> Table:
    """Blok tanda tangan kanan. tte=True: ruang dikosongkan untuk tanda tangan elektronik Srikandi."""
    baris = []
    if kota and tanggal:
        baris.append([P(f"{esc(kota)}, {tgl(tanggal)}", "n")])
    baris += [[P(esc(jabatan).upper() if jabatan else "", "n")], [Spacer(1, tinggi * cm)],
              [P(f"<u><b>{esc(nama)}</b></u>", "n")]]
    if pangkat:
        baris.append([P(esc(pangkat), "n")])
    if nip:
        baris.append([P(f"NIP. {esc(nip)}", "n")])
    t = Table(baris, colWidths=[7.0 * cm])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    outer = Table([[ "", t]], colWidths=[9.7 * cm, 7.0 * cm])
    outer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return outer


def _tabel(data, widths, header=True, grid=True, pad=3):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 10.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]
    if grid:
        st.append(("GRID", (0, 0), (-1, -1), 0.6, colors.black))
    if header:
        st += [("FONTNAME", (0, 0), (-1, 0), FONTB), ("ALIGN", (0, 0), (-1, 0), "CENTER"), ("BACKGROUND", (0, 0), (-1, 0), colors.Color(.93, .93, .93))]
    t.setStyle(TableStyle(st))
    return t


def _kv(rows, w1=0.9 * cm, w2=6.2 * cm, w3=9.6 * cm, grid=True):
    data = [[P(a, "n"), P(b, "n"), P(c, "n")] for a, b, c in rows]
    t = Table(data, colWidths=[w1, w2, w3])
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 0)]
    if grid:
        st.append(("GRID", (0, 0), (-1, -1), 0.6, colors.black))
    t.setStyle(TableStyle(st))
    return t


def _petugas_spd(isi: dict, pid: int) -> dict:
    return next(p for p in isi["petugas"] if p["id"] == pid)


# ======================= DOKUMEN =======================
TOKEN_NOMOR, TOKEN_TTD, TOKEN_PENGIRIM, TOKEN_NAMA = "${nomor_naskah}", "${ttd}", "${ttd_pengirim}", "${nama_pengirim}"


def _hari_teks(n: int) -> str:
    return f"{n} ({terbilang(n).replace(' rupiah', '').capitalize()}) Hari"


def _pg(p: dict) -> str:
    """'Pembina Tk I / IV b' (golongan ditulis tanpa garis miring, seperti contoh Srikandi)."""
    gol = str(p.get("golongan") or "").replace("/", " ").strip()
    return " / ".join(x for x in [p.get("pangkat"), gol] if x and x != "-")


def _blok_ttd(isi: dict, st: dict, mode: str, label: str | None = None, dengan_tempat: bool = True) -> Table:
    """Blok tanda tangan. mode='srikandi': memuat KODE yang diisi Srikandi saat TTE (${ttd}, ${ttd_pengirim}, ${nama_pengirim});
    mode='cetak': nama dicetak biasa dengan ruang tanda tangan basah."""
    t = isi["ttd"]
    sr = mode == "srikandi"
    kanan = []
    if dengan_tempat:
        kanan.append(P(f"{esc(isi['kota'])}, {tgl(st['tanggal_surat'])}", "n"))
    if label:
        kanan.append(P(esc(label), "n"))
    kanan.append(P(esc(t["jabatan"]), "n"))
    if sr:
        # Srikandi mengganti ${ttd_pengirim} dengan gambar QR (± 2,5 cm, berpusat di baris kode): beri ruang kosong
        # di atas & bawah agar QR tidak menimpa teks; kode hanya SATU (di kolom kanan, rata dengan nama).
        kanan += [Spacer(1, 1.35 * cm * _SKALA.get()), P(TOKEN_PENGIRIM, "n"), Spacer(1, 1.35 * cm * _SKALA.get()), P(TOKEN_NAMA, "n")]
    else:
        kanan += [Spacer(1, 1.9 * cm * _SKALA.get()), P(f"<u>{esc(t['nama'])}</u>", "n")]
    if t.get("nip"):
        kanan.append(P(f"NIP {esc(t['nip'])}", "n"))
    kiri = [Spacer(1, 1 * _SKALA.get())]
    o = Table([[kiri, kanan]], colWidths=[7.4 * cm, 9.3 * cm])
    o.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (1, 0), (1, 0), 0.2 * cm)]))
    return o


def _nomor_tampil(st: dict, mode: str) -> str:
    return TOKEN_NOMOR if mode == "srikandi" else (st.get("nomor_srikandi") or st["nomor_tampil"])


def d_st(isi: dict, st: dict, mode: str = "srikandi") -> list:
    """Surat Tugas — mengikuti contoh Srikandi Puskesmas Melati."""
    story = kop(isi["kop"])
    story += [P("SURAT TUGAS", "judulr"), P(f"NOMOR : {_nomor_tampil(st, mode)}", "c"), Spacer(1, 8 * _SKALA.get())]
    dasar = [x.strip() for x in str(st.get("dasar") or "").split("\n") if x.strip()]
    if dasar:
        t = Table([[P("Dasar", "n"), P(":", "n"), P(esc(" ".join(dasar)) if len(dasar) == 1 else "<br/>".join(f"{i}. {esc(d)}" for i, d in enumerate(dasar, 1)), "j")]],
                  colWidths=[1.9 * cm, 0.5 * cm, 14.3 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [t, Spacer(1, 8 * _SKALA.get())]
    story += [P("<b>MEMERINTAHKAN :</b>", "c"), Spacer(1, 6 * _SKALA.get())]
    rows = []
    for i, p in enumerate(isi["petugas"], 1):
        campur = [("a.", "Nama", p["nama"]), ("b.", "Pangkat/Gol", _pg(p)), ("c.", "NIP", p.get("nip") or ""), ("d.", "Jabatan", p.get("jabatan") or "")]
        for j, (h, lab, val) in enumerate(campur):
            rows.append([P("Kepada" if (i == 1 and j == 0) else "", "n"), P(":" if (i == 1 and j == 0) else "", "n"), P(str(i) if j == 0 else "", "n"), P(h, "n"), P(lab, "n"), P(":", "n"), P(esc(val), "n")])
        if i < len(isi["petugas"]):
            rows.append([""] * 7)
    tinggi = [5 * _SKALA.get() if all(c == "" for c in r) else None for r in rows]
    t = Table(rows, colWidths=[1.9 * cm, 0.5 * cm, 0.6 * cm, 0.7 * cm, 2.6 * cm, 0.4 * cm, 10.0 * cm], rowHeights=tinggi)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]))
    story += [t, Spacer(1, 6 * _SKALA.get())]
    h = isi["hari"]
    untuk = [
        [P("Untuk", "n"), P(":", "n"), P("1", "n"), P("Melaksanakan perjalanan dinas dalam rangka:<br/>" + esc(st["maksud"]), "j")],
        ["", "", P("2", "n"), Table([[P("Lama Penugasan", "n"), P(f": {_hari_teks(h)}", "n")], [P("Terhitung Mulai Tanggal", "n"), P(f": {tgl(isi['mulai'])}", "n")],
                                      [P("Kembali Tanggal", "n"), P(f": {tgl(isi['selesai'])}", "n")]], colWidths=[4.6 * cm, 9.0 * cm], style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)])],
        ["", "", P("3", "n"), P("Melaporkan hasil perjalanan dinas kepada yang mengeluarkan surat tugas", "j")],
        ["", "", P("4", "n"), P("Pembebanan Biaya pada DPA Dinas Kesehatan Unit Puskesmas Melati Nomor<br/>DPA : " + esc(isi.get("dpa") or "-"), "n")],
    ]
    t = Table(untuk, colWidths=[1.9 * cm, 0.5 * cm, 0.6 * cm, 13.7 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [t, Spacer(1, 14 * _SKALA.get()), KeepTogether([_blok_ttd(isi, st, mode)])]
    return story


def d_spd(isi: dict, st: dict, spds: list, mode: str = "srikandi") -> list:
    """SPD (lembar depan + belakang) — SATU dokumen per ST (nomor sama dengan ST), seperti contoh Srikandi:
    pegawai ber-NIP sebagai 'yang diperintah', tenaga kontrak/Non ASN sebagai 'pengikut'."""
    diperintah = [p for p in isi["petugas"] if p.get("nip") and p.get("status") != "Non ASN"] or isi["petugas"]
    ikut = [p for p in isi["petugas"] if p not in diperintah]
    nomor = _nomor_tampil(st, mode)
    story = kop(isi["kop"])
    hdr = Table([["", [P(f"Lembar ke &nbsp;&nbsp;&nbsp;: ", "tiny"), P("Kode No &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: ", "tiny"), P(f"Nomor &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {nomor}", "tiny")]]], colWidths=[10.0 * cm, 6.7 * cm])
    hdr.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [hdr, Spacer(1, 4), P("SURAT PERJALANAN DINAS", "judulr"), Spacer(1, 6)]

    def lines(items, fmt):
        return "<br/>".join(fmt(i, x) for i, x in enumerate(items, 1))
    ang = isi.get("anggaran") or {}
    def kn(v):
        a, _, b = str(v or "").partition("|")
        return a.strip(), b.strip()
    ins_k, ins_n = kn(ang.get("instansi"))
    prog = [kn(x) for x in str(ang.get("program") or "").split("\n") if x.strip()]
    keg_k, keg_n = kn(ang.get("kegiatan"))
    rek_k, rek_n = kn(ang.get("rekening") or (isi.get("kode_rekening") or ""))
    pembebanan = (f"a. &nbsp;{esc(ins_k)} &nbsp;&nbsp;({esc(ins_n)})<br/>b. &nbsp;" + "<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;".join(f"{esc(k_)}<br/><font size=8>&nbsp;&nbsp;&nbsp;({esc(n_)})</font>" for k_, n_ in prog))
    kolom = [
        ("1", "Kuasa Pengguna Anggaran", esc(isi["ttd"]["jabatan"])),
        ("2", "Nama NIP Pegawai yang diperintah", lines(diperintah, lambda i, p: f"{i} &nbsp;{esc(p['nama'])} &nbsp;/ NIP.{esc(p.get('nip') or '-')}")),
        ("3", "a. Pangkat dan Golongan", "a &nbsp;" + "<br/>&nbsp;&nbsp;&nbsp;&nbsp;".join(esc(_pg(p) or "-") for p in diperintah)),
        ("", "b. Jabatan/Instansi", "b &nbsp;" + "<br/>&nbsp;&nbsp;&nbsp;&nbsp;".join(esc(p.get("jabatan") or "-") for p in diperintah)),
        ("", "c. Tingkat Pegawai", "c &nbsp;" + " ".join(esc(p.get("tingkat") or "") for p in diperintah)),
        ("4", "Maksud Perjalanan Dinas", f"<font size=9>{esc(st['maksud'])}</font>"),
        ("5", "Alat angkut yang digunakan", esc(isi.get("alat_angkutan") or "Angkutan darat")),
        ("6", "a. Tempat Berangkat<br/>b. Tempat Tujuan", f"a. &nbsp;{esc(isi['tempat_berangkat'])}<br/>b. &nbsp;{esc(isi['lokasi'])}"),
        ("7", "a. Lama Perjalanan Dinas<br/>b. Tanggal berangkat<br/>c. Tanggal harus kembali", f"a. &nbsp;{_hari_teks(isi['hari'])}<br/>b. &nbsp;{tgl(isi['mulai'])}<br/>c. &nbsp;{tgl(isi['selesai'])}"),
        ("8", "Pengikut" + ("<br/>" + "<br/>".join(esc(p["nama"]) for p in ikut) if ikut else ""), "Keterangan" + ("<br/>" + "<br/>".join(esc(p.get("jabatan") or "") for p in ikut) if ikut else "")),
        ("9", "Pembebanan Anggaran<br/>a. Kode dan Nama Instansi<br/>b. Kode dan Nama Program<br/><br/><br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1. Kode Nama Kegiatan<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;2. Kode Rekening dan Nama Belanja",
         pembebanan + f"<br/>&nbsp;&nbsp;&nbsp;1. &nbsp;{esc(keg_k)}<br/><font size=8>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;({esc(keg_n)})</font><br/>&nbsp;&nbsp;&nbsp;2. &nbsp;{esc(rek_k)}<br/><font size=8>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;({esc(rek_n)})</font>"),
        ("10", "Keterangan Lainnya", ""),
    ]
    data = [[P(a, "tiny"), P(b, "s"), P(c, "s")] for a, b, c in kolom]
    t = Table(data, colWidths=[0.9 * cm, 6.3 * cm, 9.5 * cm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, colors.black), ("LINEBEFORE", (1, 0), (1, -1), 0.5, colors.black), ("LINEBEFORE", (2, 0), (2, -1), 0.5, colors.black),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.black), ("LINEABOVE", (0, 3), (-1, 3), 0.5, colors.black), ("LINEABOVE", (0, 5), (-1, 5), 0.5, colors.black),
                           ("LINEABOVE", (0, 6), (-1, 6), 0.5, colors.black), ("LINEABOVE", (0, 7), (-1, 7), 0.5, colors.black), ("LINEABOVE", (0, 8), (-1, 8), 0.5, colors.black),
                           ("LINEABOVE", (0, 9), (-1, 9), 0.5, colors.black), ("LINEABOVE", (0, 10), (-1, 10), 0.5, colors.black), ("LINEABOVE", (0, 11), (-1, 11), 0.5, colors.black),
                           ("LINEBELOW", (0, 3), (-1, 3), 0.0, colors.white)]))
    story += [t, Spacer(1, 5)]
    ttd_t = Table([[[P(f"Dikeluarkan di &nbsp;&nbsp;&nbsp;: {esc(isi['kota'])}", "n"), P(f"Pada Tanggal &nbsp;&nbsp;&nbsp;&nbsp;: {tgl(st['tanggal_surat'])}", "n")]]], colWidths=[16.7 * cm])
    ttd_t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 9.0 * cm)]))
    story += [ttd_t, _blok_ttd(isi, st, mode, label="Kuasa Pengguna Anggaran", dengan_tempat=False)]

    # ---------- lembar belakang ----------
    pptk = isi.get("pptk") or {}
    tujuan, asal = isi["lokasi"], isi["tempat_berangkat_instansi"] if isi.get("tempat_berangkat_instansi") else "UPT Puskesmas Melati"
    def cell(*baris):
        return [P(b, "n") for b in baris if b is not None]
    I = Table([[P("", "n"), cell(f"Berangkat dari &nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(asal)}", "(Tempat Kedudukan)", f"Pada Tanggal &nbsp;&nbsp;&nbsp;: &nbsp;{tgl(isi['mulai'])}", f"Ke &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(tujuan)}",
                    "<br/>Pejabat Pelaksana Teknis Kegiatan (PPTK)", "<br/><br/><br/>" + (esc(pptk.get("nama") or "..................................") ), (f"NIP.{esc(pptk.get('nip'))}" if pptk.get("nip") else None))]])
    back = [
        [P("I", "tiny"), cell(), cell(f"Berangkat dari &nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(asal)}", "(Tempat Kedudukan)", f"Pada Tanggal &nbsp;&nbsp;&nbsp;: &nbsp;{tgl(isi['mulai'])}", f"Ke &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(tujuan)}",
                                      "<br/>Pejabat Pelaksana Teknis Kegiatan (PPTK)", "<br/><br/><br/>" + esc(pptk.get("nama") or ".................................."), (f"NIP.{esc(pptk.get('nip'))}" if pptk.get("nip") else None))],
        [P("II", "tiny"), cell(f"Tiba di &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(tujuan)}", "", f"Pada Tanggal &nbsp;&nbsp;: &nbsp;{tgl(isi['mulai'])}"),
         cell(f"Berangkat dari &nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(tujuan)}", f"Ke &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(asal)}", f"Pada Tanggal &nbsp;&nbsp;&nbsp;: &nbsp;{tgl(isi['selesai'])}")],
        [P("III", "tiny"), cell("Tiba di &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;:", "Pada Tanggal &nbsp;&nbsp;:"), cell("Berangkat dari &nbsp;&nbsp;&nbsp;&nbsp;:", "Ke &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;:", "Pada Tanggal &nbsp;&nbsp;&nbsp;:")],
        [P("IV", "tiny"), cell("Tiba di &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;:", "Pada Tanggal &nbsp;&nbsp;:"), cell("Berangkat dari &nbsp;&nbsp;&nbsp;&nbsp;:", "Ke &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;:", "Pada Tanggal &nbsp;&nbsp;&nbsp;:")],
        [P("V", "tiny"), cell(f"Tiba di &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: &nbsp;{esc(asal)}", f"Pada Tanggal &nbsp;&nbsp;: &nbsp;{tgl(isi['selesai'])}"),
         cell("Telah diperiksa dengan keterangan bahwa perjalanan tersebut diatas perintahnya dan semata-mata untuk kepentingan jabatan dalam waktu yang sesingkat-singkatnya")],
    ]
    bt = Table(back, colWidths=[0.9 * cm, 7.8 * cm, 8.0 * cm], rowHeights=[4.2 * cm, 3.1 * cm, 3.1 * cm, 3.1 * cm, 4.6 * cm])
    bt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, colors.black), ("LINEBEFORE", (2, 0), (2, -1), 0.6, colors.black), ("LINEABOVE", (0, 1), (-1, -1), 0.5, colors.black),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    foot = Table([[P("VI", "tiny"), P("CATATAN LAIN-LAIN", "tiny")], [P("VII", "tiny"), [P("Perhatian:", "tiny"), P("PA/KPA yang menerbitkan SPD, Pegawai yang melakukan perjalanan dinas, para pejabat yang mengesahkan tanggal berangkat/tiba serta bendahara pengeluaran bertanggungjawab berdasarkan peraturan dan Perundang-Undangan Keuangan Negara/Daerah, apabila Negara/Daerah menderita/mengalami kerugian akibat kesalahan, kelalaian dan kealpaan.", "tiny")]]],
                 colWidths=[0.9 * cm, 15.8 * cm])
    foot.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, colors.black), ("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [PageBreak(), bt, foot, Spacer(1, 12), _blok_ttd(isi, st, mode, label="Kuasa Pengguna Anggaran", dengan_tempat=False)]
    return story


def d_rincian(isi: dict, st: dict, spd: dict, biaya: dict) -> list:
    k, ttdj = isi["kop"], isi["ttd"]
    p = _petugas_spd(isi, spd["pegawai_id"])
    story = kop(k) + [P("<b>RINCIAN BIAYA PERJALANAN DINAS</b>", "judul"), Spacer(1, 4),
                      P(f"Lampiran SPD Nomor : {esc(st['nomor_tampil'])}<br/>Tanggal &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {tgl(st['tanggal_surat'])}", "n"), Spacer(1, 6),
                      P(f"Nama : <b>{esc(p['nama'])}</b> (Tingkat {esc(p.get('tingkat'))})<br/>Tujuan : {esc(isi['lokasi'])}, {tgl(isi['mulai'])}" + (f" s.d. {tgl(isi['selesai'])}" if isi["hari"] > 1 else ""), "n"), Spacer(1, 6)]
    data = [["No", "Perincian Biaya", "Jumlah", "Keterangan"]]
    for i, b in enumerate(biaya["baris"], 1):
        data.append([str(i), P(esc(b["uraian"]), "kecil"), P(rp(b["jumlah"]), "r"), P(f"{b['volume']} {esc(b['satuan'])} × {rp(b['tarif'])}", "kecil")])
    if len(data) == 1:
        data.append(["", P("(tidak ada komponen biaya)", "kecil"), "", ""])
    data.append(["", P("<b>Jumlah</b>", "n"), P(f"<b>{rp(biaya['total'])}</b>", "r"), ""])
    story += [_tabel(data, [1.0 * cm, 8.2 * cm, 3.2 * cm, 4.4 * cm]), Spacer(1, 6),
              P(f"Terbilang : <i>{esc(terbilang(biaya['total']))}</i>", "n"), Spacer(1, 4)]
    for w in biaya.get("peringatan", []):
        story.append(P(f"<font size=9>* {esc(w)}</font>", "n"))
    story.append(Spacer(1, 10))
    kiri = ttd("Telah dibayar sejumlah", "", None, None, tinggi=0) if False else None
    t = Table([[P("Telah dibayar sejumlah<br/>" + rp(biaya["total"]) + "<br/><br/><b>Bendahara Pengeluaran</b><br/><br/><br/><br/>(.....................................)", "n"),
                P(f"{esc(isi['kota'])}, {tgl(st['tanggal_surat'])}<br/>Telah menerima jumlah uang sebesar<br/>" + rp(biaya["total"]) + f"<br/><b>Yang menerima</b><br/><br/><br/><br/><u>{esc(p['nama'])}</u><br/>NIP. {esc(p.get('nip') or '-')}", "n")]],
              colWidths=[8.3 * cm, 8.3 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 8), HRFlowable(width="100%", thickness=0.6, color=colors.black), Spacer(1, 4),
              P("PERHITUNGAN SPD RAMPUNG", "b"),
              _tabel([[P("Ditetapkan sejumlah", "n"), P(rp(biaya["total"]), "r")], [P("Yang telah dibayar semula", "n"), P("Rp0", "r")], [P("Sisa kurang/lebih", "n"), P(rp(biaya["total"]), "r")]], [8.0 * cm, 4.0 * cm], header=False, grid=False),
              Spacer(1, 8), ttd(ttdj["jabatan"] + ",", ttdj["nama"], ttdj.get("pangkat"), ttdj.get("nip"), tinggi=1.6)]
    return story


def d_riil(isi: dict, st: dict, spd: dict) -> list:
    p = _petugas_spd(isi, spd["pegawai_id"])
    story = kop(isi["kop"]) + [P("<b>DAFTAR PENGELUARAN RIIL</b>", "judul"), Spacer(1, 6),
                               P("Yang bertanda tangan di bawah ini:", "n"), Spacer(1, 4),
                               _kv([("", "Nama", f": {esc(p['nama'])}"), ("", "NIP", f": {esc(p.get('nip') or '-')}"), ("", "Jabatan", f": {esc(p.get('jabatan') or '-')}")], 0.2 * cm, 3.5 * cm, 13 * cm, grid=False),
                               Spacer(1, 6), P(f"berdasarkan Surat Perjalanan Dinas (SPD) Nomor {esc(st['nomor_tampil'])} tanggal {tgl(st['tanggal_surat'])}, dengan ini kami menyatakan dengan sesungguhnya bahwa:", "j"),
                               Spacer(1, 4), P("1. Biaya transport pegawai dan/atau biaya penginapan di bawah ini yang tidak dapat diperoleh bukti-bukti pengeluarannya, meliputi:", "j"), Spacer(1, 4)]
    data = [["No", "Uraian", "Jumlah"]] + [[str(i), "", ""] for i in range(1, 6)] + [["", P("<b>Jumlah</b>", "n"), ""]]
    story += [_tabel(data, [1.0 * cm, 11.4 * cm, 4.2 * cm], pad=7), Spacer(1, 6),
              P("2. Jumlah uang tersebut pada angka 1 di atas benar-benar dikeluarkan untuk pelaksanaan perjalanan dinas dimaksud dan apabila di kemudian hari terdapat kelebihan atas pembayaran, kami bersedia untuk menyetorkan kelebihan tersebut ke Kas Daerah.", "j"),
              Spacer(1, 6), P("Demikian pernyataan ini kami buat dengan sebenarnya, untuk dipergunakan sebagaimana mestinya.", "j"), Spacer(1, 12),
              Table([[P("Mengetahui/Menyetujui<br/>Pejabat Pelaksana Teknis Kegiatan,<br/><br/><br/><br/>(.....................................)", "n"),
                      P(f"{esc(isi['kota'])}, ..............................<br/>Pelaksana SPD,<br/><br/><br/><br/><u>{esc(p['nama'])}</u><br/>NIP. {esc(p.get('nip') or '-')}", "n")]], colWidths=[8.3 * cm, 8.3 * cm])]
    return story


def _pernyataan(isi, st, spd, judul, isi_teks, penutup) -> list:
    p = _petugas_spd(isi, spd["pegawai_id"])
    return (kop(isi["kop"]) + [P(f"<b><u>{judul}</u></b>", "judul"), Spacer(1, 10), P("Yang bertanda tangan di bawah ini:", "n"), Spacer(1, 4),
            _kv([("", "Nama", f": {esc(p['nama'])}"), ("", "NIP", f": {esc(p.get('nip') or '-')}"), ("", "Pangkat/Gol.", f": {esc(_pg(p) or '-')}"),
                 ("", "Jabatan", f": {esc(p.get('jabatan') or '-')}")], 0.2 * cm, 3.5 * cm, 13 * cm, grid=False), Spacer(1, 8)]
            + [P(isi_teks.format(spd=esc(st["nomor_tampil"]), tgl=tgl(st["tanggal_surat"]), lokasi=esc(isi["lokasi"]), mulai=tgl(isi["mulai"]), selesai=tgl(isi["selesai"])), "j"), Spacer(1, 8)]
            + [P(penutup, "j"), Spacer(1, 16),
               Table([[P("Mengetahui,<br/>Pejabat Pelaksana Teknis Kegiatan,<br/><br/><br/><br/>(.....................................)", "n"),
                       P(f"{esc(isi['kota'])}, ..............................<br/>Yang membuat pernyataan,<br/><br/><br/><br/><u>{esc(p['nama'])}</u><br/>NIP. {esc(p.get('nip') or '-')}", "n")]], colWidths=[8.3 * cm, 8.3 * cm])])


def d_batal(isi, st, spd) -> list:
    return _pernyataan(isi, st, spd, "SURAT PERNYATAAN PEMBATALAN PERJALANAN DINAS",
                       "berdasarkan Surat Tugas Nomor " + esc(st["nomor_tampil"]) + " dan Surat Perjalanan Dinas (SPD) Nomor {spd} tanggal {tgl} ke {lokasi} pada tanggal {mulai} s.d. {selesai}, menyatakan dengan sebenarnya bahwa perjalanan dinas tersebut <b>dibatalkan</b>, dengan alasan:<br/><br/>..............................................................................................................<br/>..............................................................................................................",
                       "Apabila telah terjadi pembayaran/biaya yang telah dikeluarkan atas perjalanan dinas tersebut, saya bersedia mengembalikannya kepada Bendahara Pengeluaran. Demikian pernyataan ini dibuat dengan sebenarnya dan dapat dipertanggungjawabkan.")


def d_kembali(isi, st, spd) -> list:
    return _pernyataan(isi, st, spd, "SURAT PERNYATAAN PENGEMBALIAN BIAYA TRANSPORT / PENGINAPAN",
                       "berdasarkan Surat Perjalanan Dinas (SPD) Nomor {spd} tanggal {tgl} ke {lokasi} pada tanggal {mulai} s.d. {selesai}, menyatakan dengan sebenarnya bahwa biaya transport dan/atau penginapan sebesar Rp ........................ (........................................................) <b>tidak digunakan seluruhnya</b>/tidak terpakai karena:<br/><br/>..............................................................................................................<br/>..............................................................................................................",
                       "Oleh karena itu, kelebihan tersebut saya kembalikan/setorkan ke Kas Daerah melalui Bendahara Pengeluaran. Demikian pernyataan ini dibuat dengan sebenarnya dan dapat dipertanggungjawabkan.")


def d_hadir(isi: dict, st: dict) -> list:
    story = kop(isi["kop"]) + [P("<b>DAFTAR HADIR</b>", "judul"), Spacer(1, 6),
                               _kv([("", "Kegiatan", f": {esc(st['maksud'])}"), ("", "Tempat", f": {esc(isi['lokasi'])}"),
                                    ("", "Hari/Tanggal", f": {tgl_hari(isi['mulai'])}" + (f" s.d. {tgl_hari(isi['selesai'])}" if isi["hari"] > 1 else "")), ("", "Dasar", f": Surat Tugas No. {esc(st['nomor_tampil'])}")], 0.2 * cm, 3.0 * cm, 13.5 * cm, grid=False), Spacer(1, 8)]
    data = [["No", "Nama", "Jabatan / Instansi", "Tanda Tangan"]]
    for i, p in enumerate(isi["petugas"], 1):
        data.append([str(i), P(esc(p["nama"]), "kecil"), P(esc(p.get("jabatan") or "-"), "kecil"), ""])
    for i in range(len(isi["petugas"]) + 1, len(isi["petugas"]) + 16):
        data.append([str(i), "", "", ""])
    story.append(_tabel(data, [1.0 * cm, 6.2 * cm, 5.0 * cm, 4.4 * cm], pad=7))
    return story


def d_kuitansi(isi: dict, st: dict, spd: dict, biaya: dict) -> list:
    ttdj = isi["ttd"]
    p = _petugas_spd(isi, spd["pegawai_id"])
    uraian = f"Biaya perjalanan dinas ke {esc(isi['lokasi'])} tanggal {tgl(isi['mulai'])}" + (f" s.d. {tgl(isi['selesai'])}" if isi["hari"] > 1 else "") + f" ({esc(st['maksud'])}) sesuai SPD No. {esc(st['nomor_tampil'])}."
    rows = [("", "Sudah terima dari", f": Bendahara Pengeluaran {esc(isi['instansi'])}"), ("", "Banyaknya uang", f": <i>{esc(terbilang(biaya['total']))}</i>"),
            ("", "Untuk pembayaran", f": {uraian}")]
    story = kop(isi["kop"]) + [P("<b>K U I T A N S I</b>", "judul"), Spacer(1, 10), _kv(rows, 0.2 * cm, 4.0 * cm, 12.5 * cm, grid=False), Spacer(1, 8)]
    t = _tabel([["Perincian", "Jumlah"]] + [[P(esc(b["uraian"]), "kecil"), P(rp(b["jumlah"]), "r")] for b in biaya["baris"]] + [[P("<b>Jumlah</b>", "n"), P(f"<b>{rp(biaya['total'])}</b>", "r")]], [12.0 * cm, 4.6 * cm])
    story += [t, Spacer(1, 6), P(f"Jumlah: <b>{rp(biaya['total'])}</b>", "n"), Spacer(1, 12)]
    tt = Table([[P("Mengetahui/Menyetujui<br/>" + esc(ttdj["jabatan"]) + f",<br/><br/><br/><br/><u>{esc(ttdj['nama'])}</u>" + (f"<br/>NIP. {esc(ttdj.get('nip'))}" if ttdj.get("nip") else ""), "n"),
                 P("Lunas dibayar,<br/>Bendahara Pengeluaran,<br/><br/><br/><br/>(.....................................)", "n"),
                 P(f"{esc(isi['kota'])}, ..............................<br/>Yang menerima,<br/>(materai sesuai ketentuan)<br/><br/><u>{esc(p['nama'])}</u><br/>NIP. {esc(p.get('nip') or '-')}", "n")]],
               colWidths=[5.6 * cm, 5.0 * cm, 6.0 * cm])
    tt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(tt)
    return story


# ======================= perakit =======================
def build_pdf(story: list, judul: str, footer_srikandi: bool = False) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.3 * cm, rightMargin=2.0 * cm, topMargin=1.4 * cm, bottomMargin=1.8 * cm,
                            title=judul, author="SIKADIN — UPT Puskesmas Melati", subject="Dokumen perjalanan dinas")

    def kaki(canvas, _doc):
        if footer_srikandi:
            canvas.saveState()
            canvas.setFont("Helvetica", 7)
            canvas.drawCentredString(A4[0] / 2, 1.05 * cm, "Dokumen ini telah ditandatangani secara elektronik menggunakan sertifikat elektronik")
            canvas.drawCentredString(A4[0] / 2, 0.7 * cm, "yang diterbitkan oleh Balai Besar Sertifikasi Elektronik (BSrE), Badan Siber dan Sandi Negara (BSSN).")
            canvas.restoreState()
    doc.build(story, onFirstPage=kaki, onLaterPages=kaki)
    return buf.getvalue()


def gabung(*bagian: list) -> list:
    out: list = []
    for i, b in enumerate(bagian):
        if i:
            out.append(PageBreak())
        out += b
    return out
