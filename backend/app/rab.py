"""Parser berkas "RAB BOK Puskesmas" (format Kemenkes: Menu → Rincian Menu → Komponen → baris biaya)."""
import io
import re

from openpyxl import load_workbook


def _txt(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v if v is not None else "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s) if s != "" else None
    except ValueError:
        return None


def _rp(n) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


def parse_rab(data: bytes) -> dict:
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = [list(r) for r in ws.iter_rows(min_row=1, min_col=1, values_only=True)]
    # Tabel di berkas bisa mulai dari kolom B: geser agar kolom "MENU" selalu di indeks 1.
    off = 0
    for r in rows[:12]:
        idx = next((j for j, v in enumerate(r) if _txt(v).upper() == "MENU"), None)
        if idx is not None:
            off = max(0, idx - 1)
            break
    rows = [r[off:] + [None] * (24 - len(r[off:])) for r in rows]
    judul = _txt(rows[0][0]) if rows else ""
    m = re.search(r"TA\s*(\d{4})", judul, re.I)
    tahun = int(m.group(1)) if m else None
    pagu = None
    menus, peringatan = [], []
    menu = rinc = komp = None

    for i, r in enumerate(rows):
        if re.search(r"jumlah total kebutuhan", _txt(r[0]), re.I):
            pagu = _num(r[17])
        if re.match(r"total pagu", _txt(r[1]), re.I):
            break
        if i < 7 or all(v is None or v == "" for v in r):
            continue
        # Baris subtotal menu (hanya angka di kolom total) → abaikan, dihitung ulang
        if all(v is None or v == "" for v in r[:16]) and _num(r[17]) is not None:
            continue
        if _txt(r[0]) != "" and _txt(r[1]) != "":
            menu = {"no": _txt(r[0]), "nama": _txt(r[1]), "rincian": []}
            menus.append(menu)
            rinc = komp = None
        if menu is None:
            continue
        if _txt(r[2]) != "" or (_txt(r[3]) != "" and rinc is None):
            rinc = {"no": _txt(r[2]), "nama": _txt(r[3]), "baris": []}
            menu["rincian"].append(rinc)
            komp = None
        if rinc is None:
            continue
        if _txt(r[4]) != "":
            komp = _txt(r[4])
        jenis, sub = _txt(r[6]), _num(r[16])
        pembulatan = bool(re.search("pembulatan", jenis, re.I)) or (bool(re.search("pembulatan", _txt(r[4]), re.I)) and jenis == "")
        if jenis == "" and not pembulatan:
            continue
        v1, v2, v3, uc = _num(r[9]), _num(r[11]), _num(r[13]), _num(r[15])
        b = {
            "komponen": None if pembulatan else (_txt(r[4]) or komp),
            "jenis_belanja": "Pembulatan" if pembulatan else jenis,
            "uraian": _txt(r[7]) or None, "satuan": _txt(r[8]) or None,
            "vol1": 1 if v1 is None else v1, "sat1": _txt(r[10]) or None,
            "vol2": 1 if v2 is None else v2, "sat2": _txt(r[12]) or None,
            "vol3": 1 if v3 is None else v3, "sat3": _txt(r[14]) or None,
            "unit_cost": int(round((sub or 0) if pembulatan else (uc or 0))),
            "jumlah": int(round(sub or 0)),
        }
        if pembulatan:
            b.update(vol1=1, vol2=1, vol3=1, sat1=None, sat2=None, sat3=None)
        hitung = b["vol1"] * b["vol2"] * b["vol3"] * b["unit_cost"]
        if round(hitung) != round(b["jumlah"]):
            peringatan.append(f"Baris {i + 1} ({b['komponen'] or rinc['nama']}): jumlah di file {_rp(b['jumlah'])} ≠ volume×tarif {_rp(hitung)}; nilai file dipakai.")
        rinc["baris"].append(b)

    total = sum(b["jumlah"] for m_ in menus for x in m_["rincian"] for b in x["baris"])
    if pagu is not None and round(pagu) != total:
        peringatan.append(f"Total baris {_rp(total)} ≠ total di file {_rp(pagu)}.")
    return {"judul": judul, "tahun": tahun, "pagu": None if pagu is None else int(round(pagu)), "menus": menus, "total": total, "peringatan": peringatan}
