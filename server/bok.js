// Pagu & RAB BOK: Menu → Rincian Menu → baris biaya. Tambah / ubah / hapus di tiap tingkat.
const XLSX = require('xlsx');
const { db } = require('./db');
const { parseRAB } = require('./rab');

const t = v => (v === undefined || v === null || String(v).trim() === '' ? null : String(v).trim());
const n = (v, label, def = null) => {
  if (v === undefined || v === null || v === '') { if (def !== null) return def; throw new Error(`${label} wajib diisi.`); }
  const x = Number(v);
  if (!Number.isFinite(x) || x < 0) throw new Error(`${label} harus angka ≥ 0.`);
  return x;
};
const hitungJumlah = b => Math.round(b.vol1 * b.vol2 * b.vol3 * b.unit_cost);

function tree(tahun) {
  const menus = db.prepare('SELECT * FROM bok_menu WHERE tahun=? ORDER BY urut,id').all(tahun);
  for (const m of menus) {
    m.rincian = db.prepare('SELECT * FROM bok_rincian WHERE menu_id=? ORDER BY urut,id').all(m.id);
    m.total = 0;
    for (const r of m.rincian) {
      r.baris = db.prepare('SELECT * FROM bok_baris WHERE rincian_id=? ORDER BY urut,id').all(r.id);
      r.total = r.baris.reduce((s, b) => s + b.jumlah, 0);
      r.baris.forEach(b => { b.beda = Math.round(b.vol1 * b.vol2 * b.vol3 * b.unit_cost) !== b.jumlah && b.jenis_belanja !== 'Pembulatan'; });
      m.total += r.total;
    }
  }
  const p = db.prepare('SELECT * FROM bok_pagu WHERE tahun=?').get(tahun) || null;
  const total = menus.reduce((s, m) => s + m.total, 0);
  return { tahun, pagu: p, total, menu: menus };
}

function pasang(app, { auth, audit, bisaTulis, bisaBaca }) {
  const tulis = (req, res, next) => bisaTulis(req.user) ? next() : res.status(403).json({ error: 'Hanya Kepala/Bendahara yang dapat mengubah pagu.' });
  const baca = (req, res, next) => bisaBaca(req.user) ? next() : res.status(403).json({ error: 'Tidak ada akses.' });
  const kerja = fn => (req, res) => { try { res.json(fn(req, res) ?? { ok: 1 }); } catch (e) { res.status(400).json({ error: /FOREIGN KEY/i.test(e.message) ? 'Data masih dipakai data lain.' : e.message }); } };

  app.get('/api/bok/tahun', auth, baca, (req, res) => res.json(db.prepare(`
    SELECT tahun FROM (SELECT tahun FROM bok_pagu UNION SELECT tahun FROM bok_menu) ORDER BY tahun DESC`).all().map(r => r.tahun)));
  app.get('/api/bok/:tahun', auth, baca, kerja(req => tree(Number(req.params.tahun))));

  app.put('/api/bok/:tahun/pagu', auth, tulis, kerja(req => {
    const tahun = Number(req.params.tahun); if (!tahun) throw new Error('Tahun tidak valid.');
    const lama = db.prepare('SELECT * FROM bok_pagu WHERE tahun=?').get(tahun);
    const d = { jenis: t(req.body.jenis) || 'Pagu Indikatif', pagu: n(req.body.pagu, 'Pagu'), keterangan: t(req.body.keterangan) };
    if (lama) db.prepare('UPDATE bok_pagu SET jenis=?,pagu=?,keterangan=? WHERE tahun=?').run(d.jenis, d.pagu, d.keterangan, tahun);
    else db.prepare('INSERT INTO bok_pagu(tahun,jenis,pagu,keterangan) VALUES(?,?,?,?)').run(tahun, d.jenis, d.pagu, d.keterangan);
    audit(req.user, 'bok_pagu', tahun, lama ? 'UBAH' : 'TAMBAH', lama, { tahun, ...d });
  }));

  // ---- Menu ----
  const urutBaru = (tbl, where, arg) => (db.prepare(`SELECT COALESCE(MAX(urut),0)+1 u FROM ${tbl} WHERE ${where}`).get(arg).u);
  app.post('/api/bok/menu', auth, tulis, kerja(req => {
    const tahun = n(req.body.tahun, 'Tahun'), nama = t(req.body.nama); if (!nama) throw new Error('Nama menu wajib diisi.');
    const id = Number(db.prepare('INSERT INTO bok_menu(tahun,no,nama,urut) VALUES(?,?,?,?)').run(tahun, t(req.body.no), nama, urutBaru('bok_menu', 'tahun=?', tahun)).lastInsertRowid);
    audit(req.user, 'bok_menu', id, 'TAMBAH', null, { tahun, no: t(req.body.no), nama }); return { id };
  }));
  app.put('/api/bok/menu/:id', auth, tulis, kerja(req => {
    const lama = db.prepare('SELECT * FROM bok_menu WHERE id=?').get(req.params.id); if (!lama) throw new Error('Menu tidak ditemukan.');
    const nama = t(req.body.nama); if (!nama) throw new Error('Nama menu wajib diisi.');
    db.prepare('UPDATE bok_menu SET no=?,nama=? WHERE id=?').run(t(req.body.no), nama, lama.id);
    audit(req.user, 'bok_menu', lama.id, 'UBAH', lama, { ...lama, no: t(req.body.no), nama });
  }));
  app.delete('/api/bok/menu/:id', auth, tulis, kerja(req => {
    const lama = db.prepare('SELECT * FROM bok_menu WHERE id=?').get(req.params.id); if (!lama) throw new Error('Menu tidak ditemukan.');
    const snap = tree(lama.tahun).menu.find(m => m.id === lama.id);
    db.prepare('DELETE FROM bok_menu WHERE id=?').run(lama.id);
    audit(req.user, 'bok_menu', lama.id, 'HAPUS', snap, null);
  }));

  // ---- Rincian ----
  app.post('/api/bok/rincian', auth, tulis, kerja(req => {
    const menu_id = n(req.body.menu_id, 'Menu'), nama = t(req.body.nama); if (!nama) throw new Error('Nama rincian wajib diisi.');
    if (!db.prepare('SELECT 1 FROM bok_menu WHERE id=?').get(menu_id)) throw new Error('Menu tidak ditemukan.');
    const id = Number(db.prepare('INSERT INTO bok_rincian(menu_id,no,nama,urut) VALUES(?,?,?,?)').run(menu_id, t(req.body.no), nama, urutBaru('bok_rincian', 'menu_id=?', menu_id)).lastInsertRowid);
    audit(req.user, 'bok_rincian', id, 'TAMBAH', null, { menu_id, no: t(req.body.no), nama }); return { id };
  }));
  app.put('/api/bok/rincian/:id', auth, tulis, kerja(req => {
    const lama = db.prepare('SELECT * FROM bok_rincian WHERE id=?').get(req.params.id); if (!lama) throw new Error('Rincian tidak ditemukan.');
    const nama = t(req.body.nama); if (!nama) throw new Error('Nama rincian wajib diisi.');
    db.prepare('UPDATE bok_rincian SET no=?,nama=? WHERE id=?').run(t(req.body.no), nama, lama.id);
    audit(req.user, 'bok_rincian', lama.id, 'UBAH', lama, { ...lama, no: t(req.body.no), nama });
  }));
  app.delete('/api/bok/rincian/:id', auth, tulis, kerja(req => {
    const lama = db.prepare('SELECT * FROM bok_rincian WHERE id=?').get(req.params.id); if (!lama) throw new Error('Rincian tidak ditemukan.');
    const baris = db.prepare('SELECT * FROM bok_baris WHERE rincian_id=?').all(lama.id);
    db.prepare('DELETE FROM bok_rincian WHERE id=?').run(lama.id);
    audit(req.user, 'bok_rincian', lama.id, 'HAPUS', { ...lama, baris }, null);
  }));

  // ---- Baris biaya ----
  function bacaBaris(b, lama) {
    const g = k => (b[k] !== undefined ? b[k] : lama ? lama[k] : undefined);
    const jenis = t(g('jenis_belanja')); if (!jenis) throw new Error('Jenis belanja wajib diisi.');
    const d = {
      komponen: t(g('komponen')), jenis_belanja: jenis, kode_rekening: t(g('kode_rekening')), uraian: t(g('uraian')), satuan: t(g('satuan')),
      vol1: n(g('vol1'), 'Volume 1', 1), sat1: t(g('sat1')), vol2: n(g('vol2'), 'Volume 2', 1), sat2: t(g('sat2')),
      vol3: n(g('vol3'), 'Volume 3', 1), sat3: t(g('sat3')), unit_cost: Math.round(n(g('unit_cost'), 'Tarif/unit cost', 0)),
    };
    const berubah = !lama || ['vol1', 'vol2', 'vol3', 'unit_cost'].some(k => Number(lama[k]) !== d[k]);
    d.jumlah = berubah ? hitungJumlah(d) : lama.jumlah;
    return d;
  }
  const kol = ['komponen', 'jenis_belanja', 'kode_rekening', 'uraian', 'satuan', 'vol1', 'sat1', 'vol2', 'sat2', 'vol3', 'sat3', 'unit_cost', 'jumlah'];
  app.post('/api/bok/baris', auth, tulis, kerja(req => {
    const rid = n(req.body.rincian_id, 'Rincian');
    if (!db.prepare('SELECT 1 FROM bok_rincian WHERE id=?').get(rid)) throw new Error('Rincian tidak ditemukan.');
    const d = bacaBaris(req.body);
    const id = Number(db.prepare(`INSERT INTO bok_baris(rincian_id,${kol.join(',')},urut) VALUES(?,${kol.map(() => '?').join(',')},?)`)
      .run(rid, ...kol.map(k => d[k]), urutBaru('bok_baris', 'rincian_id=?', rid)).lastInsertRowid);
    audit(req.user, 'bok_baris', id, 'TAMBAH', null, { rincian_id: rid, ...d }); return { id };
  }));
  app.put('/api/bok/baris/:id', auth, tulis, kerja(req => {
    const lama = db.prepare('SELECT * FROM bok_baris WHERE id=?').get(req.params.id); if (!lama) throw new Error('Baris tidak ditemukan.');
    const d = bacaBaris(req.body, lama);
    db.prepare(`UPDATE bok_baris SET ${kol.map(k => k + '=?').join(',')} WHERE id=?`).run(...kol.map(k => d[k]), lama.id);
    audit(req.user, 'bok_baris', lama.id, 'UBAH', lama, { ...lama, ...d });
  }));
  app.post('/api/bok/baris/:id/duplikat', auth, tulis, kerja(req => {
    const s = db.prepare('SELECT * FROM bok_baris WHERE id=?').get(req.params.id); if (!s) throw new Error('Baris tidak ditemukan.');
    const id = Number(db.prepare(`INSERT INTO bok_baris(rincian_id,${kol.join(',')},urut) VALUES(?,${kol.map(() => '?').join(',')},?)`)
      .run(s.rincian_id, ...kol.map(k => s[k]), urutBaru('bok_baris', 'rincian_id=?', s.rincian_id)).lastInsertRowid);
    audit(req.user, 'bok_baris', id, 'TAMBAH', null, { dari: s.id, ...s }); return { id };
  }));
  app.delete('/api/bok/baris/:id', auth, tulis, kerja(req => {
    const lama = db.prepare('SELECT * FROM bok_baris WHERE id=?').get(req.params.id); if (!lama) throw new Error('Baris tidak ditemukan.');
    db.prepare('DELETE FROM bok_baris WHERE id=?').run(lama.id);
    audit(req.user, 'bok_baris', lama.id, 'HAPUS', lama, null);
  }));

  // ---- Impor RAB (mengganti seluruh RAB BOK tahun tsb) & hapus semua ----
  function hapusTahun(tahun) { db.prepare('DELETE FROM bok_menu WHERE tahun=?').run(tahun); }
  app.post('/api/bok/import', auth, tulis, kerja(req => {
    const p = parseRAB(Buffer.from(String(req.body.file || ''), 'base64'));
    const tahun = Number(req.body.tahun) || p.tahun; if (!tahun) throw new Error('Tahun tidak terbaca, isi tahun.');
    if (!p.menus.length) throw new Error('Tidak ada menu terbaca. Pastikan format RAB BOK.');
    const ada = db.prepare('SELECT COUNT(*) c FROM bok_menu WHERE tahun=?').get(tahun).c;
    if (ada && !req.body.ganti) throw new Error(`RAB BOK ${tahun} sudah berisi ${ada} menu. Centang "ganti" untuk menimpa.`);
    const snap = ada ? tree(tahun) : null;
    db.exec('BEGIN');
    try {
      hapusTahun(tahun);
      const im = db.prepare('INSERT INTO bok_menu(tahun,no,nama,urut) VALUES(?,?,?,?)');
      const ir = db.prepare('INSERT INTO bok_rincian(menu_id,no,nama,urut) VALUES(?,?,?,?)');
      const ib = db.prepare(`INSERT INTO bok_baris(rincian_id,${kol.join(',')},urut) VALUES(?,${kol.map(() => '?').join(',')},?)`);
      let nb = 0;
      p.menus.forEach((m, i) => {
        const mid = Number(im.run(tahun, m.no, m.nama, i + 1).lastInsertRowid);
        m.rincian.forEach((r, j) => {
          const rid = Number(ir.run(mid, r.no, r.nama, j + 1).lastInsertRowid);
          r.baris.forEach((b, k) => { ib.run(rid, ...kol.map(c => b[c] ?? null), k + 1); nb++; });
        });
      });
      const lamaPagu = db.prepare('SELECT * FROM bok_pagu WHERE tahun=?').get(tahun);
      if (!lamaPagu) db.prepare('INSERT INTO bok_pagu(tahun,jenis,pagu,keterangan) VALUES(?,?,?,?)').run(tahun, 'Pagu Indikatif', p.pagu ?? p.total, 'Diimpor dari RAB BOK');
      audit(req.user, 'bok_menu', null, 'IMPOR-RAB', snap, { tahun, menu: p.menus.length, baris: nb, total: p.total });
      db.exec('COMMIT');
      return { tahun, menu: p.menus.length, baris: nb, total: p.total, pagu: p.pagu, peringatan: p.peringatan };
    } catch (e) { try { db.exec('ROLLBACK'); } catch {} throw e; }
  }));
  app.delete('/api/bok/:tahun', auth, tulis, kerja(req => {
    const tahun = Number(req.params.tahun), snap = tree(tahun);
    hapusTahun(tahun); audit(req.user, 'bok_menu', null, 'HAPUS-SEMUA', snap, null);
  }));

  app.get('/api/bok/:tahun/export.xlsx', auth, baca, (req, res) => {
    const tr = tree(Number(req.params.tahun)), rows = [];
    for (const m of tr.menu) for (const r of m.rincian) for (const b of r.baris)
      rows.push({ Menu_No: m.no, Menu: m.nama, Rincian_No: r.no, Rincian: r.nama, Komponen: b.komponen, Jenis_Belanja: b.jenis_belanja,
        Kode_Rekening: b.kode_rekening, Uraian: b.uraian, Satuan: b.satuan, Vol1: b.vol1, Sat1: b.sat1, Vol2: b.vol2, Sat2: b.sat2,
        Vol3: b.vol3, Sat3: b.sat3, Unit_Cost: b.unit_cost, Jumlah: b.jumlah });
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), 'RAB BOK ' + tr.tahun);
    res.setHeader('Content-Disposition', `attachment; filename="RAB_BOK_${tr.tahun}.xlsx"`);
    res.send(XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' }));
  });
}
module.exports = { pasang, tree };
