"""Membuat Panduan-SIKADIN.pdf — tutorial penggunaan untuk semua peran. Jalankan: python docs/buat_panduan.py (butuh reportlab)."""
import datetime as dt
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

OUT = Path(__file__).resolve().parent / "Panduan-SIKADIN.pdf"
FD = Path("C:/Windows/Fonts")
if (FD / "segoeui.ttf").exists():
    pdfmetrics.registerFont(TTFont("UI", str(FD / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("UI-B", str(FD / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("UI-SB", str(FD / "seguisb.ttf")))
    pdfmetrics.registerFont(TTFont("UI-I", str(FD / "segoeuii.ttf")))
    pdfmetrics.registerFont(TTFont("UI-L", str(FD / "segoeuil.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("UI", normal="UI", bold="UI-B", italic="UI-I", boldItalic="UI-B")
    F, FB, FS, FL = "UI", "UI-B", "UI-SB", "UI-L"
else:
    F, FB, FS, FL = "Helvetica", "Helvetica-Bold", "Helvetica-Bold", "Helvetica"

INK, G9, G7, G6, G5, MINT, SLATE, LINE, MUTED = (HexColor(x) for x in ("#0F172A", "#14532D", "#15803D", "#16A34A", "#22C55E", "#DCFCE7", "#F1F5F9", "#E2E8F0", "#64748B"))
AMB, AMBBG, RED, REDBG, BLU, BLUBG = HexColor("#B45309"), HexColor("#FEF3C7"), HexColor("#B91C1C"), HexColor("#FEE2E2"), HexColor("#1D4ED8"), HexColor("#DBEAFE")
W, H = A4
LM = 2.0 * cm
CW = W - 2 * LM

S = {
    "n": ParagraphStyle("n", fontName=F, fontSize=10.2, leading=15, textColor=INK, alignment=TA_LEFT),
    "k": ParagraphStyle("k", fontName=F, fontSize=9, leading=12.6, textColor=INK),
    "m": ParagraphStyle("m", fontName=F, fontSize=8.8, leading=12.5, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=26, leading=30, textColor=INK, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName=FB, fontSize=14, leading=18, textColor=G9, spaceBefore=14, spaceAfter=5, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName=FS, fontSize=11, leading=15, textColor=INK, spaceBefore=8, spaceAfter=2, keepWithNext=1),
    "lead": ParagraphStyle("lead", fontName=FL, fontSize=13, leading=19, textColor=MUTED, spaceAfter=10),
    "th": ParagraphStyle("th", fontName=FB, fontSize=8.8, leading=12, textColor=white),
    "step": ParagraphStyle("step", fontName=FS, fontSize=10.6, leading=14, textColor=INK),
}
P = lambda t, s="n": Paragraph(t, S[s])  # noqa: E731


class Tag(Flowable):
    """Label kecil berwarna (BAGIAN 02)."""
    def __init__(self, teks, bg=G6, fg=white):
        super().__init__()
        self.t, self.bg, self.fg = teks, bg, fg
        self.w = pdfmetrics.stringWidth(teks, FB, 8) + 16
        self.width, self.height = self.w, 16

    def wrap(self, *_):
        return self.w, 16

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg); c.rect(0, 0, self.w, 16, stroke=0, fill=1)
        c.setFillColor(self.fg); c.setFont(FB, 8); c.drawString(8, 4.6, self.t)


class Num(Flowable):
    """Lingkaran bernomor."""
    def __init__(self, n, d=22, bg=G6):
        super().__init__()
        self.n, self.d, self.bg = str(n), d, bg

    def wrap(self, *_):
        return self.d, self.d

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg); c.circle(self.d / 2, self.d / 2, self.d / 2, stroke=0, fill=1)
        c.setFillColor(white); c.setFont(FB, 10.5); c.drawCentredString(self.d / 2, self.d / 2 - 3.7, self.n)


class Alur(Flowable):
    """Diagram alur horizontal: kotak datar + panah. items = [(judul, keterangan)]"""
    def __init__(self, items, width=CW, warna=G6):
        super().__init__()
        self.items, self.width, self.warna = items, width, warna
        self.per = 4
        self.bh = 1.55 * cm
        self.gap = 0.55 * cm
        self.rows = (len(items) + self.per - 1) // self.per
        self.height = self.rows * self.bh + (self.rows - 1) * 0.5 * cm

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        bw = (self.width - (self.per - 1) * self.gap) / self.per
        for i, (a, b) in enumerate(self.items):
            r, k = divmod(i, self.per)
            x = k * (bw + self.gap)
            y = self.height - (r + 1) * self.bh - r * 0.5 * cm
            c.setFillColor(MINT if i % 2 == 0 else SLATE); c.rect(x, y, bw, self.bh, stroke=0, fill=1)
            c.setFillColor(self.warna); c.rect(x, y, 3, self.bh, stroke=0, fill=1)
            c.setFillColor(INK); c.setFont(FB, 9.2); c.drawString(x + 9, y + self.bh - 14, f"{i + 1}. {a}")
            c.setFillColor(MUTED); c.setFont(F, 7.8)
            for j, ln in enumerate(self._wrap(b, bw - 16)):
                c.drawString(x + 9, y + self.bh - 26 - j * 9.5, ln)
            if k < self.per - 1 and i < len(self.items) - 1:
                c.setFillColor(self.warna)
                p = c.beginPath(); ax = x + bw + 0.12 * cm
                p.moveTo(ax, y + self.bh / 2 + 4); p.lineTo(ax + self.gap - 0.24 * cm, y + self.bh / 2); p.lineTo(ax, y + self.bh / 2 - 4); p.close()
                c.drawPath(p, stroke=0, fill=1)

    @staticmethod
    def _wrap(t, w):
        out, cur = [], ""
        for kata in t.split():
            if pdfmetrics.stringWidth((cur + " " + kata).strip(), F, 7.8) > w:
                out.append(cur); cur = kata
            else:
                cur = (cur + " " + kata).strip()
        return out + [cur] if cur else out


def callout(kind, judul, teks):
    bg, fg = {"tip": (MINT, G7), "warn": (AMBBG, AMB), "stop": (REDBG, RED), "info": (BLUBG, BLU)}[kind]
    ikon = {"tip": "TIPS", "warn": "PERHATIAN", "stop": "JANGAN", "info": "INFO"}[kind]
    isi = [[Paragraph(f'<font name="{FB}" color="{fg.hexval()}" size="8">{ikon}</font>&nbsp;&nbsp;<font name="{FB}">{judul}</font>', S["k"])], [Paragraph(teks, S["k"])]]
    t = Table([[None, isi]], colWidths=[0.16 * cm, CW - 0.16 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), fg), ("BACKGROUND", (1, 0), (1, 0), bg), ("LEFTPADDING", (1, 0), (1, 0), 10), ("RIGHTPADDING", (1, 0), (1, 0), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0)]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 6)])


def langkah(daftar, warna=G6):
    """daftar = [(judul, teks)] -> baris bernomor."""
    rows = []
    for i, (j, t) in enumerate(daftar, 1):
        rows.append([Num(i, bg=warna), [Paragraph(j, S["step"]), Paragraph(t, S["k"])] if t else Paragraph(j, S["step"])])
    tb = Table(rows, colWidths=[0.95 * cm, CW - 0.95 * cm])
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("LINEBELOW", (1, 0), (1, -2), 0.4, LINE)]))
    return tb


def tabel(data, lebar, kepala=True, zebra=True, fs=9):
    rows = []
    for r, baris in enumerate(data):
        rows.append([Paragraph(str(c), S["th"] if (kepala and r == 0) else S["k"]) if not isinstance(c, Flowable) else c for c in baris])
    t = Table(rows, colWidths=[x * cm for x in lebar], repeatRows=1 if kepala else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if kepala:
        st.append(("BACKGROUND", (0, 0), (-1, 0), G9))
    if zebra:
        st += [("BACKGROUND", (0, r), (-1, r), SLATE) for r in range(2 if kepala else 1, len(rows), 2)]
    t.setStyle(TableStyle(st))
    return t


def bagian(no, judul, lead=None):
    out = [CondPageBreak(10 * cm), Spacer(1, 14), Tag(f"BAGIAN {no:02d}"), Spacer(1, 6), P(judul, "h1")]
    if lead:
        out.append(P(lead, "lead"))
    return out


# ------------------------------------------------------------------ halaman dasar
def halaman(c, d):
    c.saveState()
    c.setFillColor(G6); c.rect(0, H - 0.55 * cm, W, 0.55 * cm, stroke=0, fill=1)
    c.setFont(FS, 8); c.setFillColor(MUTED); c.drawString(LM, 1.15 * cm, "SIKADIN · Panduan Penggunaan · UPT Puskesmas Melati")
    c.setFillColor(INK); c.setFont(FB, 8.5); c.drawRightString(W - LM, 1.15 * cm, str(d.page))
    c.setStrokeColor(LINE); c.setLineWidth(0.5); c.line(LM, 1.55 * cm, W - LM, 1.55 * cm)
    c.restoreState()


def sampul(c, d):
    c.saveState()
    c.setFillColor(G9); c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(G7); c.circle(W - 2 * cm, H - 3 * cm, 7 * cm, stroke=0, fill=1)
    c.setFillColor(G6); c.circle(W - 1 * cm, H - 1 * cm, 3.4 * cm, stroke=0, fill=1)
    c.setFillColor(G5); c.rect(LM, 9.8 * cm, 2.2 * cm, 0.28 * cm, stroke=0, fill=1)
    c.setFillColor(white); c.setFont(FB, 54); c.drawString(LM, 12.6 * cm, "SIKADIN")
    c.setFont(FL, 20); c.drawString(LM, 11.4 * cm, "Sistem Informasi Keuangan")
    c.drawString(LM, 10.6 * cm, "& Dinas Luar")
    c.setFont(FS, 13); c.setFillColor(MINT); c.drawString(LM, 8.6 * cm, "Panduan Penggunaan untuk semua pihak")
    c.setFont(F, 10.5); c.setFillColor(HexColor("#BBF7D0"))
    for i, t in enumerate(["Kepala Puskesmas · Bendahara · Bendahara BLUD", "Pengelola Program · Pegawai"]):
        c.drawString(LM, 7.7 * cm - i * 0.55 * cm, t)
    c.setFillColor(G7); c.rect(0, 0, W, 3.2 * cm, stroke=0, fill=1)
    c.setFillColor(white); c.setFont(FB, 11); c.drawString(LM, 1.9 * cm, "UPT Puskesmas Melati")
    c.setFont(F, 9.5); c.drawString(LM, 1.3 * cm, "Kecamatan Selat, Kuala Kapuas, Kabupaten Kapuas, Kalimantan Tengah")
    c.drawRightString(W - LM, 1.3 * cm, f"Edisi {dt.date.today():%d.%m.%Y}")
    c.restoreState()


def isi():
    s = []
    # ---------- 1 MULAI DI SINI
    s += [Spacer(1, 0), Tag("MULAI DI SINI"), Spacer(1, 6), P("Apa itu SIKADIN?", "h1"),
          P("Satu aplikasi untuk mengurus perjalanan dinas dari perencanaan sampai laporan keuangan: <b>rencana → jadwal → Surat Tugas &amp; SPD → SPJ → pembayaran → laporan</b>. Semua angka tersambung, jadi tidak perlu mengetik ulang atau menyalin dari Excel.", "lead"),
          Alur([("Pagu & RAB", "Anggaran per sumber dana: BOK, DAU, BLUD"), ("Rencana", "Kegiatan, lokasi, petugas, perkiraan biaya"), ("Jadwal", "Tanggal & petugas, bebas bentrok"), ("Surat Tugas", "ST + SPD, ekspor DOCX/PDF untuk Srikandi"),
                 ("SPJ", "Pegawai mengisi realisasi & bukti"), ("Pembayaran", "Diverifikasi lalu dibayar bendahara"), ("Rekap & Laporan", "Rekap dinas, 7 laporan PSAP 13"), ("Dashboard", "Serapan & pekerjaan yang menunggu")]),
          Spacer(1, 10), P("Siapa mengerjakan apa", "h2"),
          tabel([["Peran", "Tugas utama", "Tidak bisa"],
                 ["<b>Kepala Puskesmas</b>", "Melihat semuanya; menyetujui bila diperlukan; menandatangani; koreksi pembayaran; laporan keuangan; mengatur kode surat", "—"],
                 ["<b>Bendahara</b> (BOK/DAU)", "Mengisi pagu &amp; RAB, rencana, jadwal, ST, memverifikasi &amp; membayar SPJ", "Melihat data BLUD"],
                 ["<b>Bendahara BLUD</b>", "Semua untuk BLUD (pagu, rencana, ST, SPJ, pendapatan), laporan keuangan gabungan; BOK/DAU hanya melihat", "Mengubah BOK/DAU"],
                 ["<b>Pengelola Program</b>", "Membuat rencana, menjadwalkan, menerbitkan ST &amp; SPJ untuk BOK/DAU; mengisi belanja non-perjalanan", "Mengubah pagu/RAB; membayar; melihat BLUD"],
                 ["<b>Pembuat Surat Tugas</b>", "Peran khusus pembuat surat: menjadwalkan, menerbitkan ST/SPD (juga terbit massal), mengunggah ke Srikandi sampai PDF final dan nomor tercatat. Menunya ringkas: Dashboard, Jadwal, Surat, Rekap", "Mengubah pagu/RAB; verifikasi/bayar SPJ; melihat BLUD &amp; laporan keuangan"],
                 ["<b>Pegawai</b>", "Melihat jadwal &amp; ST/SPD sendiri, mengisi SPJ perjalanannya, melihat rekap pribadi", "Melihat data orang lain"]], [3.6, 9.6, 3.8]),
          callout("info", "Persetujuan Kepala bersifat opsional", "Secara bawaan, pembuat rencana/jadwal/surat mengotorisasi sendiri dan tindakannya tercatat di <b>Riwayat Perubahan</b>. Bila Puskesmas ingin persetujuan Kepala diwajibkan, ubah pengaturan <b>kepala_wajib</b> menjadi 1 (menu Pengaturan &amp; Kop).")]

    # ---------- 2 MASUK & MENGENAL LAYAR
    s += bagian(1, "Masuk &amp; mengenal layar", "Dua menit pertama: masuk, ganti password, dan membaca beranda.")
    s += [langkah([("Buka alamat SIKADIN", "Ketik alamat yang diberikan admin (mis. <b>sikadin.pkmmelati.com</b>) di Chrome/Edge/Safari, di laptop maupun HP."),
                   ("Masukkan Username &amp; Password", "Dari admin. Salah lima kali berturut-turut, login dikunci 5 menit."),
                   ("Ganti password", "Klik <b>Ganti password</b> di pojok kanan atas, isi password lama dan baru (min. 8 karakter). Lakukan segera pada login pertama."),
                   ("Pilih menu di sisi kiri", "Di HP, ketuk ikon tiga garis di kiri atas untuk membuka menu. Menu yang tampil menyesuaikan peran Anda.")]),
          P("Beranda (Dashboard)", "h2"),
          tabel([["Bagian", "Artinya"],
                 ["Kartu Pagu / Realisasi / Proses / Sisa / Serapan", "Realisasi = SPJ yang <b>sudah dibayar</b>. Proses = SPJ yang diajukan/terverifikasi tetapi belum dibayar. Serapan hijau &lt; 60%, oranye 60–89%, merah ≥ 90%."],
                 ["Perlu tindakan", "Tombol bernomor untuk pekerjaan yang menunggu Anda. Klik untuk langsung membuka menunya."],
                 ["Peringatan", "Baris RAB hampir habis atau melebihi pagu, pegawai melebihi batas hari dinas, serapan jauh di bawah target."],
                 ["Grafik per bulan", "Batang muda = rencana yang disetujui, batang tua = realisasi dibayar."],
                 ["Jadwal 14 hari", "Dinas luar yang akan datang beserta status Surat Tugasnya."],
                 ["Ringkasan keuangan", "Hanya Kepala &amp; Bendahara BLUD: pendapatan, belanja, surplus, kas, aset."]], [5.2, 11.8]),
          callout("tip", "Ganti tahun anggaran", "Kolom <b>Tahun</b> ada di hampir setiap layar. Mengubahnya berlaku untuk semua menu sampai Anda keluar.")]

    # ---------- 3 JALUR CEPAT PER PERAN
    s += bagian(2, "Jalur cepat per peran", "Cari peran Anda, ikuti langkahnya. Penjelasan lengkap ada di Bagian 3.")
    s += [P("Pegawai", "h2"),
          langkah([("Cek jadwal &amp; Surat Tugas", "Menu <b>Surat</b> → tab Surat Tugas &amp; SPD. Klik <b>Dokumen</b> untuk mengunduh ST/SPD milik Anda (PDF)."),
                   ("Setelah kegiatan selesai, buka <b>Realisasi &amp; SPJ</b>", "SPJ Anda sudah otomatis disiapkan. Klik <b>Buka</b>, periksa tanggal berangkat/kembali, isi <b>Realisasi</b> tiap komponen (tidak boleh lebih dari tarif) dan <b>No. bukti</b>."),
                   ("Klik <b>Simpan &amp; ajukan</b>", "Bendahara akan memeriksa. Bila dikembalikan, alasannya tampil — perbaiki lalu ajukan lagi."),
                   ("Pantau di Dashboard &amp; Rekap Perjalanan", "Lihat status SPJ dan riwayat perjalanan Anda setahun.")]),
          P("Pembuat Surat Tugas", "h2"),
          langkah([("Buka menu <b>Surat</b> → tab <b>Siap diterbitkan</b>", "Daftar jadwal yang belum punya ST. Centang semuanya (atau sebagian) → <b>Terbitkan yang dipilih</b>."),
                   ("Unduh <b>DOCX Srikandi</b>", "Klik <b>Dokumen</b> pada ST → <b>DOCX Srikandi (ST + SPD)</b>. Unggah ke Srikandi untuk ditandatangani."),
                   ("Klik <b>Tandai sudah diunggah ke Srikandi</b>", "Supaya semua orang tahu surat ini sedang menunggu tanda tangan elektronik."),
                   ("Setelah ditandatangani: <b>Unggah PDF hasil Srikandi</b>", "SIKADIN membaca nomor naskah dari PDF dan menawarkan untuk mencatatnya. Konfirmasi, dan progres berubah menjadi <b>Selesai di Srikandi</b>.")]),
          P("Pengelola Program", "h2"),
          langkah([("Buat <b>Rencana</b>", "Perencanaan (RPK/POA) → <b>+ Rencana</b>: pilih baris RAB, bulan, lokasi, jumlah petugas/hari/frekuensi. Biaya dihitung otomatis dari tarif Perbup."),
                   ("Ajukan → Setujui", "Ajukan rencana, lalu setujui (oleh Anda atau Kepala sesuai pengaturan)."),
                   ("Buat <b>Jadwal</b>", "Jadwal Dinas Luar → pilih rencana, tanggal, petugas. Sistem menolak bentrok. Atau pakai <b>Generate</b> untuk satu bulan penuh."),
                   ("Terbitkan <b>Surat Tugas</b>", "Menu Surat → <b>Siap diterbitkan</b> → centang jadwal → <b>Terbitkan yang dipilih</b>.")]),
          P("Bendahara &amp; Bendahara BLUD", "h2"),
          langkah([("Susun pagu &amp; RAB", "Menu Pagu Anggaran (BOK/DAU/BLUD): impor Excel atau tambah menu → rincian → baris."),
                   ("Periksa SPJ yang masuk", "Realisasi &amp; SPJ → buka SPJ berstatus <b>Diajukan</b> → <b>Verifikasi</b> atau <b>Kembalikan</b> (alasan wajib)."),
                   ("Catat pembayaran", "SPJ <b>Diverifikasi</b> → <b>Catat pembayaran</b> (tanggal bayar; nomor bukti otomatis)."),
                   ("Bendahara BLUD: pendapatan &amp; laporan", "Akuntansi &amp; Laporan Keuangan → isi saldo awal, catat penerimaan pendapatan, lihat 7 laporan.")]),
          P("Kepala Puskesmas", "h2"),
          langkah([("Mulai dari Dashboard", "Lihat serapan, tugas menunggu, dan peringatan."),
                   ("Setujui bila diwajibkan", "Rencana, jadwal, dan SPJ yang menunggu persetujuan muncul di <b>Perlu tindakan</b>."),
                   ("Pantau laporan", "Akuntansi &amp; Laporan Keuangan: laporan gabungan DAU + BOK + BLUD, dengan pemeriksaan integritas otomatis.")])]

    # ---------- 4 PANDUAN RINCI
    s += bagian(3, "Panduan langkah demi langkah")
    s += [P("A. Pagu &amp; RAB per sumber dana", "h2"),
          P("Menu <b>Pagu Anggaran BOK / DAU / BLUD</b>. Strukturnya berjenjang: <b>Menu kegiatan → Rincian → Baris belanja</b>. Total baris menjadi pagu."),
          langkah([("Impor dari Excel (disarankan)", "Klik tombol impor, pilih berkas RAB. Pilihan <b>ganti</b> menimpa RAB tahun itu. Angka yang tidak cocok perkalian volume × harga diberi tanda."),
                   ("Atau tambah manual", "<b>+ Menu</b> → <b>+ Rincian</b> → <b>+ Baris</b>: isi jenis belanja, uraian, volume, harga satuan. Tombol <b>Ubah</b>/<b>Hapus</b> ada di tiap baris."),
                   ("Cocokkan dengan pagu resmi", "Isi pagu tahun di bagian atas. Selisih terhadap total RAB ditampilkan.")]),
          callout("warn", "Siapa yang boleh?", "Hanya Kepala, Bendahara (BOK/DAU), dan Bendahara BLUD (BLUD). Data BLUD tidak terlihat oleh peran lain."),
          P("B. Rencana (RPK/POA)", "h2"),
          langkah([("<b>+ Rencana</b>", "Pilih sumber dana, baris RAB, bulan, lokasi tujuan, durasi (≤ 8 jam atau &gt; 8 jam), jumlah petugas, jumlah hari, dan frekuensi."),
                   ("Lihat estimasi", "Biaya per orang (uang harian, transport, penginapan) dihitung dari tarif Perbup. Sistem memperingatkan bila melebihi sisa pagu baris."),
                   ("Ajukan → Setujui", "Status: Draft → Diajukan → Disetujui (atau Ditolak dengan alasan). Hanya rencana Disetujui yang bisa dijadwalkan."),
                   ("Tab <b>Matriks POA</b>", "Ringkasan rencana per bulan untuk satu tahun.")]),
          P("C. Jadwal dinas luar", "h2"),
          langkah([("Pilih rencana yang sudah disetujui", "Menu Jadwal Dinas Luar → tambah jadwal: tanggal mulai/selesai, lokasi, dan petugas."),
                   ("Sistem memeriksa otomatis", "Seseorang tidak boleh dijadwalkan dua kali pada hari yang sama (lintas sumber dana); kegiatan + lokasi + tanggal yang sama tidak boleh ganda; tidak boleh pada hari libur atau saat cuti."),
                   ("Batas ruangan", "Paling banyak <b>50%</b> pegawai satu ruangan boleh keluar pada hari yang sama (cuti ikut dihitung). Lebih dari 10 hari dinas dalam sebulan memunculkan peringatan."),
                   ("<b>Generate</b> jadwal bulanan", "Pilih bulan → <b>pratinjau</b> pembagian petugas yang adil → simpan bila sudah sesuai."),
                   ("Tampilan", "Tab Kalender, Tabel, dan Generate. Klik jadwal untuk melihat detail, menyetujui, atau membatalkan.")]),
          callout("tip", "Bentrok? Baca saransnya", "Bila ditolak, pesan merah menyebut siapa/hari apa yang bentrok dan menyarankan pengganti yang bebas."),
          P("D. Surat Tugas &amp; SPD (menu Surat)", "h2"),
          tabel([["Tab", "Fungsi"], ["Surat Tugas &amp; SPD", "Daftar ST yang terbit beserta status realisasi belanja tiap petugas."], ["Siap diterbitkan", "Jadwal yang belum punya ST. Centang beberapa lalu <b>Terbitkan yang dipilih</b>."],
                 ["Nomor surat umum &amp; kode", "Menerbitkan nomor surat selain ST; Kepala dapat mengubah kode penomoran."]], [4.2, 12.8]),
          langkah([("Terbitkan", "Dari tab Siap diterbitkan: tombol <b>Terbitkan ST</b> (satu) atau terbit massal. Periksa tanggal surat, penandatangan, dasar, dan maksud."),
                   ("Unduh dokumen", "Klik <b>Dokumen</b> pada ST. Tiap dokumen punya tombol <b>PDF</b> dan <b>DOCX</b>: Surat Tugas, SPD, Rincian biaya, Kuitansi, Daftar hadir, Pengeluaran riil, Pernyataan pembatalan/pengembalian, atau <b>Semua dokumen</b>."),
                   ("Unggah ke Srikandi", "Pakai <b>DOCX Srikandi (ST + SPD)</b>. Kode tanda tangan elektronik di dalamnya jangan diubah — Srikandi yang mengisinya."),
                   ("Tandai &amp; unggah hasil Srikandi", "Klik <b>Tandai sudah diunggah ke Srikandi</b>. Setelah ditandatangani, klik <b>Unggah PDF hasil Srikandi</b>: nomor naskah terbaca otomatis dari PDF dan Anda cukup mengonfirmasi (atau pakai <b>Catat nomor Srikandi</b> secara manual — hanya bisa diisi sekali)."),
                   ("Pantau progres", "Tiap ST menampilkan <b>Srikandi 0/3 … 3/3</b> (diunggah · nomor dicatat · PDF final) dan <b>Selesai di Srikandi</b> bila lengkap. PDF final dapat dilihat kembali kapan saja; boleh diganti, dan penggantian tercatat di riwayat."),
                   ("Salah? Batalkan &amp; terbitkan ulang", "<b>Batalkan ST</b> (alasan wajib), lalu terbitkan lagi dengan nomor baru. ST tidak bisa diedit setelah terbit.")]),
          callout("warn", "Batas satu halaman", "ST dan tanda tangannya harus muat di <b>satu halaman</b>; ukuran huruf dipadatkan otomatis. Lebih dari ± 9 petugas ditolak — pecah menjadi dua ST."),
          callout("stop", "Pembatalan ditolak bila SPJ sudah berjalan", "Jika ada SPJ yang diajukan atau dibayar, kembalikan SPJ atau koreksi pembayarannya (Kepala) terlebih dahulu.")]

    s += [P("E. Realisasi &amp; SPJ (tanpa panjar)", "h2"),
          P("Begitu ST terbit, sistem otomatis menyiapkan <b>satu SPJ per petugas</b> (status Draft). Pembayaran dilakukan <b>setelah</b> SPJ diverifikasi."),
          Alur([("Draft", "Pegawai mengisi realisasi & bukti"), ("Diajukan", "Menunggu bendahara"), ("Diverifikasi", "Bendahara memeriksa"), ("Dibayar", "Terhitung sebagai realisasi")], warna=G7),
          Spacer(1, 6),
          langkah([("Pegawai mengisi", "Menu Realisasi &amp; SPJ → <b>Buka</b>. Ubah tanggal bila berbeda dari rencana; isi angka tiap komponen (≤ tarif SPD) dan nomor bukti. <b>Simpan &amp; ajukan</b>. Pengajuan baru bisa dilakukan setelah kegiatan selesai."),
                   ("Unggah <b>foto bukti</b>", "Di dalam SPJ: <b>Ambil foto</b> (kamera HP) atau <b>Pilih foto / PDF</b>. Foto dikecilkan otomatis; maks. 8 berkas, 4 MB per berkas. Foto saja sudah cukup sebagai bukti untuk mengajukan. Bukti terkunci setelah diajukan dan ikut tercetak sebagai <b>Lampiran</b> di PDF SPJ."),
                   ("Bendahara memeriksa", "<b>Verifikasi</b> bila benar, atau <b>Kembalikan</b> dengan alasan. SPJ yang dikembalikan bisa diedit lagi oleh pegawai."),
                   ("Bendahara membayar", "<b>Catat pembayaran</b>: isi tanggal bayar. Nomor bukti dibuat otomatis, mis. <b>BP/BOK/2027/0001</b>. Tanggal bayar tidak boleh sebelum kegiatan dimulai."),
                   ("Belanja non-perjalanan", "Tombol <b>+ Belanja non-perjalanan</b>: pilih baris RAB, isi uraian, tanggal, jumlah, penerima, bukti. Alurnya sama."),
                   ("Salah catat?", "Hanya <b>Kepala</b> yang bisa <b>Koreksi pembayaran</b> (alasan wajib; tercatat di riwayat dan jurnal akuntansi dibalik).")]),
          tabel([["Aturan", "Penjelasan"], ["Batas pagu", "Total yang dibayar pada satu baris RAB tidak boleh melebihi pagu baris tersebut."], ["Terkunci", "SPJ yang sudah dibayar tidak dapat diubah (juga di basis data)."],
                 ["Tab Realisasi anggaran", "Pagu, proses, realisasi, sisa, dan persen serapan per menu/rincian/baris; ekspor rekap PDF/DOCX/XLSX."]], [4.2, 12.8]),
          P("F. Rekap Perjalanan Dinas", "h2"),
          P("Menu <b>Rekap Perjalanan Dinas</b>: perjalanan per <b>nama, tempat, waktu, tujuan, dan biaya</b>, setahun atau per bulan."),
          langkah([("Atur filter", "Pilih tahun, bulan (atau Setahun), sumber dana, pegawai, tempat, atau ketik kata pada tujuan."),
                   ("Pilih tab", "<b>Rincian</b> (satu baris per orang per perjalanan), <b>Per bulan</b> (12 bulan + jumlah), <b>Per nama</b> (matriks 12 bulan; arahkan kursor untuk melihat biaya), <b>Per tempat</b>."),
                   ("Unduh", "Tombol <b>PDF</b>, <b>DOCX</b>, atau <b>XLSX</b> (Excel, empat lembar). Biaya SPD = tarif Perbup; Realisasi = SPJ yang sudah dibayar.")]),
          P("G. Akuntansi &amp; Laporan Keuangan (Kepala &amp; Bendahara BLUD)", "h2"),
          P("Laporan disusun menurut <b>PSAP 13</b> dan menggabungkan <b>seluruh sumber dana</b> (DAU, BOK, BLUD) menjadi satu kesatuan. Menu ini hanya terlihat oleh Kepala dan Bendahara BLUD."),
          langkah([("Isi <b>Saldo awal</b> (sekali di awal tahun)", "Tab Saldo awal: isi saldo kas, piutang, peralatan, dst. Sistem memeriksa <b>Aset = Kewajiban + Ekuitas</b> sebelum menyimpan."),
                   ("Isi <b>Anggaran pendapatan</b>", "Untuk kolom Anggaran di LRA. Anggaran belanja diambil otomatis dari RAB."),
                   ("Catat <b>pendapatan</b>", "Tab Jurnal → <b>+ Penerimaan pendapatan</b>: akun, sumber dana, tanggal, jumlah. Otomatis Debit Kas / Kredit Pendapatan."),
                   ("Belanja = otomatis", "Setiap SPJ yang dibayar langsung menjadi jurnal kas; koreksi pembayaran membuat jurnal balik."),
                   ("Hal lain lewat <b>Jurnal manual</b>", "Mis. piutang klaim (basis Akrual), penyusutan, pembelian aset. Debit total harus sama dengan kredit total."),
                   ("Baca <b>Laporan</b>", "Pilih bulan (s.d.), lalu tab LRA, L-SAL, Neraca, LO, LAK, LPE, CaLK. Kotak hijau “Pemeriksaan integritas” memastikan semuanya cocok."),
                   ("Unduh", "PDF/DOCX/XLSX untuk satu laporan atau ketujuhnya.")]),
          tabel([["Laporan", "Menjawab pertanyaan"], ["LRA", "Anggaran vs realisasi pendapatan &amp; belanja (basis kas)"], ["L-SAL", "Berapa sisa anggaran lebih awal sampai akhir"], ["Neraca", "Aset, kewajiban, ekuitas pada tanggal laporan"],
                 ["LO", "Surplus/defisit kegiatan operasional (basis akrual)"], ["LAK", "Dari mana kas masuk dan ke mana keluar"], ["LPE", "Perubahan ekuitas selama periode"], ["CaLK", "Penjelasan; teksnya bisa disunting di tab Teks CaLK"]], [3.0, 14.0]),
          callout("warn", "Pemetaan akun", "Jenis belanja pada RAB dipetakan ke akun lewat kata kunci (perjalanan, insentif, obat, peralatan, dst.). Mintalah akuntan memeriksa Bagan akun sebelum laporan dipakai resmi.")]

    # ---------- 5 ATURAN & FAQ
    s += bagian(4, "Aturan penting &amp; tanya jawab")
    s += [P("Contekan aturan", "h2"),
          tabel([["Hal", "Aturan"],
                 ["Bentrok jadwal", "Satu orang satu tugas per hari; kegiatan + lokasi + tanggal tidak boleh ganda; tidak pada hari libur/cuti."],
                 ["Ruangan", "Maks. 50% pegawai satu ruangan keluar pada hari yang sama."],
                 ["Hari dinas", "Peringatan bila &gt; 10 hari dinas luar dalam sebulan."],
                 ["Tarif", "Dari Perbup Kapuas No. 8/2026 (tabel Tarif). Tingkat C untuk Eselon III/Gol. IV, selain itu D."],
                 ["Bukti SPJ", "Foto/PDF maks. 8 berkas × 4 MB; hanya dapat ditambah/dihapus saat SPJ Draft atau Dikembalikan."],
                 ["ST &amp; SPD", "Terkunci setelah terbit; perubahan hanya dengan batal + terbit ulang; harus muat satu halaman."],
                 ["SPJ", "Realisasi ≤ tarif SPD; bukti diisi; dibayar setelah diverifikasi; tidak ada panjar."],
                 ["Pagu", "Total dibayar per baris RAB ≤ pagu baris."],
                 ["BLUD", "Hanya Kepala &amp; Bendahara BLUD yang melihat/mengubah data BLUD."],
                 ["Riwayat", "Setiap perubahan penting tercatat (siapa, kapan, sebelum/sesudah) di menu Riwayat Perubahan."]], [3.6, 13.4]),
          P("Pertanyaan yang sering muncul", "h2"),
          tabel([["Pertanyaan", "Jawaban"],
                 ["Saya lupa password.", "Minta admin mengatur ulang: <b>python -m app.admin atur-sandi USERNAME</b> di server."],
                 ["Jadwal ditolak “bentrok”.", "Baca pesan merahnya: ada petugas yang sudah bertugas, libur/cuti, atau ruangannya melebihi 50%. Ganti petugas/tanggal sesuai saran."],
                 ["Tombol Terbitkan ST tidak muncul.", "Jadwal harus <b>Disetujui</b> (atau Diusulkan bila Kepala opsional) dan Anda berhak atas sumber dananya."],
                 ["ST dibatalkan tetapi SPJ masih ada.", "SPJ Draft ikut terhapus. Bila SPJ sudah diajukan/dibayar, pembatalan ditolak: kembalikan/koreksi SPJ dulu."],
                 ["Realisasi tidak bisa melebihi tarif.", "Memang aturan sistem (Perbup). Isi sesuai bukti, maksimal sebesar tarif."],
                 ["SPJ tidak bisa diajukan.", "Kegiatan belum selesai, belum ada nomor bukti, atau total nol."],
                 ["Neraca tidak seimbang.", "Periksa Saldo awal (Aset harus = Kewajiban + Ekuitas) dan jurnal manual."],
                 ["Angka realisasi di Dashboard nol.", "Realisasi hanya menghitung SPJ <b>Dibayar</b>. SPJ yang baru diajukan masuk kolom Proses."],
                 ["DOCX tampil berbeda dari PDF.", "DOCX Srikandi memakai templat resmi; PDF memakai format SIKADIN. Keduanya sah — pakai DOCX untuk diunggah ke Srikandi."],
                 ["Sesi tiba-tiba habis.", "Sesi berakhir bila server dimulai ulang atau setelah 12 jam. Masuk lagi."]], [5.4, 11.6])]

    # ---------- 6 ADMIN
    s += bagian(5, "Untuk admin &amp; pengelola data", "Pengaturan awal dan perawatan rutin.")
    s += [P("Data induk (menu Master Data)", "h2"),
          tabel([["Menu", "Isi &amp; catatan"], ["Pegawai", "Nama, NIP, golongan, ruangan. Impor/ekspor Excel. Golongan menentukan tingkat tarif; pegawai tanpa golongan dianggap D."], ["Tarif Perbup", "Tarif per tahun berlaku; perubahan tarif = tambah baris tahun baru."],
                 ["Lokasi Tujuan", "Daftar tempat tujuan dan tarif yang terkait."], ["Pejabat", "Penandatangan, Bendahara, PPTK — dipakai pada ST/SPD/laporan."], ["Hari Libur &amp; Cuti", "Dipakai sistem untuk menolak jadwal bentrok."],
                 ["Pengaturan &amp; Kop", "Kop surat, DPA, kota surat, batas hari dinas, <b>kepala_wajib</b>, <b>spj_setelah_selesai</b>."], ["Pengguna", "Hanya Kepala: akun, peran, aktif/nonaktif."]], [3.6, 13.4]),
          P("Keamanan &amp; pemeliharaan", "h2"),
          langkah([("Ganti semua password demo", "Di server: <b>python -m app.admin sandi-acak</b> — sandi acak dicetak sekali; catat. Mode produksi menolak berjalan bila sandi demo masih ada."),
                   ("Backup harian", "Jadwalkan <b>python -m app.admin backup</b> (cron). Simpan salinan di luar server dan uji pulihkan sesekali. Admin juga bisa mengunduh dari menu Backup &amp; Ekspor (Kepala)."),
                   ("Pantau", "Alamat <b>/api/health</b> harus menjawab {\"ok\":true}."),
                   ("Penayangan", "Lihat berkas <b>deploy/PANDUAN-PENAYANGAN.md</b> (Docker + Caddy atau systemd).")]),
          callout("tip", "Sebelum dipakai resmi", "Konfirmasi kode unit penomoran surat, isi saldo awal &amp; anggaran pendapatan, cocokkan bagan akun dengan akuntan, dan uji unggah satu DOCX ke Srikandi."),
          Spacer(1, 14),
          Table([[P("<b>Butuh bantuan?</b><br/>Hubungi admin SIKADIN Puskesmas Melati. Sertakan nama menu, tangkapan layar, dan pesan galat yang muncul.", "k")]], colWidths=[CW],
                style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), MINT), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))]
    return s


def main():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=LM, rightMargin=LM, topMargin=1.5 * cm, bottomMargin=2.0 * cm, title="Panduan Penggunaan SIKADIN", author="UPT Puskesmas Melati",
                          subject="Tutorial SIKADIN — Sistem Informasi Keuangan & Dinas Luar")
    kover = Frame(LM, 2 * cm, CW, H - 4 * cm, id="k")
    isi_f = Frame(LM, 2.0 * cm, CW, H - 3.9 * cm, id="i", leftPadding=0, rightPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[kover], onPage=sampul, autoNextPageTemplate="isi"), PageTemplate(id="isi", frames=[isi_f], onPage=halaman)])
    from reportlab.platypus import NextPageTemplate
    story = [NextPageTemplate("isi"), PageBreak()] + isi()
    doc.build(story)
    print("OK:", OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
