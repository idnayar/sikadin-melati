// Parser berkas "RAB BOK Puskesmas" (format Kemenkes: Menu → Rincian Menu → Komponen → baris biaya).
const XLSX = require('xlsx');

const txt = v => String(v ?? '').replace(/\s+/g, ' ').trim();
const num = v => {
  if (typeof v === 'number') return v;
  const s = String(v ?? '').trim().replace(/\./g, '').replace(',', '.');
  return s !== '' && !isNaN(Number(s)) ? Number(s) : null;
};

function parseRAB(buffer) {
  const wb = XLSX.read(buffer, { type: 'buffer' });
  const ws = wb.Sheets[wb.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '', raw: true });
  const judul = txt(rows[0] && rows[0][0]);
  const tahun = Number((judul.match(/TA\s*(\d{4})/i) || [])[1]) || null;
  let pagu = null;
  const menus = []; const peringatan = [];
  let menu = null, rinc = null, komp = null;

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (/jumlah total kebutuhan/i.test(txt(r[0]))) pagu = num(r[17]);
    if (/^total pagu/i.test(txt(r[1]))) break;
    if (i < 7) continue;                       // header tabel
    const c = k => r[k];
    const kosong = r.every(v => v === '');
    if (kosong) continue;

    // Baris subtotal menu (hanya angka di kolom total) → abaikan, dihitung ulang
    if (r.slice(0, 16).every(v => v === '') && num(r[17]) !== null) continue;

    if (txt(c(0)) !== '' && txt(c(1)) !== '') {           // menu baru
      menu = { no: txt(c(0)), nama: txt(c(1)), rincian: [] };
      menus.push(menu); rinc = null; komp = null;
    }
    if (!menu) continue;
    if (txt(c(2)) !== '' || (txt(c(3)) !== '' && !rinc)) { // rincian menu baru
      rinc = { no: txt(c(2)), nama: txt(c(3)), baris: [] };
      menu.rincian.push(rinc); komp = null;
    }
    if (!rinc) continue;
    if (txt(c(4)) !== '') komp = txt(c(4));

    const jenis = txt(c(6));
    const sub = num(c(16));
    const pembulatan = /pembulatan/i.test(jenis) || (/pembulatan/i.test(txt(c(4))) && jenis === '');
    if (jenis === '' && !pembulatan) continue;            // judul komponen tanpa biaya

    const v1 = num(c(9)), v2 = num(c(11)), v3 = num(c(13)), uc = num(c(15));
    const b = {
      komponen: pembulatan ? null : (txt(c(4)) || komp),
      jenis_belanja: pembulatan ? 'Pembulatan' : jenis,
      uraian: txt(c(7)) || null, satuan: txt(c(8)) || null,
      vol1: v1 ?? 1, sat1: txt(c(10)) || null,
      vol2: v2 ?? 1, sat2: txt(c(12)) || null,
      vol3: v3 ?? 1, sat3: txt(c(14)) || null,
      unit_cost: pembulatan ? (sub ?? 0) : (uc ?? 0),
      jumlah: sub ?? 0,
    };
    if (pembulatan) { b.vol1 = b.vol2 = b.vol3 = 1; b.sat1 = b.sat2 = b.sat3 = null; }
    const hitung = b.vol1 * b.vol2 * b.vol3 * b.unit_cost;
    if (Math.round(hitung) !== Math.round(b.jumlah))
      peringatan.push(`Baris ${i + 1} (${b.komponen || rinc.nama}): jumlah di file ${b.jumlah.toLocaleString('id-ID')} ≠ volume×tarif ${hitung.toLocaleString('id-ID')}; nilai file dipakai.`);
    rinc.baris.push(b);
  }
  const total = menus.reduce((s, m) => s + m.rincian.reduce((s2, x) => s2 + x.baris.reduce((s3, b) => s3 + b.jumlah, 0), 0), 0);
  if (pagu !== null && pagu !== total) peringatan.push(`Total baris ${total.toLocaleString('id-ID')} ≠ total di file ${pagu.toLocaleString('id-ID')}.`);
  return { judul, tahun, pagu, menus, total, peringatan };
}
module.exports = { parseRAB };
