// Perencanaan (RPK/POA) — estimasi biaya dari tarif Perbup, kontrol pagu real-time, alur status.
const { db } = require('./db');
const { hitung } = require('./calc');

const int = (v, label, min = 1, def) => {
  if ((v === undefined || v === null || v === '') && def !== undefined) return def;
  const x = Number(v); if (!Number.isInteger(x) || x < min) throw new Error(`${label} harus bilangan bulat ≥ ${min}.`); return x;
};
const rpt = n => 'Rp' + Number(n).toLocaleString('id-ID');
const bokId = () => db.prepare("SELECT id FROM sumber_dana WHERE kode='BOK'").get()?.id;
const pengaturan = (k, d) => { const r = db.prepare('SELECT nilai FROM pengaturan WHERE kunci=?').get(k); return r ? Number(r.nilai) : d; };

function infoBaris(id) {
  return db.prepare(`SELECT b.*, r.nama rincian, r.no rincian_no, r.id rincian_id, m.nama menu, m.no menu_no, m.tahun
    FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id WHERE b.id=?`).get(id);
}
const terpakaiBaris = (id, excl) => db.prepare("SELECT COALESCE(SUM(estimasi),0) s FROM rencana WHERE baris_id=? AND status!='Ditolak' AND id!=?").get(id, excl || 0).s;

/** Hitung estimasi + cek pagu. Dipakai oleh preview, simpan, dan perubahan status. */
function analisis(b, excl = 0) {
  const baris = infoBaris(int(b.baris_id, 'Pos anggaran (baris RAB)'));
  if (!baris) throw new Error('Pos anggaran (baris RAB) tidak ditemukan.');
  const tahun = baris.tahun;
  const d = {
    tahun, bulan: int(b.bulan, 'Bulan'), baris_id: baris.id, kegiatan: String(b.kegiatan || '').trim(),
    kode_rekening: String(b.kode_rekening || baris.kode_rekening || '').trim() || null,
    lokasi_id: b.lokasi_id ? int(b.lokasi_id, 'Lokasi') : null, durasi: b.durasi === 'le8' ? 'le8' : 'gt8',
    jumlah_petugas: int(b.jumlah_petugas, 'Jumlah petugas', 1, 1), jumlah_hari: int(b.jumlah_hari, 'Jumlah hari', 1, 1),
    frekuensi: int(b.frekuensi, 'Frekuensi pelaksanaan', 1, 1), tingkat: b.tingkat === 'C' ? 'C' : 'D',
    roda: Number(b.roda) === 4 ? 4 : 2, menginap: ['hotel', 'tidak_hotel'].includes(b.menginap) ? b.menginap : 'tidak',
    pp: b.pp === false || b.pp === 0 || b.pp === '0' ? 0 : 1, transport_manual: int(b.transport_manual, 'Transport manual', 0, 0),
    estimasi_manual: int(b.estimasi_manual, 'Estimasi manual', 0, 0), catatan: String(b.catatan || '').trim() || null,
  };
  if (d.bulan > 12) throw new Error('Bulan harus 1–12.');
  if (!d.kegiatan) d.kegiatan = baris.komponen || baris.rincian;
  const perjalanan = /perjalanan dinas/i.test(baris.jenis_belanja);
  const peringatan = [], galatDasar = []; let rincian = null, estimasi = 0;
  if (perjalanan) {
    if (!d.lokasi_id) throw new Error('Lokasi tujuan wajib diisi untuk perjalanan dinas.');
    const lok = db.prepare('SELECT * FROM lokasi WHERE id=?').get(d.lokasi_id); if (!lok) throw new Error('Lokasi tidak ditemukan.');
    d.jenis_perjalanan = lok.jenis;
    const h = hitung({ tingkat: d.tingkat, lokasi_id: d.lokasi_id, tahun, durasi: d.durasi, hari: d.jumlah_hari, roda: d.roda, menginap: d.menginap, pp: !!d.pp, transport_manual: d.transport_manual });
    const kali = d.jumlah_petugas * d.frekuensi;
    estimasi = h.total * kali; rincian = { per_orang: h.baris, total_per_orang: h.total, pengali: kali, tarif_tahun: h.tahun };
    peringatan.push(...h.peringatan);
    if (h.total === 0) galatDasar.push('Estimasi Rp0: periksa durasi (≤ 8 jam hanya transport lokal), lokasi, tarif master, atau isi transport manual.');
  } else {
    d.jenis_perjalanan = null; d.lokasi_id = d.lokasi_id || null;
    if (!d.estimasi_manual) throw new Error('Pos anggaran ini bukan perjalanan dinas: isi "Estimasi biaya (Rp)".');
    estimasi = d.estimasi_manual; rincian = { manual: true };
  }
  d.estimasi = estimasi;

  const terpakai = terpakaiBaris(baris.id, excl), sisaSebelum = baris.jumlah - terpakai, sisaSesudah = sisaSebelum - estimasi;
  const pagu = db.prepare('SELECT pagu FROM bok_pagu WHERE tahun=?').get(tahun)?.pagu ?? null;
  const dipakaiBok = db.prepare("SELECT COALESCE(SUM(estimasi),0) s FROM rencana WHERE tahun=? AND status!='Ditolak' AND id!=?").get(tahun, excl).s;
  const sisaBokSesudah = pagu === null ? null : pagu - dipakaiBok - estimasi;
  const rincianPagu = db.prepare('SELECT COALESCE(SUM(jumlah),0) s FROM bok_baris WHERE rincian_id=?').get(baris.rincian_id).s;
  const rincianTerpakai = db.prepare("SELECT COALESCE(SUM(r.estimasi),0) s FROM rencana r JOIN bok_baris b ON b.id=r.baris_id WHERE b.rincian_id=? AND r.status!='Ditolak' AND r.id!=?").get(baris.rincian_id, excl).s;
  const galat = [...galatDasar];
  if (sisaSesudah < 0) galat.push(`Melebihi pagu pos anggaran: sisa ${rpt(sisaSebelum)}, rencana ${rpt(estimasi)} (kurang ${rpt(-sisaSesudah)}).`);
  if (sisaBokSesudah !== null && sisaBokSesudah < 0) galat.push(`Melebihi pagu BOK ${tahun}: sisa ${rpt(pagu - dipakaiBok)}, rencana ${rpt(estimasi)}.`);
  if (pagu === null) peringatan.push(`Pagu BOK ${tahun} belum diatur di menu Pagu Anggaran BOK.`);
  const amb = pengaturan('ambang_pagu_peringatan', 10);
  if (!galat.length && baris.jumlah > 0 && sisaSesudah / baris.jumlah * 100 < amb) peringatan.push(`Sisa pagu pos anggaran tinggal ${(sisaSesudah / baris.jumlah * 100).toFixed(1)}%.`);
  return {
    d, perjalanan, rincian, estimasi, galat, peringatan, ok: !galat.length,
    pos: { baris_id: baris.id, label: `${baris.rincian_no ?? ''}. ${baris.rincian}`, komponen: baris.komponen, jenis: baris.jenis_belanja, uraian: baris.uraian,
      pagu: baris.jumlah, terpakai, sisa_sebelum: sisaSebelum, sisa_sesudah: sisaSesudah },
    kegiatan: { pagu: rincianPagu, terpakai: rincianTerpakai, sisa_sesudah: rincianPagu - rincianTerpakai - estimasi },
    bok: { pagu, terpakai: dipakaiBok, sisa_sesudah: sisaBokSesudah },
  };
}

const KOL = ['tahun', 'bulan', 'baris_id', 'kegiatan', 'kode_rekening', 'lokasi_id', 'jenis_perjalanan', 'durasi', 'jumlah_petugas', 'jumlah_hari', 'frekuensi', 'tingkat', 'roda', 'menginap', 'pp', 'transport_manual', 'estimasi_manual', 'estimasi', 'catatan'];

const ALUR = { 'Draft→Diajukan': 'tulis', 'Diajukan→Disetujui': 'kepala', 'Diajukan→Ditolak': 'kepala', 'Diajukan→Draft': 'tulis', 'Ditolak→Draft': 'tulis', 'Disetujui→Draft': 'kepala' };

function pasang(app, { auth, audit }) {
  const peran = u => u.role !== 'pegawai';
  const boleh = (req, res, next) => peran(req.user) ? next() : res.status(403).json({ error: 'Tidak ada akses.' });
  const kerja = fn => (req, res) => { try { res.json(fn(req, res) ?? { ok: 1 }); } catch (e) { res.status(400).json({ error: e.message }); } };
  const bisaUbah = (u, r) => ['kepala', 'bendahara'].includes(u.role) || (u.role === 'program' && r.dibuat_oleh === u.username);

  app.get('/api/rencana/opsi', auth, boleh, kerja(req => {
    const tahun = Number(req.query.tahun);
    const rows = db.prepare(`SELECT b.id, b.komponen, b.jenis_belanja, b.uraian, b.jumlah, b.kode_rekening, r.id rincian_id, r.no rincian_no, r.nama rincian, m.no menu_no, m.nama menu,
      b.jumlah - COALESCE((SELECT SUM(estimasi) FROM rencana x WHERE x.baris_id=b.id AND x.status!='Ditolak'),0) sisa
      FROM bok_baris b JOIN bok_rincian r ON r.id=b.rincian_id JOIN bok_menu m ON m.id=r.menu_id WHERE m.tahun=? ORDER BY m.urut, r.urut, b.urut`).all(tahun);
    rows.forEach(x => x.perjalanan = /perjalanan dinas/i.test(x.jenis_belanja));
    return rows;
  }));

  app.post('/api/rencana/preview', auth, boleh, kerja(req => {
    try { const a = analisis(req.body, Number(req.body.id) || 0); const { d, ...rest } = a; return rest; }
    catch (e) { return { error: e.message, galat: [e.message], peringatan: [], ok: false }; }
  }));

  app.get('/api/rencana', auth, boleh, kerja(req => {
    const q = ['m.tahun=?'], a = [Number(req.query.tahun)];
    if (req.query.bulan) { q.push('r.bulan=?'); a.push(Number(req.query.bulan)); }
    if (req.query.status) { q.push('r.status=?'); a.push(req.query.status); }
    const rows = db.prepare(`SELECT r.*, l.nama lokasi, b.komponen, b.jenis_belanja, b.uraian pos_uraian, rc.no rincian_no, rc.nama rincian, m.no menu_no
      FROM rencana r JOIN bok_baris b ON b.id=r.baris_id JOIN bok_rincian rc ON rc.id=b.rincian_id JOIN bok_menu m ON m.id=rc.menu_id
      LEFT JOIN lokasi l ON l.id=r.lokasi_id WHERE ${q.join(' AND ')} ORDER BY r.bulan, r.id`).all(...a);
    rows.forEach(r => { r.rincian_biaya = r.rincian_biaya ? JSON.parse(r.rincian_biaya) : null; r.bisa_ubah = bisaUbah(req.user, r); });
    return rows;
  }));

  app.post('/api/rencana', auth, boleh, kerja(req => {
    if (req.user.role === 'pegawai') throw new Error('Tidak ada akses.');
    const a = analisis(req.body); if (!a.ok) throw new Error(a.galat.join(' '));
    const sd = bokId(); if (!sd) throw new Error('Sumber dana BOK belum ada di master.');
    const id = Number(db.prepare(`INSERT INTO rencana(sumber_dana_id,${KOL.join(',')},rincian_biaya,dibuat_oleh) VALUES(?,${KOL.map(() => '?').join(',')},?,?)`)
      .run(sd, ...KOL.map(k => a.d[k] ?? null), JSON.stringify(a.rincian), req.user.username).lastInsertRowid);
    audit(req.user, 'rencana', id, 'TAMBAH', null, a.d); return { id, peringatan: a.peringatan };
  }));

  app.put('/api/rencana/:id', auth, boleh, kerja(req => {
    const lama = db.prepare('SELECT * FROM rencana WHERE id=?').get(req.params.id); if (!lama) throw new Error('Rencana tidak ditemukan.');
    if (!bisaUbah(req.user, lama)) throw new Error('Anda tidak berhak mengubah rencana ini.');
    if (lama.status !== 'Draft') throw new Error('Hanya rencana berstatus Draft yang dapat diubah. Tarik kembali ke Draft terlebih dahulu.');
    const a = analisis({ ...req.body, id: lama.id }, lama.id); if (!a.ok) throw new Error(a.galat.join(' '));
    db.prepare(`UPDATE rencana SET ${KOL.map(k => k + '=?').join(',')}, rincian_biaya=? WHERE id=?`).run(...KOL.map(k => a.d[k] ?? null), JSON.stringify(a.rincian), lama.id);
    audit(req.user, 'rencana', lama.id, 'UBAH', lama, a.d); return { peringatan: a.peringatan };
  }));

  app.delete('/api/rencana/:id', auth, boleh, kerja(req => {
    const lama = db.prepare('SELECT * FROM rencana WHERE id=?').get(req.params.id); if (!lama) throw new Error('Rencana tidak ditemukan.');
    if (!bisaUbah(req.user, lama)) throw new Error('Anda tidak berhak menghapus rencana ini.');
    if (lama.status !== 'Draft') throw new Error('Hanya rencana Draft yang dapat dihapus.');
    db.prepare('DELETE FROM rencana WHERE id=?').run(lama.id); audit(req.user, 'rencana', lama.id, 'HAPUS', lama, null);
  }));

  app.post('/api/rencana/:id/status', auth, boleh, kerja(req => {
    const lama = db.prepare('SELECT * FROM rencana WHERE id=?').get(req.params.id); if (!lama) throw new Error('Rencana tidak ditemukan.');
    const ke = String(req.body.ke || ''), kunci = `${lama.status}→${ke}`, syarat = ALUR[kunci];
    if (!syarat) throw new Error(`Perubahan status ${lama.status} → ${ke} tidak diizinkan.`);
    if (syarat === 'kepala' && req.user.role !== 'kepala') throw new Error('Hanya Kepala Puskesmas yang dapat menyetujui/menolak.');
    if (syarat === 'tulis' && !bisaUbah(req.user, lama)) throw new Error('Anda tidak berhak mengubah status rencana ini.');
    if (ke === 'Ditolak' && !String(req.body.alasan || '').trim()) throw new Error('Alasan penolakan wajib diisi.');
    if (ke === 'Diajukan' || ke === 'Disetujui') { const a = analisis(lama, lama.id); if (!a.ok) throw new Error(a.galat.join(' ')); }
    const now = "datetime('now','localtime')";
    if (ke === 'Diajukan') db.prepare(`UPDATE rencana SET status=?, diajukan_pada=${now}, alasan_tolak=NULL WHERE id=?`).run(ke, lama.id);
    else if (ke === 'Disetujui' || ke === 'Ditolak') db.prepare(`UPDATE rencana SET status=?, diputuskan_oleh=?, diputuskan_pada=${now}, alasan_tolak=? WHERE id=?`).run(ke, req.user.username, ke === 'Ditolak' ? String(req.body.alasan).trim() : null, lama.id);
    else db.prepare('UPDATE rencana SET status=? WHERE id=?').run(ke, lama.id);
    audit(req.user, 'rencana', lama.id, 'STATUS', { status: lama.status }, { status: ke, alasan: req.body.alasan || undefined });
  }));

  // Matriks POA: kegiatan (rincian menu) × bulan
  app.get('/api/rencana/poa', auth, boleh, kerja(req => {
    const tahun = Number(req.query.tahun);
    const rows = db.prepare(`SELECT m.no menu_no, m.nama menu, rc.id rincian_id, rc.no rincian_no, rc.nama rincian,
      (SELECT COALESCE(SUM(jumlah),0) FROM bok_baris WHERE rincian_id=rc.id) pagu FROM bok_rincian rc JOIN bok_menu m ON m.id=rc.menu_id
      WHERE m.tahun=? ORDER BY m.urut, rc.urut`).all(tahun);
    const sums = db.prepare(`SELECT b.rincian_id, r.bulan, SUM(r.estimasi) s FROM rencana r JOIN bok_baris b ON b.id=r.baris_id
      WHERE r.tahun=? AND r.status!='Ditolak' GROUP BY b.rincian_id, r.bulan`).all(tahun);
    rows.forEach(x => { x.bulan = Array(12).fill(0); });
    sums.forEach(s => { const x = rows.find(y => y.rincian_id === s.rincian_id); if (x) x.bulan[s.bulan - 1] = s.s; });
    rows.forEach(x => { x.total = x.bulan.reduce((a, b) => a + b, 0); x.sisa = x.pagu - x.total; });
    return rows;
  }));
}
module.exports = { pasang, analisis };
