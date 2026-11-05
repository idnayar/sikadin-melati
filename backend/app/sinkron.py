"""Sinkronisasi Surat Tugas/SPD <-> realisasi belanja (SPJ).
ST yang terbit otomatis melahirkan satu SPJ (Draft) per petugas; pembatalan ST ikut membersihkan SPJ yang belum diajukan
dan DITOLAK bila ada SPJ yang sudah diajukan/dibayar (harus dikembalikan/dikoreksi lebih dulu)."""
import json

from .core import Gagal, audit


def buat_spj_dari_spd(db, user, spd_id: int):
    """Idempoten: mengembalikan id SPJ (baru atau yang sudah ada); None bila ST sudah dibatalkan."""
    d = db.execute("""SELECT d.*, st.status st_status, st.sumber_dana_id, j.tahun, st.nomor, j.baris_id, j.mulai, j.selesai, j.kegiatan, p.nama pegawai, sd.kode dana
        FROM spd d JOIN surat_tugas st ON st.id=d.st_id JOIN jadwal j ON j.id=st.jadwal_id JOIN pegawai p ON p.id=d.pegawai_id JOIN sumber_dana sd ON sd.id=st.sumber_dana_id
        WHERE d.id=?""", (spd_id,)).fetchone()
    if not d or d["st_status"] != "Terbit":
        return None
    ada = db.execute("SELECT id FROM spj WHERE spd_id=?", (spd_id,)).fetchone()
    if ada:
        return ada["id"]
    biaya = json.loads(d["biaya_json"])
    rinci = [{"uraian": b["uraian"], "volume": b["volume"], "satuan": b["satuan"], "tarif": b["tarif"], "rencana": int(b["jumlah"]), "jumlah": int(b["jumlah"]), "bukti": ""} for b in biaya["baris"]]
    tot = sum(x["jumlah"] for x in rinci)
    sid = db.execute("""INSERT INTO spj(jenis,tahun,sumber_dana_id,baris_id,spd_id,st_id,pegawai_id,tanggal,mulai,selesai,uraian,penerima,rincian_json,total_rencana,total,dibuat_oleh)
        VALUES('SPD',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (d["tahun"], d["sumber_dana_id"], d["baris_id"], spd_id, d["st_id"], d["pegawai_id"], d["selesai"], d["mulai"], d["selesai"],
                      f"Perjalanan dinas: {d['kegiatan']}", d["pegawai"], json.dumps(rinci, ensure_ascii=False), tot, tot, user["username"])).lastrowid
    audit(db, user, "spj", sid, "BUAT", None, {"jenis": "SPD", "spd_id": spd_id, "total": tot, "otomatis": True}, d["dana"])
    return sid


def tutup_spj_st(db, user, st_id: int, dana: str) -> int:
    """Dipanggil saat ST dibatalkan. Menolak bila ada SPJ yang sudah berjalan; selain itu menghapus SPJ Draft/Dikembalikan."""
    rows = db.execute("SELECT id, status, pegawai_id FROM spj WHERE st_id=?", (st_id,)).fetchall()
    jalan = [r for r in rows if r["status"] not in ("Draft", "Dikembalikan")]
    if jalan:
        raise Gagal(f"ST tidak dapat dibatalkan: {len(jalan)} SPJ sudah diajukan/dibayar (status {', '.join(sorted({r['status'] for r in jalan}))}). "
                    "Kembalikan SPJ yang diajukan atau koreksi pembayarannya (Kepala) terlebih dahulu.")
    for r in rows:
        db.execute("DELETE FROM spj WHERE id=?", (r["id"],))
        audit(db, user, "spj", r["id"], "HAPUS", {"alasan": "ST dibatalkan"}, None, dana)
    return len(rows)
