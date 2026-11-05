'use strict';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const rp = n => n === null || n === undefined || n === '' ? '' : 'Rp' + Number(n).toLocaleString('id-ID');
const ROLE = { kepala: 'Kepala Puskesmas', bendahara: 'Bendahara', program: 'Pengelola Program', pegawai: 'Pegawai' };
let S = { meta: {}, user: null, bisaTulis: false, bisaBaca: false, refs: {}, tahun: 2026 };

async function api(url, opt = {}) {
  const r = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opt, body: opt.body && typeof opt.body !== 'string' ? JSON.stringify(opt.body) : opt.body });
  if (r.status === 401 && !url.includes('login')) { showLogin(); throw new Error('Sesi berakhir.'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || 'Terjadi kesalahan.'); e.galat = j.galat; throw e; }
  return j;
}
function toast(msg, bad) { const t = $('#toast'); t.textContent = msg; t.className = 'toast show' + (bad ? ' bad' : ''); clearTimeout(toast.t); toast.t = setTimeout(() => t.className = 'toast', 3500); }
async function download(url, name) {
  const r = await fetch(url, { credentials: 'same-origin' });
  if (!r.ok) return toast((await r.json().catch(() => ({}))).error || 'Gagal mengunduh.', 1);
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ---------- login ----------
function showLogin() { $('#app').hidden = true; $('#login').hidden = false; }
$('#loginForm').onsubmit = async e => {
  e.preventDefault(); $('#loginErr').textContent = '';
  const f = new FormData(e.target);
  try { await api('/api/login', { method: 'POST', body: Object.fromEntries(f) }); e.target.reset(); await start(); }
  catch (x) { $('#loginErr').textContent = x.message; }
};
$('#logoutBtn').onclick = async () => { await api('/api/logout', { method: 'POST' }); showLogin(); };
$('#menuBtn').onclick = () => $('#nav').classList.toggle('open');
$('#pwBtn').onclick = () => dialog('Ganti password', `
  <label>Password lama<input name="lama" type="password" required></label>
  <label>Password baru (min. 8 karakter)<input name="baru" type="password" minlength="8" required></label>`,
  async d => { await api('/api/ganti-password', { method: 'POST', body: d }); toast('Password diganti.'); });

// ---------- dialog ----------
function dialog(judul, bodyHtml, onSave, saveLabel = 'Simpan') {
  const dlg = $('#dlg');
  $('#dlgForm').innerHTML = `<div class="dlg"><h3>${esc(judul)}</h3>${bodyHtml}<div class="err" id="dlgErr" role="alert"></div>
    <div class="row"><button type="button" class="btn" id="dlgCancel">Batal</button>${onSave ? `<button class="btn primary" id="dlgOk">${saveLabel}</button>` : ''}</div></div>`;
  $('#dlgCancel').onclick = () => dlg.close();
  $('#dlgForm').onsubmit = async e => {
    e.preventDefault(); if (!onSave) return;
    const fd = new FormData(e.target), d = {};
    e.target.querySelectorAll('input,select,textarea').forEach(el => { d[el.name] = el.type === 'checkbox' ? el.checked : fd.get(el.name); });
    try { await onSave(d); dlg.close(); } catch (x) { $('#dlgErr').textContent = x.message + (x.galat ? ' — ' + x.galat.join('; ') : ''); }
  };
  dlg.showModal();
}

// ---------- navigasi ----------
const MENU = [
  ['Anggaran', [['bok', 'Pagu Anggaran BOK'], ['rencana', 'Perencanaan (RPK/POA)']]],
  ['Dinas Luar', [['jadwal', 'Jadwal Dinas Luar']]],
  ['Master Data', [['pegawai', 'Pegawai'], ['sumber_dana', 'Sumber Dana'], ['pagu', 'Pagu DAU / BLUD'], ['lokasi', 'Lokasi Tujuan'], ['tarif', 'Tarif Perbup'], ['pejabat', 'Pejabat'], ['libur', 'Hari Libur'], ['cuti', 'Cuti Pegawai'], ['pengaturan', 'Pengaturan & Kop']]],
  ['Alat', [['kalkulator', 'Kalkulator Biaya'], ['riwayat', 'Riwayat Perubahan'], ['data', 'Backup & Ekspor']]],
  ['Sistem', [['users', 'Pengguna']]],
];
function buildNav() {
  let h = '';
  for (const [g, items] of MENU) {
    const vis = items.filter(([k]) => S.meta[k] || (['kalkulator', 'data', 'bok', 'rencana', 'jadwal'].includes(k) && S.bisaBaca) || (k === 'riwayat' && S.bisaTulis));
    if (!vis.length) continue;
    h += `<h4>${g}</h4>` + vis.map(([k, l]) => `<a data-k="${k}">${l}</a>`).join('');
  }
  if (!S.bisaBaca) h = '<h4>Akses terbatas</h4><a class="on">Beranda</a>';
  $('#nav').innerHTML = h;
  $('#nav').onclick = e => { const k = e.target.dataset.k; if (k) { location.hash = k; $('#nav').classList.remove('open'); } };
}
async function route() {
  const k = location.hash.slice(1) || (S.bisaBaca ? 'bok' : '');
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.k === k));
  const m = $('#main');
  try {
    if (!S.bisaBaca) m.innerHTML = `<div class="card"><h2>Selamat datang, ${esc(S.user.nama)}</h2><p class="muted">Jadwal, Surat Tugas, dan rincian uang Anda akan tampil di sini pada tahap berikutnya.</p></div>`;
    else if (k === 'bok') await viewBok(m);
    else if (k === 'rencana') await viewRencana(m);
    else if (k === 'jadwal') await viewJadwal(m);
    else if (k === 'kalkulator') await viewKalkulator(m);
    else if (k === 'riwayat') await viewRiwayat(m);
    else if (k === 'data') viewData(m);
    else if (S.meta[k]) await viewTabel(m, k);
  } catch (e) { m.innerHTML = `<div class="card err">${esc(e.message)}</div>`; }
}
window.onhashchange = route;

async function refs() {
  for (const r of ['pegawai', 'sumber_dana', 'lokasi']) if (S.meta[r]) S.refs[r] = await api('/api/data/' + r);
}

// ---------- tabel master generik ----------
function cell(f, v, row) {
  if (f.type === 'bool') return v ? 'Ya' : '<span class="badge off">Nonaktif</span>';
  if (f.type === 'rupiah') return rp(v);
  if (f.type === 'ref') { const x = (S.refs[f.ref] || []).find(o => o.id === v); return esc(x ? x[f.refLabel] : v ?? ''); }
  if (f.type === 'select') { const o = f.opts.find(o => (Array.isArray(o) ? o[0] : o) === v); return esc(o ? (Array.isArray(o) ? o[1] : o) : v ?? ''); }
  if (f.k === 'tingkat' && f.ro) return v ? `<span class="badge ${v}">Tingkat ${esc(v)}</span>` : '';
  return esc(v ?? '');
}
async function viewTabel(m, k) {
  const M = S.meta[k], rw = S.bisaTulis && !(k === 'users' && S.user.role !== 'kepala');
  await refs();
  const q = { teks: '', tahun: S.tahun };
  const load = async () => (await api('/api/data/' + k + (M.tahunFilter ? '?tahun=' + q.tahun : '')));
  let rows = await load();
  const cols = M.list.map(c => M.fields.find(f => f.k === c));
  const draw = () => {
    const t = q.teks.toLowerCase();
    const vis = rows.filter(r => !t || JSON.stringify(Object.values(r)).toLowerCase().includes(t) || cols.some(c => String(cell(c, r[c.k], r)).toLowerCase().includes(t)));
    $('#tb').innerHTML = vis.map(r => `<tr>${cols.map(c => `<td class="${c.type === 'rupiah' ? 'num' : ''}">${cell(c, r[c.k], r)}</td>`).join('')}
      ${rw ? `<td style="white-space:nowrap"><button class="btn small" data-e="${r.id}">Ubah</button>${M.noDelete ? '' : ` <button class="btn small danger" data-d="${r.id}">Hapus</button>`}</td>` : ''}</tr>`).join('')
      || `<tr><td colspan="${cols.length + 1}" class="muted">Tidak ada data.</td></tr>`;
    $('#cnt').textContent = vis.length + ' data';
  };
  m.innerHTML = `<h2>${esc(M.judul)}</h2>
   <div class="bar">
     <input id="cari" type="search" placeholder="Cari…" aria-label="Cari">
     ${M.tahunFilter ? `<label style="display:flex;gap:6px;align-items:center">Tahun <input id="thn" type="number" value="${q.tahun}" style="width:90px"></label>` : ''}
     <span class="muted" id="cnt"></span><span class="spacer" style="flex:1"></span>
     ${rw && !M.noCreate ? `<button class="btn primary" id="add">+ Tambah</button>` : ''}
     ${rw && !M.noCreate && k !== 'users' ? `<button class="btn" id="imp">Impor Excel</button><button class="btn" id="tpl">Template</button>` : ''}
   </div>
   ${k === 'pegawai' ? '<p class="muted">Tingkat biaya dihitung otomatis (Perbup Pasal 7): Eselon III / Gol. IV = C; Eselon IV / Gol. III, II, I & Non ASN = D.</p>' : ''}
   ${k === 'tarif' ? '<p class="muted">Tarif disimpan per tahun berlaku & dasar hukum. Jika Perbup berubah, tambahkan tarif tahun baru (atau impor dari Excel) — hitungan otomatis mengikuti.</p>' : ''}
   <div class="tbl-wrap"><table><thead><tr>${cols.map(c => `<th>${esc(c.label.replace(/ \(.*/, ''))}</th>`).join('')}${rw ? '<th></th>' : ''}</tr></thead><tbody id="tb"></tbody></table></div>`;
  draw();
  $('#cari').oninput = e => { q.teks = e.target.value; draw(); };
  if ($('#thn')) $('#thn').onchange = async e => { q.tahun = S.tahun = Number(e.target.value); rows = await load(); draw(); };
  const reload = async () => { await refs(); rows = await load(); draw(); };
  const form = (row = {}) => {
    const fields = M.fields.filter(f => !(f.ro && !row.id));
    return `<div class="grid2">` + fields.map(f => {
      const v = row[f.k] ?? f.def ?? (f.k === 'tahun' || f.k === 'tahun_berlaku' ? q.tahun : '');
      const ro = f.ro ? ' readonly' : '';
      let inp;
      if (f.type === 'bool') inp = `<input type="checkbox" name="${f.k}" ${v ? 'checked' : ''}>`;
      else if (f.type === 'select') inp = `<select name="${f.k}">${f.req ? '' : '<option value=""></option>'}${f.opts.map(o => { const [a, b] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(a)}" ${a === v ? 'selected' : ''}>${esc(b)}</option>`; }).join('')}</select>`;
      else if (f.type === 'ref') inp = `<select name="${f.k}"><option value=""></option>${(S.refs[f.ref] || []).filter(o => o.id !== row.id).map(o => `<option value="${o.id}" ${o.id === v ? 'selected' : ''}>${esc(o[f.refLabel])}</option>`).join('')}</select>`;
      else inp = `<input name="${f.k}" type="${f.type === 'number' || f.type === 'rupiah' ? 'number' : f.type === 'date' ? 'date' : f.type === 'password' ? 'password' : 'text'}" value="${f.type === 'password' ? '' : esc(v)}" ${f.type === 'rupiah' ? 'min="0" step="1"' : ''} ${f.req ? 'required' : ''}${ro}>`;
      return `<label ${f.k === 'kunci_tarif' || f.k === 'keterangan' || f.k === 'uraian' ? 'style="grid-column:1/-1"' : ''}>${esc(f.label)}${inp}</label>`;
    }).join('') + '</div>';
  };
  if ($('#add')) $('#add').onclick = () => dialog('Tambah ' + M.judul, form(), async d => { await api('/api/data/' + k, { method: 'POST', body: d }); toast('Tersimpan.'); await reload(); });
  if ($('#tpl')) $('#tpl').onclick = () => download('/api/template/' + k, `template_${k}.xlsx`);
  if ($('#imp')) $('#imp').onclick = () => dialog('Impor Excel — ' + M.judul, `<p class="muted">Gunakan <b>Template</b> (baris pertama = nama kolom). Baris yang kuncinya sama akan diperbarui, lainnya ditambahkan. Jika ada satu baris salah, seluruh impor dibatalkan.</p><input type="file" name="berkas" accept=".xlsx,.xls,.csv" required>`,
    async () => {
      const file = $('#dlgForm input[type=file]').files[0]; if (!file) throw new Error('Pilih berkas.');
      const b64 = btoa(new Uint8Array(await file.arrayBuffer()).reduce((s, b) => s + String.fromCharCode(b), ''));
      const r = await api('/api/import/' + k, { method: 'POST', body: { file: b64 } });
      toast(`Impor selesai: ${r.tambah} ditambah, ${r.ubah} diperbarui.`); await reload();
    }, 'Impor');
  $('#tb').onclick = e => {
    const id = Number(e.target.dataset.e || e.target.dataset.d); if (!id) return;
    const row = rows.find(r => r.id === id);
    if (e.target.dataset.e) dialog('Ubah ' + M.judul, form(row), async d => { await api(`/api/data/${k}/${id}`, { method: 'PUT', body: d }); toast('Perubahan disimpan.'); await reload(); });
    else dialog('Hapus data?', `<p>Data ini akan dihapus dan tercatat di riwayat. Untuk pegawai/lokasi sebaiknya <b>nonaktifkan</b>, bukan hapus.</p>`, async () => { await api(`/api/data/${k}/${id}`, { method: 'DELETE' }); toast('Dihapus.'); await reload(); }, 'Hapus');
  };
}

// ---------- Pagu Anggaran BOK ----------
const fmt = v => Number(v).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const volTxt = b => [[b.vol1, b.sat1], [b.vol2, b.sat2], [b.vol3, b.sat3]].filter(([v, s]) => Number(v) !== 1 || s).map(([v, s]) => `${fmt(v)}${s ? ' ' + esc(s) : ''}`).join(' × ') || '1';
S.bokTahun = 2027; S.bokOpen = new Set(); S.bokCari = '';

async function viewBok(m) {
  const T = S.bokTahun;
  const [tr, tahunList] = await Promise.all([api('/api/bok/' + T), api('/api/bok/tahun')]);
  const rw = S.bisaTulis, pagu = tr.pagu ? tr.pagu.pagu : 0, selisih = pagu - tr.total;
  const nR = tr.menu.reduce((s, x) => s + x.rincian.length, 0), nB = tr.menu.reduce((s, x) => s + x.rincian.reduce((a, r) => a + r.baris.length, 0), 0);
  const jenisList = [...new Set(tr.menu.flatMap(x => x.rincian.flatMap(r => r.baris.map(b => b.jenis_belanja))))];
  const q = S.bokCari.toLowerCase();
  const cocok = (...a) => !q || a.join(' ').toLowerCase().includes(q);
  const btn = (act, id, label, cls = '') => rw ? `<button class="btn small ${cls}" data-act="${act}" data-id="${id}">${label}</button>` : '';

  const barisRow = (b, r) => `<tr><td>${esc(b.komponen ?? '')}</td><td>${esc(b.jenis_belanja)}${b.kode_rekening ? `<br><span class="muted">${esc(b.kode_rekening)}</span>` : ''}</td>
    <td>${esc(b.uraian ?? '')}${b.satuan ? ` <span class="muted">(${esc(b.satuan)})</span>` : ''}</td><td>${volTxt(b)}</td><td class="num">${rp(b.unit_cost)}</td>
    <td class="num">${rp(b.jumlah)}${b.beda ? `<br><span class="warn" title="Jumlah dari berkas Excel tidak sama dengan volume × tarif">⚠ ≠ hitungan</span>` : ''}</td>
    ${rw ? `<td style="white-space:nowrap">${btn('ub-baris', b.id, 'Ubah')} ${btn('dup-baris', b.id, 'Salin')} ${btn('hps-baris', b.id, 'Hapus', 'danger')}</td>` : ''}</tr>`;

  const menus = tr.menu.map(mn => {
    const rinc = mn.rincian.map(r => {
      const bar = r.baris.filter(b => cocok(mn.nama, r.nama, b.komponen, b.jenis_belanja, b.uraian));
      if (q && !bar.length && !cocok(r.nama)) return '';
      return `<div class="rinc"><div class="rinc-h"><div><b>${esc(r.no ?? '')}. ${esc(r.nama)}</b><br><span class="muted">${r.baris.length} baris · ${rp(r.total)}</span></div>
        <div class="acts">${btn('tmb-baris', r.id, '+ Baris', 'primary')} ${btn('ub-rinc', r.id, 'Ubah')} ${btn('hps-rinc', r.id, 'Hapus', 'danger')}</div></div>
        ${bar.length ? `<div class="tbl-wrap"><table><thead><tr><th>Komponen</th><th>Jenis belanja</th><th>Uraian</th><th>Volume</th><th>Tarif</th><th>Jumlah</th>${rw ? '<th></th>' : ''}</tr></thead><tbody>${bar.map(b => barisRow(b, r)).join('')}</tbody></table></div>` : '<p class="muted" style="margin:6px 0">Belum ada baris biaya.</p>'}</div>`;
    }).join('');
    if (q && !rinc) return '';
    const persen = pagu ? (mn.total / pagu * 100).toFixed(1) : '0';
    return `<details class="menu" data-m="${mn.id}" ${S.bokOpen.has(mn.id) || q ? 'open' : ''}><summary><div class="sum-l"><b>Menu ${esc(mn.no ?? '')} — ${esc(mn.nama)}</b>
      <span class="muted">${mn.rincian.length} rincian · ${persen}% dari pagu</span></div><div class="sum-r"><b>${rp(mn.total)}</b></div></summary>
      <div class="acts" style="margin:8px 0">${btn('tmb-rinc', mn.id, '+ Rincian Menu', 'primary')} ${btn('ub-menu', mn.id, 'Ubah menu')} ${btn('hps-menu', mn.id, 'Hapus menu', 'danger')}</div>${rinc || '<p class="muted">Belum ada rincian menu.</p>'}</details>`;
  }).join('');

  m.innerHTML = `<h2>Pagu Anggaran BOK</h2><p class="muted">Rencana Anggaran Biaya (RAB) BOK Puskesmas: Menu → Rincian Menu → baris biaya. Baris-baris inilah yang nanti dipakai Perencanaan, Panjar, dan SPJ.</p>
  <div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="bThn" type="number" value="${T}" style="width:90px" list="bThnList"></label>
   <datalist id="bThnList">${tahunList.map(t => `<option value="${t}">`).join('')}</datalist>
   <input id="bCari" type="search" placeholder="Cari kegiatan / belanja…" value="${esc(S.bokCari)}" aria-label="Cari">
   <span style="flex:1"></span>
   ${rw ? `<button class="btn primary" data-act="tmb-menu">+ Menu</button><button class="btn" data-act="imp-rab">Impor RAB Excel</button>` : ''}
   <button class="btn" data-act="exp-rab">Ekspor Excel</button>
   ${rw && tr.menu.length ? `<button class="btn danger" data-act="hps-semua">Kosongkan</button>` : ''}</div>
  <div class="kv">
   <div class="card"><span class="muted">${esc(tr.pagu ? tr.pagu.jenis : 'Pagu')} ${T}</span><b>${rp(pagu)}</b>${rw ? `<button class="btn small" data-act="ub-pagu">${tr.pagu ? 'Ubah pagu' : 'Atur pagu'}</button>` : ''}</div>
   <div class="card"><span class="muted">Total RAB (jumlah baris)</span><b>${rp(tr.total)}</b><span class="muted">${tr.menu.length} menu · ${nR} rincian · ${nB} baris</span></div>
   <div class="card"><span class="muted">${selisih < 0 ? 'Melebihi pagu' : selisih === 0 ? 'Selisih' : 'Belum teralokasi'}</span><b class="${selisih < 0 ? 'err' : selisih === 0 ? 'okc' : 'warn'}">${rp(Math.abs(selisih))}</b>
    <span class="muted">${selisih === 0 && pagu ? '✓ RAB sama dengan pagu' : selisih < 0 ? 'Kurangi baris atau naikkan pagu' : ''}</span></div></div>
  ${tr.menu.length ? menus : `<div class="card"><p>Belum ada RAB BOK untuk tahun ${T}.</p>${rw ? '<p class="muted">Tambah menu satu per satu, atau gunakan <b>Impor RAB Excel</b> (format RAB BOK Puskesmas).</p>' : ''}</div>`}`;

  const reload = async () => { await viewBok(m); };
  $('#bThn').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); };
  $('#bCari').oninput = e => { S.bokCari = e.target.value; clearTimeout(viewBok.t); viewBok.t = setTimeout(async () => { await reload(); const c = $('#bCari'); c.focus(); c.setSelectionRange(c.value.length, c.value.length); }, 300); };
  m.querySelectorAll('details.menu').forEach(d => d.addEventListener('toggle', () => { const id = Number(d.dataset.m); d.open ? S.bokOpen.add(id) : S.bokOpen.delete(id); }));

  const menuById = id => tr.menu.find(x => x.id === id);
  const rincById = id => tr.menu.flatMap(x => x.rincian).find(x => x.id === id);
  const barisById = id => tr.menu.flatMap(x => x.rincian.flatMap(r => r.baris)).find(x => x.id === id);
  const done = msg => async () => { toast(msg); await reload(); };
  const formNoNama = (o = {}, lblNo, lblNama) => `<div class="grid2"><label>${lblNo}<input name="no" value="${esc(o.no ?? '')}"></label></div><label>${lblNama}<input name="nama" value="${esc(o.nama ?? '')}" required></label>`;
  function formBaris(b = {}) {
    const v = (k, d = '') => esc(b[k] ?? d);
    return `<datalist id="jb">${jenisList.map(j => `<option value="${esc(j)}">`).join('')}</datalist>
    <label>Komponen / sub-kegiatan (opsional)<input name="komponen" value="${v('komponen')}"></label>
    <div class="grid2"><label>Jenis belanja<input name="jenis_belanja" list="jb" value="${v('jenis_belanja')}" required></label>
     <label>Kode rekening (opsional)<input name="kode_rekening" value="${v('kode_rekening')}"></label></div>
    <div class="grid2"><label>Uraian komponen<input name="uraian" value="${v('uraian')}" placeholder="mis. Transport Petugas"></label>
     <label>Satuan<input name="satuan" value="${v('satuan')}" placeholder="mis. Orang/Hari"></label></div>
    ${[1, 2, 3].map(i => `<div class="grid2"><label>Volume ${i}<input name="vol${i}" type="number" min="0" step="any" value="${v('vol' + i, 1)}"></label><label>Satuan volume ${i}<input name="sat${i}" value="${v('sat' + i)}"></label></div>`).join('')}
    <label>Tarif / unit cost (Rp)<input name="unit_cost" type="number" min="0" step="1" value="${v('unit_cost', 0)}"></label>
    <div class="card" style="padding:10px">Jumlah = Vol1 × Vol2 × Vol3 × Tarif = <b id="prevJ">${rp(b.jumlah ?? 0)}</b></div>`;
  }
  function liveJumlah() {
    const f = $('#dlgForm'), calc = () => { const g = n => Number(f.elements[n].value) || 0; $('#prevJ').textContent = rp(Math.round(g('vol1') * g('vol2') * g('vol3') * g('unit_cost'))); };
    f.addEventListener('input', calc);
  }

  m.onclick = async e => {
    const el = e.target.closest('[data-act]'); if (!el) return;
    e.preventDefault(); const act = el.dataset.act, id = Number(el.dataset.id);
    if (act === 'tmb-menu') dialog('Tambah Menu', formNoNama({}, 'No. menu', 'Nama menu'), async d => { await api('/api/bok/menu', { method: 'POST', body: { ...d, tahun: T } }); await done('Menu ditambahkan.')(); });
    else if (act === 'ub-menu') { const x = menuById(id); dialog('Ubah Menu', formNoNama(x, 'No. menu', 'Nama menu'), async d => { await api('/api/bok/menu/' + id, { method: 'PUT', body: d }); await done('Menu diubah.')(); }); }
    else if (act === 'hps-menu') { const x = menuById(id); dialog('Hapus menu?', `<p>Menu <b>${esc(x.nama)}</b> beserta ${x.rincian.length} rincian dan ${x.rincian.reduce((s, r) => s + r.baris.length, 0)} baris (${rp(x.total)}) akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/bok/menu/' + id, { method: 'DELETE' }); await done('Menu dihapus.')(); }, 'Hapus'); }
    else if (act === 'tmb-rinc') dialog('Tambah Rincian Menu', formNoNama({}, 'No. rincian', 'Nama rincian menu'), async d => { S.bokOpen.add(id); await api('/api/bok/rincian', { method: 'POST', body: { ...d, menu_id: id } }); await done('Rincian ditambahkan.')(); });
    else if (act === 'ub-rinc') { const x = rincById(id); dialog('Ubah Rincian Menu', formNoNama(x, 'No. rincian', 'Nama rincian menu'), async d => { await api('/api/bok/rincian/' + id, { method: 'PUT', body: d }); await done('Rincian diubah.')(); }); }
    else if (act === 'hps-rinc') { const x = rincById(id); dialog('Hapus rincian menu?', `<p><b>${esc(x.nama)}</b> beserta ${x.baris.length} baris (${rp(x.total)}) akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/bok/rincian/' + id, { method: 'DELETE' }); await done('Rincian dihapus.')(); }, 'Hapus'); }
    else if (act === 'tmb-baris') { dialog('Tambah Baris Biaya', formBaris(), async d => { await api('/api/bok/baris', { method: 'POST', body: { ...d, rincian_id: id } }); await done('Baris ditambahkan.')(); }); liveJumlah(); }
    else if (act === 'ub-baris') { dialog('Ubah Baris Biaya', formBaris(barisById(id)), async d => { await api('/api/bok/baris/' + id, { method: 'PUT', body: d }); await done('Baris diubah.')(); }); liveJumlah(); }
    else if (act === 'dup-baris') { await api(`/api/bok/baris/${id}/duplikat`, { method: 'POST' }); await done('Baris disalin.')(); }
    else if (act === 'hps-baris') { const b = barisById(id); dialog('Hapus baris?', `<p>${esc(b.komponen || b.uraian || b.jenis_belanja)} — ${rp(b.jumlah)} akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/bok/baris/' + id, { method: 'DELETE' }); await done('Baris dihapus.')(); }, 'Hapus'); }
    else if (act === 'ub-pagu') dialog('Pagu BOK ' + T, `<label>Jenis<select name="jenis">${['Pagu Indikatif', 'Pagu Definitif', 'Pagu Perubahan'].map(j => `<option ${tr.pagu && tr.pagu.jenis === j ? 'selected' : ''}>${j}</option>`).join('')}</select></label>
      <label>Jumlah pagu (Rp)<input name="pagu" type="number" min="0" step="1" required value="${pagu}"></label><label>Keterangan<input name="keterangan" value="${esc(tr.pagu?.keterangan ?? '')}"></label>`,
      async d => { await api(`/api/bok/${T}/pagu`, { method: 'PUT', body: d }); await done('Pagu disimpan.')(); });
    else if (act === 'hps-semua') dialog('Kosongkan RAB BOK ' + T + '?', `<p>Seluruh ${tr.menu.length} menu, ${nR} rincian, dan ${nB} baris tahun ${T} akan dihapus (pagu tetap). Tercatat di riwayat.</p>`, async () => { await api('/api/bok/' + T, { method: 'DELETE' }); await done('RAB dikosongkan.')(); }, 'Kosongkan');
    else if (act === 'exp-rab') download(`/api/bok/${T}/export.xlsx`, `RAB_BOK_${T}.xlsx`);
    else if (act === 'imp-rab') {
      let hasil = null;
      dialog('Impor RAB BOK', `<p class="muted">Pilih berkas RAB BOK Puskesmas (.xlsx). Menu, rincian, dan baris dibaca otomatis; pagu diisi dari "Jumlah Total Kebutuhan Anggaran" bila belum ada.</p>
        <input type="file" name="berkas" accept=".xlsx,.xls" required><label>Tahun<input name="tahun" type="number" value="${T}"></label>
        <label style="grid-auto-flow:column;justify-content:start;align-items:center;gap:8px"><input type="checkbox" name="ganti" ${tr.menu.length ? 'checked' : ''}> Ganti RAB tahun ini bila sudah ada</label>`,
        async d => {
          const file = $('#dlgForm input[type=file]').files[0]; if (!file) throw new Error('Pilih berkas.');
          const b64 = btoa(new Uint8Array(await file.arrayBuffer()).reduce((s, x) => s + String.fromCharCode(x), ''));
          hasil = await api('/api/bok/import', { method: 'POST', body: { file: b64, tahun: Number(d.tahun), ganti: d.ganti } });
          S.bokTahun = hasil.tahun; await reload();
          setTimeout(() => dialog('Impor selesai', `<p>Tahun <b>${hasil.tahun}</b>: ${hasil.menu} menu, ${hasil.baris} baris, total <b>${rp(hasil.total)}</b>.</p>${(hasil.peringatan || []).map(p => `<p class="warn">⚠ ${esc(p)}</p>`).join('')}`), 150);
        }, 'Impor');
    }
  };
}

// ---------- Perencanaan (RPK/POA) ----------
const BLN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];
const STATUS = ['Draft', 'Diajukan', 'Ditolak', 'Disetujui', 'Terjadwal', 'Terlaksana', 'SPJ Selesai'];
S.rcTab = 'daftar'; S.rcBulan = ''; S.rcStatus = '';

async function viewRencana(m) {
  const T = S.bokTahun, rw = S.user.role !== 'pegawai', kepala = S.user.role === 'kepala';
  await refs();
  const qs = `tahun=${T}` + (S.rcBulan ? `&bulan=${S.rcBulan}` : '') + (S.rcStatus ? `&status=${encodeURIComponent(S.rcStatus)}` : '');
  const [list, poa, tr] = await Promise.all([api('/api/rencana?' + qs), api('/api/rencana/poa?tahun=' + T), api('/api/bok/' + T)]);
  const aktif = x => x.status !== 'Ditolak';
  const semua = S.rcBulan || S.rcStatus ? await api(`/api/rencana?tahun=${T}`) : list;
  const totalRencana = semua.filter(aktif).reduce((s, x) => s + x.estimasi, 0), disetujui = semua.filter(x => ['Disetujui', 'Terjadwal', 'Terlaksana', 'SPJ Selesai'].includes(x.status)).reduce((s, x) => s + x.estimasi, 0);
  const pagu = tr.pagu ? tr.pagu.pagu : 0;
  const bdg = s => `<span class="badge st-${s.replace(/ /g, '')}">${s}</span>`;

  const aksi = r => {
    const b = (a, l, c = '') => `<button class="btn small ${c}" data-a="${a}" data-id="${r.id}">${l}</button>`;
    if (r.status === 'Draft' && r.bisa_ubah) return [b('ubah', 'Ubah'), b('ajukan', 'Ajukan', 'primary'), b('hapus', 'Hapus', 'danger')].join(' ');
    if (r.status === 'Diajukan') return [r.bisa_ubah ? b('tarik', 'Tarik') : '', kepala ? b('setuju', 'Setujui', 'primary') + ' ' + b('tolak', 'Tolak', 'danger') : ''].join(' ');
    if (r.status === 'Ditolak' && r.bisa_ubah) return b('revisi', 'Revisi');
    if (r.status === 'Disetujui' && kepala) return b('batal', 'Batalkan persetujuan');
    return '';
  };
  const baris = list.map(r => `<tr><td>${BLN[r.bulan - 1].slice(0, 3)}</td>
    <td><b>${esc(r.kegiatan)}</b><br><span class="muted">${esc(r.rincian_no ?? '')}. ${esc(r.rincian)} · ${esc(r.pos_uraian ?? r.jenis_belanja)}</span>${r.alasan_tolak ? `<br><span class="err">Ditolak: ${esc(r.alasan_tolak)}</span>` : ''}</td>
    <td>${esc(r.lokasi ?? '–')}</td><td>${r.jenis_perjalanan ? `${r.jumlah_petugas} org × ${r.jumlah_hari} hr × ${r.frekuensi}x<br><span class="muted">Tk. ${r.tingkat}${r.durasi === 'le8' ? ' · ≤8 jam' : ''}</span>` : '–'}</td>
    <td class="num">${rp(r.estimasi)}</td><td>${bdg(r.status)}</td>${rw ? `<td style="white-space:nowrap">${aksi(r)}</td>` : ''}</tr>`).join('');

  const poaRows = []; let lastMenu = null; const tot = Array(12).fill(0);
  poa.forEach(x => {
    if (x.menu !== lastMenu) { poaRows.push(`<tr class="grp"><td colspan="16">Menu ${esc(x.menu_no ?? '')} — ${esc(x.menu)}</td></tr>`); lastMenu = x.menu; }
    x.bulan.forEach((v, i) => tot[i] += v);
    poaRows.push(`<tr><td>${esc(x.rincian_no ?? '')}. ${esc(x.rincian)}</td><td class="num">${rp(x.pagu)}</td>${x.bulan.map(v => `<td class="num">${v ? rp(v) : '<span class="muted">·</span>'}</td>`).join('')}<td class="num"><b>${rp(x.total)}</b></td><td class="num ${x.sisa < 0 ? 'err' : ''}">${rp(x.sisa)}</td></tr>`);
  });

  m.innerHTML = `<h2>Perencanaan Kegiatan (RPK/POA) BOK</h2>
  <p class="muted">Setiap rencana terikat ke satu baris RAB. Estimasi dihitung otomatis dari tarif Perbup, dan ditolak bila melebihi pagu baris atau pagu BOK.</p>
  <div class="kv"><div class="card"><span class="muted">Pagu BOK ${T}</span><b>${rp(pagu)}</b></div>
   <div class="card"><span class="muted">Total direncanakan</span><b>${rp(totalRencana)}</b><span class="muted">${pagu ? (totalRencana / pagu * 100).toFixed(1) : 0}% dari pagu</span></div>
   <div class="card"><span class="muted">Sudah disetujui</span><b>${rp(disetujui)}</b></div>
   <div class="card"><span class="muted">Sisa pagu belum direncanakan</span><b class="${pagu - totalRencana < 0 ? 'err' : ''}">${rp(pagu - totalRencana)}</b></div></div>
  <div class="tabs"><button class="tab ${S.rcTab === 'daftar' ? 'on' : ''}" data-tab="daftar">Daftar Rencana</button><button class="tab ${S.rcTab === 'poa' ? 'on' : ''}" data-tab="poa">Matriks POA per Bulan</button></div>
  ${S.rcTab === 'daftar' ? `<div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="rThn" type="number" value="${T}" style="width:90px"></label>
    <select id="rBln"><option value="">Semua bulan</option>${BLN.map((b, i) => `<option value="${i + 1}" ${String(S.rcBulan) === String(i + 1) ? 'selected' : ''}>${b}</option>`).join('')}</select>
    <select id="rSt"><option value="">Semua status</option>${STATUS.map(s => `<option ${S.rcStatus === s ? 'selected' : ''}>${s}</option>`).join('')}</select>
    <span style="flex:1"></span>${rw ? '<button class="btn primary" data-a="tambah">+ Rencana Kegiatan</button>' : ''}</div>
   <div class="tbl-wrap"><table><thead><tr><th>Bln</th><th>Kegiatan / pos anggaran</th><th>Lokasi</th><th>Petugas</th><th>Estimasi</th><th>Status</th>${rw ? '<th></th>' : ''}</tr></thead><tbody>${baris || `<tr><td colspan="7" class="muted">Belum ada rencana.</td></tr>`}</tbody></table></div>`
  : `<div class="tbl-wrap"><table class="poa"><thead><tr><th>Kegiatan (rincian menu)</th><th>Pagu RAB</th>${BLN.map(b => `<th>${b.slice(0, 3)}</th>`).join('')}<th>Total</th><th>Sisa</th></tr></thead><tbody>${poaRows.join('') || '<tr><td colspan="16" class="muted">Belum ada RAB.</td></tr>'}
   <tr class="grp"><td>Jumlah</td><td class="num">${rp(poa.reduce((s, x) => s + x.pagu, 0))}</td>${tot.map(v => `<td class="num">${rp(v)}</td>`).join('')}<td class="num">${rp(tot.reduce((a, b) => a + b, 0))}</td><td class="num">${rp(poa.reduce((s, x) => s + x.sisa, 0))}</td></tr></tbody></table></div>
   <p class="muted">Rencana berstatus Ditolak tidak dihitung.</p>`}`;

  const reload = () => viewRencana(m);
  m.querySelectorAll('[data-tab]').forEach(t => t.onclick = () => { S.rcTab = t.dataset.tab; reload(); });
  if ($('#rThn')) { $('#rThn').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); }; $('#rBln').onchange = e => { S.rcBulan = e.target.value; reload(); }; $('#rSt').onchange = e => { S.rcStatus = e.target.value; reload(); }; }

  const ubahStatus = async (id, ke, alasan) => { await api(`/api/rencana/${id}/status`, { method: 'POST', body: { ke, alasan } }); toast('Status: ' + ke); await reload(); };
  async function formRencana(r) {
    const opsi = await api('/api/rencana/opsi?tahun=' + T);
    if (!opsi.length) return toast('Belum ada RAB BOK untuk tahun ini. Isi dulu di Pagu Anggaran BOK.', 1);
    const lok = S.refs.lokasi.filter(l => l.aktif), v = (k, d = '') => esc(r?.[k] ?? d);
    const grup = []; opsi.forEach(o => { let g = grup.find(x => x.id === o.rincian_id); if (!g) grup.push(g = { id: o.rincian_id, label: `Menu ${o.menu_no ?? ''} › ${o.rincian_no ?? ''}. ${o.rincian}`, items: [] }); g.items.push(o); });
    const optPos = grup.map(g => `<optgroup label="${esc(g.label.slice(0, 90))}">${g.items.map(o => `<option value="${o.id}" ${r?.baris_id === o.id ? 'selected' : ''}>${esc((o.komponen ? o.komponen + ' · ' : '') + (o.uraian || o.jenis_belanja))} — sisa ${rp(o.sisa + (r?.baris_id === o.id ? r.estimasi : 0))}</option>`).join('')}</optgroup>`).join('');
    dialog(r ? 'Ubah Rencana Kegiatan' : 'Tambah Rencana Kegiatan', `
     <div class="grid2"><label>Bulan pelaksanaan<select name="bulan">${BLN.map((b, i) => `<option value="${i + 1}" ${(r?.bulan ?? new Date().getMonth() + 1) === i + 1 ? 'selected' : ''}>${b}</option>`).join('')}</select></label>
      <label>Kode rekening (opsional)<input name="kode_rekening" value="${v('kode_rekening')}"></label></div>
     <label>Pos anggaran (baris RAB BOK)<select name="baris_id" required><option value="">— pilih —</option>${optPos}</select></label>
     <label>Nama kegiatan<input name="kegiatan" value="${v('kegiatan')}" placeholder="otomatis dari rincian menu bila kosong"></label>
     <div id="secT"><div class="grid2">
      <label>Lokasi tujuan<select name="lokasi_id"><option value="">— pilih —</option>${lok.map(l => `<option value="${l.id}" ${r?.lokasi_id === l.id ? 'selected' : ''}>${esc(l.nama)}</option>`).join('')}</select></label>
      <label>Durasi (dalam kota)<select name="durasi"><option value="gt8" ${r?.durasi !== 'le8' ? 'selected' : ''}>Lebih dari 8 jam</option><option value="le8" ${r?.durasi === 'le8' ? 'selected' : ''}>Sampai dengan 8 jam</option></select></label>
      <label>Jumlah petugas<input name="jumlah_petugas" type="number" min="1" value="${v('jumlah_petugas', 2)}"></label>
      <label>Jumlah hari per pelaksanaan<input name="jumlah_hari" type="number" min="1" value="${v('jumlah_hari', 1)}"></label>
      <label>Frekuensi (berapa kali/lokasi)<input name="frekuensi" type="number" min="1" value="${v('frekuensi', 1)}"></label>
      <label>Tingkat biaya petugas<select name="tingkat"><option ${r?.tingkat !== 'C' ? 'selected' : ''}>D</option><option ${r?.tingkat === 'C' ? 'selected' : ''}>C</option></select></label>
      <label>Kendaraan (antar kecamatan)<select name="roda"><option value="2" ${r?.roda !== 4 ? 'selected' : ''}>Roda 2</option><option value="4" ${r?.roda === 4 ? 'selected' : ''}>Roda 4</option></select></label>
      <label>Penginapan<select name="menginap"><option value="tidak">Tidak menginap</option><option value="hotel" ${r?.menginap === 'hotel' ? 'selected' : ''}>Hotel (maks. tarif)</option><option value="tidak_hotel" ${r?.menginap === 'tidak_hotel' ? 'selected' : ''}>Lumpsum tanpa hotel</option></select></label>
      <label>Transport lokal tambahan/orang (Rp)<input name="transport_manual" type="number" min="0" value="${v('transport_manual', 0)}"></label>
      <label style="align-content:end"><span><input type="checkbox" name="pp" ${r?.pp === 0 ? '' : 'checked'}> Pulang-pergi</span></label></div></div>
     <div id="secM"><label>Estimasi biaya (Rp) — bukan perjalanan dinas<input name="estimasi_manual" type="number" min="0" value="${v('estimasi_manual', 0)}"></label></div>
     <label>Catatan<input name="catatan" value="${v('catatan')}"></label>
     <div id="prev" class="card prev">Pilih pos anggaran untuk melihat estimasi.</div>`,
      async d => { const res = await api(r ? `/api/rencana/${r.id}` : '/api/rencana', { method: r ? 'PUT' : 'POST', body: d }); toast('Rencana disimpan.' + (res.peringatan?.length ? ' ⚠ ' + res.peringatan[0] : '')); await reload(); });
    const f = $('#dlgForm'), ok = $('#dlgOk'); let tm;
    const koleksi = () => { const d = {}; [...f.elements].forEach(e => { if (e.name) d[e.name] = e.type === 'checkbox' ? e.checked : e.value; }); if (r) d.id = r.id; return d; };
    const segarkan = async () => {
      const o = opsi.find(x => x.id === Number(f.elements.baris_id.value));
      $('#secT').style.display = !o || o.perjalanan ? '' : 'none'; $('#secM').style.display = o && !o.perjalanan ? '' : 'none';
      if (!o) { ok.disabled = true; return; }
      if (!f.elements.kegiatan.value || f.elements.kegiatan.dataset.auto) { f.elements.kegiatan.value = o.komponen || o.rincian; f.elements.kegiatan.dataset.auto = 1; }
      if (!f.elements.kode_rekening.value && o.kode_rekening) f.elements.kode_rekening.value = o.kode_rekening;
      const a = await api('/api/rencana/preview', { method: 'POST', body: koleksi() });
      const L = (t, v, bad) => `<div class="pl"><span>${t}</span><b class="${bad ? 'err' : ''}">${v}</b></div>`;
      $('#prev').innerHTML = `<div class="pl big"><span>Estimasi biaya</span><b>${rp(a.estimasi ?? 0)}</b></div>
       ${a.rincian?.per_orang?.length ? `<div class="muted" style="font-size:.85em">Per orang: ${a.rincian.per_orang.map(x => `${esc(x.uraian)} ${x.volume}×${rp(x.tarif)}`).join(' + ')} = ${rp(a.rincian.total_per_orang)} · pengali ${a.rincian.pengali} (petugas × frekuensi)</div>` : ''}
       ${a.pos ? L('Pagu pos anggaran', rp(a.pos.pagu)) + L('Sudah direncanakan', rp(a.pos.terpakai)) + L('Sisa pos setelah rencana ini', rp(a.pos.sisa_sesudah), a.pos.sisa_sesudah < 0) + L('Sisa kegiatan (semua baris)', rp(a.kegiatan.sisa_sesudah), a.kegiatan.sisa_sesudah < 0) + (a.bok.pagu !== null ? L('Sisa pagu BOK', rp(a.bok.sisa_sesudah), a.bok.sisa_sesudah < 0) : '') : ''}
       ${(a.galat || []).map(g => `<p class="err">✖ ${esc(g)}</p>`).join('')}${(a.peringatan || []).map(p => `<p class="warn">⚠ ${esc(p)}</p>`).join('')}`;
      ok.disabled = !a.ok;
    };
    f.addEventListener('input', e => { if (e.target.name === 'kegiatan') delete e.target.dataset.auto; clearTimeout(tm); tm = setTimeout(segarkan, 250); });
    f.addEventListener('change', () => { clearTimeout(tm); tm = setTimeout(segarkan, 50); });
    ok.disabled = true; segarkan();
  }

  m.onclick = async e => {
    const el = e.target.closest('[data-a]'); if (!el) return; const a = el.dataset.a, id = Number(el.dataset.id), r = list.find(x => x.id === id);
    try {
      if (a === 'tambah') await formRencana();
      else if (a === 'ubah') await formRencana(r);
      else if (a === 'ajukan') await ubahStatus(id, 'Diajukan');
      else if (a === 'tarik' || a === 'revisi') await ubahStatus(id, 'Draft');
      else if (a === 'setuju') await ubahStatus(id, 'Disetujui');
      else if (a === 'batal') dialog('Batalkan persetujuan?', '<p>Rencana kembali ke Draft agar bisa diubah.</p>', async () => { await ubahStatus(id, 'Draft'); }, 'Batalkan');
      else if (a === 'tolak') dialog('Tolak rencana', '<label>Alasan penolakan<input name="alasan" required></label>', async d => { await ubahStatus(id, 'Ditolak', d.alasan); }, 'Tolak');
      else if (a === 'hapus') dialog('Hapus rencana?', `<p>${esc(r.kegiatan)} (${rp(r.estimasi)}) akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/rencana/' + id, { method: 'DELETE' }); toast('Dihapus.'); await reload(); }, 'Hapus');
    } catch (x) { toast(x.message, 1); }
  };
}

// ---------- Jadwal Dinas Luar (kalender + tabel + anti-doubling) ----------
const pad = n => String(n).padStart(2, '0');
const isoD = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const tglID = s => s ? s.slice(8, 10) + '-' + s.slice(5, 7) + '-' + s.slice(0, 4) : '';
const HARI = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'];
S.jwYM = null; S.jwTab = 'kalender'; S.jwF = { pegawai_id: '', lokasi_id: '', program: '', sumber_dana_id: '', status: '' };

async function viewJadwal(m) {
  const rw = S.user.role !== 'pegawai', kepala = S.user.role === 'kepala';
  await refs();
  if (!S.jwYM) { const n = new Date(); S.jwYM = `${n.getFullYear()}-${pad(n.getMonth() + 1)}`; }
  const [Y, M] = S.jwYM.split('-').map(Number), F = S.jwF;
  const dari = `${Y}-${pad(M)}-01`, jmlHari = new Date(Y, M, 0).getDate(), sampai = `${Y}-${pad(M)}-${pad(jmlHari)}`;
  const qs = new URLSearchParams({ dari, sampai }); Object.entries(F).forEach(([k, v]) => v && qs.set(k, v));
  const [list, libur, cuti] = await Promise.all([api('/api/jadwal?' + qs), api('/api/data/libur'), api('/api/data/cuti')]);
  const liburMap = Object.fromEntries(libur.map(x => [x.tanggal, x.keterangan || 'Libur']));
  const pegAktif = S.refs.pegawai.filter(p => p.aktif);
  const unit = [...new Set(pegAktif.flatMap(p => [p.program, p.ruangan]).filter(Boolean))].sort();
  const bdg = s => `<span class="badge st-${s}">${s}</span>`;
  const namaSingkat = n => n.split(',')[0];

  const aksi = j => {
    const a = [];
    if (j.status === 'Diusulkan' && j.bisa_ubah) a.push(['Ubah', () => formJadwal(j), '']);
    if (j.status === 'Diusulkan' && kepala) a.push(['Setujui', () => ubahStatus(j, 'Disetujui'), 'primary'], ['Tolak', () => alasanStatus(j, 'Ditolak'), 'danger']);
    if ((j.status === 'Diusulkan' && j.bisa_ubah) || (j.status === 'Disetujui' && kepala)) a.push(['Batalkan', () => alasanStatus(j, 'Dibatalkan'), 'danger']);
    return a;
  };
  async function ubahStatus(j, ke, alasan) { await api(`/api/jadwal/${j.id}/status`, { method: 'POST', body: { ke, alasan } }); toast('Jadwal ' + ke.toLowerCase() + '.'); await reload(); }
  const alasanStatus = (j, ke) => dialog(ke + ' jadwal', '<label>Alasan<input name="alasan" required></label>', async d => { await ubahStatus(j, ke, d.alasan); }, ke === 'Ditolak' ? 'Tolak' : 'Batalkan');
  const detail = j => {
    dialog('Detail Jadwal #' + j.id, `<div class="kvl"><b>Kegiatan</b><span>${esc(j.kegiatan)}</span><b>Tanggal</b><span>${tglID(j.mulai)}${j.selesai !== j.mulai ? ' s.d. ' + tglID(j.selesai) : ''}</span>
      <b>Lokasi</b><span>${esc(j.lokasi)}</span><b>Sumber dana</b><span>${esc(j.dana)}</span><b>Durasi</b><span>${j.durasi === 'le8' ? '≤ 8 jam (transport lokal)' : '> 8 jam'}</span>
      <b>Status</b><span>${bdg(j.status)}</span><b>No. ST</b><span>${esc(j.no_st || 'belum terbit')}</span>
      <b>Petugas</b><span>${j.petugas.map(p => `${esc(namaSingkat(p.nama))} <span class="muted">(${esc(p.ruangan || p.program || 'Tk. ' + p.tingkat)})</span>`).join('<br>')}</span>
      ${j.alasan ? `<b>Alasan</b><span>${esc(j.alasan)}</span>` : ''}${j.catatan ? `<b>Catatan</b><span>${esc(j.catatan)}</span>` : ''}</div><div class="acts" id="dAksi"></div>`);
    const box = $('#dAksi'); aksi(j).forEach(([l, fn, c]) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'btn small ' + c; b.textContent = l; b.onclick = () => { $('#dlg').close(); fn(); }; box.appendChild(b); });
  };

  // ----- kalender -----
  const hariKal = () => {
    const first = new Date(Y, M - 1, 1), off = (first.getDay() + 6) % 7, today = isoD(new Date());
    let h = HARI.map(x => `<div class="cal-h">${x}</div>`).join('');
    for (let i = 0; i < off; i++) h += '<div class="day pad"></div>';
    for (let d = 1; d <= jmlHari; d++) {
      const iso = `${Y}-${pad(M)}-${pad(d)}`, wd = (off + d - 1) % 7;
      const items = list.filter(j => j.mulai <= iso && j.selesai >= iso);
      const cutiAda = F.pegawai_id ? cuti.find(c => c.pegawai_id === Number(F.pegawai_id) && c.mulai <= iso && c.selesai >= iso) : null;
      h += `<div class="day ${wd >= 5 ? 'we' : ''} ${liburMap[iso] ? 'lib' : ''} ${iso === today ? 'today' : ''} ${items.length || liburMap[iso] || cutiAda ? '' : 'kosong'}" data-d="${iso}">
        <div class="dn"><span class="dw">${HARI[wd]}, </span>${d}${liburMap[iso] ? `<em title="${esc(liburMap[iso])}">${esc(liburMap[iso].slice(0, 22))}</em>` : ''}</div>
        ${cutiAda ? `<div class="chip cuti">Cuti: ${esc(cutiAda.keterangan || '')}</div>` : ''}
        ${items.map(j => `<button class="chip st-${j.status}" data-j="${j.id}" title="${esc(j.kegiatan)} — ${esc(j.lokasi)}"><b>${esc(j.lokasi.replace(/^Kelurahan /, 'Kel. ').slice(0, 20))}</b> ${esc(j.kegiatan.slice(0, 34))} · ${j.petugas.length} org</button>`).join('')}</div>`;
    }
    return `<div class="cal">${h}</div>`;
  };
  const tabel = () => `<div class="tbl-wrap"><table><thead><tr><th>Tanggal</th><th>Kegiatan</th><th>Lokasi</th><th>Petugas</th><th>Dana</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(j => `<tr><td style="white-space:nowrap">${tglID(j.mulai)}${j.selesai !== j.mulai ? '<br>s.d. ' + tglID(j.selesai) : ''}</td><td><b>${esc(j.kegiatan)}</b>${j.no_st ? `<br><span class="muted">ST ${esc(j.no_st)}</span>` : ''}</td>
      <td>${esc(j.lokasi)}</td><td>${j.petugas.map(p => esc(namaSingkat(p.nama))).join(', ')}</td><td>${esc(j.dana)}</td><td>${bdg(j.status)}</td>
      <td style="white-space:nowrap"><button class="btn small" data-det="${j.id}">Detail</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">Tidak ada jadwal pada filter ini.</td></tr>'}</tbody></table></div>`;

  const opt = (v, l, sel) => `<option value="${esc(v)}" ${String(sel) === String(v) ? 'selected' : ''}>${esc(l)}</option>`;
  m.innerHTML = `<h2>Jadwal Dinas Luar</h2>
  <p class="muted">Jadwal dibuat dari rencana yang sudah disetujui. Sistem menolak bentrok petugas, kegiatan ganda, tanggal libur/cuti, dan uang harian ganda lintas sumber dana.</p>
  <div class="bar"><button class="btn" id="jPrev" aria-label="Bulan sebelumnya">‹</button><b style="min-width:150px;text-align:center">${BLN[M - 1]} ${Y}</b><button class="btn" id="jNext" aria-label="Bulan berikutnya">›</button><button class="btn small" id="jNow">Bulan ini</button>
   <span style="flex:1"></span>${rw ? '<button class="btn primary" id="jAdd">+ Jadwal</button>' : ''}</div>
  <div class="bar filt">
   <select id="fPeg"><option value="">Semua pegawai</option>${pegAktif.map(p => opt(p.id, namaSingkat(p.nama), F.pegawai_id)).join('')}</select>
   <select id="fLok"><option value="">Semua lokasi</option>${S.refs.lokasi.filter(l => l.aktif).map(l => opt(l.id, l.nama, F.lokasi_id)).join('')}</select>
   <select id="fProg"><option value="">Semua program/ruangan</option>${unit.map(u => opt(u, u, F.program)).join('')}</select>
   <select id="fDana"><option value="">Semua sumber dana</option>${S.refs.sumber_dana.map(s => opt(s.id, s.kode, F.sumber_dana_id)).join('')}</select>
   <select id="fSt"><option value="">Aktif (semua)</option>${['Diusulkan', 'Disetujui', 'Terlaksana', 'Dibatalkan', 'Ditolak'].map(s => opt(s, s, F.status)).join('')}</select></div>
  <div class="tabs"><button class="tab ${S.jwTab === 'kalender' ? 'on' : ''}" data-tab="kalender">Kalender</button><button class="tab ${S.jwTab === 'tabel' ? 'on' : ''}" data-tab="tabel">Tabel</button>
   <span class="muted" style="margin-left:auto;align-self:center">${list.length} jadwal</span></div>
  ${S.jwTab === 'kalender' ? hariKal() : tabel()}
  <p class="legend"><span class="chip st-Diusulkan">Diusulkan</span> <span class="chip st-Disetujui">Disetujui</span> <span class="chip st-Terlaksana">Terlaksana</span> <span class="chip cuti">Cuti</span> <span class="lib-key">Libur</span></p>`;

  const reload = () => viewJadwal(m);
  const geser = n => { const d = new Date(Y, M - 1 + n, 1); S.jwYM = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; reload(); };
  $('#jPrev').onclick = () => geser(-1); $('#jNext').onclick = () => geser(1);
  $('#jNow').onclick = () => { S.jwYM = null; reload(); };
  [['fPeg', 'pegawai_id'], ['fLok', 'lokasi_id'], ['fProg', 'program'], ['fDana', 'sumber_dana_id'], ['fSt', 'status']].forEach(([id, k]) => $('#' + id).onchange = e => { S.jwF[k] = e.target.value; reload(); });
  m.querySelectorAll('[data-tab]').forEach(t => t.onclick = () => { S.jwTab = t.dataset.tab; reload(); });
  if ($('#jAdd')) $('#jAdd').onclick = () => formJadwal(null, dari);
  m.onclick = e => {
    const c = e.target.closest('[data-j],[data-det]'); if (c) { const j = list.find(x => x.id === Number(c.dataset.j || c.dataset.det)); if (j) detail(j); return; }
    const dEl = e.target.closest('.day[data-d]'); if (dEl && rw && !e.target.closest('.chip')) formJadwal(null, dEl.dataset.d);
  };

  // ----- form jadwal + pengecekan bentrok real-time -----
  async function formJadwal(j, tglAwal) {
    const siap = await api(`/api/jadwal/rencana-siap?tahun=${Y}`);
    if (!j && !siap.length) return toast(`Belum ada rencana Disetujui yang masih bisa dijadwalkan pada tahun ${Y}. Setujui rencana di menu Perencanaan.`, 1);
    const pilih = new Set((j?.petugas || []).map(p => p.id)); let selesaiManual = !!j;
    const lok = S.refs.lokasi.filter(l => l.aktif);
    const rencOpt = j ? `<option value="${j.rencana_id}">${esc(j.kegiatan)}</option>` : '<option value="">— pilih rencana yang sudah disetujui —</option>' + siap.map(r => `<option value="${r.id}">${BLN[r.bulan - 1].slice(0, 3)} · ${esc(r.kegiatan.slice(0, 70))} — ${r.terjadwal}/${r.frekuensi} terjadwal</option>`).join('');
    dialog(j ? 'Ubah Jadwal #' + j.id : 'Tambah Jadwal Dinas Luar', `
      <label>Rencana kegiatan<select name="rencana_id" ${j ? 'disabled' : 'required'}>${rencOpt}</select></label>
      <div class="grid2"><label>Tanggal mulai<input name="mulai" type="date" value="${j ? j.mulai : tglAwal || ''}" required></label>
        <label>Tanggal selesai<input name="selesai" type="date" value="${j ? j.selesai : tglAwal || ''}" required></label>
        <label>Lokasi tujuan<select name="lokasi_id"><option value="">— pilih —</option>${lok.map(l => `<option value="${l.id}" ${j?.lokasi_id === l.id ? 'selected' : ''}>${esc(l.nama)}</option>`).join('')}</select></label>
        <label>Durasi (dalam kota)<select name="durasi"><option value="gt8" ${j?.durasi !== 'le8' ? 'selected' : ''}>Lebih dari 8 jam</option><option value="le8" ${j?.durasi === 'le8' ? 'selected' : ''}>Sampai dengan 8 jam</option></select></label></div>
      <div><div class="bar" style="margin:4px 0"><b>Petugas</b> <span class="muted" id="pCount"></span><span style="flex:1"></span>
        <input id="pCari" type="search" placeholder="Cari nama/ruangan…" style="min-width:150px"><button type="button" class="btn small" id="pAuto">⚙ Bagi petugas otomatis</button></div>
        <div class="plist" id="pList"></div></div>
      <label>Catatan<input name="catatan" value="${esc(j?.catatan ?? '')}"></label>
      <div id="cek" class="card prev">Lengkapi rencana, tanggal, dan petugas untuk memeriksa bentrok.</div>`,
      async d => {
        const body = { ...d, rencana_id: Number(j ? j.rencana_id : d.rencana_id), lokasi_id: Number(d.lokasi_id) || null, petugas: [...pilih], id: j?.id };
        const res = await api(j ? `/api/jadwal/${j.id}` : '/api/jadwal', { method: j ? 'PUT' : 'POST', body });
        toast('Jadwal diusulkan.' + (res.peringatan?.length ? ' ⚠ ' + res.peringatan[0] : '')); await reload();
      });
    const f = $('#dlgForm'), ok = $('#dlgOk'); let tm;
    const rencanaTerpilih = () => j ? { jumlah_petugas: j.rencana_petugas, jumlah_hari: 1 } : siap.find(r => r.id === Number(f.elements.rencana_id.value));
    const gambarDaftar = () => {
      const q = $('#pCari').value.toLowerCase();
      $('#pList').innerHTML = pegAktif.filter(p => !/^kepala puskesmas/i.test(p.jabatan || '')).filter(p => pilih.has(p.id) || !q || `${p.nama} ${p.ruangan} ${p.jabatan}`.toLowerCase().includes(q))
        .sort((a, b) => (pilih.has(b.id) - pilih.has(a.id)) || a.nama.localeCompare(b.nama)).map(p => `<label class="prow ${pilih.has(p.id) ? 'on' : ''}"><input type="checkbox" data-id="${p.id}" ${pilih.has(p.id) ? 'checked' : ''}>
         <span><b>${esc(namaSingkat(p.nama))}</b> <span class="muted">${esc(p.ruangan || p.program || '')} · ${esc((p.jabatan || '').slice(0, 30))}</span></span></label>`).join('');
      const r = rencanaTerpilih(); $('#pCount').textContent = `(${pilih.size} dipilih${r ? ' dari ' + r.jumlah_petugas + ' direncanakan' : ''})`;
    };
    const periksa = async () => {
      const d = Object.fromEntries(new FormData(f)); if (j) d.rencana_id = j.rencana_id;
      if (!d.rencana_id || !d.mulai || !d.selesai || !pilih.size) { ok.disabled = true; return; }
      const a = await api('/api/jadwal/periksa', { method: 'POST', body: { ...d, rencana_id: Number(d.rencana_id), lokasi_id: Number(d.lokasi_id) || null, petugas: [...pilih], id: j?.id } });
      $('#cek').innerHTML = (a.ok ? `<p class="okc">✓ Tidak ada bentrok. ${a.jumlah_hari ?? ''} hari, ${pilih.size} petugas.</p>` : '')
        + a.galat.map((g, i) => `<div class="gal"><p class="err">✖ ${esc(g.pesan)}</p>${g.pengganti?.length ? `<div class="peng">Petugas kosong pada tanggal itu: ${g.pengganti.map(x => `<button type="button" class="chipb" data-ganti="${g.pegawai_id ?? ''}" data-baru="${x.id}">${esc(namaSingkat(x.nama))} <small>· ${x.beban_bulan ?? 0} hr bln ini</small></button>`).join(' ')}</div>` : ''}</div>`).join('')
        + a.peringatan.map(p => `<p class="warn">⚠ ${esc(p)}</p>`).join('');
      ok.disabled = !a.ok;
    };
    const tunda = (ms = 250) => { clearTimeout(tm); tm = setTimeout(periksa, ms); };
    ok.disabled = true; gambarDaftar(); periksa();
    f.addEventListener('change', e => {
      if (e.target.name === 'rencana_id') {
        const r = siap.find(x => x.id === Number(e.target.value));
        if (r) { if (r.lokasi_id) f.elements.lokasi_id.value = r.lokasi_id; f.elements.durasi.value = r.durasi || 'gt8'; if (f.elements.mulai.value && !selesaiManual) f.elements.selesai.value = isoD(new Date(new Date(f.elements.mulai.value).getTime() + (r.jumlah_hari - 1) * 864e5)); gambarDaftar(); }
      }
      if (e.target.name === 'mulai' && !selesaiManual) { const r = rencanaTerpilih(); f.elements.selesai.value = isoD(new Date(new Date(e.target.value).getTime() + ((r?.jumlah_hari || 1) - 1) * 864e5)); }
      if (e.target.name === 'selesai') selesaiManual = true;
      if (e.target.dataset.id) { const id = Number(e.target.dataset.id); e.target.checked ? pilih.add(id) : pilih.delete(id); gambarDaftar(); }
      tunda(50);
    });
    f.addEventListener('input', e => { if (e.target.id === 'pCari') gambarDaftar(); else tunda(); });
    f.addEventListener('click', e => {
      const g = e.target.closest('[data-baru]');
      if (g) { if (g.dataset.ganti) pilih.delete(Number(g.dataset.ganti)); pilih.add(Number(g.dataset.baru)); gambarDaftar(); tunda(30); }
    });
    $('#pAuto').onclick = async () => {
      const r = rencanaTerpilih(); if (!r) return toast('Pilih rencana dulu.', 1);
      if (!f.elements.mulai.value || !f.elements.selesai.value) return toast('Isi tanggal dulu.', 1);
      try {
        const s = await api('/api/jadwal/saran', { method: 'POST', body: { mulai: f.elements.mulai.value, selesai: f.elements.selesai.value, jumlah: r.jumlah_petugas, id: j?.id } });
        pilih.clear(); s.dipilih.forEach(p => pilih.add(p.id)); gambarDaftar(); tunda(30);
        toast(s.kurang ? `Hanya ${s.dipilih.length} petugas kosong (kurang ${s.kurang}).` : `Dipilih ${s.dipilih.length} petugas dengan beban terendah.`, !!s.kurang);
      } catch (x) { toast(x.message, 1); }
    };
  }
}

// ---------- kalkulator ----------
async function viewKalkulator(m) {
  await refs();
  const peg = S.refs.pegawai.filter(p => p.aktif), lok = S.refs.lokasi.filter(l => l.aktif);
  m.innerHTML = `<h2>Kalkulator Biaya Perjalanan Dinas</h2><p class="muted">Estimasi otomatis dari tarif master (Perbup). Inilah mesin hitung yang dipakai Perencanaan & Panjar pada tahap berikutnya.</p>
  <form id="kf" class="card"><div class="grid2">
   <label>Pegawai<select name="pegawai_id">${peg.map(p => `<option value="${p.id}">${esc(p.nama)} — Tk. ${p.tingkat}</option>`).join('')}</select></label>
   <label>Lokasi tujuan<select name="lokasi_id">${lok.map(l => `<option value="${l.id}">${esc(l.nama)}</option>`).join('')}</select></label>
   <label>Durasi (dalam kota)<select name="durasi"><option value="gt8">Lebih dari 8 jam</option><option value="le8">Sampai dengan 8 jam</option></select></label>
   <label>Jumlah hari<input name="hari" type="number" min="1" value="1"></label>
   <label>Kendaraan (antar kecamatan)<select name="roda"><option value="2">Roda 2</option><option value="4">Roda 4</option></select></label>
   <label>Penginapan<select name="menginap"><option value="tidak">Tidak menginap</option><option value="hotel">Hotel (biaya riil)</option><option value="tidak_hotel">Menginap tanpa hotel (lumpsum)</option></select></label>
   <label>Biaya hotel riil per malam (Rp)<input name="inap_riil" type="number" min="0" placeholder="kosong = sesuai tarif"></label>
   <label>Transport lokal/riil tambahan (Rp)<input name="transport_manual" type="number" min="0"></label>
   <label><span><input type="checkbox" name="pp" checked> Pulang-pergi (transport ×2)</span></label>
   <label><span><input type="checkbox" name="diklat"> Diklat dalam kota</span></label>
  </div><div class="bar"><button class="btn primary">Hitung</button></div></form><div id="hasil" style="margin-top:14px"></div>`;
  $('#kf').onsubmit = async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    d.pp = e.target.pp.checked; d.diklat = e.target.diklat.checked;
    ['pegawai_id', 'lokasi_id'].forEach(x => d[x] = Number(d[x]));
    try {
      const r = await api('/api/hitung-biaya', { method: 'POST', body: d });
      $('#hasil').innerHTML = `<div class="card"><b>${esc(r.pegawai)}</b> (Tingkat ${r.tingkat}) → ${esc(r.lokasi)} · tarif tahun ${r.tahun}
      <div class="tbl-wrap" style="margin-top:8px"><table><thead><tr><th>Komponen</th><th>Vol</th><th>Tarif</th><th>Jumlah</th></tr></thead><tbody>
      ${r.baris.map(b => `<tr><td>${esc(b.uraian)}</td><td>${b.volume} ${esc(b.satuan)}</td><td class="num">${rp(b.tarif)}</td><td class="num">${rp(b.jumlah)}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">Tidak ada komponen biaya.</td></tr>'}
      <tr><td colspan="3"><b>Total estimasi</b></td><td class="num"><b>${rp(r.total)}</b></td></tr></tbody></table></div>
      ${r.peringatan.map(p => `<p class="warn">⚠ ${esc(p)}</p>`).join('')}</div>`;
    } catch (x) { toast(x.message, 1); }
  };
}

// ---------- riwayat ----------
async function viewRiwayat(m) {
  const rows = await api('/api/riwayat');
  const ringkas = r => {
    let a = {}, b = {}; try { a = JSON.parse(r.data_lama || '{}'); b = JSON.parse(r.data_baru || '{}'); } catch {}
    if (r.aksi === 'UBAH') { const ch = Object.keys(b).filter(k => JSON.stringify(a[k]) !== JSON.stringify(b[k])); return ch.map(k => `${esc(k)}: ${esc(a[k] ?? '∅')} → ${esc(b[k] ?? '∅')}`).join('; '); }
    return esc((r.aksi === 'HAPUS' ? r.data_lama : r.data_baru) || '').slice(0, 240);
  };
  m.innerHTML = `<h2>Riwayat Perubahan</h2><p class="muted">300 catatan terakhir: siapa, kapan, data lama → data baru.</p>
  <div class="tbl-wrap"><table><thead><tr><th>Waktu</th><th>Pengguna</th><th>Tabel</th><th>Aksi</th><th>Perubahan</th></tr></thead><tbody>
  ${rows.map(r => `<tr><td style="white-space:nowrap">${esc(r.waktu)}</td><td>${esc(r.username)}</td><td>${esc(r.tabel)} #${r.record_id ?? ''}</td><td>${esc(r.aksi)}</td><td class="diff">${ringkas(r)}</td></tr>`).join('')}</tbody></table></div>`;
}

// ---------- backup ----------
function viewData(m) {
  m.innerHTML = `<h2>Backup & Ekspor</h2><div class="card" style="display:grid;gap:10px;max-width:520px">
   <div><b>Ekspor seluruh data ke Excel</b><p class="muted">Satu sheet per tabel master (plus riwayat untuk Kepala/Bendahara).</p><button class="btn primary" id="x1">Unduh Excel</button></div>
   ${S.bisaTulis ? `<div><b>Backup database</b><p class="muted">Salinan utuh basis data (.db). Simpan di tempat aman secara berkala.</p><button class="btn" id="x2">Unduh backup</button></div>` : ''}</div>`;
  $('#x1').onclick = () => download('/api/export/xlsx', 'sikadin_data.xlsx');
  if ($('#x2')) $('#x2').onclick = () => download('/api/backup', 'sikadin_backup.db');
}

// ---------- mulai ----------
async function start() {
  try {
    const m = await api('/api/meta');
    S.meta = m.meta; S.user = m.user; S.bisaTulis = m.bisaTulis; S.bisaBaca = m.bisaBaca;
  } catch { return showLogin(); }
  $('#login').hidden = true; $('#app').hidden = false;
  $('#who').textContent = `${S.user.nama} · ${ROLE[S.user.role]}`;
  buildNav(); route();
}
start();
