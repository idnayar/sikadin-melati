// Penghitung estimasi biaya perjalanan dinas dari tarif Perbup (data master, bukan hard-code).
const { db } = require('./db');

const num = (v, d = 0) => (v === undefined || v === null || v === '' ? d : Number(v));

function cari(tahun, kategori, tujuan, tingkat = '') {
  // Tarif terbaru yang sudah berlaku pada tahun tsb (Perbup berlaku sampai diganti Perbup baru).
  return db.prepare('SELECT * FROM tarif WHERE tahun_berlaku<=? AND kategori=? AND tujuan=? AND tingkat=? ORDER BY tahun_berlaku DESC LIMIT 1')
    .get(tahun, kategori, tujuan, tingkat);
}
function pengaturan(k, d) {
  const r = db.prepare('SELECT nilai FROM pengaturan WHERE kunci=?').get(k);
  return r ? Number(r.nilai) : d;
}

/**
 * in: { pegawai_id, lokasi_id, tahun, durasi: 'gt8'|'le8', hari, roda: 2|4, menginap: 'hotel'|'tidak_hotel'|'tidak',
 *       pp: bool, inap_riil, transport_manual, diklat: bool }
 * out: { tingkat, baris:[{kode,uraian,volume,satuan,tarif,jumlah}], total, peringatan:[] }
 */
function hitung(inp) {
  // Saat perencanaan petugas belum ditentukan: pakai `tingkat` (C/D). Saat penugasan: pegawai_id.
  const peg = inp.pegawai_id ? db.prepare('SELECT * FROM pegawai WHERE id=?').get(inp.pegawai_id)
    : { nama: `Petugas Tingkat ${inp.tingkat || 'D'}`, tingkat: inp.tingkat || 'D' };
  const lok = db.prepare('SELECT * FROM lokasi WHERE id=?').get(inp.lokasi_id);
  if (!peg) throw new Error('Pegawai tidak ditemukan');
  if (!lok) throw new Error('Lokasi tidak ditemukan');
  const tahun = num(inp.tahun, pengaturan('tahun_anggaran', new Date().getFullYear()));
  const hari = Math.max(1, num(inp.hari, 1));
  const malam = Math.max(0, hari - 1);
  const pp = inp.pp !== false;
  const roda = num(inp.roda, 2) === 4 ? 4 : 2;
  const tingkat = peg.tingkat;
  const key = lok.kunci_tarif || lok.nama;
  const baris = [], peringatan = [];
  const add = (kode, uraian, volume, satuan, tarif) => baris.push({ kode, uraian, volume, satuan, tarif, jumlah: volume * tarif });
  const dalamKota = lok.jenis === 'DK_WILAYAH' || lok.jenis === 'DK_ANTAR';
  const batas = pengaturan('batas_jam_dalam_kota', 8);

  // ---- Uang harian ----
  if (dalamKota) {
    if (inp.durasi === 'le8') {
      peringatan.push(`Durasi ≤ ${batas} jam: tidak mendapat uang harian, hanya uang transport lokal (Pasal 6 ayat 3).`);
    } else {
      const t = cari(tahun, inp.diklat ? 'UH_DIKLAT_DK' : 'UH_DK', 'Kab. Kapuas');
      if (t) add('UH', inp.diklat ? 'Uang harian diklat dalam kota > 8 jam' : 'Uang harian dalam kota > 8 jam', hari, 'OH', t.nilai);
      else peringatan.push('Tarif uang harian dalam kota belum ada di master.');
    }
  } else if (lok.jenis === 'LK_KALTENG') {
    const t = cari(tahun, 'UH_LK_KALTENG', 'Kalimantan Tengah');
    if (t) add('UH', 'Uang harian luar kota dalam Provinsi Kalteng', hari, 'OH', t.nilai);
    else peringatan.push('Tarif uang harian luar kota Kalteng belum ada di master.');
  } else {
    const t = cari(tahun, 'UH_LUAR_PROV', lok.provinsi || key);
    if (t) add('UH', `Uang harian luar provinsi (${lok.provinsi || key})`, hari, 'OH', t.nilai);
    else peringatan.push(`Tarif uang harian provinsi "${lok.provinsi || key}" belum ada — impor tabel Lampiran I.`);
  }

  // ---- Transport ----
  if (lok.jenis === 'DK_ANTAR') {
    const t = cari(tahun, 'TR_DK', key);
    const v = t && (roda === 4 ? t.nilai2 : t.nilai);
    if (v) add('TR', `Transport ke ${lok.nama} (Roda ${roda})`, pp ? 2 : 1, 'kali', v);
    else peringatan.push(`Tarif transport Roda ${roda} ke ${lok.nama} tidak tersedia.`);
  } else if (lok.jenis === 'LK_KALTENG') {
    const t = cari(tahun, 'TR_DARAT_LK', key);
    if (t) add('TR', `Transport darat ke ${lok.nama}${pp ? ' (pulang-pergi)' : ''}`, pp ? 2 : 1, 'kali', t.nilai);
    else peringatan.push(`Tarif transport darat ke ${lok.nama} belum ada.`);
  } else if (lok.jenis === 'LK_LUAR_PROV') {
    peringatan.push('Tiket pesawat/taksi luar provinsi: isi sesuai bukti riil (Lampiran I VII & VIII).');
  }
  if (num(inp.transport_manual) > 0) add('TR', 'Transport lokal/riil sesuai bukti', 1, 'paket', num(inp.transport_manual));

  // ---- Penginapan ----
  if (malam > 0 && inp.menginap && inp.menginap !== 'tidak') {
    let tarifInap = null;
    if (lok.jenis === 'DK_ANTAR') tarifInap = cari(tahun, 'INAP_DK', key);
    else if (lok.jenis === 'DK_WILAYAH') tarifInap = cari(tahun, 'INAP_DK', 'Kec. Selat');
    else if (lok.jenis === 'LK_KALTENG') tarifInap = cari(tahun, 'INAP_KALTENG', key === 'Palangka Raya' ? 'Palangka Raya' : 'Kabupaten lain', tingkat);
    else tarifInap = cari(tahun, 'INAP_LUAR_PROV', lok.provinsi || key, tingkat);
    if (!tarifInap) peringatan.push('Tarif penginapan tujuan ini belum ada di master.');
    else if (inp.menginap === 'hotel') {
      const riil = inp.inap_riil !== undefined && inp.inap_riil !== '' ? num(inp.inap_riil) : tarifInap.nilai;
      add('INAP', 'Penginapan (biaya riil, maks. tarif)', malam, 'malam', Math.min(riil, tarifInap.nilai));
      if (riil > tarifInap.nilai) peringatan.push('Biaya hotel riil melebihi tarif — dibatasi sesuai tarif.');
    } else {
      const p = pengaturan('lumpsum_inap_persen', 30);
      add('INAP', `Penginapan lumpsum ${p}% (tidak menginap di hotel)`, malam, 'malam', Math.floor(tarifInap.nilai * p / 100));
    }
  }

  const total = baris.reduce((s, b) => s + b.jumlah, 0);
  return { pegawai: peg.nama, tingkat, lokasi: lok.nama, tahun, baris, total, peringatan };
}

module.exports = { hitung };
