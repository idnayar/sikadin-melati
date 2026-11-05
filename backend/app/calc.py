"""Penghitung estimasi biaya perjalanan dinas dari tarif Perbup (data master, bukan hard-code)."""
import datetime as dt
import math

from .core import Gagal


def _num(v, d=0):
    if v is None or v == "":
        return d
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _cari(db, tahun, kategori, tujuan, tingkat=""):
    # Tarif terbaru yang sudah berlaku pada tahun tsb (Perbup berlaku sampai diganti Perbup baru).
    return db.execute("SELECT * FROM tarif WHERE tahun_berlaku<=? AND kategori=? AND tujuan=? AND tingkat=? ORDER BY tahun_berlaku DESC LIMIT 1",
                      (tahun, kategori, tujuan, tingkat)).fetchone()


def _setting(db, k, d):
    r = db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (k,)).fetchone()
    try:
        return float(r["nilai"]) if r else d
    except (TypeError, ValueError):
        return d


def hitung(db, inp: dict) -> dict:
    """inp: pegawai_id | tingkat, lokasi_id, tahun, durasi 'gt8'|'le8', hari, roda 2|4, menginap 'hotel'|'tidak_hotel'|'tidak',
    pp, inap_riil, transport_manual, diklat. Saat perencanaan petugas belum ditentukan: pakai `tingkat`."""
    if inp.get("pegawai_id"):
        peg = db.execute("SELECT * FROM pegawai WHERE id=?", (inp["pegawai_id"],)).fetchone()
    else:
        t = inp.get("tingkat") or "D"
        peg = {"nama": f"Petugas Tingkat {t}", "tingkat": t}
    lok = db.execute("SELECT * FROM lokasi WHERE id=?", (inp.get("lokasi_id"),)).fetchone()
    if not peg:
        raise Gagal("Pegawai tidak ditemukan")
    if not lok:
        raise Gagal("Lokasi tidak ditemukan")
    tahun = int(_num(inp.get("tahun"), _setting(db, "tahun_anggaran", dt.date.today().year)))
    hari = max(1, int(_num(inp.get("hari"), 1)))
    malam = max(0, hari - 1)
    pp = inp.get("pp") not in (False, 0, "0")
    roda = 4 if int(_num(inp.get("roda"), 2)) == 4 else 2
    tingkat = peg["tingkat"]
    key = lok["kunci_tarif"] or lok["nama"]
    baris, peringatan = [], []

    def add(kode, uraian, volume, satuan, tarif):
        baris.append({"kode": kode, "uraian": uraian, "volume": volume, "satuan": satuan, "tarif": tarif, "jumlah": volume * tarif})

    dalam_kota = lok["jenis"] in ("DK_WILAYAH", "DK_ANTAR")
    batas = int(_setting(db, "batas_jam_dalam_kota", 8))

    # ---- Uang harian ----
    if dalam_kota:
        if inp.get("durasi") == "le8":
            peringatan.append(f"Durasi ≤ {batas} jam: tidak mendapat uang harian, hanya uang transport lokal (Pasal 6 ayat 3).")
        else:
            diklat = bool(inp.get("diklat"))
            t = _cari(db, tahun, "UH_DIKLAT_DK" if diklat else "UH_DK", "Kab. Kapuas")
            if t:
                add("UH", "Uang harian diklat dalam kota > 8 jam" if diklat else "Uang harian dalam kota > 8 jam", hari, "OH", t["nilai"])
            else:
                peringatan.append("Tarif uang harian dalam kota belum ada di master.")
    elif lok["jenis"] == "LK_KALTENG":
        t = _cari(db, tahun, "UH_LK_KALTENG", "Kalimantan Tengah")
        if t:
            add("UH", "Uang harian luar kota dalam Provinsi Kalteng", hari, "OH", t["nilai"])
        else:
            peringatan.append("Tarif uang harian luar kota Kalteng belum ada di master.")
    else:
        prov = lok["provinsi"] or key
        t = _cari(db, tahun, "UH_LUAR_PROV", prov)
        if t:
            add("UH", f"Uang harian luar provinsi ({prov})", hari, "OH", t["nilai"])
        else:
            peringatan.append(f'Tarif uang harian provinsi "{prov}" belum ada — impor tabel Lampiran I.')

    # ---- Transport ----
    if lok["jenis"] == "DK_ANTAR":
        t = _cari(db, tahun, "TR_DK", key)
        v = t and (t["nilai2"] if roda == 4 else t["nilai"])
        if v:
            add("TR", f"Transport ke {lok['nama']} (Roda {roda})", 2 if pp else 1, "kali", v)
        else:
            peringatan.append(f"Tarif transport Roda {roda} ke {lok['nama']} tidak tersedia.")
    elif lok["jenis"] == "LK_KALTENG":
        t = _cari(db, tahun, "TR_DARAT_LK", key)
        if t:
            add("TR", f"Transport darat ke {lok['nama']}{' (pulang-pergi)' if pp else ''}", 2 if pp else 1, "kali", t["nilai"])
        else:
            peringatan.append(f"Tarif transport darat ke {lok['nama']} belum ada.")
    elif lok["jenis"] == "LK_LUAR_PROV":
        peringatan.append("Tiket pesawat/taksi luar provinsi: isi sesuai bukti riil (Lampiran I VII & VIII).")
    if _num(inp.get("transport_manual")) > 0:
        add("TR", "Transport lokal/riil sesuai bukti", 1, "paket", int(_num(inp["transport_manual"])))

    # ---- Penginapan ----
    menginap = inp.get("menginap")
    if malam > 0 and menginap and menginap != "tidak":
        if lok["jenis"] == "DK_ANTAR":
            ti = _cari(db, tahun, "INAP_DK", key)
        elif lok["jenis"] == "DK_WILAYAH":
            ti = _cari(db, tahun, "INAP_DK", "Kec. Selat")
        elif lok["jenis"] == "LK_KALTENG":
            ti = _cari(db, tahun, "INAP_KALTENG", "Palangka Raya" if key == "Palangka Raya" else "Kabupaten lain", tingkat)
        else:
            ti = _cari(db, tahun, "INAP_LUAR_PROV", lok["provinsi"] or key, tingkat)
        if not ti:
            peringatan.append("Tarif penginapan tujuan ini belum ada di master.")
        elif menginap == "hotel":
            riil = _num(inp["inap_riil"]) if inp.get("inap_riil") not in (None, "") else ti["nilai"]
            add("INAP", "Penginapan (biaya riil, maks. tarif)", malam, "malam", int(min(riil, ti["nilai"])))
            if riil > ti["nilai"]:
                peringatan.append("Biaya hotel riil melebihi tarif — dibatasi sesuai tarif.")
        else:
            p = _setting(db, "lumpsum_inap_persen", 30)
            add("INAP", f"Penginapan lumpsum {int(p)}% (tidak menginap di hotel)", malam, "malam", math.floor(ti["nilai"] * p / 100))

    total = sum(b["jumlah"] for b in baris)
    return {"pegawai": peg["nama"], "tingkat": tingkat, "lokasi": lok["nama"], "tahun": tahun, "baris": baris, "total": total, "peringatan": peringatan}
