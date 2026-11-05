const express = require('express');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const os = require('os');
const XLSX = require('xlsx');
const { db, hashPassword, verifyPassword, hitungTingkat, DB_PATH } = require('./db');
const { hitung } = require('./calc');

const app = express();
app.use(express.json({ limit: '25mb' }));

// ---------------- Definisi sumber daya master (satu sumber kebenaran untuk server & UI) ----------------
const F = (k, label, type = 'text', o = {}) => ({ k, label, type, ...o });
const AKTIF = F('aktif', 'Aktif', 'bool', { def: 1 });
const RES = {
  pegawai: {
    judul: 'Pegawai', tabel: 'pegawai', urut: 'aktif DESC, nama',
    unik: ['nip'],
    fields: [F('nama', 'Nama', 'text', { req: 1 }), F('nip', 'NIP'), F('pangkat', 'Pangkat'),
      F('golongan', 'Golongan (mis. III/b, IV/a)'), F('jabatan', 'Jabatan'), F('eselon', 'Eselon (III/IV/kosong)'),
      F('status', 'Status', 'select', { req: 1, opts: ['ASN', 'PPPK', 'Non ASN'], def: 'ASN' }),
      F('program', 'Program'), F('tingkat', 'Tingkat biaya (otomatis)', 'text', { ro: 1 }), AKTIF],
    list: ['nama', 'nip', 'golongan', 'jabatan', 'status', 'program', 'tingkat', 'aktif'],
  },
  sumber_dana: {
    judul: 'Sumber Dana', tabel: 'sumber_dana', urut: 'kode', unik: ['kode'],
    fields: [F('kode', 'Kode', 'text', { req: 1 }), F('nama', 'Nama', 'text', { req: 1 })], list: ['kode', 'nama'],
  },
  pagu: {
    judul: 'Pagu per Rekening', tabel: 'pagu', urut: 'tahun DESC, sumber_dana_id, kode_rekening', tahunFilter: 'tahun',
    unik: ['tahun', 'sumber_dana_id', 'program', 'kegiatan', 'sub_kegiatan', 'kode_rekening'],
    imp: { sumber_dana_id: ['sumber_dana', 'sumber_dana', 'kode'] },
    fields: [F('tahun', 'Tahun', 'number', { req: 1 }), F('sumber_dana_id', 'Sumber dana', 'ref', { req: 1, ref: 'sumber_dana', refLabel: 'kode' }),
      F('program', 'Program'), F('kegiatan', 'Kegiatan'), F('sub_kegiatan', 'Sub kegiatan'),
      F('kode_rekening', 'Kode rekening belanja', 'text', { req: 1 }), F('uraian', 'Uraian rekening'),
      F('pagu', 'Pagu (Rp)', 'rupiah', { req: 1 })],
    list: ['tahun', 'sumber_dana_id', 'kegiatan', 'kode_rekening', 'uraian', 'pagu'],
  },
  lokasi: {
    judul: 'Lokasi Tujuan', tabel: 'lokasi', urut: 'jenis, nama', unik: ['nama', 'jenis'],
    fields: [F('nama', 'Nama lokasi', 'text', { req: 1 }),
      F('jenis', 'Jenis', 'select', { req: 1, opts: [['DK_WILAYAH', 'Dalam kota – wilayah kerja'], ['DK_ANTAR', 'Dalam kota – antar kecamatan/desa'], ['LK_KALTENG', 'Luar kota – Kalteng'], ['LK_LUAR_PROV', 'Luar kota – luar provinsi']] }),
      F('kecamatan', 'Kecamatan'), F('provinsi', 'Provinsi'),
      F('induk_id', 'Berada di (induk)', 'ref', { ref: 'lokasi', refLabel: 'nama' }),
      F('kunci_tarif', 'Kunci tarif (cocok dgn "Tujuan" di tabel tarif)'), AKTIF],
    list: ['nama', 'jenis', 'kecamatan', 'provinsi', 'kunci_tarif', 'aktif'],
  },
  tarif: {
    judul: 'Tarif Perbup', tabel: 'tarif', urut: 'kategori, tujuan, tingkat', tahunFilter: 'tahun_berlaku',
    unik: ['tahun_berlaku', 'kategori', 'tujuan', 'tingkat'],
    fields: [F('tahun_berlaku', 'Tahun berlaku', 'number', { req: 1 }), F('dasar_hukum', 'Dasar hukum', 'text', { req: 1 }),
      F('kategori', 'Kategori', 'select', { req: 1, opts: [['UH_DK', 'Uang harian dalam kota'], ['UH_DIKLAT_DK', 'Uang harian diklat dalam kota'], ['UH_LK_KALTENG', 'Uang harian luar kota Kalteng'], ['UH_LUAR_PROV', 'Uang harian luar provinsi'], ['TR_DK', 'Transport dalam kota (R2/R4)'], ['TR_DARAT_LK', 'Transport darat luar kota'], ['INAP_DK', 'Penginapan dalam kota'], ['INAP_KALTENG', 'Penginapan Kalteng'], ['INAP_LUAR_PROV', 'Penginapan luar provinsi'], ['TIKET_PESAWAT', 'Tiket pesawat'], ['TAKSI', 'Taksi']] }),
      F('tujuan', 'Tujuan / wilayah'), F('tingkat', 'Tingkat (C/D, kosong = semua)'),
      F('nilai', 'Nilai (Rp) / Roda 2', 'rupiah'), F('nilai2', 'Nilai 2 (Rp) / Roda 4', 'rupiah'),
      F('satuan', 'Satuan'), F('lampiran', 'Lampiran Perbup'), F('keterangan', 'Keterangan')],
    list: ['kategori', 'tujuan', 'tingkat', 'nilai', 'nilai2', 'satuan', 'lampiran'],
  },
  pejabat: {
    judul: 'Pejabat Penandatangan', tabel: 'pejabat', urut: 'peran',
    fields: [F('peran', 'Peran', 'text', { req: 1 }), F('nama', 'Nama', 'text', { req: 1 }), F('nip', 'NIP'), F('pangkat', 'Pangkat/Gol'), F('jabatan', 'Jabatan'), AKTIF],
    list: ['peran', 'nama', 'nip', 'jabatan', 'aktif'],
  },
  pengaturan: {
    judul: 'Pengaturan & Kop Surat', tabel: 'pengaturan', urut: 'id', noCreate: 1, noDelete: 1,
    fields: [F('kunci', 'Kunci', 'text', { ro: 1 }), F('nilai', 'Nilai'), F('keterangan', 'Keterangan', 'text', { ro: 1 })],
    list: ['kunci', 'nilai', 'keterangan'],
  },
  libur: {
    judul: 'Hari Libur', tabel: 'libur', urut: 'tanggal', unik: ['tanggal'],
    fields: [F('tanggal', 'Tanggal', 'date', { req: 1 }), F('keterangan', 'Keterangan')], list: ['tanggal', 'keterangan'],
  },
  cuti: {
    judul: 'Cuti Pegawai', tabel: 'cuti', urut: 'mulai DESC',
    imp: { pegawai_id: ['nip', 'pegawai', 'nip'] },
    fields: [F('pegawai_id', 'Pegawai', 'ref', { req: 1, ref: 'pegawai', refLabel: 'nama' }), F('mulai', 'Mulai', 'date', { req: 1 }), F('selesai', 'Selesai', 'date', { req: 1 }), F('keterangan', 'Keterangan')],
    list: ['pegawai_id', 'mulai', 'selesai', 'keterangan'],
  },
  users: {
    judul: 'Pengguna', tabel: 'users', urut: 'username', onlyKepala: 1, unik: ['username'],
    fields: [F('username', 'Username', 'text', { req: 1 }), F('nama', 'Nama', 'text', { req: 1 }),
      F('role', 'Hak akses', 'select', { req: 1, opts: [['kepala', 'Kepala Puskesmas'], ['bendahara', 'Bendahara'], ['program', 'Pengelola Program'], ['pegawai', 'Pegawai']] }),
      F('pegawai_id', 'Terkait pegawai', 'ref', { ref: 'pegawai', refLabel: 'nama' }),
      F('password', 'Password (isi untuk mengubah)', 'password', { virtual: 1 }), AKTIF],
    list: ['username', 'nama', 'role', 'aktif'],
  },
};
const dbFields = r => r.fields.filter(f => !f.virtual);

// ---------------- Sesi & hak akses ----------------
const sessions = new Map();
const cookie = req => Object.fromEntries((req.headers.cookie || '').split(';').map(s => s.trim().split('=')).filter(a => a[0]));
function auth(req, res, next) {
  const u = sessions.get(cookie(req).sid);
  if (!u) return res.status(401).json({ error: 'Silakan login terlebih dahulu.' });
  req.user = u; next();
}
const bisaTulis = u => u.role === 'kepala' || u.role === 'bendahara';
const bisaBaca = u => u.role !== 'pegawai';
const gagal = {};
app.post('/api/login', (req, res) => {
  const { username = '', password = '' } = req.body || {};
  const ip = req.ip, g = gagal[ip] || { n: 0, t: 0 };
  if (g.n >= 5 && Date.now() - g.t < 5 * 60 * 1000) return res.status(429).json({ error: 'Terlalu banyak percobaan. Coba lagi 5 menit.' });
  const u = db.prepare('SELECT * FROM users WHERE username=? AND aktif=1').get(String(username));
  if (!u || !verifyPassword(String(password), u.password_hash)) {
    gagal[ip] = { n: g.n + 1, t: Date.now() };
    return res.status(401).json({ error: 'Username atau password salah.' });
  }
  delete gagal[ip];
  const sid = crypto.randomBytes(24).toString('hex');
  sessions.set(sid, { id: u.id, username: u.username, nama: u.nama, role: u.role, pegawai_id: u.pegawai_id });
  res.setHeader('Set-Cookie', `sid=${sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`);
  res.json(sessions.get(sid));
});
app.post('/api/logout', (req, res) => { sessions.delete(cookie(req).sid); res.setHeader('Set-Cookie', 'sid=; Max-Age=0; Path=/'); res.json({ ok: 1 }); });
app.get('/api/me', auth, (req, res) => res.json(req.user));
app.post('/api/ganti-password', auth, (req, res) => {
  const { lama = '', baru = '' } = req.body || {};
  const u = db.prepare('SELECT * FROM users WHERE id=?').get(req.user.id);
  if (!verifyPassword(String(lama), u.password_hash)) return res.status(400).json({ error: 'Password lama salah.' });
  if (String(baru).length < 8) return res.status(400).json({ error: 'Password baru minimal 8 karakter.' });
  db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(hashPassword(String(baru)), u.id);
  audit(req.user, 'users', u.id, 'UBAH', { password: '***' }, { password: '*** (diganti)' });
  res.json({ ok: 1 });
});

// ---------------- Audit ----------------
function audit(user, tabel, id, aksi, lama, baru) {
  db.prepare('INSERT INTO audit_log(user_id,username,tabel,record_id,aksi,data_lama,data_baru) VALUES(?,?,?,?,?,?,?)')
    .run(user.id, user.username, tabel, id, aksi, lama ? JSON.stringify(lama) : null, baru ? JSON.stringify(baru) : null);
}
const bersih = r => { if (r && 'password_hash' in r) { r = { ...r }; delete r.password_hash; } return r; };

// ---------------- CRUD generik ----------------
function cekHak(req, res, key, tulis) {
  const r = RES[key];
  if (!r) { res.status(404).json({ error: 'Sumber daya tidak dikenal.' }); return null; }
  if (r.onlyKepala && req.user.role !== 'kepala') { res.status(403).json({ error: 'Hanya Kepala Puskesmas yang dapat mengelola pengguna.' }); return null; }
  if (tulis ? !bisaTulis(req.user) : !bisaBaca(req.user)) { res.status(403).json({ error: 'Anda tidak memiliki hak akses untuk tindakan ini.' }); return null; }
  return r;
}
function normalisasi(r, body, lama) {
  const out = {};
  for (const f of dbFields(r)) {
    if (f.ro) continue;
    let v = body[f.k];
    if (v === undefined) { if (lama) continue; v = f.def !== undefined ? f.def : null; }
    if (f.type === 'bool') v = v ? 1 : 0;
    else if (f.type === 'number' || f.type === 'rupiah' || f.type === 'ref') v = (v === '' || v === null) ? null : Number(v);
    else if (typeof v === 'string') v = v.trim();
    if ((v === '' || v === null) && (f.k === 'tujuan' || f.k === 'tingkat')) v = '';
    else if (v === '') v = null;
    if (f.req && (v === null || v === undefined || Number.isNaN(v))) throw new Error(`${f.label} wajib diisi.`);
    if (typeof v === 'number' && Number.isNaN(v)) throw new Error(`${f.label} harus berupa angka.`);
    if (f.type === 'rupiah' && v !== null && v < 0) throw new Error(`${f.label} tidak boleh negatif.`);
    if (f.type === 'select' && v !== null) {
      const ok = f.opts.map(o => Array.isArray(o) ? o[0] : o);
      if (!ok.includes(v)) throw new Error(`${f.label} tidak valid.`);
    }
    out[f.k] = v;
  }
  if (r.tabel === 'pegawai') {
    const m = { ...(lama || {}), ...out };
    out.tingkat = hitungTingkat(m);
  }
  if (r.tabel === 'cuti' || r.tabel === 'tarif') { /* aturan tambahan di DB */ }
  return out;
}
function pesanDB(e) {
  const m = String(e.message || e);
  if (/UNIQUE/i.test(m)) return 'Data dengan nilai kunci yang sama sudah ada (duplikat).';
  if (/FOREIGN KEY/i.test(m)) return 'Data masih dipakai data lain. Nonaktifkan saja, jangan dihapus.';
  if (/CHECK/i.test(m)) return 'Nilai tidak memenuhi aturan (cek tanggal/jenis/pagu).';
  return m;
}

app.get('/api/meta', auth, (req, res) => {
  const meta = {};
  for (const [k, r] of Object.entries(RES)) {
    if (r.onlyKepala && req.user.role !== 'kepala') continue;
    meta[k] = { judul: r.judul, fields: r.fields.map(f => ({ ...f })), list: r.list, tahunFilter: r.tahunFilter, noCreate: r.noCreate, noDelete: r.noDelete };
  }
  res.json({ user: req.user, meta, bisaTulis: bisaTulis(req.user), bisaBaca: bisaBaca(req.user) });
});

app.get('/api/data/:res', auth, (req, res) => {
  const r = cekHak(req, res, req.params.res, false); if (!r) return;
  let sql = `SELECT * FROM ${r.tabel}`; const args = [];
  if (r.tahunFilter && req.query.tahun) { sql += ` WHERE ${r.tahunFilter}=?`; args.push(Number(req.query.tahun)); }
  sql += ` ORDER BY ${r.urut}`;
  res.json(db.prepare(sql).all(...args).map(bersih));
});

app.post('/api/data/:res', auth, (req, res) => {
  const r = cekHak(req, res, req.params.res, true); if (!r) return;
  if (r.noCreate) return res.status(400).json({ error: 'Data ini tidak bisa ditambah.' });
  try {
    const d = normalisasi(r, req.body);
    const extra = {};
    if (r.tabel === 'users') {
      const pw = String(req.body.password || '');
      if (pw.length < 8) throw new Error('Password minimal 8 karakter.');
      extra.password_hash = hashPassword(pw);
    }
    const all = { ...d, ...extra }, cols = Object.keys(all);
    const info = db.prepare(`INSERT INTO ${r.tabel}(${cols.join(',')}) VALUES(${cols.map(() => '?').join(',')})`).run(...cols.map(c => all[c]));
    audit(req.user, r.tabel, Number(info.lastInsertRowid), 'TAMBAH', null, bersih(all));
    res.json({ id: Number(info.lastInsertRowid) });
  } catch (e) { res.status(400).json({ error: pesanDB(e) }); }
});

app.put('/api/data/:res/:id', auth, (req, res) => {
  const r = cekHak(req, res, req.params.res, true); if (!r) return;
  try {
    const lama = db.prepare(`SELECT * FROM ${r.tabel} WHERE id=?`).get(req.params.id);
    if (!lama) return res.status(404).json({ error: 'Data tidak ditemukan.' });
    const d = normalisasi(r, req.body, lama);
    if (r.tabel === 'users' && req.body.password) {
      if (String(req.body.password).length < 8) throw new Error('Password minimal 8 karakter.');
      d.password_hash = hashPassword(String(req.body.password));
    }
    const cols = Object.keys(d);
    if (!cols.length) return res.json({ ok: 1 });
    db.prepare(`UPDATE ${r.tabel} SET ${cols.map(c => c + '=?').join(',')} WHERE id=?`).run(...cols.map(c => d[c]), req.params.id);
    const baru = db.prepare(`SELECT * FROM ${r.tabel} WHERE id=?`).get(req.params.id);
    audit(req.user, r.tabel, Number(req.params.id), 'UBAH', bersih(lama), bersih(baru));
    res.json({ ok: 1 });
  } catch (e) { res.status(400).json({ error: pesanDB(e) }); }
});

app.delete('/api/data/:res/:id', auth, (req, res) => {
  const r = cekHak(req, res, req.params.res, true); if (!r) return;
  if (r.noDelete) return res.status(400).json({ error: 'Data ini tidak bisa dihapus.' });
  try {
    const lama = db.prepare(`SELECT * FROM ${r.tabel} WHERE id=?`).get(req.params.id);
    if (!lama) return res.status(404).json({ error: 'Data tidak ditemukan.' });
    if (r.tabel === 'users' && lama.id === req.user.id) throw new Error('Tidak dapat menghapus akun sendiri.');
    db.prepare(`DELETE FROM ${r.tabel} WHERE id=?`).run(req.params.id);
    audit(req.user, r.tabel, Number(req.params.id), 'HAPUS', bersih(lama), null);
    res.json({ ok: 1 });
  } catch (e) { res.status(400).json({ error: pesanDB(e) }); }
});

// ---------------- Impor / ekspor Excel ----------------
function kolomExcel(r) {
  return r.fields.filter(f => !f.virtual && !f.ro &&!(r.imp && r.imp[f.k]))
    .map(f => f.k).concat(r.imp ? Object.values(r.imp).map(a => a[1]) : []);
}
app.get('/api/template/:res', auth, (req, res) => {
  const r = cekHak(req, res, req.params.res, true); if (!r) return;
  const ws = XLSX.utils.aoa_to_sheet([kolomExcel(r)]);
  const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, r.tabel);
  res.setHeader('Content-Disposition', `attachment; filename="template_${r.tabel}.xlsx"`);
  res.send(XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' }));
});

app.post('/api/import/:res', auth, (req, res) => {
  const r = cekHak(req, res, req.params.res, true); if (!r || r.onlyKepala) return;
  if (r.noCreate) return res.status(400).json({ error: 'Data ini tidak dapat diimpor.' });
  try {
    const wb = XLSX.read(Buffer.from(String(req.body.file || ''), 'base64'), { type: 'buffer', cellDates: false });
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '', raw: true });
    if (!rows.length) throw new Error('File kosong.');
    let tambah = 0, ubah = 0; const galat = [];
    db.exec('BEGIN');
    try {
      rows.forEach((row, i) => {
        try {
          const body = { ...row };
          for (const [fk, [tbl, col, by]] of Object.entries(r.imp || {})) {
            const val = String(row[col] ?? '').trim();
            const rec = val && db.prepare(`SELECT id FROM ${tbl} WHERE ${by}=?`).get(val);
            if (!rec) throw new Error(`"${val}" tidak ditemukan di ${tbl}.`);
            body[fk] = rec.id;
          }
          const d = normalisasi(r, body);
          const uk = r.unik;
          let ada = null;
          if (uk && !(r.tabel === 'pegawai' && !d.nip)) {
            ada = db.prepare(`SELECT * FROM ${r.tabel} WHERE ${uk.map(c => c + ' IS ?').join(' AND ')}`).get(...uk.map(c => d[c] ?? null));
          }
          if (ada) {
            const cols = Object.keys(d);
            db.prepare(`UPDATE ${r.tabel} SET ${cols.map(c => c + '=?').join(',')} WHERE id=?`).run(...cols.map(c => d[c]), ada.id);
            audit(req.user, r.tabel, ada.id, 'IMPOR-UBAH', ada, d); ubah++;
          } else {
            const cols = Object.keys(d);
            const info = db.prepare(`INSERT INTO ${r.tabel}(${cols.join(',')}) VALUES(${cols.map(() => '?').join(',')})`).run(...cols.map(c => d[c]));
            audit(req.user, r.tabel, Number(info.lastInsertRowid), 'IMPOR-TAMBAH', null, d); tambah++;
          }
        } catch (e) { galat.push(`Baris ${i + 2}: ${pesanDB(e)}`); }
      });
      if (galat.length) { db.exec('ROLLBACK'); return res.status(400).json({ error: 'Impor dibatalkan, tidak ada data tersimpan.', galat: galat.slice(0, 20) }); }
      db.exec('COMMIT');
    } catch (e) { try { db.exec('ROLLBACK'); } catch {} throw e; }
    res.json({ tambah, ubah });
  } catch (e) { res.status(400).json({ error: pesanDB(e) }); }
});

app.get('/api/export/xlsx', auth, (req, res) => {
  if (!bisaBaca(req.user)) return res.status(403).json({ error: 'Tidak ada akses.' });
  const wb = XLSX.utils.book_new();
  for (const [k, r] of Object.entries(RES)) {
    if (r.onlyKepala) continue;
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(db.prepare(`SELECT * FROM ${r.tabel} ORDER BY id`).all()), k);
  }
  if (req.user.role === 'kepala' || req.user.role === 'bendahara')
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(db.prepare('SELECT * FROM audit_log ORDER BY id').all()), 'riwayat');
  res.setHeader('Content-Disposition', `attachment; filename="sikadin_data_${new Date().toISOString().slice(0, 10)}.xlsx"`);
  res.send(XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' }));
});
app.get('/api/backup', auth, (req, res) => {
  if (!bisaTulis(req.user)) return res.status(403).json({ error: 'Tidak ada akses.' });
  const tmp = path.join(os.tmpdir(), `sikadin_backup_${Date.now()}.db`);
  db.exec(`VACUUM INTO '${tmp.replace(/'/g, "''")}'`);
  audit(req.user, 'sistem', null, 'BACKUP', null, null);
  res.download(tmp, `sikadin_backup_${new Date().toISOString().slice(0, 10)}.db`, () => fs.unlink(tmp, () => {}));
});

// ---------------- Riwayat perubahan ----------------
app.get('/api/riwayat', auth, (req, res) => {
  if (!bisaTulis(req.user)) return res.status(403).json({ error: 'Hanya Kepala/Bendahara.' });
  const q = [], a = [];
  if (req.query.tabel) { q.push('tabel=?'); a.push(req.query.tabel); }
  res.json(db.prepare(`SELECT * FROM audit_log ${q.length ? 'WHERE ' + q.join(' AND ') : ''} ORDER BY id DESC LIMIT 300`).all(...a));
});

require('./bok').pasang(app, { auth, audit, bisaTulis, bisaBaca });
require('./rencana').pasang(app, { auth, audit });

// ---------------- Kalkulator biaya ----------------
app.post('/api/hitung-biaya', auth, (req, res) => {
  if (!bisaBaca(req.user)) return res.status(403).json({ error: 'Tidak ada akses.' });
  try { res.json(hitung(req.body || {})); } catch (e) { res.status(400).json({ error: e.message }); }
});

app.use(express.static(path.join(__dirname, '..', 'public')));
const PORT = Number(process.env.PORT || 3100);
app.listen(PORT, () => console.log(`SIKADIN berjalan di http://localhost:${PORT}  (DB: ${DB_PATH})`));
