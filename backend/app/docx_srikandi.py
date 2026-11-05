"""Mengisi templat Srikandi "Surat Tugas dan SPD OPD (2 Tandatangan)" (.docx) dengan data jadwal.

Templat resmi dipakai apa adanya: hanya titik-titik isian (………) yang diisi, sedangkan KODE Srikandi dibiarkan utuh agar
diisi Srikandi saat penandatanganan elektronik:
  ${nomor_naskah}  ${tanggal_naskah}  ${ttd_pengirim2} ${nama_pengirim2} ${pangkat_pengirim2} ${nip_pengirim2}  (Kepala / Pengguna Anggaran)
  ${ttd_pengirim1} ${nama_pengirim1} ${nip_pengirim1}                                                          (PPTK)
"""
import copy
import io
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from .dokumen import BULAN, _hari_teks, _pg, tgl

TEMPLAT = Path(__file__).parent / "assets" / "templat_st_spd_srikandi.docx"
TITIK = re.compile(r"^[\s…\.]{3,}$")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


# ---------- util XML ----------
def _runs(p):
    return [r for r in p.iter(qn("w:r"))]


def _wt(r):
    return r.findall(qn("w:t"))


def _teks_run(r) -> str:
    return "".join(t.text or "" for t in _wt(r))


def _set_run(r, text: str) -> None:
    ts = _wt(r)
    if not ts:
        t = r.makeelement(qn("w:t"), {})
        r.append(t)
        ts = [t]
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")
    for extra in ts[1:]:
        r.remove(extra)


def _isi_titik(p, nilai: list) -> None:
    """Ganti run yang hanya berisi titik-titik (………) berurutan dengan nilai[]; sisa titik dikosongkan."""
    i = 0
    for r in _runs(p):
        if _wt(r) and TITIK.match(_teks_run(r)):
            _set_run(r, str(nilai[i]) if i < len(nilai) and nilai[i] is not None else "")
            i += 1


def _set_par(p, text: str) -> None:
    """Isi paragraf dengan satu teks (format run pertama dipertahankan; run lain dihapus kecuali tab)."""
    runs = [r for r in _runs(p) if _wt(r)]
    if not runs:
        r = p.makeelement(qn("w:r"), {})
        ppr = p.find(qn("w:pPr"))
        rpr = ppr.find(qn("w:rPr")) if ppr is not None else None
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        p.append(r)
        runs = [r]
    _set_run(runs[0], text)
    for r in runs[1:]:
        r.getparent().remove(r)


def _tambah_teks(p, text: str) -> None:
    """Tambahkan run teks di akhir paragraf, memakai format run terakhir."""
    rs = _runs(p)
    r = p.makeelement(qn("w:r"), {})
    if rs and rs[-1].find(qn("w:rPr")) is not None:
        r.append(copy.deepcopy(rs[-1].find(qn("w:rPr"))))
    t = r.makeelement(qn("w:t"), {})
    t.text = text
    t.set(XML_SPACE, "preserve")
    r.append(t)
    p.append(r)


def _par_teks(p) -> str:
    return "".join(t.text or "" for t in p.iter(qn("w:t")))


def _klon_setelah(p, acuan=None):
    c = copy.deepcopy(p)
    (acuan if acuan is not None else p).addnext(c)
    return c


def _paras(el):
    return el.findall(qn("w:p"))


def _atur_jumlah(paragrafs: list, n: int) -> list:
    """Pastikan jumlah paragraf = n: hapus kelebihan atau gandakan paragraf terakhir."""
    paragrafs = list(paragrafs)
    while len(paragrafs) > n:
        p = paragrafs.pop()
        p.getparent().remove(p)
    while len(paragrafs) < n:
        paragrafs.append(_klon_setelah(paragrafs[-1]))
    return paragrafs


def _kamus_angka_pertama(p, n: int) -> None:
    for r in _runs(p):
        tx = _teks_run(r)
        if _wt(r) and re.fullmatch(r"\d+\.?", tx.strip()):
            _set_run(r, str(n) + ("." if tx.strip().endswith(".") else ""))
            return


def _tabel_cells(tbl):
    return [[tc for tc in tr.findall(qn("w:tc"))] for tr in tbl.findall(qn("w:tr"))]


def _daftar(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(f"{i}. {x}" for i, x in enumerate(items[:-1], 1)) + f" dan {len(items)}. {items[-1]}"


def _kn(v) -> tuple[str, str]:
    a, _, b = str(v or "").partition("|")
    return a.strip(), b.strip()


def _rentang(isi) -> str:
    return tgl(isi["mulai"]) if isi["hari"] == 1 else f"{tgl(isi['mulai'])} s.d. {tgl(isi['selesai'])}"


# ---------- tata letak halaman: urutan elemen OOXML, ukuran font, penjaga satu-halaman ----------
ORD_RPR = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish",
           "webHidden", "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang",
           "eastAsianLayout", "specVanish", "oMath"]
ORD_PPR = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku",
           "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
           "suppressOverlap", "jc", "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"]
ORD_TRPR = ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter", "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden"]


def _urut(tag: str, order: list) -> int:
    n = tag.split("}")[1]
    return order.index(n) if n in order else len(order)


def _sisip(parent, anak, order: list) -> None:
    """Sisipkan `anak` pada posisi yang benar menurut urutan skema (Word menolak urutan yang salah)."""
    nama = anak.tag
    for lama in parent.findall(nama):
        parent.remove(lama)
    u = _urut(nama, order)
    for i, c in enumerate(list(parent)):
        if _urut(c.tag, order) > u:
            parent.insert(i, anak)
            return
    parent.append(anak)


def _w(tag: str, **attr):
    from docx.oxml import OxmlElement
    e = OxmlElement("w:" + tag)
    for k, v in attr.items():
        e.set(qn("w:" + k), str(v))
    return e


def _ppr(p):
    ppr = p.find(qn("w:pPr"))
    if ppr is None:
        ppr = _w("pPr")
        p.insert(0, ppr)
    return ppr


def _ukuran(el, pt: float, line: int | None = None, after: int | None = None) -> None:
    """Set ukuran font (pt) pada semua run & tanda paragraf di `el`; opsional atur jarak baris/after."""
    half = int(round(pt * 2))
    for r in el.iter(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is None:
            rpr = _w("rPr")
            r.insert(0, rpr)
        _sisip(rpr, _w("sz", val=half), ORD_RPR)
        _sisip(rpr, _w("szCs", val=half), ORD_RPR)
    for p in el.iter(qn("w:p")):
        ppr = _ppr(p)
        rpr = ppr.find(qn("w:rPr"))
        if rpr is None:
            rpr = _w("rPr")
            _sisip(ppr, rpr, ORD_PPR)
        _sisip(rpr, _w("sz", val=half), ORD_RPR)
        _sisip(rpr, _w("szCs", val=half), ORD_RPR)
        if line is not None or after is not None:
            sp = ppr.find(qn("w:spacing"))
            sp = sp if sp is not None else _w("spacing")
            if line is not None:
                sp.set(qn("w:line"), str(line))
                sp.set(qn("w:lineRule"), "auto")
            if after is not None:
                sp.set(qn("w:after"), str(after))
            _sisip(ppr, sp, ORD_PPR)


def _page_break_before(p) -> None:
    _sisip(_ppr(p), _w("pageBreakBefore"), ORD_PPR)


def _tak_terbelah(tbl) -> None:
    for tr in tbl.findall(qn("w:tr")):
        trpr = tr.find(qn("w:trPr"))
        if trpr is None:
            trpr = _w("trPr")
            ex = tr.find(qn("w:tblPrEx"))
            tr.insert(1 if ex is not None else 0, trpr)
        _sisip(trpr, _w("cantSplit"), ORD_TRPR)


def _isi_baris_nilai(tc, nilai: list) -> None:
    """Isi sel NILAI (1 paragraf) dengan beberapa baris (dipisah <w:br/>), selaras dengan label di sebelahnya."""
    p = tc.find(qn("w:p"))
    for r in list(p.findall(qn("w:r"))):
        p.remove(r)
    ppr = p.find(qn("w:pPr"))
    rpr0 = ppr.find(qn("w:rPr")) if ppr is not None else None
    for i, v in enumerate(nilai):
        r = p.makeelement(qn("w:r"), {})
        if rpr0 is not None:
            rp = copy.deepcopy(rpr0)
            r.append(rp)
        if i:
            r.append(r.makeelement(qn("w:br"), {}))
        t = r.makeelement(qn("w:t"), {})
        t.text = v
        t.set(XML_SPACE, "preserve")
        r.append(t)
        p.append(r)


# --- perkiraan tinggi (Arial ~ Helvetica) untuk memilih tingkat pemadatan; lihat uji kalibrasi ---
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402

KAPASITAS = 700.0          # pt tinggi isi halaman (A4, kop 2 baris, margin atas/bawah templat) dikurangi cadangan aman
LEBAR_TEKS_DASAR = 418.0   # lebar teks Dasar/Untuk setelah indent 1276 twips
LEBAR_NILAI_ST = 320.0     # lebar nilai pada blok "Kepada"
LEBAR_SPD_LABEL, LEBAR_SPD_NILAI = 205.0, 262.0


def _n_baris(teks: str, size: float, lebar: float) -> int:
    n, cur = 1, 0.0
    for w in str(teks or "").replace("\n", " ").split(" "):
        lw = stringWidth(w + " ", "Helvetica", size)
        if cur + lw > lebar and cur > 0:
            n, cur = n + 1, lw
        else:
            cur += lw
    return n


LEVEL = [(11.0, 1.15, True), (11.0, 1.15, False), (10.0, 1.0, False), (9.0, 1.0, False), (8.0, 1.0, False)]   # (ukuran, jarak, sisakan baris kosong antar petugas)


def _tinggi_st(petugas, dasar, maksud, dpa, tahun, rentang, level: int) -> float:
    size, spasi, sep = LEVEL[level]
    lh = size * 1.15 * spasi
    lh0 = 11 * 1.15 * 1.15
    h = 3 * lh0 + lh0 + lh0 + 10.6                      # judul, nomor, kosong, kosong, MEMERINTAHKAN, kosong kecil
    h += sum(_n_baris(d, size, LEBAR_TEKS_DASAR) for d in dasar) * lh
    for pg in petugas:
        h += (_n_baris(pg["nama"], size, LEBAR_NILAI_ST) + _n_baris(_pg(pg) or "-", size, LEBAR_NILAI_ST) + 1 + _n_baris(pg.get("jabatan") or "-", size, LEBAR_NILAI_ST)) * lh
        if sep:
            h += lh
    h += lh + 10.6                                       # kosong penutup blok + kosong kecil
    after = 6 if spasi > 1 else 3
    for t in (f"Dalam rangka {maksud}", f"Lama penugasan 1 (satu) hari, pada tanggal {rentang}", "Melaporkan hasil pelaksanaan tugas kepada yang mengeluarkan Surat Tugas.",
              f"Pembebanan biaya pada DPA {dpa} Tahun Anggaran {tahun}."):
        h += _n_baris(t, size, LEBAR_TEKS_DASAR) * lh + after
    return h + 175.0                                     # blok tanda tangan (tabel) ± 12 baris


def _tinggi_spd(diperintah, ikut, maksud, ang_baris, level: int) -> float:
    size = (11.0, 10.0, 9.0, 8.0)[level]
    lh = size * 1.15 * 1.15
    kol, kv = LEBAR_SPD_LABEL, LEBAR_SPD_NILAI
    h = 3 * (11 * 1.15 * 1.15) + 11 * 1.15 * 1.15 + 19.0          # Lembar/Kode/Nomor, kosong, judul
    def baris(t, w):
        return _n_baris(t, size, w)
    rows = [
        1,
        sum(baris(f"{p['nama']} / {p.get('nip') or '-'}", kv) for p in diperintah),
        baris("a. " + _daftar([(_pg(p) or "-") for p in diperintah]), kv) + baris("b. " + _daftar([(p.get("jabatan") or "-") for p in diperintah]) + " / UPT Puskesmas Melati", kv)
        + baris("c. " + _daftar([p.get("tingkat") or "-" for p in diperintah]), kv),
        baris(maksud, kv), 1, 2, 3, 1 + max(len(ikut), 1) * 1,
        sum(baris(b, kv) for b in ang_baris), 2, 1,
    ]
    h += sum(r * lh + 4 for r in rows)
    return h + 17.0 + 150.0                              # dua baris kecil + blok tanda tangan


def cek_muat(isi: dict, dasar_teks: str, maksud: str) -> dict:
    """Apakah ST + SPD muat satu halaman (dengan pemadatan maksimum)? Dipakai untuk memblokir ST yang tanda tangannya akan terpisah."""
    petugas = isi["petugas"]
    diperintah = [p for p in petugas if p.get("nip") and p.get("status") != "Non ASN"] or petugas
    ikut = [p for p in petugas if p not in diperintah]
    dasar = [x.strip() for x in str(dasar_teks or "").split("\n") if x.strip()] or [""]
    ang = isi.get("anggaran") or {}
    prog = [_kn(x) for x in str(ang.get("program") or "").split("\n") if x.strip()]
    ang_baris = [f"Program {k}  ({n})" for k, n in prog] + ["Kegiatan x (y)", "a. x", "b. y"]

    def st_ok(n):
        pt = (petugas * (n // max(len(petugas), 1) + 1))[:n] if n else petugas
        return _tinggi_st(pt, dasar, maksud, isi.get("dpa") or "", isi.get("tahun") or "", _rentang(isi), len(LEVEL) - 1) <= KAPASITAS
    h_st = _tinggi_st(petugas, dasar, maksud, isi.get("dpa") or "", isi.get("tahun") or "", _rentang(isi), len(LEVEL) - 1)
    h_spd = _tinggi_spd(diperintah, ikut, maksud, ang_baris, 3)
    maks = max([n for n in range(1, 40) if st_ok(n)] or [1])
    return {"ok": h_st <= KAPASITAS and h_spd <= KAPASITAS, "h_st": round(h_st), "h_spd": round(h_spd), "maks_petugas": maks}


def _pilih_level(fn, maks: int) -> tuple[int, float]:
    for lv in range(maks + 1):
        h = fn(lv)
        if h <= KAPASITAS:
            return lv, h
    return maks, fn(maks)


# ---------- header (kop) ----------
def _isi_header(doc: Document, isi: dict) -> None:
    k = isi["kop"]
    nilai = [k.get("jalan") or "", k.get("kodepos") or "", k.get("laman") or "", k.get("email") or ""]
    for sec in doc.sections:
        for h in (sec.header, sec.first_page_header, sec.even_page_header):
            try:
                el = h._element
            except Exception:
                continue
            i = 0
            for t in el.iter(qn("w:t")):
                tx = t.text or ""
                if tx.strip() == "NAMA PERANGKAT DAERAH":
                    t.text = k.get("baris2") or "DINAS KESEHATAN"
                    br = t.getparent().makeelement(qn("w:br"), {})
                    t.addnext(br)
                    t2 = t.getparent().makeelement(qn("w:t"), {})
                    t2.text = k.get("baris3") or "UPT PUSKESMAS MELATI"
                    br.addnext(t2)
                elif TITIK.match(tx):
                    t.text = nilai[i] if i < len(nilai) else ""
                    t.set(XML_SPACE, "preserve")
                    i += 1


# ---------- pengisi utama ----------
def isi_templat(isi: dict, st: dict) -> bytes:
    doc = Document(str(TEMPLAT))
    body = doc.element.body
    kids = list(body)
    assert _par_teks(kids[0]).strip() == "SURAT TUGAS" and kids[29].tag == qn("w:tbl"), "Templat Srikandi berubah; sesuaikan pengisi."
    petugas = isi["petugas"]
    diperintah = [p for p in petugas if p.get("nip") and p.get("status") != "Non ASN"] or petugas
    ikut = [p for p in petugas if p not in diperintah]
    pej_jab = re.sub(r"^Kepala\s+", "", isi["ttd"]["jabatan"], flags=re.I)

    # ---- ST: Dasar ----
    dasar = [x.strip() for x in str(st.get("dasar") or "").split("\n") if x.strip()] or [""]
    p_dasar1, p_dasar2, p_dasar3 = kids[3], kids[4], kids[5]
    basis = copy.deepcopy(p_dasar3)               # TAB, TAB 'n.', TAB '………'
    last = _runs(p_dasar1)[-1]
    _set_run(last, dasar[0])
    prev = p_dasar1
    for i, d in enumerate(dasar[1:], 2):
        c = copy.deepcopy(basis)
        _kamus_angka_pertama(c, i)
        _isi_titik(c, [d])
        prev.addnext(c)
        prev = c
    for p in (p_dasar2, p_dasar3):
        p.getparent().remove(p)

    # ---- ST: Kepada (blok petugas) ----
    blok = [[kids[9], kids[10], kids[11], kids[12]], [kids[14], kids[15], kids[16], kids[17]], [kids[19], kids[20], kids[21], kids[22]]]
    sumber = [[copy.deepcopy(p) for p in b] for b in blok]
    sep = copy.deepcopy(kids[13])
    anchor = kids[9].getprevious()
    for idx in list(range(9, 24)):
        kids[idx].getparent().remove(kids[idx])
    for n, pg in enumerate(petugas, 1):
        src = sumber[0] if n == 1 else (sumber[1] if n == 2 else sumber[2])
        ps = [copy.deepcopy(x) for x in src]
        _kamus_angka_pertama(ps[0], n)
        for p, v in zip(ps, [pg["nama"], _pg(pg), pg.get("nip") or "", pg.get("jabatan") or ""]):
            _isi_titik(p, [v])
        for p in ps:
            anchor.addnext(p)
            anchor = p
        s = copy.deepcopy(sep)
        anchor.addnext(s)
        anchor = s

    # ---- ST: pilih tingkat pemadatan agar tanda tangan tetap SATU halaman dengan isinya ----
    ringkas = {}
    lv_st, h_st = _pilih_level(lambda lv: _tinggi_st(petugas, dasar, st["maksud"], isi.get("dpa") or "", isi.get("tahun") or "", _rentang(isi), lv), len(LEVEL) - 1)
    ringkas["st"] = (lv_st, round(h_st))

    # ---- ST: Untuk ----
    for p in body.findall(qn("w:p")):
        t = _par_teks(p)
        if t.startswith("Untuk"):
            _isi_titik(p, [st["maksud"]])
        elif "Lama penugasan" in t:
            _isi_titik(p, [isi["hari"], _hari_teks(isi["hari"]).split("(")[1].split(")")[0].lower(), _rentang(isi)])
        elif "Pembebanan biaya pada DPA" in t:
            _isi_titik(p, [isi.get("dpa") or "", isi.get("tahun") or ""])
    kids = list(body)
    tabel_ttd_st = next(k for k in kids if k.tag == qn("w:tbl"))
    for p in tabel_ttd_st.iter(qn("w:p")):
        if _par_teks(p).strip().startswith("Kepala"):
            _isi_titik(p, [pej_jab])
    _tak_terbelah(tabel_ttd_st)

    # ---- terapkan pemadatan ST (hanya paragraf ST: dari 'SURAT TUGAS' sampai sebelum tabel tanda tangan) ----
    size, spasi, sep = LEVEL[lv_st]
    elemen = list(body)
    i_ttd = elemen.index(tabel_ttd_st)
    bagian = [e for e in elemen[:i_ttd] if e.tag == qn("w:p")]
    if not sep:                               # buang baris kosong antar petugas & penutup blok (paragraf kosong tanpa ukuran khusus)
        kosong = [e for e in bagian if not _par_teks(e).strip() and e.find(qn("w:pPr") + "/" + qn("w:rPr") + "/" + qn("w:sz")) is None]
        for e in kosong[1:]:                  # sisakan kosong pertama (jarak setelah nomor)
            e.getparent().remove(e)
        bagian = [e for e in bagian if e.getparent() is not None]
    if size < 11:
        for e in bagian:
            if _par_teks(e).strip() and not _par_teks(e).startswith(("SURAT TUGAS", "NOMOR")):
                _ukuran(e, size, line=240 if spasi == 1.0 else None, after=60 if _par_teks(e).startswith(("Untuk", "2.Lama", "3.Melaporkan", "4.Pembebanan")) else None)
    # baris kosong pengisi halaman diganti pemisah halaman eksplisit (SPD selalu mulai di halaman baru)
    elemen = list(body)
    ikut_ttd = elemen[elemen.index(tabel_ttd_st) + 1:]
    kosong_pengisi = []
    for e in ikut_ttd:
        if e.tag == qn("w:p") and not _par_teks(e).strip():
            kosong_pengisi.append(e)
        else:
            break
    for e in kosong_pengisi:
        e.getparent().remove(e)
    p_lembar = next(e for e in body.findall(qn("w:p")) if _par_teks(e).startswith("Lembar ke"))
    _page_break_before(p_lembar)

    # ---- SPD: nomor ----
    for p in body.findall(qn("w:p")):
        if _par_teks(p).replace("\t", "").strip() in ("Nomor:", "Nomor :", "Nomor"):
            _tambah_teks(p, " ${nomor_naskah}")
    tbls = [k for k in body if k.tag == qn("w:tbl")]
    spd, ttd_spd, balik = tbls[1], tbls[2], tbls[3]
    C = _tabel_cells(spd)
    # 1 Kepala ….
    _isi_titik(_paras(C[0][2])[0], [pej_jab])
    # 2 Nama / NIP
    ps = _atur_jumlah(_paras(C[1][2]), len(diperintah))
    for p, pg in zip(ps, diperintah):
        _isi_titik(p, [pg["nama"], pg.get("nip") or "-"])
    # 3 Pangkat / Jabatan / Tingkat
    a, b, c = _paras(C[2][2])[:3]
    _set_par(a, "a.  " + _daftar([(_pg(p) or "-") for p in diperintah]))
    _set_par(b, "b.  " + _daftar([(p.get("jabatan") or "-") for p in diperintah]) + " / " + isi["instansi"])
    _set_par(c, "c.  " + _daftar([p.get("tingkat") or "-" for p in diperintah]))
    # 4 maksud, 5 alat angkut, 6 tempat, 7 lama
    _set_par(_paras(C[3][2])[0], st["maksud"])
    _set_par(_paras(C[4][2])[0], isi.get("alat_angkutan") or "Angkutan darat")
    p6 = _paras(C[5][2])
    _set_par(p6[0], "a.  " + isi["tempat_berangkat"])
    _set_par(p6[1], "b.  " + isi["lokasi"])
    p7 = _paras(C[6][2])
    _isi_titik(p7[0], [isi["hari"], _hari_teks(isi["hari"]).split("(")[1].split(")")[0].lower()])
    _set_par(p7[1], "b.  " + tgl(isi["mulai"]))
    _set_par(p7[2], "c.  " + tgl(isi["selesai"]))
    # 8 pengikut
    n_ik = max(len(ikut), 1)
    c1, c2, c3 = _atur_jumlah(_paras(C[8][1]), n_ik), _atur_jumlah(_paras(C[8][2]), n_ik), _paras(C[8][3])
    c3 = _atur_jumlah(c3, n_ik)
    for i in range(n_ik):
        if ikut:
            _set_par(c1[i], f"{i + 1}. {ikut[i]['nama']}")
            _set_par(c2[i], "-")
            _set_par(c3[i], ikut[i].get("jabatan") or "")
        else:
            _set_par(c1[i], "-")
            _set_par(c2[i], "-")
            _set_par(c3[i], "")
    # 9 pembebanan anggaran
    ang = isi.get("anggaran") or {}
    ik, in_ = _kn(ang.get("instansi"))
    prog = [_kn(x) for x in str(ang.get("program") or "").split("\n") if x.strip()]
    gk, gn = _kn(ang.get("kegiatan"))
    rk, rn = _kn(ang.get("rekening") or isi.get("kode_rekening") or "")
    baris9 = [f"Program {k}  ({n})" for k, n in prog] + [f"Kegiatan  {gk}  ({gn})"]
    ps9 = _atur_jumlah(_paras(C[9][2]), len(baris9))
    for p, t in zip(ps9, baris9):
        _set_par(p, t)
    p10 = _paras(C[10][2])
    _set_par(p10[0], f"a.  {ik}  ({in_})")
    _set_par(p10[1], f"b.  {rk}  ({rn})")
    ang_baris = baris9 + [f"a.  {ik}  ({in_})", f"b.  {rk}  ({rn})"]
    lv_spd, h_spd = _pilih_level(lambda lv: _tinggi_spd(diperintah, ikut, st["maksud"], ang_baris, lv), 3)
    ringkas["spd"] = (lv_spd, round(h_spd))
    if lv_spd > 0:
        _ukuran(spd, (11.0, 10.0, 9.0, 8.0)[lv_spd], line=240, after=0)
    _tak_terbelah(ttd_spd)
    # tanda tangan SPD: Dikeluarkan di
    for p in ttd_spd.iter(qn("w:p")):
        if _par_teks(p).startswith("Dikeluarkan di"):
            _isi_titik(p, [isi["kota"]])
    # ---- lembar belakang ----
    B = _tabel_cells(balik)
    asal, tuj = isi["tempat_berangkat"], isi["lokasi"]

    def kolon(tc, nilai):
        for p, v in zip(_paras(tc), nilai):
            if v is not None:
                _set_par(p, ": " + v if v else ":")
    # Nilai diisi ke SEL NILAI (bukan sel titik dua); baris dipisah <w:br/> agar selaras dengan label
    _isi_baris_nilai(B[0][7], [asal, "", tuj, tgl(isi["mulai"])])
    _isi_baris_nilai(B[2][3], [tuj, tgl(isi["mulai"])])
    _isi_baris_nilai(B[2][7], [tuj, asal, tgl(isi["selesai"])])
    _isi_baris_nilai(B[6][3], [asal, tgl(isi["selesai"])])
    # halaman belakang selalu mulai di halaman baru: baris kosong pengisi diganti satu paragraf kecil bertanda pemisah halaman
    sebelum_balik = []
    e = balik.getprevious()
    while e is not None and e.tag == qn("w:p") and not _par_teks(e).strip():
        sebelum_balik.append(e)
        e = e.getprevious()
    for e2 in sebelum_balik[1:]:
        e2.getparent().remove(e2)
    if sebelum_balik:
        _page_break_before(sebelum_balik[0])
    # nilai panjang di kolom sempit lembar belakang: kecilkan font agar tinggi baris tidak membengkak
    if max((len(x) for x in (asal, tuj)), default=0) > 18:
        _ukuran(balik, 9.0 if max(len(asal), len(tuj)) <= 34 else 8.0)
    doc._sikadin_ringkas = ringkas

    _isi_header(doc, isi)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue(), ringkas
