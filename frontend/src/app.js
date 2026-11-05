'use strict';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const rp = n => n === null || n === undefined || n === '' ? '' : 'Rp' + Number(n).toLocaleString('id-ID');
const ROLE = { kepala: 'Kepala Puskesmas', bendahara: 'Bendahara', bendahara_blud: 'Bendahara BLUD', program: 'Pengelola Program', pembuat_surat: 'Pembuat Surat Tugas', pegawai: 'Pegawai' };
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
  ['Beranda', [['dashboard', 'Dashboard']]],
  ['Anggaran', [['bok', 'Pagu Anggaran BOK'], ['dau', 'Pagu Anggaran DAU'], ['blud', 'Pagu Anggaran BLUD'], ['rencana', 'Perencanaan (RPK/POA)']]],
  ['Dinas Luar', [['jadwal', 'Jadwal Dinas Luar'], ['st', 'Surat (ST, SPD & Nomor)'], ['rekap', 'Rekap Perjalanan Dinas']]],
  ['Keuangan', [['spj', 'Realisasi & SPJ'], ['akun', 'Akuntansi & Laporan Keuangan']]],
  ['Master Data', [['pegawai', 'Pegawai'], ['sumber_dana', 'Sumber Dana'], ['lokasi', 'Lokasi Tujuan'], ['tarif', 'Tarif Perbup'], ['pejabat', 'Pejabat'], ['libur', 'Hari Libur'], ['cuti', 'Cuti Pegawai'], ['pengaturan', 'Pengaturan & Kop']]],
  ['Alat', [['kalkulator', 'Kalkulator Biaya'], ['riwayat', 'Riwayat Perubahan'], ['data', 'Backup & Ekspor']]],
  ['Sistem', [['users', 'Pengguna']]],
];
function buildNav() {
  let h = '';
  for (const [g, items] of MENU) {
    const vis = items.filter(([k]) => !(S.user.role === 'pembuat_surat' && !['dashboard', 'jadwal', 'st', 'rekap', 'kalkulator'].includes(k))).filter(([k]) => S.meta[k] || (['kalkulator', 'data', 'rencana', 'jadwal', 'nomor'].includes(k) && S.bisaBaca) || k === 'dashboard' || k === 'st' || k === 'spj' || k === 'rekap' || (k === 'akun' && S.akuntansi) || (['bok', 'dau', 'blud'].includes(k) && S.akses[k.toUpperCase()].baca) || (k === 'riwayat' && (S.bisaTulis || S.user.role === 'bendahara_blud')));
    if (!vis.length) continue;
    h += `<h4>${g}</h4>` + vis.map(([k, l]) => `<a data-k="${k}">${l}</a>`).join('');
  }
  if (!S.bisaBaca) h = '<h4>Beranda</h4><a data-k="dashboard">Dashboard</a><h4>Dinas Luar</h4><a data-k="st">Surat Tugas &amp; SPD Saya</a><a data-k="rekap">Rekap Perjalanan Saya</a><h4>Keuangan</h4><a data-k="spj">SPJ Saya</a>';
  $('#nav').innerHTML = h;
  $('#nav').onclick = e => { const k = e.target.dataset.k; if (k) { location.hash = k; $('#nav').classList.remove('open'); } };
}
async function route() {
  const k = location.hash.slice(1) || 'dashboard';
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.k === k));
  const m = $('#main');
  try {
    if (k === 'dashboard') await viewDashboard(m);
    else if (k === 'st') await viewSurat(m);
    else if (k === 'spj') await viewSpj(m);
    else if (k === 'rekap') await viewRekap(m);
    else if (k === 'akun' && S.akuntansi) await viewAkun(m);
    else if (k === 'nomor') { S.stTab = 'nomor'; location.hash = 'st'; }
    else if (!S.bisaBaca) m.innerHTML = `<div class="card"><h2>Selamat datang, ${esc(S.user.nama)}</h2><p class="muted">Jadwal, Surat Tugas, dan rincian uang Anda akan tampil di sini pada tahap berikutnya.</p></div>`;
    else if (['bok', 'dau', 'blud'].includes(k)) await viewBok(m, k.toUpperCase());
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

async function viewBok(m, kode = 'BOK') {
  const T = S.bokTahun;
  const [tr, tahunList] = await Promise.all([api(`/api/bok/${T}?sumber=${kode}`), api(`/api/bok/tahun?sumber=${kode}`)]);
  const rw = S.akses[kode].pagu, pagu = tr.pagu ? tr.pagu.pagu : 0, selisih = pagu - tr.total;
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

  m.innerHTML = `<h2>Pagu Anggaran ${kode}</h2><p class="muted">Rencana Anggaran Biaya (RAB) ${kode} Puskesmas${kode === 'BLUD' ? ' — <b>khusus Kepala Puskesmas &amp; Bendahara BLUD</b>' : ''}: Menu → Rincian Menu → baris biaya. Baris-baris inilah yang nanti dipakai Perencanaan, Panjar, dan SPJ.</p>
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
  ${tr.menu.length ? menus : `<div class="card"><p>Belum ada RAB ${kode} untuk tahun ${T}.</p>${rw ? '<p class="muted">Tambah menu satu per satu, atau gunakan <b>Impor RAB Excel</b> (format RAB BOK Puskesmas; untuk ${kode} susun manual atau gunakan format yang sama).</p>' : ''}</div>`}`;

  const reload = async () => { await viewBok(m, kode); };
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
    if (act === 'tmb-menu') dialog('Tambah Menu', formNoNama({}, 'No. menu', 'Nama menu'), async d => { await api('/api/bok/menu', { method: 'POST', body: { ...d, tahun: T, sumber: kode } }); await done('Menu ditambahkan.')(); });
    else if (act === 'ub-menu') { const x = menuById(id); dialog('Ubah Menu', formNoNama(x, 'No. menu', 'Nama menu'), async d => { await api('/api/bok/menu/' + id, { method: 'PUT', body: d }); await done('Menu diubah.')(); }); }
    else if (act === 'hps-menu') { const x = menuById(id); dialog('Hapus menu?', `<p>Menu <b>${esc(x.nama)}</b> beserta ${x.rincian.length} rincian dan ${x.rincian.reduce((s, r) => s + r.baris.length, 0)} baris (${rp(x.total)}) akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/bok/menu/' + id, { method: 'DELETE' }); await done('Menu dihapus.')(); }, 'Hapus'); }
    else if (act === 'tmb-rinc') dialog('Tambah Rincian Menu', formNoNama({}, 'No. rincian', 'Nama rincian menu'), async d => { S.bokOpen.add(id); await api('/api/bok/rincian', { method: 'POST', body: { ...d, menu_id: id } }); await done('Rincian ditambahkan.')(); });
    else if (act === 'ub-rinc') { const x = rincById(id); dialog('Ubah Rincian Menu', formNoNama(x, 'No. rincian', 'Nama rincian menu'), async d => { await api('/api/bok/rincian/' + id, { method: 'PUT', body: d }); await done('Rincian diubah.')(); }); }
    else if (act === 'hps-rinc') { const x = rincById(id); dialog('Hapus rincian menu?', `<p><b>${esc(x.nama)}</b> beserta ${x.baris.length} baris (${rp(x.total)}) akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/bok/rincian/' + id, { method: 'DELETE' }); await done('Rincian dihapus.')(); }, 'Hapus'); }
    else if (act === 'tmb-baris') { dialog('Tambah Baris Biaya', formBaris(), async d => { await api('/api/bok/baris', { method: 'POST', body: { ...d, rincian_id: id } }); await done('Baris ditambahkan.')(); }); liveJumlah(); }
    else if (act === 'ub-baris') { dialog('Ubah Baris Biaya', formBaris(barisById(id)), async d => { await api('/api/bok/baris/' + id, { method: 'PUT', body: d }); await done('Baris diubah.')(); }); liveJumlah(); }
    else if (act === 'dup-baris') { await api(`/api/bok/baris/${id}/duplikat`, { method: 'POST' }); await done('Baris disalin.')(); }
    else if (act === 'hps-baris') { const b = barisById(id); dialog('Hapus baris?', `<p>${esc(b.komponen || b.uraian || b.jenis_belanja)} — ${rp(b.jumlah)} akan dihapus. Tercatat di riwayat.</p>`, async () => { await api('/api/bok/baris/' + id, { method: 'DELETE' }); await done('Baris dihapus.')(); }, 'Hapus'); }
    else if (act === 'ub-pagu') dialog('Pagu ' + kode + ' ' + T, `<label>Jenis<select name="jenis">${['Pagu Indikatif', 'Pagu Definitif', 'Pagu Perubahan'].map(j => `<option ${tr.pagu && tr.pagu.jenis === j ? 'selected' : ''}>${j}</option>`).join('')}</select></label>
      <label>Jumlah pagu (Rp)<input name="pagu" type="number" min="0" step="1" required value="${pagu}"></label><label>Keterangan<input name="keterangan" value="${esc(tr.pagu?.keterangan ?? '')}"></label>`,
      async d => { await api(`/api/bok/${T}/pagu?sumber=${kode}`, { method: 'PUT', body: d }); await done('Pagu disimpan.')(); });
    else if (act === 'hps-semua') dialog('Kosongkan RAB ' + kode + ' ' + T + '?', `<p>Seluruh ${tr.menu.length} menu, ${nR} rincian, dan ${nB} baris tahun ${T} akan dihapus (pagu tetap). Tercatat di riwayat.</p>`, async () => { await api(`/api/bok/${T}?sumber=${kode}`, { method: 'DELETE' }); await done('RAB dikosongkan.')(); }, 'Kosongkan');
    else if (act === 'exp-rab') download(`/api/bok/${T}/export.xlsx?sumber=${kode}`, `RAB_${kode}_${T}.xlsx`);
    else if (act === 'imp-rab') {
      let hasil = null;
      dialog('Impor RAB ' + kode, `<p class="muted">Pilih berkas RAB ${kode} Puskesmas (.xlsx; format sama dengan RAB BOK). Menu, rincian, dan baris dibaca otomatis; pagu diisi dari "Jumlah Total Kebutuhan Anggaran" bila belum ada.</p>
        <input type="file" name="berkas" accept=".xlsx,.xls" required><label>Tahun<input name="tahun" type="number" value="${T}"></label>
        <label style="grid-auto-flow:column;justify-content:start;align-items:center;gap:8px"><input type="checkbox" name="ganti" ${tr.menu.length ? 'checked' : ''}> Ganti RAB tahun ini bila sudah ada</label>`,
        async d => {
          const file = $('#dlgForm input[type=file]').files[0]; if (!file) throw new Error('Pilih berkas.');
          const b64 = btoa(new Uint8Array(await file.arrayBuffer()).reduce((s, x) => s + String.fromCharCode(x), ''));
          hasil = await api('/api/bok/import', { method: 'POST', body: { file: b64, tahun: Number(d.tahun), ganti: d.ganti, sumber: kode } });
          S.bokTahun = hasil.tahun; await reload();
          setTimeout(() => dialog('Impor selesai', `<p>Tahun <b>${hasil.tahun}</b>: ${hasil.menu} menu, ${hasil.baris} baris, total <b>${rp(hasil.total)}</b>.</p>${(hasil.peringatan || []).map(p => `<p class="warn">⚠ ${esc(p)}</p>`).join('')}`), 150);
        }, 'Impor');
    }
  };
}

// ---------- Perencanaan (RPK/POA) ----------
const BLN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];
const STATUS = ['Draft', 'Diajukan', 'Ditolak', 'Disetujui', 'Terjadwal', 'Terlaksana', 'SPJ Selesai'];
S.rcTab = 'daftar'; S.rcBulan = ''; S.rcStatus = ''; S.rcSumber = null;

async function viewRencana(m) {
  const bolehSumber = ['BOK', 'DAU', 'BLUD'].filter(k => S.akses[k].baca);
  if (!S.rcSumber || !bolehSumber.includes(S.rcSumber)) S.rcSumber = bolehSumber[0];
  const kode = S.rcSumber;
  const T = S.bokTahun, rw = S.akses[kode].rencana, kepala = S.user.role === 'kepala';
  await refs();
  const qs = `sumber=${kode}&tahun=${T}` + (S.rcBulan ? `&bulan=${S.rcBulan}` : '') + (S.rcStatus ? `&status=${encodeURIComponent(S.rcStatus)}` : '');
  const [list, poa, tr] = await Promise.all([api('/api/rencana?' + qs), api(`/api/rencana/poa?tahun=${T}&sumber=${kode}`), api(`/api/bok/${T}?sumber=${kode}`)]);
  const aktif = x => x.status !== 'Ditolak';
  const semua = S.rcBulan || S.rcStatus ? await api(`/api/rencana?tahun=${T}&sumber=${kode}`) : list;
  const totalRencana = semua.filter(aktif).reduce((s, x) => s + x.estimasi, 0), disetujui = semua.filter(x => ['Disetujui', 'Terjadwal', 'Terlaksana', 'SPJ Selesai'].includes(x.status)).reduce((s, x) => s + x.estimasi, 0);
  const pagu = tr.pagu ? tr.pagu.pagu : 0;
  const bdg = s => `<span class="badge st-${s.replace(/ /g, '')}">${s}</span>`;

  const aksi = r => {
    const b = (a, l, c = '') => `<button class="btn small ${c}" data-a="${a}" data-id="${r.id}">${l}</button>`;
    if (r.status === 'Draft' && r.bisa_ubah) return [b('ubah', 'Ubah'), b('ajukan', 'Ajukan', 'primary'), b('hapus', 'Hapus', 'danger')].join(' ');
    if (r.status === 'Diajukan') return [r.bisa_ubah ? b('tarik', 'Tarik') : '', (kepala || (!S.kepalaWajib && rw)) ? b('setuju', 'Setujui', 'primary') + ' ' + b('tolak', 'Tolak', 'danger') : ''].join(' ');
    if (r.status === 'Ditolak' && r.bisa_ubah) return b('revisi', 'Revisi');
    if (r.status === 'Disetujui' && (kepala || (!S.kepalaWajib && rw))) return b('batal', 'Batalkan persetujuan');
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
  <div class="kv"><div class="card"><span class="muted">Pagu ${kode} ${T}</span><b>${rp(pagu)}</b></div>
   <div class="card"><span class="muted">Total direncanakan</span><b>${rp(totalRencana)}</b><span class="muted">${pagu ? (totalRencana / pagu * 100).toFixed(1) : 0}% dari pagu</span></div>
   <div class="card"><span class="muted">Sudah disetujui</span><b>${rp(disetujui)}</b></div>
   <div class="card"><span class="muted">Sisa pagu belum direncanakan</span><b class="${pagu - totalRencana < 0 ? 'err' : ''}">${rp(pagu - totalRencana)}</b></div></div>
  <div class="tabs sumber">${bolehSumber.map(k => `<button class="tab ${k === kode ? 'on' : ''}" data-sumber="${k}">${k}</button>`).join('')}<span class="muted" style="margin-left:auto;align-self:center">Sumber dana</span></div>
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
  m.querySelectorAll('[data-sumber]').forEach(t => t.onclick = () => { S.rcSumber = t.dataset.sumber; reload(); });
  if ($('#rThn')) { $('#rThn').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); }; $('#rBln').onchange = e => { S.rcBulan = e.target.value; reload(); }; $('#rSt').onchange = e => { S.rcStatus = e.target.value; reload(); }; }

  const ubahStatus = async (id, ke, alasan) => { await api(`/api/rencana/${id}/status`, { method: 'POST', body: { ke, alasan } }); toast('Status: ' + ke); await reload(); };
  async function formRencana(r) {
    const opsi = await api(`/api/rencana/opsi?tahun=${T}&sumber=${kode}`);
    if (!opsi.length) return toast(`Belum ada RAB ${kode} untuk tahun ini. Isi dulu di Pagu Anggaran ${kode}.`, 1);
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
    const setuju = kepala || (!S.kepalaWajib && rw);
    if (!j.no_st && rw && ['Diusulkan', 'Disetujui'].includes(j.status) && (j.status === 'Disetujui' || setuju)) a.push(['Buat Surat Tugas', () => { S.stTab = 'siap'; location.hash = 'st'; }, 'primary']);
    if (j.status === 'Diusulkan' && setuju) a.push(['Setujui', () => ubahStatus(j, 'Disetujui'), 'primary'], ['Tolak', () => alasanStatus(j, 'Ditolak'), 'danger']);
    if ((j.status === 'Diusulkan' && j.bisa_ubah) || (j.status === 'Disetujui' && setuju)) a.push(['Batalkan', () => alasanStatus(j, 'Dibatalkan'), 'danger']);
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
   <span style="flex:1"></span>${rw ? '<button class="btn" id="jGen">⚙ Generate bulanan</button><button class="btn primary" id="jAdd">+ Jadwal</button>' : ''}</div>
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
  if ($('#jGen')) $('#jGen').onclick = () => formGenerate().catch(x => toast(x.message, 1));
  m.onclick = e => {
    const c = e.target.closest('[data-j],[data-det]'); if (c) { const j = list.find(x => x.id === Number(c.dataset.j || c.dataset.det)); if (j) detail(j); return; }
    const dEl = e.target.closest('.day[data-d]'); if (dEl && rw && !e.target.closest('.chip')) formJadwal(null, dEl.dataset.d);
  };

  // ----- generate jadwal bulanan -----
  async function formGenerate() {
    const siap = (await api(`/api/jadwal/rencana-siap?tahun=${Y}`)).filter(r => r.bulan === M);
    const pen = await api('/api/data/pengaturan'), persen = (pen.find(x => x.kunci === 'batas_persen_ruangan') || {}).nilai || 50;
    if (!siap.length) return toast(`Tidak ada rencana Disetujui untuk ${BLN[M - 1]} ${Y} yang masih perlu dijadwalkan. Setujui rencana di menu Perencanaan.`, 1);
    dialog(`Generate Jadwal ${BLN[M - 1]} ${Y}`, `
      <p class="muted">Sistem menyusun usulan jadwal otomatis. Aturan: tanpa bentrok petugas, tanpa kegiatan ganda di lokasi &amp; tanggal yang sama, di luar libur &amp; cuti,
        beban petugas dibagi merata, dan <b>satu ruangan tidak boleh ditinggal lebih dari ${esc(persen)}% pegawainya</b> pada hari yang sama. Hasil ditampilkan dulu sebagai pratinjau.</p>
      <label>Hari kerja<select name="hari_kerja"><option value="5">Senin – Jumat</option><option value="6">Senin – Sabtu</option></select></label>
      <div><div class="bar" style="margin:4px 0"><b>Rencana yang dijadwalkan</b><span style="flex:1"></span><button type="button" class="btn small" id="gAll">Pilih semua</button><button type="button" class="btn small" id="gNone">Kosongkan</button></div>
       <div class="plist">${siap.map(r => `<label class="prow on"><input type="checkbox" data-r="${r.id}" checked><span><b>[${esc(r.dana)}] ${esc(r.kegiatan.slice(0, 80))}</b>
         <span class="muted"> · ${esc(r.lokasi || 'tanpa lokasi')} · ${r.jumlah_petugas} petugas × ${r.jumlah_hari} hr · ${r.frekuensi - r.terjadwal} pelaksanaan tersisa</span></span></label>`).join('')}</div></div>`,
      async d => {
        const ids = [...document.querySelectorAll('#dlgForm [data-r]:checked')].map(x => Number(x.dataset.r));
        if (!ids.length) throw new Error('Pilih minimal satu rencana.');
        const g = await api('/api/jadwal/generate', { method: 'POST', body: { tahun: Y, bulan: M, rencana_ids: ids, hari_kerja: Number(d.hari_kerja) } });
        setTimeout(() => pratinjau(g), 150);
      }, 'Buat pratinjau');
    $('#gAll').onclick = () => document.querySelectorAll('#dlgForm [data-r]').forEach(x => x.checked = true);
    $('#gNone').onclick = () => document.querySelectorAll('#dlgForm [data-r]').forEach(x => x.checked = false);
  }
  function pratinjau(g) {
    const r = g.ringkas;
    dialog('Pratinjau Jadwal ' + BLN[g.bulan - 1] + ' ' + g.tahun, `<div id="gen">
      <div class="kv" style="margin:0"><div class="card"><span class="muted">Jadwal tersusun</span><b>${r.jadwal}</b></div><div class="card"><span class="muted">Petugas terlibat</span><b>${r.petugas}</b></div>
       <div class="card"><span class="muted">Tidak bisa dijadwalkan</span><b class="${r.gagal ? 'err' : 'okc'}">${r.gagal}</b></div></div>
      ${g.gagal.length ? `<div class="gal">${g.gagal.map(x => `<p class="err">✖ ${esc(x.kegiatan.slice(0, 70))} (${x.jumlah}×): ${esc(x.alasan)}</p>`).join('')}</div>` : ''}
      <details open><summary><b>Jadwal usulan (${g.usulan.length})</b></summary><div class="tbl-wrap"><table><thead><tr><th>Tanggal</th><th>Kegiatan</th><th>Lokasi</th><th>Petugas (ruangan)</th></tr></thead><tbody>
       ${g.usulan.map(u => `<tr><td style="white-space:nowrap">${tglID(u.mulai).slice(0, 5)}${u.selesai !== u.mulai ? '–' + tglID(u.selesai).slice(0, 5) : ''}</td><td>${esc(u.kegiatan.slice(0, 60))}<br><span class="muted">pelaksanaan ${u.ke}/${u.dari}</span></td><td>${esc(u.lokasi.replace(/^Kelurahan /, 'Kel. '))}</td>
        <td style="font-size:.85em">${u.petugas.map(p => `${esc(p.nama.split(',')[0])} <span class="muted">(${esc(p.ruangan || '–')})</span>`).join(', ')}${u.peringatan.map(w => `<br><span class="warn">⚠ ${esc(w)}</span>`).join('')}</td></tr>`).join('')}</tbody></table></div></details>
      <details><summary><b>Dampak ke ruangan</b> <span class="muted">(puncak pegawai yang meninggalkan ruangan; batas ${g.persen}%)</span></summary><div class="tbl-wrap"><table><thead><tr><th>Ruangan</th><th>Pegawai</th><th>Puncak keluar</th><th></th></tr></thead><tbody>
       ${g.dampak.map(d => `<tr><td>${esc(d.ruangan)}</td><td>${d.pegawai}</td><td>${d.puncak} orang${d.tanggal ? ' · ' + tglID(d.tanggal).slice(0, 5) : ''}</td><td style="min-width:110px"><div class="bar-meter"><i style="width:${Math.min(100, d.persen)}%" class="${d.persen > g.persen ? 'bad' : ''}"></i></div><small>${d.persen}%</small></td></tr>`).join('')}</tbody></table></div></details>
      <details><summary><b>Sebaran beban petugas</b> <span class="muted">(hari dinas terbanyak)</span></summary><p style="font-size:.88em">${g.sebaran.map(s => `${esc(s.nama.split(',')[0])}: ${s.hari} hr`).join(' · ')}</p></details></div>`,
      async () => {
        if (!g.usulan.length) throw new Error('Tidak ada jadwal untuk disimpan.');
        const res = await api('/api/jadwal/generate/simpan', { method: 'POST', body: { items: g.usulan } });
        toast(`${res.tersimpan} jadwal disimpan sebagai usulan.` + (res.gagal.length ? ` ${res.gagal.length} gagal: ${res.gagal[0].alasan}` : ''), !!res.gagal.length);
        S.jwYM = `${g.tahun}-${pad(g.bulan)}`; await reload();
      }, `Simpan ${g.usulan.length} usulan`);
  }

  // ----- form jadwal + pengecekan bentrok real-time -----
  async function formJadwal(j, tglAwal) {
    const siap = await api(`/api/jadwal/rencana-siap?tahun=${Y}`);
    if (!j && !siap.length) return toast(`Belum ada rencana Disetujui yang masih bisa dijadwalkan pada tahun ${Y}. Setujui rencana di menu Perencanaan.`, 1);
    const pilih = new Set((j?.petugas || []).map(p => p.id)); let selesaiManual = !!j;
    const lok = S.refs.lokasi.filter(l => l.aktif);
    const rencOpt = j ? `<option value="${j.rencana_id}">${esc(j.kegiatan)}</option>` : '<option value="">— pilih rencana yang sudah disetujui —</option>' + siap.map(r => `<option value="${r.id}">${BLN[r.bulan - 1].slice(0, 3)} · [${esc(r.dana)}] ${esc(r.kegiatan.slice(0, 70))} — ${r.terjadwal}/${r.frekuensi} terjadwal</option>`).join('');
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

// ---------- Dashboard ----------
const PERAN_TXT = { kepala: 'Kepala Puskesmas', bendahara: 'Bendahara', bendahara_blud: 'Bendahara BLUD', program: 'Pengelola Program', pembuat_surat: 'Pembuat Surat Tugas', pegawai: 'Pegawai' };
async function viewDashboard(m) {
  const T = S.bokTahun, D = await api('/api/dashboard?tahun=' + T);
  const sal = `<h2>Dashboard</h2><p class="muted">Selamat datang, <b>${esc(S.user.nama)}</b> · ${PERAN_TXT[S.user.role] || ''} · tahun anggaran <input id="dbTh" type="number" value="${T}" style="width:80px"></p>`;
  if (D.peran === 'pegawai') {
    m.innerHTML = sal + `<div class="cards"><div class="card"><small>Perjalanan dinas tahun ini</small><b>${D.total.perjalanan}</b></div><div class="card"><small>Total hari</small><b>${D.total.hari}</b></div><div class="card"><small>Total biaya SPD</small><b>${rp(D.total.biaya)}</b></div></div>
     ${D.perlu_tindakan.length ? `<div class="card" style="border-color:#fcd34d"><b>SPJ yang perlu Anda lengkapi</b>${D.perlu_tindakan.map(x => `<p style="margin:6px 0">${tglID(x.mulai)} · ${esc(x.maksud)} <span class="badge ${SP_BADGE[x.spj_status]}">${x.spj_status}</span> <a class="btn small" href="#spj">Buka SPJ</a></p>`).join('')}</div>` : ''}
     <div class="card"><b>Perjalanan dinas mendatang</b>${D.perjalanan.map(x => `<p style="margin:6px 0">${tglID(x.mulai)}${x.selesai !== x.mulai ? ' – ' + tglID(x.selesai) : ''} · ${esc(x.tempat)} · ${esc(x.maksud)} <span class="muted">(${rp(x.total)})</span></p>`).join('') || '<p class="muted">Belum ada jadwal mendatang.</p>'}</div>
     <div class="card"><b>Status SPJ saya</b><p>${Object.entries(D.spj).map(([k, v]) => `<span class="badge ${SP_BADGE[k] || ''}">${k}: ${v}</span>`).join(' ') || '<span class="muted">Belum ada.</span>'}</p></div>`;
    $('#dbTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; viewDashboard(m); };
    return;
  }
  const t = D.total, mx = Math.max(1, ...D.bulanan.rencana, ...D.bulanan.realisasi);
  const warna = p => p >= 90 ? '#dc2626' : p >= 60 ? '#d97706' : '#16a34a';
  const k = D.keuangan;
  m.innerHTML = sal + `
   <div class="cards"><div class="card"><small>Pagu ${D.sumber.join(' + ')}</small><b>${rp(t.pagu)}</b></div><div class="card"><small>Realisasi (dibayar)</small><b>${rp(t.realisasi)}</b></div><div class="card"><small>Dalam proses SPJ</small><b>${rp(t.proses)}</b></div><div class="card"><small>Sisa pagu</small><b>${rp(t.sisa)}</b></div><div class="card"><small>Serapan</small><b style="color:${warna(t.persen)}">${t.persen}%</b></div>
    <div class="card"><small>Perjalanan dinas ${T}</small><b>${D.dinas.st} ST · ${D.dinas.orang} orang</b></div></div>
   ${D.tugas.length ? `<div class="card" style="border-color:#fcd34d"><b>Perlu tindakan</b><div class="acts" style="margin-top:6px">${D.tugas.map(x => `<a class="btn" href="#${x.tujuan}">${esc(x.label)} <span class="badge">${x.n}</span></a>`).join('')}</div></div>` : '<div class="card" style="border-color:#86efac">✔ Tidak ada pekerjaan yang menunggu.</div>'}
   ${D.peringatan.length ? `<div class="card"><b>Peringatan</b>${D.peringatan.map(x => `<p style="margin:5px 0;color:${x.level === 'bad' ? '#b91c1c' : x.level === 'warn' ? '#b45309' : 'inherit'}">${x.level === 'bad' ? '⛔' : x.level === 'warn' ? '⚠' : 'ℹ'} ${esc(x.teks)}</p>`).join('')}</div>` : ''}
   <div class="card"><b>Serapan per sumber dana</b><div class="tbl-wrap"><table><thead><tr><th>Sumber</th><th>Pagu</th><th>Rencana disetujui</th><th>Proses</th><th>Realisasi</th><th>Sisa</th><th style="min-width:120px">Serapan</th></tr></thead><tbody>
    ${D.serapan.map(x => `<tr><td><b>${x.sumber}</b></td><td class="num">${rp(x.pagu)}</td><td class="num">${rp(x.rencana)}</td><td class="num">${rp(x.proses)}</td><td class="num">${rp(x.realisasi)}</td><td class="num">${rp(x.sisa)}</td><td><div class="persen"><i style="width:${Math.min(100, x.persen)}%;background:${warna(x.persen)}"></i></div>${x.persen}%</td></tr>`).join('')}</tbody></table></div></div>
   <div class="card"><b>Rencana vs realisasi per bulan</b> <span class="muted" style="font-size:.85em">(<i style="display:inline-block;width:10px;height:10px;background:#bbf7d0"></i> rencana disetujui · <i style="display:inline-block;width:10px;height:10px;background:#15803d"></i> realisasi dibayar)</span>
    <div style="display:flex;gap:6px;align-items:flex-end;height:150px;margin-top:8px">${D.bulanan.rencana.map((r, i) => `<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%" title="${BLN[i]} — rencana ${rp(r)}, realisasi ${rp(D.bulanan.realisasi[i])}">
      <div style="display:flex;gap:2px;align-items:flex-end;height:120px;width:100%;justify-content:center"><div style="width:42%;background:#bbf7d0;height:${Math.round(100 * r / mx)}%"></div><div style="width:42%;background:#15803d;height:${Math.round(100 * D.bulanan.realisasi[i] / mx)}%"></div></div><small class="muted">${BLN[i].slice(0, 3)}</small></div>`).join('')}</div></div>
   <div class="card"><b>Jadwal dinas luar 14 hari ke depan</b>${D.jadwal_dekat.length ? `<div class="tbl-wrap"><table><thead><tr><th>Tanggal</th><th>Kegiatan</th><th>Tempat</th><th>Petugas</th><th>Dana</th><th>Status</th></tr></thead><tbody>${D.jadwal_dekat.map(j => `<tr><td style="white-space:nowrap">${tglID(j.mulai)}${j.selesai !== j.mulai ? ' – ' + tglID(j.selesai) : ''}</td><td>${esc(j.kegiatan)}</td><td>${esc(j.lokasi)}</td><td>${j.petugas} orang</td><td>${j.dana}</td><td><span class="badge ${j.punya_st ? 'st-Disetujui' : 'st-Diajukan'}">${j.punya_st ? 'ST terbit' : j.status}</span></td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">Tidak ada jadwal dalam 14 hari ke depan.</p>'}</div>
   ${k ? `<div class="card"><b>Ringkasan keuangan (s.d. ${BLN[k.bulan - 1]} ${T}, semua sumber)</b><div class="cards"><div class="card"><small>Pendapatan (LRA)</small><b>${rp(k.pendapatan)}</b></div><div class="card"><small>Belanja (LRA)</small><b>${rp(k.belanja)}</b></div><div class="card"><small>Surplus/(defisit) LRA</small><b>${rp(k.surplus_lra)}</b></div><div class="card"><small>Surplus/(defisit) LO</small><b>${rp(k.surplus_lo)}</b></div><div class="card"><small>Saldo kas</small><b>${rp(k.kas)}</b></div><div class="card"><small>Total aset</small><b>${rp(k.aset)}</b></div></div>
     <p class="muted" style="margin:0">${k.seimbang ? '✔ Neraca seimbang.' : '⚠ Neraca belum seimbang — periksa saldo awal/jurnal.'} <a href="#akun">Buka laporan keuangan →</a></p></div>` : ''}`;
  $('#dbTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; viewDashboard(m); };
}

// ---------- Rekap Perjalanan Dinas ----------
S.rkTab = 'rincian'; S.rkBulan = 0; S.rkSumber = ''; S.rkPeg = 0; S.rkTempat = 0; S.rkQ = '';
async function viewRekap(m) {
  const T = S.bokTahun, penuh = S.bisaBaca;
  const qs = `tahun=${T}&bulan=${S.rkBulan}&sumber=${S.rkSumber}&pegawai_id=${S.rkPeg}&lokasi_id=${S.rkTempat}&q=${encodeURIComponent(S.rkQ)}`;
  const R = await api('/api/rekap-dinas?' + qs);
  const sumberOk = ['BOK', 'DAU', 'BLUD'].filter(k => S.akses && S.akses[k].baca);
  const t = R.total, tab = S.rkTab;
  const head = x => `<th>${x}</th>`;
  let isi = '';
  if (tab === 'rincian') isi = `<div class="tbl-wrap"><table><thead><tr>${['No', 'Nama', 'Tempat', 'Tanggal', 'Hari', 'Tujuan', 'No. ST', 'Dana', 'Biaya SPD', 'Realisasi', 'SPJ'].map(head).join('')}</tr></thead><tbody>
    ${R.rows.map((r, i) => `<tr><td>${i + 1}</td><td><b>${esc(r.nama)}</b></td><td>${esc(r.tempat)}</td><td style="white-space:nowrap">${tglID(r.mulai)}${r.selesai !== r.mulai ? '<br>s.d. ' + tglID(r.selesai) : ''}</td><td>${r.hari}</td><td>${esc(r.tujuan)}</td><td style="font-size:.8em">${esc(r.nomor_srikandi || r.nomor)}</td><td>${r.dana}</td><td class="num">${rp(r.rencana)}</td><td class="num">${rp(r.realisasi)}</td><td>${r.spj_status ? `<span class="badge ${SP_BADGE[r.spj_status]}">${r.spj_status}</span>` : '-'}</td></tr>`).join('') || '<tr><td colspan="11" class="muted">Tidak ada perjalanan dinas pada filter ini.</td></tr>'}
    <tr class="grp"><td colspan="8"><b>Jumlah (${t.perjalanan} perjalanan-orang, ${t.st} ST)</b></td><td class="num"><b>${rp(t.rencana)}</b></td><td class="num"><b>${rp(t.realisasi)}</b></td><td></td></tr></tbody></table></div>`;
  else if (tab === 'bulanan') isi = `<div class="tbl-wrap"><table><thead><tr>${['Bulan', 'Jumlah ST', 'Perjalanan (orang)', 'Hari (orang)', 'Biaya SPD', 'Realisasi'].map(head).join('')}</tr></thead><tbody>
    ${R.bulanan.map(b => `<tr><td>${BLN[b.bulan - 1]}</td><td>${b.st}</td><td>${b.perjalanan}</td><td>${b.hari}</td><td class="num">${rp(b.rencana)}</td><td class="num">${rp(b.realisasi)}</td></tr>`).join('')}
    <tr class="grp"><td><b>Jumlah</b></td><td><b>${t.st}</b></td><td><b>${t.perjalanan}</b></td><td><b>${t.hari}</b></td><td class="num"><b>${rp(t.rencana)}</b></td><td class="num"><b>${rp(t.realisasi)}</b></td></tr></tbody></table></div>`;
  else if (tab === 'pegawai') isi = `<div class="tbl-wrap"><table><thead><tr><th>Nama</th>${BLN.map(b => `<th title="${b}">${b.slice(0, 3)}</th>`).join('')}<th>Perj.</th><th>Hari</th><th>Biaya SPD</th><th>Realisasi</th></tr></thead><tbody>
    ${R.per_pegawai.map(p => `<tr><td><b>${esc(p.nama)}</b><br><span class="muted" style="font-size:.8em">${esc(p.ruangan || '')}</span></td>${p.bln_jml.map((n, i) => `<td title="${BLN[i]}: ${rp(p.bln_biaya[i])}" style="${n ? 'background:#dcfce7;font-weight:600' : 'color:#94a3b8'}">${n || '·'}</td>`).join('')}<td>${p.perjalanan}</td><td>${p.hari}</td><td class="num">${rp(p.rencana)}</td><td class="num">${rp(p.realisasi)}</td></tr>`).join('') || '<tr><td colspan="17" class="muted">Tidak ada data.</td></tr>'}</tbody></table></div>
    <p class="muted" style="font-size:.85em">Angka per bulan = jumlah perjalanan (arahkan kursor untuk melihat biayanya).</p>`;
  else isi = `<div class="tbl-wrap"><table><thead><tr>${['Tempat', 'Perjalanan (orang)', 'Hari (orang)', 'Biaya SPD', 'Realisasi'].map(head).join('')}</tr></thead><tbody>
    ${R.per_tempat.map(x => `<tr><td><b>${esc(x.tempat)}</b></td><td>${x.perjalanan}</td><td>${x.hari}</td><td class="num">${rp(x.rencana)}</td><td class="num">${rp(x.realisasi)}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">Tidak ada data.</td></tr>'}</tbody></table></div>`;
  m.innerHTML = `<h2>Rekap Perjalanan Dinas</h2>
   <p class="muted">${penuh ? 'Per nama, tempat, waktu, tujuan, dan biaya — setahun dan per bulan. Biaya SPD = tarif Perbup; Realisasi = SPJ yang sudah dibayar.' : 'Perjalanan dinas Anda.'}</p>
   <div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="rkTh" type="number" value="${T}" style="width:90px"></label>
    <select id="rkBln"><option value="0">Setahun</option>${BLN.map((b, i) => `<option value="${i + 1}" ${S.rkBulan === i + 1 ? 'selected' : ''}>${b}</option>`).join('')}</select>
    ${penuh ? `<select id="rkSd"><option value="">Semua sumber</option>${sumberOk.map(k => `<option ${S.rkSumber === k ? 'selected' : ''}>${k}</option>`).join('')}</select>
    <select id="rkPeg"><option value="0">Semua pegawai</option>${R.pilihan.pegawai.map(x => `<option value="${x.id}" ${S.rkPeg === x.id ? 'selected' : ''}>${esc(x.nama)}</option>`).join('')}</select>
    <select id="rkTmp"><option value="0">Semua tempat</option>${R.pilihan.tempat.map(x => `<option value="${x.id}" ${S.rkTempat === x.id ? 'selected' : ''}>${esc(x.nama)}</option>`).join('')}</select>
    <input id="rkQ" placeholder="Cari tujuan / nama / tempat" value="${esc(S.rkQ)}" style="min-width:200px">` : ''}
    <span style="flex:1"></span><a class="btn small" href="/api/rekap-dinas/dok?${qs}&format=pdf" target="_blank">PDF</a><button class="btn small" data-rk="docx">DOCX</button><button class="btn small" data-rk="xlsx">XLSX</button></div>
   <div class="cards"><div class="card"><small>Surat Tugas</small><b>${t.st}</b></div><div class="card"><small>Perjalanan (orang)</small><b>${t.perjalanan}</b></div><div class="card"><small>Hari (orang)</small><b>${t.hari}</b></div><div class="card"><small>Biaya SPD</small><b>${rp(t.rencana)}</b></div><div class="card"><small>Realisasi dibayar</small><b>${rp(t.realisasi)}</b></div></div>
   <div class="tabs">${[['rincian', 'Rincian'], ['bulanan', 'Per bulan'], ['pegawai', 'Per nama'], ['tempat', 'Per tempat']].map(([k, l]) => `<button class="tab ${tab === k ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div>${isi}`;
  const reload = () => viewRekap(m);
  $('#rkTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); };
  $('#rkBln').onchange = e => { S.rkBulan = Number(e.target.value); reload(); };
  if ($('#rkSd')) { $('#rkSd').onchange = e => { S.rkSumber = e.target.value; reload(); }; $('#rkPeg').onchange = e => { S.rkPeg = Number(e.target.value); reload(); }; $('#rkTmp').onchange = e => { S.rkTempat = Number(e.target.value); reload(); }; $('#rkQ').onchange = e => { S.rkQ = e.target.value.trim(); reload(); }; }
  m.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { S.rkTab = b.dataset.tab; reload(); });
  m.querySelectorAll('[data-rk]').forEach(b => b.onclick = () => download(`/api/rekap-dinas/dok?${qs}&format=${b.dataset.rk}`, `Rekap_Perjalanan_Dinas_${T}.${b.dataset.rk}`));
}

// ---------- Akuntansi & Laporan Keuangan (PSAP 13) ----------
S.akTab = 'laporan'; S.akJenis = 'lra'; S.akBulan = 12;
const LAP = [['lra', 'LRA'], ['lsal', 'L-SAL'], ['neraca', 'Neraca'], ['lo', 'LO'], ['lak', 'LAK'], ['lpe', 'LPE'], ['calk', 'CaLK']];
const fl = n => n === null || n === undefined ? '' : n < 0 ? '(' + Math.abs(n).toLocaleString('id-ID') + ')' : n.toLocaleString('id-ID');
const fx = (c, n) => c === '%' ? (n === null || n === undefined ? '' : String(n).replace('.', ',') + '%') : fl(n);
async function viewAkun(m) {
  const T = S.bokTahun, tab = S.akTab;
  const reload = () => viewAkun(m);
  let isi = '';
  const dlBtns = (jenis) => { const sf = jenis ? ' ' + jenis.toUpperCase() : ' (semua)'; return `<a class="btn small" href="/api/laporan/dok?tahun=${T}&bulan=${S.akBulan}${jenis ? '&jenis=' + jenis : ''}&format=pdf" target="_blank">PDF${sf}</a><button class="btn small" data-lap="docx" data-j="${jenis}">DOCX${sf}</button><button class="btn small" data-lap="xlsx" data-j="${jenis}">XLSX${sf}</button>`; };
  if (tab === 'laporan') {
    const [rep, cek] = await Promise.all([api(`/api/laporan?tahun=${T}&bulan=${S.akBulan}&jenis=${S.akJenis}`), api(`/api/laporan/periksa?tahun=${T}&bulan=${S.akBulan}`)]);
    const kol = rep.kolom;
    isi = `${cek.ok ? '<div class="card" style="padding:8px;border-color:#86efac">✔ Pemeriksaan integritas: semua jurnal seimbang dan laporan saling cocok.</div>' : `<div class="card err" style="padding:8px">${cek.jurnal_tidak_seimbang.length ? 'Ada jurnal tidak seimbang. ' : ''}${cek.peringatan.map(esc).join('<br>')}</div>`}
     <div class="tabs">${LAP.map(([k, l]) => `<button class="tab ${S.akJenis === k ? 'on' : ''}" data-jenis="${k}">${l}</button>`).join('')}</div>
     <div class="card"><div style="text-align:center"><b>${esc(rep.judul)}</b><br><span class="muted">${esc(rep.periode)}${S.akJenis !== 'calk' ? ' · (dalam Rupiah)' : ''}</span></div>
     ${S.akJenis === 'calk' ? `<div style="margin-top:8px">${rep.baris.map(r => r.teks ? `<p>${esc(r.teks)}</p>` : r.t ? `<p style="margin:10px 0 2px"><b>${esc(r.u)}</b></p>` : `<div style="display:flex;justify-content:space-between;padding:1px 0 1px ${r.lv * 14}px"><span>${esc(r.u)}</span><span>${fl(r.v[0])}</span></div>`).join('')}</div>`
      : `<div class="tbl-wrap"><table><thead><tr><th>Uraian</th>${kol.map(k => `<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${rep.baris.map(r => `<tr class="${r.b && !r.t ? 'grp' : ''}"><td style="padding-left:${8 + r.lv * 16}px;${r.b ? 'font-weight:700' : ''}">${esc(r.u)}</td>${kol.map((c, i) => `<td class="num" style="${r.b ? 'font-weight:700' : ''}">${fx(c, r.v[i])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
     ${(rep.catatan || []).map(c => `<p class="muted" style="font-size:.85em">* ${esc(c)}</p>`).join('')}</div>`;
  } else if (tab === 'jurnal') {
    const j = await api('/api/akun/jurnal?tahun=' + T);
    isi = `<div class="bar"><button class="btn primary" id="akPend">+ Penerimaan pendapatan</button><button class="btn" id="akJur">+ Jurnal manual</button><span class="muted">SPJ yang dibayar otomatis menjadi jurnal kas.</span></div>
     <div class="tbl-wrap"><table><thead><tr><th>Tanggal</th><th>Bukti</th><th>Uraian</th><th>Basis</th><th>Dana</th><th>Akun (D / K)</th><th>Jumlah</th><th></th></tr></thead><tbody>
     ${j.map(x => `<tr><td style="white-space:nowrap">${tglID(x.tanggal)}</td><td style="font-size:.8em">${esc(x.no_bukti || '')}</td><td>${esc(x.uraian)}</td><td><span class="badge">${x.basis}</span></td><td>${x.dana || ''}</td>
      <td style="font-size:.82em">${x.baris.map(b => `${b.debit ? 'D' : 'K'} ${esc(b.kode)} ${esc(b.nama)}`).join('<br>')}</td><td class="num">${rp(x.total)}</td><td>${x.ref_jenis || x.basis === 'AWAL' ? '<span class="muted" style="font-size:.8em">otomatis</span>' : `<button class="btn small danger" data-hj="${x.id}">Hapus</button>`}</td></tr>`).join('') || '<tr><td colspan="8" class="muted">Belum ada jurnal.</td></tr>'}</tbody></table></div>`;
  } else if (tab === 'saldo') {
    const sa = await api('/api/akun/saldo-awal?tahun=' + T);
    isi = `<p class="muted">Saldo awal (neraca awal) tahun ${T}. Aset harus sama dengan Kewajiban + Ekuitas. Isi nilai positif pada sisi normal akun (akumulasi penyusutan diisi positif).</p>
     <div class="tbl-wrap"><table><thead><tr><th>Kode</th><th>Akun</th><th>Jenis</th><th>Saldo awal (Rp)</th></tr></thead><tbody>${sa.map(a => `<tr><td>${a.kode}</td><td>${esc(a.nama)}</td><td>${a.jenis}</td><td><input type="number" min="0" class="saldo" data-a="${a.id}" data-j="${a.jenis}" data-n="${a.normal}" value="${a.debit || a.kredit || ''}" style="width:160px"></td></tr>`).join('')}</tbody></table></div>
     <div class="bar"><span id="saldoCek" class="muted"></span><span style="flex:1"></span><button class="btn primary" id="saldoSimpan">Simpan saldo awal</button></div>`;
  } else if (tab === 'anggaran') {
    const an = await api('/api/akun/anggaran-pendapatan?tahun=' + T);
    isi = `<p class="muted">Anggaran pendapatan tahun ${T} (untuk kolom Anggaran pada LRA). Anggaran belanja diambil otomatis dari RAB semua sumber dana.</p>
     <div class="tbl-wrap"><table><thead><tr><th>Kode</th><th>Akun pendapatan</th><th>Anggaran (Rp)</th></tr></thead><tbody>${an.map(a => `<tr><td>${a.kode}</td><td>${esc(a.nama)}</td><td><input type="number" min="0" class="ang" data-a="${a.id}" value="${a.jumlah || ''}" style="width:170px"></td></tr>`).join('')}</tbody></table></div>
     <div class="bar"><span style="flex:1"></span><button class="btn primary" id="angSimpan">Simpan anggaran</button></div>`;
  } else if (tab === 'bagan') {
    const ak = await api('/api/akun');
    isi = `<div class="bar"><button class="btn primary" id="akBaru">+ Akun baru</button></div><div class="tbl-wrap"><table><thead><tr><th>Kode</th><th>Nama</th><th>Jenis</th><th>Normal</th><th>Keterangan</th><th></th></tr></thead><tbody>
     ${ak.map(a => `<tr class="${a.aktif ? '' : 'batal'}"><td>${a.kode}</td><td>${esc(a.nama)}</td><td>${a.jenis}</td><td>${a.normal === 'D' ? 'Debit' : 'Kredit'}</td><td class="muted" style="font-size:.82em">${a.kas ? 'akun kas · ' : ''}${a.lra === 'BELANJA_MODAL' ? 'belanja modal · ' : a.lra === 'PEMBIAYAAN' ? 'pembiayaan · ' : ''}${a.arus.toLowerCase()}${a.dipakai ? ` · ${a.dipakai} baris jurnal` : ''}</td><td><button class="btn small" data-akt="${a.id}" data-on="${a.aktif}">${a.aktif ? 'Nonaktifkan' : 'Aktifkan'}</button></td></tr>`).join('')}</tbody></table></div>`;
  } else if (tab === 'calk') {
    const c = await api('/api/laporan/calk-teks?tahun=' + T);
    isi = `<p class="muted">Teks Catatan atas Laporan Keuangan. Angka rincian pos disusun otomatis dari jurnal.</p>${c.map(x => `<label>${esc(x.judul)}<textarea class="calk" data-k="${x.kode}" rows="4">${esc(x.isi)}</textarea></label>`).join('')}<div class="bar"><span style="flex:1"></span><button class="btn primary" id="calkSimpan">Simpan CaLK</button></div>`;
  }
  m.innerHTML = `<h2>Akuntansi &amp; Laporan Keuangan</h2>
   <p class="muted">Laporan keuangan BLU menurut PSAP 13 — <b>satu kesatuan</b> semua sumber dana (DAU, BOK, BLUD). Hanya Kepala dan Bendahara BLUD.</p>
   <div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="akTh" type="number" value="${T}" style="width:90px"></label>
    ${tab === 'laporan' ? `<select id="akBln">${BLN.map((b, i) => `<option value="${i + 1}" ${S.akBulan === i + 1 ? 'selected' : ''}>s.d. ${b}</option>`).join('')}</select><span style="flex:1"></span>${dlBtns('')}${dlBtns(S.akJenis)}` : ''}</div>
   <div class="tabs">${[['laporan', 'Laporan'], ['jurnal', 'Jurnal'], ['saldo', 'Saldo awal'], ['anggaran', 'Anggaran pendapatan'], ['bagan', 'Bagan akun'], ['calk', 'Teks CaLK']].map(([k, l]) => `<button class="tab ${tab === k ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div>${isi}`;
  $('#akTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); };
  if ($('#akBln')) $('#akBln').onchange = e => { S.akBulan = Number(e.target.value); reload(); };
  m.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { S.akTab = b.dataset.tab; reload(); });
  m.querySelectorAll('[data-jenis]').forEach(b => b.onclick = () => { S.akJenis = b.dataset.jenis; reload(); });
  m.querySelectorAll('[data-lap]').forEach(b => b.onclick = () => download(`/api/laporan/dok?tahun=${T}&bulan=${S.akBulan}${b.dataset.j ? '&jenis=' + b.dataset.j : ''}&format=${b.dataset.lap}`, `Laporan_Keuangan_${T}${b.dataset.j ? '_' + b.dataset.j : ''}.${b.dataset.lap}`));
  const aksi = fn => async () => { try { await fn(); } catch (x) { toast(x.message, 1); } };
  if ($('#akPend')) $('#akPend').onclick = async () => {
    const ak = (await api('/api/akun')).filter(a => a.jenis === 'PENDAPATAN' && a.aktif);
    dialog('Penerimaan pendapatan', `<label>Akun pendapatan<select name="akun_id">${ak.map(a => `<option value="${a.id}">${a.kode} ${esc(a.nama)}</option>`).join('')}</select></label>
      <div class="grid2"><label>Sumber dana<select name="sumber"><option>BLUD</option><option>BOK</option><option>DAU</option></select></label><label>Tanggal<input name="tanggal" type="date" value="${new Date().toISOString().slice(0, 10)}" required></label></div>
      <div class="grid2"><label>Jumlah (Rp)<input name="jumlah" type="number" min="1" required></label><label>No. bukti<input name="no_bukti"></label></div><label>Uraian<input name="uraian"></label>
      <p class="muted" style="font-size:.85em">Dicatat sebagai: Debit Kas (sesuai sumber dana) / Kredit akun pendapatan.</p>`, async d => { await api('/api/akun/pendapatan', { method: 'POST', body: d }); toast('Pendapatan dicatat.'); await reload(); });
  };
  if ($('#akJur')) $('#akJur').onclick = async () => {
    const ak = (await api('/api/akun')).filter(a => a.aktif), opt = ak.map(a => `<option value="${a.id}">${a.kode} ${esc(a.nama)}</option>`).join('');
    const baris = i => `<div class="grid3" style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:6px;margin-top:4px"><select name="a${i}"><option value="">— akun —</option>${opt}</select><input name="d${i}" type="number" min="0" placeholder="Debit"><input name="k${i}" type="number" min="0" placeholder="Kredit"></div>`;
    dialog('Jurnal manual', `<div class="grid2"><label>Tanggal<input name="tanggal" type="date" value="${new Date().toISOString().slice(0, 10)}" required></label><label>Basis<select name="basis"><option value="AKRUAL">Akrual (tidak ke LRA/LAK)</option><option value="KAS">Kas (masuk LRA &amp; LAK)</option></select></label></div>
      <label>Uraian<input name="uraian" required></label>${[0, 1, 2, 3].map(baris).join('')}<p class="muted" style="font-size:.85em">Debit total harus sama dengan kredit total.</p>`,
      async d => { const b = [0, 1, 2, 3].filter(i => d['a' + i]).map(i => ({ akun_id: Number(d['a' + i]), debit: Number(d['d' + i] || 0), kredit: Number(d['k' + i] || 0) })); await api('/api/akun/jurnal', { method: 'POST', body: { tanggal: d.tanggal, basis: d.basis, uraian: d.uraian, baris: b } }); toast('Jurnal tersimpan.'); await reload(); });
  };
  m.querySelectorAll('[data-hj]').forEach(b => b.onclick = () => dialog('Hapus jurnal?', '<p>Jurnal manual akan dihapus (tercatat di riwayat).</p>', async () => { await api('/api/akun/jurnal/' + b.dataset.hj, { method: 'DELETE' }); toast('Dihapus.'); await reload(); }, 'Hapus'));
  if ($('#saldoSimpan')) {
    const hitung = () => { let a = 0, p = 0; m.querySelectorAll('.saldo').forEach(i => { const v = Number(i.value || 0); if (i.dataset.j === 'ASET') a += i.dataset.n === 'D' ? v : -v; else p += v; }); $('#saldoCek').innerHTML = `Aset ${rp(a)} · Kewajiban+Ekuitas ${rp(p)} · ` + (a === p ? '<b class="okc">seimbang</b>' : `<b class="err">selisih ${rp(a - p)}</b>`); };
    m.querySelectorAll('.saldo').forEach(i => i.oninput = hitung); hitung();
    $('#saldoSimpan').onclick = aksi(async () => { await api('/api/akun/saldo-awal', { method: 'PUT', body: { tahun: T, saldo: [...m.querySelectorAll('.saldo')].map(i => ({ akun_id: Number(i.dataset.a), saldo: Number(i.value || 0) })) } }); toast('Saldo awal tersimpan.'); });
  }
  if ($('#angSimpan')) $('#angSimpan').onclick = aksi(async () => { await api('/api/akun/anggaran-pendapatan', { method: 'PUT', body: { tahun: T, anggaran: [...m.querySelectorAll('.ang')].map(i => ({ akun_id: Number(i.dataset.a), jumlah: Number(i.value || 0) })) } }); toast('Anggaran tersimpan.'); });
  if ($('#calkSimpan')) $('#calkSimpan').onclick = aksi(async () => { const b = {}; m.querySelectorAll('.calk').forEach(t => { b[t.dataset.k] = t.value; }); await api('/api/laporan/calk', { method: 'PUT', body: { tahun: T, bagian: b } }); toast('CaLK tersimpan.'); });
  if ($('#akBaru')) $('#akBaru').onclick = () => dialog('Akun baru', `<div class="grid2"><label>Kode<input name="kode" required placeholder="1.1.1.03"></label><label>Jenis<select name="jenis">${['ASET', 'KEWAJIBAN', 'EKUITAS', 'PENDAPATAN', 'BEBAN'].map(x => `<option>${x}</option>`).join('')}</select></label></div><label>Nama<input name="nama" required></label>
    <div class="grid2"><label>Arus kas<select name="arus"><option value="OPERASI">Operasi</option><option value="INVESTASI">Investasi</option><option value="PENDANAAN">Pendanaan</option></select></label><label>Pemetaan LRA<select name="lra"><option value="">—</option><option value="BELANJA_MODAL">Belanja modal</option><option value="PEMBIAYAAN">Pembiayaan</option></select></label></div>
    <label><input type="checkbox" name="kas"> Akun kas (khusus Aset)</label>`, async d => { await api('/api/akun', { method: 'POST', body: d }); toast('Akun ditambahkan.'); await reload(); });
  m.querySelectorAll('[data-akt]').forEach(b => b.onclick = aksi(async () => { await api('/api/akun/' + b.dataset.akt, { method: 'PUT', body: { aktif: b.dataset.on === '1' ? 0 : 1 } }); await reload(); }));
}

// ---------- Realisasi & SPJ ----------
S.spTab = 'spj'; S.spStatus = ''; S.spSumber = '';
const SP_BADGE = { Draft: 'st-Draft', Diajukan: 'st-Diajukan', Dikembalikan: 'st-Ditolak', Diverifikasi: 'st-Terjadwal', Dibayar: 'st-Terlaksana' };
async function viewSpj(m) {
  const T = S.bokTahun, penuhRole = S.bisaBaca;
  const sumberOk = ['BOK', 'DAU', 'BLUD'].filter(k => S.akses && S.akses[k].baca);
  if (!S.spSumber || !sumberOk.includes(S.spSumber)) S.spSumber = sumberOk[0] || '';
  const tab = !penuhRole ? 'spj' : S.spTab;
  const q = `tahun=${T}` + (S.spStatus ? `&status=${S.spStatus}` : '');
  const [daftar, belum] = await Promise.all([api('/api/spj?' + q), api('/api/spj/belum?tahun=' + T)]);
  const rgk = penuhRole && tab === 'realisasi' && S.spSumber ? await api(`/api/spj/ringkasan?tahun=${T}&sumber=${S.spSumber}`) : null;
  const baris = x => `<tr><td style="white-space:nowrap">${tglID(x.tanggal)}</td><td><b>${esc(x.pegawai_nama || x.penerima || '-')}</b><br><span class="muted">${esc(x.uraian)}</span></td>
    <td>${x.dana}</td><td class="num">${rp(x.total)}</td><td><span class="badge ${SP_BADGE[x.status]}">${x.status}</span>${x.no_bukti ? `<br><span class="muted" style="font-size:.8em">${esc(x.no_bukti)}</span>` : ''}</td>
    <td><button class="btn small" data-spj="${x.id}">Buka</button></td></tr>`;
  const bar = (p) => `<div class="persen"><i style="width:${Math.min(100, p)}%"></i></div>`;
  let isi = '';
  if (tab === 'spj') {
    isi = `<div class="tbl-wrap"><table><thead><tr><th>Tanggal</th><th>Penerima / uraian</th><th>Dana</th><th>Jumlah</th><th>Status</th><th></th></tr></thead><tbody>${daftar.map(baris).join('') || '<tr><td colspan="6" class="muted">Belum ada SPJ.</td></tr>'}</tbody></table></div>`;
  } else if (tab === 'belum') {
    isi = `<p class="muted">Perjalanan dinas yang ST/SPD-nya sudah terbit tetapi SPJ-nya belum dibuat.</p><div class="tbl-wrap"><table><thead><tr><th>ST</th><th>Petugas</th><th>Kegiatan</th><th>Tanggal</th><th>Biaya SPD</th><th></th></tr></thead><tbody>
      ${belum.map(x => `<tr><td style="white-space:nowrap">${esc(x.nomor)}<br><span class="muted">${x.dana}</span></td><td>${esc(x.pegawai)}</td><td>${esc(x.maksud)}</td><td>${tglID(x.mulai)}${x.selesai !== x.mulai ? ' – ' + tglID(x.selesai) : ''}</td><td class="num">${rp(x.total)}</td><td><button class="btn small primary" data-buat="${x.spd_id}">Buat SPJ</button></td></tr>`).join('') || '<tr><td colspan="6" class="muted">Semua SPD sudah memiliki SPJ.</td></tr>'}</tbody></table></div>`;
  } else if (rgk) {
    const t = rgk.total;
    isi = `<div class="tabs sumber">${sumberOk.map(k => `<button class="tab ${k === S.spSumber ? 'on' : ''}" data-sumber="${k}">${k}</button>`).join('')}</div>
      <div class="cards"><div class="card"><small>Pagu</small><b>${rp(t.pagu)}</b></div><div class="card"><small>Realisasi (dibayar)</small><b>${rp(t.realisasi)}</b></div><div class="card"><small>Dalam proses SPJ</small><b>${rp(t.proses)}</b></div><div class="card"><small>Sisa pagu</small><b>${rp(t.sisa)}</b></div><div class="card"><small>Serapan</small><b>${t.persen}%</b></div></div>
      <div class="bar"><a class="btn small" href="/api/spj/rekap/dok?tahun=${T}&sumber=${S.spSumber}">Rekap PDF</a><button class="btn small" data-rekap="docx">Rekap DOCX</button><button class="btn small" data-rekap="xlsx">Rekap XLSX</button></div>
      <div class="tbl-wrap"><table><thead><tr><th>Menu / rincian / baris</th><th>Pagu</th><th>Realisasi</th><th>Proses</th><th>Sisa</th><th>Serapan</th></tr></thead><tbody>
      ${rgk.menu.map(mn => `<tr class="grp"><td><b>${esc(mn.no)} ${esc(mn.nama)}</b></td><td class="num">${rp(mn.pagu)}</td><td class="num">${rp(mn.realisasi)}</td><td class="num">${rp(mn.proses)}</td><td class="num">${rp(mn.sisa)}</td><td>${mn.persen}%</td></tr>`
        + mn.rincian.map(ri => `<tr><td style="padding-left:18px"><b>${esc(ri.nama)}</b></td><td class="num">${rp(ri.pagu)}</td><td class="num">${rp(ri.realisasi)}</td><td class="num">${rp(ri.proses)}</td><td class="num">${rp(ri.sisa)}</td><td>${ri.persen}%</td></tr>`
          + ri.baris.map(b => `<tr><td style="padding-left:36px" class="muted">${esc(b.uraian)}</td><td class="num">${rp(b.pagu)}</td><td class="num">${rp(b.realisasi)}</td><td class="num">${rp(b.proses)}</td><td class="num">${rp(b.sisa)}</td><td>${bar(b.persen)}</td></tr>`).join('')).join('')).join('') || '<tr><td colspan="6" class="muted">Belum ada RAB untuk tahun/sumber ini.</td></tr>'}</tbody></table></div>`;
  }
  m.innerHTML = `<h2>Realisasi &amp; SPJ</h2>
   <p class="muted">${penuhRole ? 'Alur: Draft → Diajukan → Diverifikasi → Dibayar (tanpa panjar; dibayar setelah SPJ diverifikasi). Hanya SPJ <b>Dibayar</b> yang dihitung sebagai realisasi.' : 'SPJ perjalanan dinas Anda. Isi realisasi biaya dan nomor bukti, lalu ajukan ke bendahara.'}</p>
   <div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="spTh" type="number" value="${T}" style="width:90px"></label>
    ${tab === 'spj' ? `<select id="spSt"><option value="">Semua status</option>${['Draft', 'Diajukan', 'Dikembalikan', 'Diverifikasi', 'Dibayar'].map(x => `<option ${S.spStatus === x ? 'selected' : ''}>${x}</option>`).join('')}</select>` : ''}
    <span style="flex:1"></span>${penuhRole && S.spSumber && S.akses[S.spSumber].rencana ? '<button class="btn" id="spUmum">+ Belanja non-perjalanan</button>' : ''}</div>
   ${penuhRole ? `<div class="tabs"><button class="tab ${tab === 'spj' ? 'on' : ''}" data-tab="spj">Daftar SPJ</button><button class="tab ${tab === 'belum' ? 'on' : ''}" data-tab="belum">Belum dibuat (${belum.length})</button><button class="tab ${tab === 'realisasi' ? 'on' : ''}" data-tab="realisasi">Realisasi anggaran</button></div>`
     : (belum.length ? `<div class="card"><b>Perjalanan dinas Anda yang belum dibuat SPJ-nya:</b>${belum.map(x => `<p>${tglID(x.mulai)} · ${esc(x.maksud)} (${rp(x.total)}) <button class="btn small primary" data-buat="${x.spd_id}">Buat SPJ</button></p>`).join('')}</div>` : '')}
   ${isi}`;
  const reload = () => viewSpj(m);
  $('#spTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); };
  if ($('#spSt')) $('#spSt').onchange = e => { S.spStatus = e.target.value; reload(); };
  m.querySelectorAll('[data-tab]').forEach(t => t.onclick = () => { S.spTab = t.dataset.tab; reload(); });
  m.querySelectorAll('[data-sumber]').forEach(t => t.onclick = () => { S.spSumber = t.dataset.sumber; reload(); });
  m.querySelectorAll('[data-rekap]').forEach(b => b.onclick = () => download(`/api/spj/rekap/dok?tahun=${T}&sumber=${S.spSumber}&format=${b.dataset.rekap}`, `Rekap_SPJ_${S.spSumber}_${T}.${b.dataset.rekap}`));
  m.querySelectorAll('[data-buat]').forEach(b => b.onclick = async () => { try { const r = await api(`/api/spj/spd/${b.dataset.buat}`, { method: 'POST' }); S.spTab = 'spj'; await bukaSpj(r.id, reload); } catch (x) { toast(x.message, 1); } });
  m.querySelectorAll('[data-spj]').forEach(b => b.onclick = () => bukaSpj(Number(b.dataset.spj), reload).catch(x => toast(x.message, 1)));
  if ($('#spUmum')) $('#spUmum').onclick = async () => {
    const rg = await api(`/api/spj/ringkasan?tahun=${T}&sumber=${S.spSumber}`);
    const opsi = rg.menu.flatMap(mn => mn.rincian.flatMap(ri => ri.baris.map(b => `<option value="${b.baris_id}">${esc(mn.no)} · ${esc(ri.nama)} · ${esc(b.uraian)} (sisa ${rp(b.sisa)})</option>`)));
    dialog('Belanja non-perjalanan — ' + S.spSumber, `<label>Baris RAB<select name="baris_id" required>${opsi.join('')}</select></label>
      <label>Uraian<input name="uraian" required minlength="3"></label><div class="grid2"><label>Tanggal<input name="tanggal" type="date" value="${new Date().toISOString().slice(0, 10)}" required></label><label>Jumlah (Rp)<input name="jumlah" type="number" min="1" required></label></div>
      <div class="grid2"><label>Penerima / toko<input name="penerima"></label><label>No. bukti (nota/kuitansi)<input name="bukti"></label></div>`,
      async d => { const r = await api('/api/spj', { method: 'POST', body: d }); toast('SPJ dibuat (Draft).'); await reload(); await bukaSpj(r.id, reload); });
  };
}
async function bukaSpj(id, reload) {
  const x = await api('/api/spj/' + id), umum = x.jenis === 'UMUM';
  const edit = x.bisa_ubah;
  const dok = f => `<a class="btn small" href="/api/spj/${id}/dok" target="_blank">PDF</a> <button type="button" class="btn small" data-dl="docx">DOCX</button>`;
  const rinci = x.rincian.map((r, i) => umum ? '' : `<tr><td>${esc(r.uraian)}<br><span class="muted" style="font-size:.8em">${r.volume} ${esc(r.satuan)} × ${rp(r.tarif)}</span></td><td class="num">${rp(r.rencana)}</td>
     <td>${edit ? `<input data-j="${i}" type="number" min="0" max="${r.rencana}" value="${r.jumlah}" style="width:120px">` : rp(r.jumlah)}</td><td>${edit ? `<input data-b="${i}" value="${esc(r.bukti || '')}" placeholder="No. bukti / ket.">` : esc(r.bukti || '')}</td></tr>`).join('');
  dialog(`SPJ #${x.id} — ${x.status}`, `<div class="kvl"><b>Dana</b><span>${x.dana} · ${esc(x.kode_rekening || '')}</span><b>Penerima</b><span>${esc(x.pegawai_nama || x.penerima || '-')}</span>
     <b>Uraian</b><span>${esc(x.uraian)}</span>${x.st_nomor ? `<b>ST</b><span>${esc(x.st_srikandi || x.st_nomor)}</span>` : ''}
     ${x.no_bukti ? `<b>Bukti bayar</b><span>${esc(x.no_bukti)} · ${tglID(x.tanggal_bayar)}</span>` : ''}${x.alasan_kembali ? `<b>Dikembalikan</b><span class="err">${esc(x.alasan_kembali)}</span>` : ''}</div>
    ${umum ? (edit ? `<label>Uraian<input name="uraian" value="${esc(x.uraian)}"></label><div class="grid2"><label>Tanggal<input name="tanggal" type="date" value="${x.tanggal}"></label><label>Jumlah<input name="jumlah" type="number" min="1" value="${x.total}"></label></div><div class="grid2"><label>Penerima<input name="penerima" value="${esc(x.penerima || '')}"></label><label>No. bukti<input name="bukti" value="${esc(x.rincian[0]?.bukti || '')}"></label></div>` : `<p><b>${rp(x.total)}</b> · bukti: ${esc(x.rincian[0]?.bukti || '-')}</p>`)
      : `${edit ? `<div class="grid2"><label>Berangkat<input name="mulai" type="date" value="${x.mulai}"></label><label>Kembali<input name="selesai" type="date" value="${x.selesai}"></label></div>` : `<p>Pelaksanaan: ${tglID(x.mulai)} – ${tglID(x.selesai)}</p>`}
      <div class="tbl-wrap"><table><thead><tr><th>Komponen</th><th>Tarif SPD</th><th>Realisasi</th><th>Bukti</th></tr></thead><tbody>${rinci}</tbody><tfoot><tr><td><b>Total</b></td><td class="num">${rp(x.total_rencana)}</td><td colspan="2"><b>${rp(x.total)}</b></td></tr></tfoot></table></div>
      ${edit ? '<p class="muted" style="font-size:.85em">Realisasi tidak boleh melebihi tarif SPD (Perbup). Kosongkan/ turunkan komponen yang tidak dipakai.</p>' : ''}`}
    <h4 style="margin:12px 0 4px">Foto bukti <span class="muted" style="font-weight:400">(${x.berkas.length}/8)</span></h4>
    <div class="galeri">${x.berkas.map(b => b.tipe.startsWith('image/')
      ? `<div class="bk"><a href="/api/spj/bukti/${b.id}" target="_blank" title="${esc(b.nama)}"><img src="/api/spj/bukti/${b.id}" alt="${esc(b.nama)}" loading="lazy"></a>${edit ? `<button type="button" class="bkdel" data-bkdel="${b.id}" title="Hapus">×</button>` : ''}</div>`
      : `<div class="bk pdf"><a href="/api/spj/bukti/${b.id}" target="_blank">PDF<br><small>${esc(b.nama.slice(0, 14))}</small></a>${edit ? `<button type="button" class="bkdel" data-bkdel="${b.id}" title="Hapus">×</button>` : ''}</div>`).join('') || '<span class="muted">Belum ada foto bukti.</span>'}</div>
    ${edit ? `<div class="acts" style="margin-top:6px"><button type="button" class="btn small" id="bkKamera">📷 Ambil foto</button><button type="button" class="btn small" id="bkPilih">Pilih foto / PDF</button>
      <input type="file" id="bkInK" accept="image/*" capture="environment" hidden><input type="file" id="bkInP" accept="image/*,application/pdf" multiple hidden></div>
      <p class="muted" style="font-size:.82em;margin:4px 0">Foto dikecilkan otomatis. Maks. 8 berkas, 4 MB per berkas. Foto atau nomor bukti cukup untuk mengajukan SPJ.</p>` : ''}
    ${edit ? `<label>Catatan<input name="catatan" value="${esc(x.catatan || '')}"></label>` : ''}
    <div class="acts" style="margin-top:10px">${dok()}</div>
    <div class="acts" style="margin-top:10px;border-top:1px solid var(--line);padding-top:10px">
     ${edit ? '<button type="button" class="btn small" data-a="simpan">Simpan perubahan</button><button type="button" class="btn small primary" data-a="Diajukan">Simpan &amp; ajukan</button>' : ''}
     ${x.bisa_verifikasi ? '<button type="button" class="btn small primary" data-a="Diverifikasi">Verifikasi</button><button type="button" class="btn small danger" data-a="Dikembalikan">Kembalikan</button>' : ''}
     ${x.bisa_bayar ? '<button type="button" class="btn small primary" data-a="Dibayar">Catat pembayaran</button><button type="button" class="btn small danger" data-a="Dikembalikan">Kembalikan</button>' : ''}
     ${x.bisa_koreksi ? '<button type="button" class="btn small danger" data-a="koreksi">Koreksi pembayaran (Kepala)</button>' : ''}
     ${edit ? '<button type="button" class="btn small danger" data-a="hapus">Hapus</button>' : ''}</div>`, null);
  const f = $('#dlgForm');
  const kecilkan = file => new Promise((ok, gagal) => {
    if (file.type === 'application/pdf') return ok(file);
    const u = URL.createObjectURL(file), im = new Image();
    im.onload = () => {
      const k = Math.min(1, 1600 / Math.max(im.width, im.height)), c = document.createElement('canvas');
      c.width = Math.round(im.width * k); c.height = Math.round(im.height * k);
      c.getContext('2d').drawImage(im, 0, 0, c.width, c.height); URL.revokeObjectURL(u);
      c.toBlob(b => b ? ok(b) : gagal(new Error('Gagal memproses foto.')), 'image/jpeg', 0.82);
    };
    im.onerror = () => { URL.revokeObjectURL(u); gagal(new Error('Foto tidak dapat dibaca (format tidak didukung browser).')); };
    im.src = u;
  });
  const unggah = async daftar => {
    try {
      for (const file of daftar) {
        const blob = await kecilkan(file);
        const nama = (file.name || 'foto').replace(/\.[^.]+$/, '');
        const r = await fetch(`/api/spj/${id}/bukti?nama=${encodeURIComponent(nama)}`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: blob });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.error || 'Gagal mengunggah.');
      }
      try { await api('/api/spj/' + id, { method: 'PUT', body: kumpul() }); } catch { /* isian belum valid: abaikan, foto tetap tersimpan */ }
      toast('Bukti terunggah.'); $('#dlg').close(); await bukaSpj(id, reload);
    } catch (er) { toast(er.message, 1); }
  };
  if ($('#bkKamera')) {
    $('#bkKamera').onclick = () => $('#bkInK').click(); $('#bkPilih').onclick = () => $('#bkInP').click();
    $('#bkInK').onchange = e => unggah([...e.target.files]); $('#bkInP').onchange = e => unggah([...e.target.files]);
  }
  f.querySelectorAll('[data-bkdel]').forEach(b => b.onclick = async () => {
    if (!confirm('Hapus bukti ini?')) return;
    try { await api('/api/spj/bukti/' + b.dataset.bkdel, { method: 'DELETE' }); $('#dlg').close(); await bukaSpj(id, reload); } catch (er) { toast(er.message, 1); }
  });
  const kumpul = () => {
    const g = n => f.elements[n]?.value;
    if (umum) return { uraian: g('uraian'), tanggal: g('tanggal'), jumlah: g('jumlah'), penerima: g('penerima'), bukti: g('bukti'), catatan: g('catatan') };
    return { mulai: g('mulai'), selesai: g('selesai'), catatan: g('catatan'), rincian: x.rincian.map((_, i) => ({ jumlah: f.querySelector(`[data-j="${i}"]`).value, bukti: f.querySelector(`[data-b="${i}"]`).value })) };
  };
  f.onclick = async e => {
    const b = e.target.closest('[data-a],[data-dl]'); if (!b) return;
    if (b.dataset.dl) return download(`/api/spj/${id}/dok?format=docx`, `SPJ_${id}.docx`);
    const a = b.dataset.a, tutup = async () => { $('#dlg').close(); await reload(); };
    try {
      if (a === 'simpan') { await api('/api/spj/' + id, { method: 'PUT', body: kumpul() }); toast('Tersimpan.'); await tutup(); }
      else if (a === 'Diajukan') { await api('/api/spj/' + id, { method: 'PUT', body: kumpul() }); await api(`/api/spj/${id}/status`, { method: 'POST', body: { ke: 'Diajukan' } }); toast('SPJ diajukan.'); await tutup(); }
      else if (a === 'Diverifikasi') { await api(`/api/spj/${id}/status`, { method: 'POST', body: { ke: a } }); toast('SPJ diverifikasi.'); await tutup(); }
      else if (a === 'hapus') { if (confirm('Hapus SPJ ini?')) { await api('/api/spj/' + id, { method: 'DELETE' }); toast('Dihapus.'); await tutup(); } }
      else {
        $('#dlg').close();
        const judul = { Dikembalikan: 'Kembalikan SPJ', Dibayar: 'Catat pembayaran', koreksi: 'Koreksi pembayaran' }[a];
        const isiF = a === 'Dibayar' ? `<div class="grid2"><label>Tanggal bayar<input name="tanggal_bayar" type="date" value="${new Date().toISOString().slice(0, 10)}" required></label><label>No. bukti (kosong = otomatis)<input name="no_bukti"></label></div><p>Total <b>${rp(x.total)}</b></p>` : '<label>Alasan<input name="alasan" required minlength="5"></label>';
        dialog(judul, isiF, async d => { await api(a === 'koreksi' ? `/api/spj/${id}/koreksi` : `/api/spj/${id}/status`, { method: 'POST', body: a === 'koreksi' ? d : { ke: a, ...d } }); toast('Berhasil.'); await reload(); });
      }
    } catch (er) { toast(er.message, 1); }
  };
}

// ---------- Penomoran Surat ----------
S.nmJenis = '';
async function viewNomor(m) {
  const T = S.bokTahun, kepala = S.user.role === 'kepala';
  const [jenis, daftar] = await Promise.all([api('/api/nomor/jenis'), api(`/api/nomor?tahun=${T}` + (S.nmJenis ? `&jenis=${S.nmJenis}` : ''))]);
  const umum = jenis.filter(j => !j.kode.startsWith('ST-') && j.aktif);
  m.innerHTML = `<h3>Nomor surat umum &amp; kode penomoran</h3>
   <p class="muted">Pola nomor mengikuti contoh Srikandi: <code>klasifikasi/yymm-urut/unit/bulan-romawi/tahun</code>. Klasifikasi arsip menurut Permendagri 83/2022 (<b>000.1.2.3</b> = Perjalanan Dinas Pegawai; <b>000</b> = Umum); tata naskah menurut Permendagri 1/2023.
   Seri nomor <b>terpisah</b> untuk BOK, DAU, BLUD, dan Surat Umum; nomor tidak pernah dipakai ulang. Nomor resmi Surat Tugas tetap diberikan Srikandi saat TTE.</p>
   <div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="nTh" type="number" value="${T}" style="width:90px"></label>
    <select id="nJn"><option value="">Semua jenis</option>${jenis.map(j => `<option value="${j.kode}" ${S.nmJenis === j.kode ? 'selected' : ''}>${esc(j.nama)}</option>`).join('')}</select><span style="flex:1"></span>
    <button class="btn primary" id="nBaru">+ Terbitkan nomor surat</button></div>
   <div class="tbl-wrap"><table><thead><tr><th>Nomor</th><th>Tanggal</th><th>Perihal / tujuan</th><th>Status</th><th></th></tr></thead><tbody>
    ${daftar.map(n => `<tr class="${n.status === 'Dibatalkan' ? 'batal' : ''}"><td style="white-space:nowrap"><b>${esc(n.nomor)}</b></td><td>${tglID(n.tanggal)}</td><td>${esc(n.perihal)}${n.tujuan ? `<br><span class="muted">kepada ${esc(n.tujuan)}</span>` : ''}</td>
      <td><span class="badge ${n.status === 'Terbit' ? 'st-Disetujui' : 'st-Dibatalkan'}">${n.status}</span>${n.alasan_batal ? `<br><span class="err" style="font-size:.8em">${esc(n.alasan_batal)}</span>` : ''}</td>
      <td>${n.status === 'Terbit' ? `<button class="btn small danger" data-batal="${n.id}">Batalkan</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">Belum ada nomor surat umum pada tahun ini. Nomor Surat Tugas ada di menu Surat Tugas &amp; SPD.</td></tr>'}</tbody></table></div>
   <h3 style="margin-top:22px">Kode penomoran</h3>
   <div class="tbl-wrap"><table><thead><tr><th>Jenis</th><th>Klasifikasi</th><th>Kode unit</th><th>Contoh nomor berikutnya</th>${kepala ? '<th></th>' : ''}</tr></thead><tbody id="nKode"></tbody></table></div>
   <p class="muted" style="font-size:.85em">Kode unit membedakan seri BOK / DAU / BLUD / Umum. Hanya Kepala Puskesmas yang dapat mengubah kode; perubahan berlaku untuk nomor berikutnya.</p>`;
  const hari = new Date().toISOString().slice(0, 10);
  const contoh = await Promise.all(jenis.map(j => api(`/api/nomor/pratinjau?jenis=${j.kode}&tanggal=${hari}`).then(r => r.nomor).catch(() => '–')));
  $('#nKode').innerHTML = jenis.map((j, i) => `<tr><td><b>${esc(j.nama)}</b><br><span class="muted" style="font-size:.82em">${esc(j.keterangan || '')}</span></td><td>${esc(j.klasifikasi)}</td><td>${esc(j.unit)}</td><td><code>${esc(contoh[i])}</code></td>
    ${kepala ? `<td><button class="btn small" data-kode="${j.kode}">Ubah</button></td>` : ''}</tr>`).join('');
  const reload = () => viewNomor(m);
  $('#nTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); };
  $('#nJn').onchange = e => { S.nmJenis = e.target.value; reload(); };
  $('#nBaru').onclick = () => {
    dialog('Terbitkan nomor surat', `<label>Jenis<select name="jenis">${umum.map(j => `<option value="${j.kode}">${esc(j.nama)}</option>`).join('')}</select></label>
      <div class="grid2"><label>Tanggal surat<input name="tanggal" type="date" value="${hari}" required></label><label>Klasifikasi (boleh dirinci)<input name="klasifikasi" placeholder="${esc(umum[0]?.klasifikasi || '000')}"></label></div>
      <label>Perihal<input name="perihal" required></label><label>Tujuan / kepada (opsional)<input name="tujuan"></label>
      <div class="card" style="padding:10px">Nomor berikutnya: <b id="nPrev">…</b></div>`,
      async d => { const r = await api('/api/nomor', { method: 'POST', body: d }); toast('Nomor terbit: ' + r.nomor); await reload(); });
    const f = $('#dlgForm'); let tm;
    const seg = async () => { const q = new URLSearchParams({ jenis: f.elements.jenis.value, tanggal: f.elements.tanggal.value || hari }); if (f.elements.klasifikasi.value) q.set('klasifikasi', f.elements.klasifikasi.value); try { $('#nPrev').textContent = (await api('/api/nomor/pratinjau?' + q)).nomor; } catch (x) { $('#nPrev').textContent = x.message; } };
    f.addEventListener('input', () => { clearTimeout(tm); tm = setTimeout(seg, 250); }); f.addEventListener('change', seg); seg();
  };
  m.onclick = e => {
    const b = e.target.closest('[data-batal]'), k = e.target.closest('[data-kode]');
    if (b) dialog('Batalkan nomor?', '<p>Nomor yang dibatalkan <b>tidak dipakai ulang</b>.</p><label>Alasan<input name="alasan" required minlength="5"></label>', async d => { await api(`/api/nomor/${b.dataset.batal}/batal`, { method: 'POST', body: d }); toast('Nomor dibatalkan.'); await reload(); }, 'Batalkan');
    if (k) { const j = jenis.find(x => x.kode === k.dataset.kode); dialog('Kode penomoran — ' + j.nama, `<div class="grid2"><label>Klasifikasi arsip<input name="klasifikasi" value="${esc(j.klasifikasi)}" required></label><label>Kode unit<input name="unit" value="${esc(j.unit)}" required></label></div>
      <label>Format<input name="format" value="${esc(j.format)}" required></label><p class="muted" style="font-size:.82em">Kode yang tersedia: {klasifikasi} {yymm} {urut} {unit} {bulan_romawi} {tahun}. Format wajib memuat {urut}.</p>`, async d => { await api('/api/nomor/jenis/' + j.kode, { method: 'PUT', body: d }); toast('Kode penomoran disimpan.'); await reload(); }); }
  };
}

// ---------- Surat Tugas (ST) & SPD ----------
S.stTab = 'terbit';
async function viewSurat(m) {
  const T = S.bokTahun, penuhRole = S.bisaBaca;
  const [siap, daftar] = await Promise.all([penuhRole ? api(`/api/st/siap?tahun=${T}`) : Promise.resolve([]), api(`/api/st?tahun=${T}`)]);
  const tab = ['siap', 'nomor'].includes(S.stTab) && penuhRole ? S.stTab : 'terbit';
  const bdg = x => `<span class="badge ${x.status === 'Terbit' ? 'st-Disetujui' : 'st-Dibatalkan'}">${x.status}${x.versi > 1 ? ' v' + x.versi : ''}</span>`;
  const nm = n => n.split(',')[0];
  m.innerHTML = `<h2>Surat</h2>
   <p class="muted">${penuhRole ? 'ST dan SPD dibuat dari jadwal yang sudah disetujui. Ekspor <b>DOCX Srikandi</b> memakai templat resmi (kode tanda tangan elektronik dibiarkan untuk diisi Srikandi). Setelah terbit, isi ST <b>terkunci</b>; perubahan hanya lewat pembatalan + terbit ulang.' : 'Surat Tugas dan SPD Anda.'}</p>
   ${tab === 'nomor' ? '' : `<div class="bar"><label style="display:flex;gap:6px;align-items:center">Tahun <input id="sTh" type="number" value="${T}" style="width:90px"></label></div>`}
   ${penuhRole ? `<div class="tabs"><button class="tab ${tab === 'terbit' ? 'on' : ''}" data-tab="terbit">Surat Tugas &amp; SPD (${daftar.length})</button><button class="tab ${tab === 'siap' ? 'on' : ''}" data-tab="siap">Siap diterbitkan (${siap.length})</button><button class="tab ${tab === 'nomor' ? 'on' : ''}" data-tab="nomor">Nomor surat umum &amp; kode</button></div>` : ''}
   ${tab === 'nomor' ? '<div id="nomorBox"></div>' : tab === 'siap' ? (siap.length ? `<div class="bar"><span class="muted">${S.kepalaWajib ? 'Hanya jadwal yang sudah disetujui Kepala.' : 'Persetujuan Kepala opsional: Anda mengotorisasi sendiri saat menerbitkan.'}</span><span style="flex:1"></span><button class="btn primary" id="terbitMassal">Terbitkan yang dipilih</button></div><div class="tbl-wrap"><table><thead><tr><th><input type="checkbox" id="siapSemua" title="Pilih semua"></th><th>Tanggal</th><th>Kegiatan</th><th>Lokasi</th><th>Petugas</th><th>Dana</th><th></th></tr></thead><tbody>
      ${siap.map(j => `<tr><td><input type="checkbox" class="siapPilih" value="${j.id}"></td><td style="white-space:nowrap">${tglID(j.mulai)}${j.selesai !== j.mulai ? '<br>s.d. ' + tglID(j.selesai) : ''}</td><td>${esc(j.kegiatan)}</td><td>${esc(j.lokasi)}</td><td>${j.petugas.map(x => esc(nm(x))).join(', ')}</td><td>${esc(j.dana)}</td>
       <td><button class="btn small primary" data-terbit="${j.id}">Terbitkan ST</button></td></tr>`).join('')}</tbody></table></div>`
      : '<div class="card"><p>Tidak ada jadwal Disetujui yang menunggu Surat Tugas.</p><p class="muted">Jadwal harus berstatus <b>Disetujui</b> (oleh Kepala) dan Anda harus berwenang atas sumber dananya. Pengelola Program tidak menerbitkan ST.</p></div>')
    : `<div class="tbl-wrap"><table><thead><tr><th>Nomor</th><th>Tanggal</th><th>Kegiatan / tujuan</th><th>Petugas</th><th>Realisasi belanja</th><th>Status</th><th></th></tr></thead><tbody>
      ${daftar.map(x => `<tr class="${x.status === 'Dibatalkan' ? 'batal' : ''}"><td style="white-space:nowrap"><b>${esc(x.nomor)}</b><br>${x.nomor_srikandi ? `<span class="okc">Srikandi: ${esc(x.nomor_srikandi)}</span>` : '<span class="muted">belum ada nomor Srikandi</span>'}</td>
        <td style="white-space:nowrap">${tglID(x.mulai)}${x.selesai !== x.mulai ? '<br>s.d. ' + tglID(x.selesai) : ''}</td><td>${esc(x.maksud)}<br><span class="muted">${esc(x.lokasi)} · ${esc(x.dana)}</span></td>
        <td>${x.spd.length} orang</td><td style="white-space:nowrap">${x.status === 'Dibatalkan' ? '-' : x.penuh ? `${rp(x.realisasi.dibayar)}<br><span class="muted">${x.realisasi.lunas}/${x.realisasi.petugas} SPJ dibayar</span>` : x.spd.map(p => `<span class="badge ${SP_BADGE[p.spj_status] || ''}">${p.spj_status || '-'}</span>`).join(' ')}</td><td>${bdg(x)}${x.status === 'Terbit' ? `<br><span class="badge ${x.srikandi.selesai ? 'st-Terlaksana' : 'st-Diajukan'}" title="Diunggah ke Srikandi · nomor dicatat · PDF final">${x.srikandi.selesai ? 'Selesai di Srikandi' : 'Srikandi ' + [x.srikandi.diunggah, x.srikandi.nomor, x.srikandi.final].filter(Boolean).length + '/3'}</span>` : ''}${x.alasan_batal ? `<br><span class="err" style="font-size:.8em">${esc(x.alasan_batal)}</span>` : ''}</td><td><button class="btn small" data-buka="${x.id}">Dokumen</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">Belum ada Surat Tugas.</td></tr>'}</tbody></table></div>`}`;
  const reload = () => viewSurat(m);
  if (tab === 'nomor') { m.querySelectorAll('[data-tab]').forEach(t => t.onclick = () => { S.stTab = t.dataset.tab; reload(); }); return viewNomor($('#nomorBox')); }
  $('#sTh').onchange = e => { S.bokTahun = Number(e.target.value) || T; reload(); };
  m.querySelectorAll('[data-tab]').forEach(t => t.onclick = () => { S.stTab = t.dataset.tab; reload(); });

  if ($('#siapSemua')) {
    $('#siapSemua').onchange = e => m.querySelectorAll('.siapPilih').forEach(c => { c.checked = e.target.checked; });
    $('#terbitMassal').onclick = async () => {
      const ids = [...m.querySelectorAll('.siapPilih:checked')].map(c => Number(c.value));
      if (!ids.length) return toast('Centang jadwal yang akan diterbitkan.', 1);
      if (!confirm(`Terbitkan ${ids.length} Surat Tugas dengan isian bawaan (dasar, maksud, DPA, penandatangan utama)? Hanya yang berstatus siap akan diproses.`)) return;
      try {
        const r = await api('/api/st/terbit-massal', { method: 'POST', body: { jadwal_ids: ids } });
        toast(`${r.berhasil} ST terbit${r.gagal ? `, ${r.gagal} gagal: ` + r.hasil.filter(x => !x.ok).map(x => x.error).join('; ') : ''}`, r.gagal ? 1 : 0);
        S.stTab = 'terbit'; await reload();
      } catch (x) { toast(x.message, 1); }
    };
  }
  async function terbit(jid) {
    const dr = await api('/api/st/draft/' + jid);
    dialog('Terbitkan Surat Tugas', `
      <div class="card" style="padding:10px"><b>${esc(dr.kegiatan)}</b><br><span class="muted">${esc(dr.lokasi)} · ${tglID(dr.mulai)}${dr.selesai !== dr.mulai ? ' s.d. ' + tglID(dr.selesai) : ''} · ${esc(dr.dana)}<br>Petugas: ${dr.petugas.map(x => esc(nm(x))).join(', ')}</span></div>
      <p class="muted" style="margin:0">Nomor internal berikutnya: <b>${esc(dr.nomor_pratinjau)}</b>. Nomor naskah resmi (<code>\${nomor_naskah}</code>) diberikan Srikandi saat ditandatangani; catat setelahnya.</p>
      <div class="grid2"><label>Tanggal surat<input name="tanggal_surat" type="date" value="${dr.tanggal_surat}" required></label>
       <label>Penandatangan<select name="penandatangan_id">${dr.pejabat.map(p => `<option value="${p.id}">${esc(p.label)}</option>`).join('')}</select></label></div>
      <label>Dasar (satu baris per dasar)<textarea name="dasar" rows="3">${esc(dr.dasar)}</textarea></label>
      <label>Untuk — dalam rangka<textarea name="maksud" rows="3" required>${esc(dr.maksud)}</textarea></label>
      <label>Nomor DPA<input name="dpa" value="${esc(dr.dpa)}"></label>
      <p class="warn" style="margin:0">Setelah terbit, isi ST tidak dapat diubah (hanya dibatalkan, lalu diterbitkan ulang dengan nomor baru).</p>`,
      async d => { const r = await api('/api/st/terbit', { method: 'POST', body: { ...d, jadwal_id: jid } }); toast(`ST terbit: ${r.nomor}`); S.stTab = 'terbit'; await reload(); }, 'Terbitkan');
  }
  const docUrl = (id, dok, mode) => `/api/st/${id}/dok?dok=${dok}${mode ? '&mode=' + mode : ''}`;
  function buka(id) {
    const x = daftar.find(r => r.id === id), aktif = x.status === 'Terbit';
    const L = (dok, label, cls = '') => `<span class="fmt"><b>${label}</b> <button type="button" class="btn small" data-d="${dok}">PDF</button>${x.penuh || !['st', 'spd', 'paket'].includes(dok) ? ` <button type="button" class="btn small" data-d="${dok}" data-f="docx">DOCX</button>` : ''}</span> `;
    dialog(`ST ${x.nomor}`, `<div class="kvl"><b>Status</b><span>${bdg(x)}</span><b>Nomor Srikandi</b><span>${x.nomor_srikandi ? esc(x.nomor_srikandi) : '<span class="muted">belum dicatat</span>'}</span>
      <b>Kegiatan</b><span>${esc(x.maksud)}</span><b>Tempat/Waktu</b><span>${esc(x.lokasi)}, ${tglID(x.mulai)}${x.selesai !== x.mulai ? ' s.d. ' + tglID(x.selesai) : ''}</span>
      <b>Petugas</b><span>${x.spd.map(p => `${esc(nm(p.nama))}${x.penuh ? ` <span class="muted">(${rp(p.total)})</span>` : ''}`).join('<br>')}</span>
      ${aktif ? `<b>Realisasi belanja</b><span>${x.spd.map(p => `${esc(nm(p.nama))}: <span class="badge ${SP_BADGE[p.spj_status] || ''}">${p.spj_status || 'belum ada SPJ'}</span>${p.spj_total != null && x.penuh ? ' ' + rp(p.spj_total) : ''}${p.spj_bukti ? ` <span class="muted">${esc(p.spj_bukti)}</span>` : ''} ${p.spj_id ? `<button type="button" class="btn small" data-spj="${p.spj_id}">Buka SPJ</button>` : ''}`).join('<br>')}</span>` : ''}
      <b>Diterbitkan</b><span>${esc(x.dibuat_oleh)} · ${esc(x.dibuat_pada)}</span>${x.alasan_batal ? `<b>Dibatalkan</b><span class="err">${esc(x.alasan_batal)} (${esc(x.dibatalkan_oleh)})</span>` : ''}</div>
      ${aktif && x.penuh ? `<h4 style="margin:12px 0 4px">Penyelesaian di Srikandi</h4>
        <div class="alurmini">${[['Terbit di SIKADIN', true], ['Diunggah ke Srikandi', x.srikandi.diunggah], ['Nomor naskah dicatat', x.srikandi.nomor], ['PDF final tersimpan', x.srikandi.final]].map(([l, ok], i) => `<span class="${ok ? 'ok' : ''}"><b>${ok ? '✔' : i + 1}</b> ${l}</span>`).join('')}</div>
        <div class="acts" style="margin-top:6px">${x.srikandi.diunggah ? '' : '<button type="button" class="btn small" data-aksi="tandai">Tandai sudah diunggah ke Srikandi</button>'}
          <label class="btn small" for="stFinal">${x.srikandi.final ? 'Ganti PDF hasil Srikandi' : 'Unggah PDF hasil Srikandi'}</label><input type="file" id="stFinal" accept="application/pdf" hidden>
          ${x.srikandi.final ? `<a class="btn small" href="/api/st/${id}/final" target="_blank">Lihat PDF final</a>` : ''}${x.nomor_srikandi ? '' : '<button type="button" class="btn small" data-aksi="nomor">Catat nomor Srikandi</button>'}</div>
        <p class="muted" style="font-size:.82em;margin:4px 0">Alur: unduh DOCX → unggah ke Srikandi → setelah ditandatangani, unggah PDF hasilnya di sini. Nomor naskah dibaca otomatis dari PDF bila terdeteksi (Anda yang mengonfirmasi).</p>` : ''}
      ${!aktif && x.srikandi.final ? `<a class="btn small" href="/api/st/${id}/final" target="_blank">Lihat PDF final</a>` : ''}
      ${x.penuh ? `<h4 style="margin:12px 0 4px">Ekspor ke Srikandi</h4><div class="acts">${aktif ? L('srikandi', '⬇ DOCX Srikandi (ST + SPD)', 'primary') : '<span class="muted">ST dibatalkan — tidak dapat diekspor.</span>'}</div>
        <p class="muted" style="font-size:.82em;margin:4px 0">Unggah berkas ini ke Srikandi; kode <code>\${nomor_naskah}</code>, <code>\${ttd_pengirim1/2}</code>, dst. diisi Srikandi saat TTE.</p>` : ''}
      <h4 style="margin:12px 0 4px">Cetak / pratinjau (PDF)</h4><div class="acts">${L('st', 'Surat Tugas')}${L('spd', 'SPD')}${L('rincian', 'Rincian biaya')}${x.penuh ? L('paket', 'Paket ST+SPD+Rincian') : ''}</div>
      ${x.penuh ? `<div class="acts" style="margin-top:6px">${L('kuitansi', 'Kuitansi')}${L('hadir', 'Daftar hadir')}${L('riil', 'Pengeluaran riil')}${L('batal', 'Pernyataan pembatalan')}${L('kembali', 'Pernyataan pengembalian biaya')}${L('lengkap', 'Semua dokumen')}</div>` : ''}
      ${x.penuh && aktif ? `<div class="acts" style="margin-top:14px;border-top:1px solid var(--line);padding-top:10px">${x.bisa_batal ? '<button type="button" class="btn small danger" data-aksi="batal">Batalkan ST</button>' : ''}</div>` : ''}`);
    if ($('#stFinal')) $('#stFinal').onchange = async e => {
      const file = e.target.files[0]; if (!file) return;
      try {
        const r = await fetch(`/api/st/${id}/final?nama=${encodeURIComponent(file.name.replace(/\.[^.]+$/, ''))}`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: file });
        const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Gagal mengunggah.');
        if (j.nomor_terdeteksi && !j.nomor_tercatat && confirm(`Nomor naskah terdeteksi di PDF:\n${j.nomor_terdeteksi}\n\nCatat sebagai nomor Srikandi? (hanya dapat diisi sekali)`)) {
          await api(`/api/st/${id}/nomor-srikandi`, { method: 'PUT', body: { nomor: j.nomor_terdeteksi } });
        }
        toast(j.diganti ? 'PDF final diganti.' : 'PDF hasil Srikandi tersimpan.'); $('#dlg').close(); await reload();
      } catch (er) { toast(er.message, 1); }
    };
    $('#dlgForm').onclick = e => {
      const b = e.target.closest('[data-d],[data-aksi],[data-spj]'); if (!b) return;
      if (b.dataset.spj) { $('#dlg').close(); bukaSpj(Number(b.dataset.spj), reload).catch(er => toast(er.message, 1)); return; }
      if (b.dataset.d === 'srikandi') { download(docUrl(id, 'srikandi'), `ST_SPD_Srikandi_${x.nomor_urut}.docx`); return; }
      if (b.dataset.d && b.dataset.f === 'docx') { download(docUrl(id, b.dataset.d) + '&format=docx', `${b.dataset.d.toUpperCase()}_${x.nomor_urut}.docx`); return; }
      if (b.dataset.d) { window.open(docUrl(id, b.dataset.d), '_blank'); return; }
      $('#dlg').close();
      if (b.dataset.aksi === 'tandai') { api(`/api/st/${id}/tandai-srikandi`, { method: 'POST' }).then(() => { toast('Ditandai: menunggu tanda tangan elektronik di Srikandi.'); reload(); }).catch(er => toast(er.message, 1)); return; }
      if (b.dataset.aksi === 'nomor') dialog('Catat nomor Srikandi', `<p class="muted">Salin nomor naskah dari Srikandi setelah ST ditandatangani. Hanya dapat diisi sekali.</p><label>Nomor naskah<input name="nomor" placeholder="000.1.2.3/2611-1179/PKM.MELATI/XI/2026" required></label>`, async d => { await api(`/api/st/${id}/nomor-srikandi`, { method: 'PUT', body: d }); toast('Nomor Srikandi tersimpan.'); await reload(); });
      if (b.dataset.aksi === 'batal') dialog('Batalkan Surat Tugas?', `<p>ST <b>${esc(x.nomor)}</b> akan dibatalkan. Tanggal petugas tetap terkunci pada jadwal sampai jadwal diubah/dibatalkan. Nomor tidak dipakai ulang; ST pengganti memakai nomor baru.</p><label>Alasan pembatalan<input name="alasan" required minlength="5"></label>`, async d => { await api(`/api/st/${id}/batal`, { method: 'POST', body: d }); toast('ST dibatalkan.'); await reload(); }, 'Batalkan ST');
    };
  }
  m.onclick = e => { const t = e.target.closest('[data-terbit]'), b = e.target.closest('[data-buka]'); if (t) terbit(Number(t.dataset.terbit)).catch(x => toast(x.message, 1)); if (b) buka(Number(b.dataset.buka)); };
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
   ${S.user.role === 'kepala' ? `<div><b>Backup database</b><p class="muted">Salinan utuh basis data (.db). Simpan di tempat aman secara berkala.</p><button class="btn" id="x2">Unduh backup</button></div>
   <div><b>Pulihkan database dari backup</b><p class="muted">Mengganti <b>seluruh</b> data dengan berkas backup (.db). Database saat ini disalin dulu di server; semua pengguna harus masuk lagi. Dipakai untuk memindahkan data ke server baru.</p><input type="file" id="x3f" accept=".db"> <button class="btn danger" id="x3">Pulihkan</button></div>` : ''}</div>`;
  $('#x1').onclick = () => download('/api/export/xlsx', 'sikadin_data.xlsx');
  if ($('#x2')) $('#x2').onclick = () => download('/api/backup', 'sikadin_backup.db');
  if ($('#x3')) $('#x3').onclick = async () => {
    const f = $('#x3f').files[0]; if (!f) return toast('Pilih berkas backup (.db) dahulu.', 1);
    if (!confirm(`Ganti SELURUH data dengan isi "${f.name}"? Tindakan ini tidak dapat dibatalkan dari aplikasi (salinan data lama disimpan di server).`)) return;
    try {
      const r = await fetch('/api/pulihkan', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: f });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) return toast(j.error || 'Gagal memulihkan.', 1);
      toast('Database dipulihkan. Silakan masuk kembali.'); setTimeout(() => location.reload(), 1200);
    } catch (x) { toast(x.message, 1); }
  };
}

// ---------- mulai ----------
async function start() {
  try {
    const m = await api('/api/meta');
    S.meta = m.meta; S.user = m.user; S.bisaTulis = m.bisaTulis; S.bisaBaca = m.bisaBaca; S.akses = m.akses; S.kepalaWajib = m.kepalaWajib; S.akuntansi = m.akuntansi;
  } catch { return showLogin(); }
  $('#login').hidden = true; $('#app').hidden = false;
  $('#who').textContent = `${S.user.nama} · ${ROLE[S.user.role]}`;
  buildNav(); route();
}
start();
