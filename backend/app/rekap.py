"""Rekap perjalanan dinas: per nama, tempat, waktu, tujuan, dan biaya — setahun dan per bulan.
Sumber: SPD pada Surat Tugas berstatus Terbit (rencana biaya = tarif SPD) + SPJ berstatus Dibayar (realisasi).
Hak akses mengikuti Surat Tugas: pengelola sumber dana melihat semua sumber yang berhak (BLUD hanya Kepala/Bendahara BLUD); pegawai hanya miliknya."""
import datetime as dt
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from . import dokumen as dk
from .core import Gagal, akses_sumber, auth, get_db
from .surat import DOCX, _pdf_ke_docx

router = APIRouter(prefix="/api/rekap-dinas")


def _data(db, user, tahun, bulan=0, sumber="", pegawai_id=0, lokasi_id=0, q=""):
    sumber = sumber.upper()
    rows = db.execute("""SELECT st.id st_id, st.nomor, st.nomor_srikandi, st.maksud tujuan, sd.kode dana, d.id spd_id, d.pegawai_id, p.nama, p.nip, p.ruangan,
        l.id lokasi_id, l.nama tempat, j.mulai, j.selesai, d.total rencana, x.status spj_status, CASE WHEN x.status='Dibayar' THEN x.total ELSE 0 END realisasi, x.no_bukti
        FROM spd d JOIN surat_tugas st ON st.id=d.st_id AND st.status='Terbit' JOIN jadwal j ON j.id=st.jadwal_id JOIN lokasi l ON l.id=j.lokasi_id
        JOIN pegawai p ON p.id=d.pegawai_id JOIN sumber_dana sd ON sd.id=st.sumber_dana_id LEFT JOIN spj x ON x.spd_id=d.id
        WHERE substr(j.mulai,1,4)=? ORDER BY j.mulai, st.id, p.nama""", (str(tahun),)).fetchall()
    out = []
    for r in rows:
        penuh = user["role"] != "pegawai" and akses_sumber(user, r["dana"], "baca")
        if not penuh and r["pegawai_id"] != user.get("pegawai_id"):
            continue
        r["bulan"] = int(r["mulai"][5:7])
        r["hari"] = (dt.date.fromisoformat(r["selesai"]) - dt.date.fromisoformat(r["mulai"])).days + 1
        if (bulan and r["bulan"] != bulan) or (sumber and r["dana"] != sumber) or (pegawai_id and r["pegawai_id"] != pegawai_id) or (lokasi_id and r["lokasi_id"] != lokasi_id):
            continue
        if q and q.lower() not in f"{r['tujuan']} {r['tempat']} {r['nama']}".lower():
            continue
        out.append(r)
    return out


def _agg(rows):
    bulanan = [{"bulan": i, "st": set(), "perjalanan": 0, "hari": 0, "rencana": 0, "realisasi": 0} for i in range(1, 13)]
    peg: dict = {}
    tmp: dict = {}
    for r in rows:
        b = bulanan[r["bulan"] - 1]
        b["st"].add(r["st_id"]); b["perjalanan"] += 1; b["hari"] += r["hari"]; b["rencana"] += r["rencana"]; b["realisasi"] += r["realisasi"]
        p = peg.setdefault(r["pegawai_id"], {"pegawai_id": r["pegawai_id"], "nama": r["nama"], "nip": r["nip"], "ruangan": r["ruangan"], "perjalanan": 0, "hari": 0, "rencana": 0, "realisasi": 0,
                                             "bln_jml": [0] * 12, "bln_biaya": [0] * 12})
        p["perjalanan"] += 1; p["hari"] += r["hari"]; p["rencana"] += r["rencana"]; p["realisasi"] += r["realisasi"]
        p["bln_jml"][r["bulan"] - 1] += 1; p["bln_biaya"][r["bulan"] - 1] += r["rencana"]
        t = tmp.setdefault(r["lokasi_id"], {"lokasi_id": r["lokasi_id"], "tempat": r["tempat"], "perjalanan": 0, "hari": 0, "rencana": 0, "realisasi": 0})
        t["perjalanan"] += 1; t["hari"] += r["hari"]; t["rencana"] += r["rencana"]; t["realisasi"] += r["realisasi"]
    for b in bulanan:
        b["st"] = len(b["st"])
    tot = {"st": len({r["st_id"] for r in rows}), "perjalanan": len(rows), "hari": sum(r["hari"] for r in rows), "rencana": sum(r["rencana"] for r in rows), "realisasi": sum(r["realisasi"] for r in rows)}
    return {"bulanan": bulanan, "per_pegawai": sorted(peg.values(), key=lambda x: x["nama"]), "per_tempat": sorted(tmp.values(), key=lambda x: -x["perjalanan"]), "total": tot}


def _param(tahun, bulan):
    if not 2000 < tahun < 2100 or not 0 <= bulan <= 12:
        raise Gagal("Tahun/bulan tidak valid.")


@router.get("")
def rekap(tahun: int, bulan: int = 0, sumber: str = "", pegawai_id: int = 0, lokasi_id: int = 0, q: str = "", user=Depends(auth), db=Depends(get_db)):
    _param(tahun, bulan)
    rows = _data(db, user, tahun, bulan, sumber, pegawai_id, lokasi_id, q)
    pilihan = {"pegawai": sorted({(r["pegawai_id"], r["nama"]) for r in _data(db, user, tahun)}, key=lambda x: x[1]),
               "tempat": sorted({(r["lokasi_id"], r["tempat"]) for r in _data(db, user, tahun)}, key=lambda x: x[1])}
    return {"rows": rows, **_agg(rows), "pilihan": {"pegawai": [{"id": a, "nama": b} for a, b in pilihan["pegawai"]], "tempat": [{"id": a, "nama": b} for a, b in pilihan["tempat"]]}}


@router.get("/dok")
def dokumen(tahun: int, bulan: int = 0, sumber: str = "", pegawai_id: int = 0, lokasi_id: int = 0, q: str = "", format: str = "pdf", user=Depends(auth), db=Depends(get_db)):
    _param(tahun, bulan)
    rows = _data(db, user, tahun, bulan, sumber, pegawai_id, lokasi_id, q)
    a = _agg(rows)
    BL = dk.BULAN
    periode = f"{BL[bulan - 1]} {tahun}" if bulan else f"Tahun {tahun}"
    nama = f"Rekap_Perjalanan_Dinas_{tahun}" + (f"_{bulan:02d}" if bulan else "")
    if format == "xlsx":
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook(); wb.remove(wb.active)

        def sheet(judul, kepala, isi, lebar):
            ws = wb.create_sheet(judul)
            ws.append([f"REKAP PERJALANAN DINAS — {periode}"]); ws["A1"].font = Font(bold=True, size=13); ws.append([])
            ws.append(kepala)
            for c in ws[3]:
                c.font = Font(bold=True)
            for r in isi:
                ws.append(r)
            for i, w in enumerate(lebar):
                ws.column_dimensions[chr(65 + i)].width = w
            for row in ws.iter_rows(min_row=4):
                for c in row:
                    if isinstance(c.value, int) and c.column > 1 and kepala[c.column - 1] in ("Biaya SPD (Rp)", "Realisasi (Rp)") or (isinstance(c.value, int) and "Rp" in str(kepala[c.column - 1])):
                        c.number_format = "#,##0"
        sheet("Rincian", ["No", "Nama", "NIP", "Tempat", "Mulai", "Selesai", "Hari", "Tujuan", "No. ST", "Dana", "Biaya SPD (Rp)", "Realisasi (Rp)", "Status SPJ"],
              [[i, r["nama"], r["nip"], r["tempat"], r["mulai"], r["selesai"], r["hari"], r["tujuan"], r["nomor_srikandi"] or r["nomor"], r["dana"], r["rencana"], r["realisasi"], r["spj_status"] or "-"] for i, r in enumerate(rows, 1)],
              [5, 30, 20, 22, 12, 12, 6, 50, 38, 8, 16, 16, 14])
        sheet("Bulanan", ["Bulan", "Jumlah ST", "Perjalanan (orang)", "Hari (orang)", "Biaya SPD (Rp)", "Realisasi (Rp)"],
              [[BL[b["bulan"] - 1], b["st"], b["perjalanan"], b["hari"], b["rencana"], b["realisasi"]] for b in a["bulanan"]] + [["JUMLAH", a["total"]["st"], a["total"]["perjalanan"], a["total"]["hari"], a["total"]["rencana"], a["total"]["realisasi"]]],
              [14, 12, 18, 14, 18, 18])
        sheet("Per Pegawai", ["Nama", "Ruangan"] + [x[:3] for x in BL] + ["Perjalanan", "Hari", "Biaya SPD (Rp)", "Realisasi (Rp)"],
              [[p["nama"], p["ruangan"] or ""] + p["bln_jml"] + [p["perjalanan"], p["hari"], p["rencana"], p["realisasi"]] for p in a["per_pegawai"]], [30, 18] + [5] * 12 + [12, 8, 16, 16])
        sheet("Per Tempat", ["Tempat", "Perjalanan (orang)", "Hari (orang)", "Biaya SPD (Rp)", "Realisasi (Rp)"],
              [[t["tempat"], t["perjalanan"], t["hari"], t["rencana"], t["realisasi"]] for t in a["per_tempat"]], [30, 18, 14, 18, 18])
        buf = io.BytesIO(); wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{nama}.xlsx"', "Cache-Control": "no-store"})
    P, esc, rp = dk.P, dk.esc, dk.rp
    kop = {k: (db.execute("SELECT nilai FROM pengaturan WHERE kunci=?", (f"kop_{k}",)).fetchone() or {}).get("nilai", "") for k in ("baris1", "baris2", "baris3", "alamat", "jalan", "kodepos", "laman", "email")}
    story = dk.kop(kop) + [P("<b>REKAP PERJALANAN DINAS</b>", "judul"), P(f"Periode : {periode}", "c"), dk.Spacer(1, 6), P("<b>A. Ringkasan per bulan</b>", "n")]
    d1 = [["Bulan", "ST", "Orang", "Hari", "Biaya SPD", "Realisasi"]] + [[BL[b["bulan"] - 1], str(b["st"]), str(b["perjalanan"]), str(b["hari"]), P(rp(b["rencana"]), "r"), P(rp(b["realisasi"]), "r")] for b in a["bulanan"] if (not bulan or b["bulan"] == bulan)]
    d1.append([P("<b>Jumlah</b>", "n"), str(a["total"]["st"]), str(a["total"]["perjalanan"]), str(a["total"]["hari"]), P(f"<b>{rp(a['total']['rencana'])}</b>", "r"), P(f"<b>{rp(a['total']['realisasi'])}</b>", "r")])
    story += [dk._tabel(d1, [3.0 * dk.cm, 1.4 * dk.cm, 1.8 * dk.cm, 1.6 * dk.cm, 4.3 * dk.cm, 4.3 * dk.cm]), dk.Spacer(1, 8), P("<b>B. Rincian perjalanan</b>", "n")]
    d2 = [["No", "Nama", "Tempat", "Tanggal", "Tujuan", "Biaya SPD", "Realisasi"]]
    for i, r in enumerate(rows, 1):
        tg = dk.tgl(r["mulai"]) if r["selesai"] == r["mulai"] else f"{dk.tgl(r['mulai'])} s.d. {dk.tgl(r['selesai'])}"
        d2.append([str(i), P(esc(r["nama"]), "kecil"), P(esc(r["tempat"]), "kecil"), P(tg, "kecil"), P(esc(r["tujuan"]), "kecil"), P(rp(r["rencana"]), "r"), P(rp(r["realisasi"]), "r")])
    if len(d2) == 1:
        d2.append(["", P("(tidak ada perjalanan dinas pada periode ini)", "kecil"), "", "", "", "", ""])
    story += [dk._tabel(d2, [0.7 * dk.cm, 2.9 * dk.cm, 2.0 * dk.cm, 2.5 * dk.cm, 3.0 * dk.cm, 2.65 * dk.cm, 2.65 * dk.cm]), dk.Spacer(1, 8), P("<b>C. Rekap per pegawai</b>", "n")]
    d3 = [["Nama", "Perj.", "Hari", "Biaya SPD", "Realisasi"]] + [[P(esc(p["nama"]), "kecil"), str(p["perjalanan"]), str(p["hari"]), P(rp(p["rencana"]), "r"), P(rp(p["realisasi"]), "r")] for p in a["per_pegawai"]]
    story += [dk._tabel(d3, [6.6 * dk.cm, 1.4 * dk.cm, 1.4 * dk.cm, 3.5 * dk.cm, 3.5 * dk.cm]), dk.Spacer(1, 8), P("<b>D. Rekap per tempat tujuan</b>", "n")]
    d4 = [["Tempat", "Perj.", "Hari", "Biaya SPD", "Realisasi"]] + [[P(esc(t["tempat"]), "kecil"), str(t["perjalanan"]), str(t["hari"]), P(rp(t["rencana"]), "r"), P(rp(t["realisasi"]), "r")] for t in a["per_tempat"]]
    story += [dk._tabel(d4, [6.6 * dk.cm, 1.4 * dk.cm, 1.4 * dk.cm, 3.5 * dk.cm, 3.5 * dk.cm]), dk.Spacer(1, 4), P("<font size=8>Biaya SPD = tarif Perbup pada SPD; Realisasi = SPJ yang telah dibayar. Perjalanan dihitung per orang.</font>", "n")]
    pdf = dk.build_pdf(story, f"Rekap Perjalanan Dinas {periode}")
    if format == "docx":
        return Response(_pdf_ke_docx(pdf), media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{nama}.docx"', "Cache-Control": "no-store"})
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nama}.pdf"', "Cache-Control": "no-store"})
