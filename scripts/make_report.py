#!/usr/bin/env python3
"""make_report.py - Membangun report/laporan.pdf dari data hasil benchmark.

Semua angka (tabel, speedup, efficiency, LOC, estimasi Amdahl) dihitung dari
results/summary.csv, results/env.json dan kode di src/. Bagian narasi yang
bergantung pada data (anomali, perbandingan) dibuat otomatis mengikuti data,
sehingga laporan selalu konsisten dengan hasil pengukuran pada mesin yang
menjalankan `make bench`.

Pemakaian: python3 scripts/make_report.py --nama "Nama" --nim "123456"
"""
import argparse, json, math, os, re
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Image, PageBreak, Preformatted, KeepTogether)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
VARS = ["ijk", "ikj", "transpose", "tiled"]

ap = argparse.ArgumentParser()
ap.add_argument("--nama", default="")
ap.add_argument("--nim", default="")
args = ap.parse_args()
NAMA = args.nama.strip() or "[Nama]"
NIM = args.nim.strip() or "[NIM]"

# ------------------------------------------------------------------ data
s = pd.read_csv(os.path.join(RES, "summary.csv"))
env = json.load(open(os.path.join(RES, "env.json")))
sizes = sorted(s.N.unique()); n0 = int(sizes[0])
threads = sorted(t for t in s.threads.unique() if t >= 1)
tmax = max(threads)
cores, logical = int(env["physical_cores"]), int(env["logical_cpus"])
all_ok = bool((s.verified == 1).all())

def row(ap_, v, n, t):
    d = s[(s.approach == ap_) & (s.variant == v) & (s.N == n) & (s.threads == t)]
    return d.iloc[0] if len(d) else None

ser = {(v, n): row("serial", v, n, 1) for v in VARS for n in sizes}
best_v = min(VARS, key=lambda v: ser[(v, n0)]["mean"])          # varian serial tercepat
# ------------------------------------------------------------------ LOC
def loc(path, region=False):
    txt = open(os.path.join(ROOT, path)).read()
    if region:
        m = re.search(r"PAR-BEGIN.*?\n(.*?)/\* PAR-END", txt, re.S)
        txt = m.group(1) if m else ""
    n, incomment = 0, False
    for ln in txt.splitlines():
        t = ln.strip()
        if incomment:
            if "*/" in t: incomment = False
            continue
        if not t or t.startswith("//"): continue
        if t.startswith("/*"):
            if "*/" not in t: incomment = True
            continue
        n += 1
    return n
LOC = {k: (loc(f"src/{k}.c"), loc(f"src/{k}.c", True)) for k in ("serial", "pthreads", "openmp")}
LOC_common = loc("src/common.h")
n_pragma = open(os.path.join(ROOT, "src/openmp.c")).read().count("#pragma omp")
n_pth = len(re.findall(r"pthread_\w+", open(os.path.join(ROOT, "src/pthreads.c")).read()))

# ------------------------------------------------------------------ styles
ss = getSampleStyleSheet()
body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=14, spaceBefore=6, spaceAfter=8)
h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, spaceBefore=8, spaceAfter=4)
title = ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=17, leading=22, spaceAfter=4)
sub = ParagraphStyle("s", parent=body, alignment=TA_CENTER, spaceAfter=2)
cap = ParagraphStyle("c", parent=body, fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#444"))
code = ParagraphStyle("code", fontName="Courier", fontSize=8, leading=9.6, backColor=colors.HexColor("#f4f4f4"),
                      borderPadding=4, spaceBefore=4, spaceAfter=8, leftIndent=4)
bul = ParagraphStyle("bul", parent=body, leftIndent=14, bulletIndent=2, spaceAfter=3)
cell = ParagraphStyle("cell", parent=body, fontSize=8.5, leading=10.5, alignment=TA_CENTER, spaceAfter=0)

def P(t, st=body): return Paragraph(t, st)
def B(items): return [Paragraph(t, bul, bulletText="\u2022") for t in items]
def esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def C(t): return Preformatted(t.strip("\n"), code)
def fig(name, w=15.5, ratio=7 / 9, caption=""):
    out = [Image(os.path.join(RES, name), width=w * cm, height=w * ratio * cm)]
    if caption: out.append(P(caption, cap))
    return KeepTogether(out)

def table(data, colw=None, hdr=1, zebra=True):
    t = Table([[Paragraph(str(c), cell) for c in r] for r in data], colWidths=colw, repeatRows=hdr)
    st = [("GRID", (0, 0), (-1, -1), .4, colors.grey), ("BACKGROUND", (0, 0), (-1, hdr - 1), colors.HexColor("#dde6f3")),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    t.setStyle(TableStyle(st)); return t

# ------------------------------------------------------------------ derived numbers
def ms(r): return f"{r['mean']:.3f} \u00b1 {r['std']:.3f}"
cache_ratio = {n: ser[("ijk", n)]["mean"] / ser[("ikj", n)]["mean"] for n in sizes}
tr_ratio = {n: ser[("ijk", n)]["mean"] / ser[("transpose", n)]["mean"] for n in sizes}
tile_ratio = {n: ser[("ikj", n)]["mean"] / ser[("tiled", n)]["mean"] for n in sizes}

# Pthreads vs OpenMP (rasio waktu pthreads/openmp, geometric mean semua konfigurasi paralel)
rat = []
for v in VARS:
    for n in sizes:
        for t in threads:
            a, b = row("pthreads", v, n, t), row("openmp", v, n, t)
            if a is not None and b is not None: rat.append(a["mean"] / b["mean"])
gm = math.exp(sum(math.log(x) for x in rat) / len(rat))
max_dev = max(abs(x - 1) for x in rat)

# Karp-Flatt: e = (1/S - 1/p)/(1 - 1/p), hanya p <= core fisik
def karp(ap_, v, n, p):
    r = row(ap_, v, n, p)
    if r is None or p < 2: return None
    S = r["speedup"]; return (1 / S - 1 / p) / (1 - 1 / p)
valid_p = [p for p in threads if 2 <= p <= cores]
amdahl_ok = len(valid_p) > 0
p_est = max(valid_p) if amdahl_ok else None

# ------------------------------------------------------------------ anomali (otomatis dari data)
anom = []
if tmax > logical:
    anom.append(f"<b>Oversubscription.</b> Pengujian sampai {tmax} thread dijalankan pada mesin dengan {logical} CPU logis "
                f"({cores} core fisik). Thread yang melebihi jumlah CPU harus bergantian memakai core (context switch), sehingga "
                f"speedup tidak dapat melampaui sekitar {min(logical, tmax)}x dan efficiency turun hampir proporsional dengan 1/T.")
elif tmax > cores:
    anom.append(f"<b>Hyper-threading.</b> Konfigurasi {tmax} thread melebihi {cores} core fisik; thread tambahan berbagi unit eksekusi "
                f"dan cache core yang sama sehingga tambahan kinerjanya jauh di bawah linear.")
t1 = [(ap_, v, n) for ap_ in ("pthreads", "openmp") for v in VARS for n in sizes
      if row(ap_, v, n, 1) is not None and abs(row(ap_, v, n, 1)["speedup"] - 1) > 0.10]
if t1:
    ex = t1[0]; r = row(*ex[:2], ex[2], 1) if False else row(ex[0], ex[1], ex[2], 1)
    anom.append(f"<b>Versi paralel dengan 1 thread tidak identik dengan serial.</b> Pada {len(t1)} konfigurasi, selisih waktu T=1 terhadap serial "
                f"melebihi 10% (mis. {ex[0]}/{ex[1]}, N={ex[2]}: speedup {r['speedup']:.2f}). Secara teori keduanya mengeksekusi kernel yang sama, "
                f"jadi selisih ini berasal dari overhead pembuatan thread/runtime di satu sisi dan derau pengukuran / variasi frekuensi CPU "
                f"serta efek alignment dan penempatan kode oleh compiler di sisi lain. Hal ini menjadi pengingat bahwa selisih di bawah ~10% "
                f"pada pengukuran ini tidak boleh ditafsirkan sebagai keunggulan nyata.")
noisy = s[(s['mean'] > 0) & (s['std'] / s['mean'] > 0.10)]
if len(noisy):
    w = noisy.sort_values("std", ascending=False).iloc[0]
    anom.append(f"<b>Variansi antar-ulangan tinggi.</b> {len(noisy)} konfigurasi memiliki simpangan baku &gt; 10% dari rata-ratanya "
                f"(terbesar: {w['approach']}/{w['variant']}, N={int(w['N'])}, T={int(w['threads'])}, {100*w['std']/w['mean']:.0f}%). "
                f"Penyebab lazim: proses lain di sistem, penjadwalan thread oleh OS, throttling frekuensi, atau mesin virtual yang berbagi host.")
sup = s[(s.approach != "serial") & (s.efficiency > 1.05) & (s.threads > 1)]
if len(sup):
    anom.append(f"<b>Efficiency &gt; 1.</b> {len(sup)} konfigurasi menunjukkan efficiency di atas 1,0 (speedup 'superlinear'). Penyebab yang "
                f"masuk akal adalah efek cache (working set per thread mengecil sehingga muat di cache) atau derau pada waktu serial acuan; "
                f"perlu dicek terhadap simpangan baku sebelum disimpulkan.")
if max_dev > 0.10:
    anom.append(f"<b>Perbedaan Pthreads vs OpenMP.</b> Pada beberapa konfigurasi selisih waktu keduanya mencapai {100*max_dev:.0f}%, padahal "
                f"strategi pembagian kerja serupa (blok baris kontigu). Kemungkinan penyebab: cara compiler meng-inline/mem-vektorisasi kernel "
                f"(OpenMP memuat kernel langsung di dalam fungsi yang di-outline, Pthreads melalui <font face='Courier'>mm_rows</font>), "
                f"serta derau pengukuran.")
if tile_ratio[n0] < 1.05:
    anom.append(f"<b>Tiling tidak lebih cepat dari i-k-j.</b> Pada N={n0}, varian tiled berjalan {tile_ratio[n0]:.2f}x kecepatan i-k-j serial. "
                f"Urutan i-k-j sudah hampir seluruhnya sekuensial dan di-vektorisasi otomatis oleh compiler pada -O2; tiling baru memberi "
                f"keuntungan jelas bila ukuran data jauh melebihi kapasitas cache (mesin ini: L2 {env['l2']}, L3 {env['l3']}) atau untuk N yang lebih besar, "
                f"dan loop tambahan menambah overhead.")
if not anom:
    anom.append("Tidak ditemukan anomali yang signifikan pada data ini.")

# ------------------------------------------------------------------ dokumen
story = []
story += [P("Perkalian Matriks Paralel: Analisis Komparatif POSIX Threads dan OpenMP", title),
          P("Laporan Tugas Pemrograman Paralel", sub), P(f"<b>{esc(NAMA)}</b> &nbsp;|&nbsp; NIM {esc(NIM)}", sub),
          P(f"Repository: github.com/&lt;username&gt;/paralel-{esc(NIM)}-{esc(NAMA.replace(' ', '-'))}", sub), Spacer(1, 8)]

# 1. PENDAHULUAN
story += [P("1. Pendahuluan", h1),
 P("Perkalian matriks C = A &times; B adalah operasi inti di komputasi ilmiah, grafika, dan pembelajaran mesin. Untuk matriks N &times; N "
   "kompleksitas algoritma standar adalah O(N<super>3</super>): N<super>2</super> elemen hasil, masing-masing membutuhkan N perkalian-penjumlahan. "
   f"Pada N = {n0} sudah diperlukan sekitar {2*n0**3/1e9:.1f} miliar operasi floating point, sehingga operasi ini menjadi kandidat yang ideal untuk "
   "paralelisasi. Setiap elemen C[i][j] dapat dihitung secara independen, sehingga masalah ini bersifat <i>embarrassingly parallel</i> "
   "pada sisi komputasi, tetapi performanya sangat dipengaruhi oleh pola akses memori (cache locality) dan bandwidth memori."),
 P("Tugas ini mengimplementasikan perkalian matriks (tipe data <font face='Courier'>double</font>, ukuran minimal 1000 &times; 1000, "
   "inisialisasi <font face='Courier'>srand(42)</font>) dengan dua model pemrograman paralel memori-bersama: (1) POSIX Threads (Pthreads) "
   "yang eksplisit/manual, dan (2) OpenMP yang berbasis compiler directive."),
 P("<b>Tujuan:</b>"), *B([
   "Membuat baseline serial dan dua implementasi paralel yang menghasilkan hasil identik dan terverifikasi.",
   "Mengukur waktu eksekusi, speedup, dan efficiency untuk 1, 2, 4, dan 8 thread.",
   "Menganalisis efek urutan loop dan cache locality (i-j-k, i-k-j, transpose, tiling) terhadap performa.",
   "Membandingkan kompleksitas kode, kemudahan perawatan, dan kontrol yang ditawarkan Pthreads dibanding OpenMP, termasuk analisis bottleneck dengan Amdahl's Law."]),
 P(f"<b>Lingkungan pengujian:</b> {esc(env['cpu'])}; {cores} core fisik / {logical} CPU logis; cache L1d {esc(env['l1d'])}, L2 {esc(env['l2'])}, "
   f"L3 {esc(env['l3'])}; RAM {esc(env['mem'])}; {esc(env['os'])}; {esc(env['gcc'])}, opsi <font face='Courier'>-O2</font>. "
   f"Setiap konfigurasi diulang {env['reps']} kali dan dilaporkan sebagai rata-rata &plusmn; simpangan baku (waktu wall-clock, "
   f"<font face='Courier'>CLOCK_MONOTONIC</font>).")]

# 2. DESAIN
story += [PageBreak(), P("2. Desain Implementasi", h1), P("2.1 Algoritma Serial (Baseline)", h2),
 P("Matriks disimpan row-major dalam array 1D (elemen (i,j) = <font face='Courier'>M[i*N+j]</font>). Nilai A dan B diisi "
   "<font face='Courier'>rand()/RAND_MAX</font> setelah <font face='Courier'>srand(42)</font> sehingga data identik pada setiap eksekusi. "
   "Empat varian kernel dibuat untuk menjawab tantangan optimasi memori:"),
 table([["Varian", "Urutan loop / teknik", "Pola akses memori"],
        ["ijk", "i, j, k; akumulasi ke variabel lokal", "A[i][k] sekuensial, <b>B[k][j] melompat N elemen</b> (stride-N) pada loop dalam"],
        ["ikj", "i, k, j; C[i][j] += A[i][k]*B[k][j]", "A[i][k] konstan di loop dalam; B dan C diakses <b>sekuensial</b> per baris"],
        ["transpose", "B ditranspos ke B<super>T</super> (serial), lalu dot-product baris A &times; baris B<super>T</super>", "Kedua operand sekuensial; biaya tambahan O(N<super>2</super>) untuk transpos"],
        ["tiled", "i-k-j dengan blok 64 &times; 64 pada k dan j", "Blok B (64&times;64&times;8 B = 32 KB) dipakai ulang selagi masih di cache"]],
       colw=[2.2 * cm, 6.8 * cm, 7.5 * cm]),
 Spacer(1, 6),
 P("Kernel serial inti ditulis sekali dalam fungsi <font face='Courier'>mm_rows(v, A, B, Bt, C, N, r0, r1)</font> yang menghitung "
   "baris C[r0..r1-1]; baseline serial memanggilnya dengan r0=0, r1=N."),
 C("""
/* varian ikj (kernel baris r0..r1-1) */
for (int i = r0; i < r1; i++) {
    for (int j = 0; j < N; j++) C[i*N+j] = 0.0;
    for (int k = 0; k < N; k++) {
        double a = A[i*N+k];
        for (int j = 0; j < N; j++) C[i*N+j] += a * B[k*N+j];
    }
}"""),
 P("<b>Verifikasi kebenaran.</b> Setiap program menjalankan <i>selftest</i> 10 &times; 10 sebelum pengukuran: (1) A[i][k]=i+1 dan B[k][j]=j+1, "
   "sehingga hasil manual C[i][j] = 10(i+1)(j+1) (mis. C[0][0]=10, C[2][4]=150, C[9][9]=1000); (2) A = matriks identitas sehingga C harus sama dengan B. "
   "Pada N besar, hasil setiap konfigurasi dibandingkan dengan matriks referensi memakai toleransi relatif 10<super>-9</super>.")]

story += [P("2.2 Strategi Paralelisasi Pthreads", h2),
 P("<b>Pembagian workload.</b> Digunakan <i>domain decomposition</i> per baris matriks C. Thread ke-t menerima blok baris yang kontigu "
   "[r0, r1) dengan ukuran N/T; sisa N mod T disebar satu baris ke thread-thread pertama sehingga selisih beban antar thread maksimal satu baris. "
   "Pembagian berbasis baris dipilih karena (a) baris C bersifat independen, (b) tiap thread membaca baris A miliknya secara sekuensial, "
   "dan (c) thread menulis daerah memori yang berbeda sehingga risiko <i>false sharing</i> hanya ada di perbatasan blok."),
 P("<b>Mekanisme sinkronisasi.</b> Matriks A, B, dan B<super>T</super> hanya dibaca (shared read-only), sedangkan setiap baris C hanya ditulis "
   "oleh tepat satu thread. Karena itu <b>tidak ada race condition dan tidak diperlukan mutex/semaphore</b>. Satu-satunya sinkronisasi adalah "
   "<font face='Courier'>pthread_join</font> di thread utama, yang berfungsi sebagai barrier akhir. Transpos B dikerjakan serial sebelum thread dibuat."),
 C("""
typedef struct { int v, N, r0, r1; const double *A,*B,*Bt; double *C; } task_t;
static void *worker(void *arg) {
    task_t *t = (task_t *)arg;
    mm_rows(t->v, t->A, t->B, t->Bt, t->C, t->N, t->r0, t->r1);
    return NULL;
}
/* di matmul(): */
int base = N / T, extra = N % T, row = 0;
for (int t = 0; t < T; t++) {
    int cnt = base + (t < extra ? 1 : 0);
    tasks[t] = (task_t){v, N, row, row + cnt, A, B, Bt, C};
    row += cnt;
    pthread_create(&th[t], NULL, worker, &tasks[t]);
}
for (int t = 0; t < T; t++) pthread_join(th[t], NULL);"""),
 P("2.3 Strategi Paralelisasi OpenMP", h2),
 P("<b>Pemilihan pragma dan clause.</b> Paralelisasi dilakukan dengan <font face='Courier'>#pragma omp parallel for</font> pada loop terluar (indeks baris i), "
   "yang secara semantik setara dengan pembagian baris pada Pthreads. Clause <font face='Courier'>schedule(static)</font> dipilih karena beban setiap iterasi "
   "seragam, sehingga penjadwalan statis menghasilkan blok kontigu dengan overhead runtime terendah (penjadwalan dynamic/guided hanya menambah overhead tanpa manfaat). "
   "Jumlah thread diatur dengan <font face='Courier'>omp_set_num_threads(T)</font>. Barrier implisit di akhir <i>parallel for</i> menggantikan <font face='Courier'>pthread_join</font>."),
 P("<b>Scope variabel.</b> Memakai <font face='Courier'>default(none)</font> agar setiap variabel wajib dideklarasikan eksplisit (mencegah kesalahan scope yang diam-diam):"),
 *B(["<b>shared</b>: A, B (atau B<super>T</super>), C, N. A dan B hanya dibaca; elemen C yang ditulis tidak pernah tumpang tindih antar thread.",
     "<b>private</b>: indeks loop i, j, k (dan ii, jj, kk pada varian tiled) serta akumulator <font face='Courier'>sum</font>; setiap thread punya salinan sendiri. "
     "Menjadikan <font face='Courier'>sum</font> shared adalah bug klasik yang menimbulkan race condition."]),
 C("""
#pragma omp parallel for schedule(static) default(none) \\
        shared(A, B, C, N) private(i, j, k)
for (i = 0; i < N; i++) {
    for (j = 0; j < N; j++) C[i*N+j] = 0.0;
    for (k = 0; k < N; k++) {
        double a = A[i*N+k];
        for (j = 0; j < N; j++) C[i*N+j] += a * B[k*N+j];
    }
}""")]

# 3. HASIL
story += [PageBreak(), P("3. Hasil Pengujian", h1), P("3.1 Verifikasi Correctness", h2),
 P(("Seluruh konfigurasi (3 program &times; 4 varian &times; %d variasi thread &times; %d ukuran N) lulus selftest 10&times;10 dan menghasilkan matriks yang "
    "sama dengan referensi serial pada toleransi 10<super>-9</super> (kolom <i>verified</i> = 1 pada seluruh %d baris ringkasan). Bukti mentah ada di "
    "<font face='Courier'>results/results.csv</font>.") % (len(threads), len(sizes), len(s)) if all_ok else
   "<b>PERINGATAN:</b> terdapat konfigurasi yang gagal verifikasi; periksa results/summary.csv."),
 P("Karena varian ijk, ikj, transpose, dan tiled menjumlahkan suku-suku C[i][j] dengan urutan k yang sama (naik), perbedaan numerik antar varian "
   "praktis nol; toleransi tetap dipakai karena aritmetika floating point tidak asosiatif jika urutan penjumlahan berubah.")]

def time_table(n):
    hdr = ["Program", "Thread"] + VARS
    rows = [hdr, ["serial", "1"] + [ms(ser[(v, n)]) for v in VARS]]
    for ap_ in ("pthreads", "openmp"):
        for t in threads:
            rows.append([ap_, str(t)] + [ms(row(ap_, v, n, t)) for v in VARS])
    return table(rows, colw=[2.4 * cm, 1.5 * cm] + [3.1 * cm] * 4)

story += [P("3.2 Waktu Eksekusi", h2), P(f"Tabel 1 memuat waktu eksekusi (detik, rata-rata &plusmn; simpangan baku dari {env['reps']} ulangan) untuk N = {n0}."),
          time_table(n0), P(f"Tabel 1. Waktu eksekusi (detik), N = {n0}.", cap)]
for n in sizes[1:]:
    story += [Spacer(1, 6), time_table(n), P(f"Tabel 2. Waktu eksekusi (detik), N = {n}.", cap)]

def sp_table(n, v):
    rows = [["Pendekatan", "Thread", "Waktu (s)", "Speedup", "Efficiency"]]
    for ap_ in ("pthreads", "openmp"):
        for t in threads:
            r = row(ap_, v, n, t); rows.append([ap_, str(t), f"{r['mean']:.3f}", f"{r['speedup']:.2f}", f"{r['efficiency']:.2f}"])
    return table(rows, colw=[3 * cm, 2 * cm, 2.6 * cm, 2.4 * cm, 2.4 * cm])
story += [P(f"3.3 Speedup dan Efficiency", h2),
 P(f"Speedup S = T<sub>serial</sub> / T<sub>paralel</sub> dan efficiency E = S / T dihitung terhadap waktu serial varian yang sama. "
   f"Tabel 3 merangkum varian tercepat pada baseline serial ({best_v}); grafik lengkap untuk keempat varian ditunjukkan pada Gambar 1-3."),
 sp_table(n0, best_v), P(f"Tabel 3. Speedup dan efficiency varian {best_v}, N = {n0} (T<sub>serial</sub> = {ser[(best_v, n0)]['mean']:.3f} s).", cap),
 fig("fig_time.png", caption=f"Gambar 1. Waktu eksekusi vs jumlah thread (N = {n0}). Error bar = 1 simpangan baku."),
 fig("fig_speedup.png", caption=f"Gambar 2. Speedup vs jumlah thread (N = {n0}); garis putus-putus = speedup ideal."),
 fig("fig_efficiency.png", caption=f"Gambar 3. Efficiency vs jumlah thread (N = {n0}).")]

story += [P("3.4 Efek Cache Locality (Baseline Serial)", h2),
 P("Gambar 4 membandingkan waktu keempat varian pada eksekusi serial. " +
   " ".join([f"Pada N = {n}, urutan ijk membutuhkan {cache_ratio[n]:.2f}x waktu i-k-j; transpose {ser[('transpose', n)]['mean']/ser[('ikj', n)]['mean']:.2f}x; "
             f"tiled {ser[('tiled', n)]['mean']/ser[('ikj', n)]['mean']:.2f}x dari waktu i-k-j." for n in sizes])),
 fig("fig_cache.png", w=10.5, ratio=3.8 / 6.5, caption="Gambar 4. Waktu serial per varian kernel.")]

# 4. ANALISIS
story += [PageBreak(), P("4. Analisis Kritis", h1), P("4.1 Cache Locality dan Pola Akses Memori", h2),
 P(f"Perbedaan antar varian serial berasal dari pola akses ke matriks B. Pada urutan i-j-k, loop terdalam (k) mengakses B[k][j] dengan lompatan N&times;8 = {n0*8} byte; "
   "setiap akses jatuh ke cache line yang berbeda (satu cache line 64 byte memuat 8 double), sehingga hanya 1 dari 8 elemen pada line yang termuat yang langsung "
   "dipakai, dan kolom B harus dimuat ulang untuk setiap pasangan (i, j) jika tidak muat di cache. Pada urutan i-k-j, loop terdalam (j) membaca B[k][:] dan menulis C[i][:] "
   "secara sekuensial: seluruh byte tiap cache line terpakai, prefetcher hardware bekerja optimal, dan compiler dapat melakukan vektorisasi SIMD. "
   f"Terukur pada N = {n0}: i-j-k membutuhkan {cache_ratio[n0]:.2f}x waktu i-k-j, sedangkan varian transpose {tr_ratio[n0]:.2f}x lebih cepat daripada i-j-k. "
   + (f"Rasio ini kemungkinan lebih kecil daripada pada CPU dengan cache kecil karena mesin uji memiliki L2 {esc(env['l2'])} dan L3 {esc(env['l3'])}, "
      "dan prefetcher modern dapat menyembunyikan sebagian latensi akses ber-stride; pada mesin lain (atau N lebih besar) selisihnya dapat jauh lebih besar. "
      if cache_ratio[n0] < 3 else "Selisih besar ini konsisten dengan teori: akses stride-N memicu banyak cache miss. ") +
   "Varian transpose membayar biaya O(N<super>2</super>) untuk transpos serial, tetapi dot-product sekuensial pada B<super>T</super> menjadi jauh lebih ramah cache, sehingga biayanya cepat terbayar untuk N besar. "
   "Varian tiled menjaga blok B (32 KB) tetap di L1/L2 selama dipakai ulang oleh BS baris A; manfaatnya meningkat ketika working set (3 matriks &times; 8 MB pada N = 1000) jauh melampaui cache."),
 P("4.2 Perbandingan Kompleksitas Kode", h2),
 table([["Berkas", "LOC total (tanpa komentar & baris kosong)", "LOC lapisan paralel*", "Keterangan"],
        ["src/common.h", str(LOC_common), "-", "Kernel serial, timer, verifikasi, driver (dipakai bersama)"],
        ["src/serial.c", str(LOC["serial"][0]), "-", "Baseline"],
        ["src/pthreads.c", str(LOC["pthreads"][0]), str(LOC["pthreads"][1]), f"{n_pth} referensi API pthread_*; struct argumen, worker, partisi manual, create/join"],
        ["src/openmp.c", str(LOC["openmp"][0]), str(LOC["openmp"][1]), f"{n_pragma} direktif #pragma omp; seluruh kernel ditulis ulang inline"]],
       colw=[2.7 * cm, 3.6 * cm, 2.8 * cm, 7.4 * cm]),
 P("*Baris di antara penanda PAR-BEGIN/PAR-END pada masing-masing berkas. Catatan kejujuran metodologis: pada kode ini Pthreads memakai ulang <font face='Courier'>mm_rows</font> "
   "dari common.h, sedangkan OpenMP menulis ulang kernel di dalam loop yang dianotasi pragma (pragma harus berada tepat di atas loop). Maka perbandingan LOC mentah "
   "tidak mencerminkan beban paralelisasinya. Ukuran yang lebih adil adalah <i>kode tambahan untuk paralelisasi</i>: OpenMP cukup menambah <b>satu baris pragma (+ 1 baris omp_set_num_threads)</b> "
   "pada kernel serial, sedangkan Pthreads menambah struct argumen, fungsi worker, perhitungan partisi, alokasi array thread, pembuatan, penggabungan, dan penanganan error: "
   f"sekitar {LOC['pthreads'][1]} baris (lapisan paralel) dan perubahan struktur program (loop harus diekstrak menjadi fungsi dengan parameter rentang baris)."),
 P("<b>Maintainability.</b> Kode OpenMP yang hanya memakai pragma tetap menjadi program serial yang benar bila dikompilasi tanpa <font face='Courier'>-fopenmp</font> "
   "(pragma diabaikan), sehingga logika dapat di-debug secara serial. (Pada implementasi ini pemanggilan <font face='Courier'>omp_set_num_threads</font> dan <font face='Courier'>omp.h</font> "
   "memerlukan guard <font face='Courier'>#ifdef _OPENMP</font> agar sifat tersebut berlaku.) Kode Pthreads mengikat logika komputasi dengan manajemen thread; setiap perubahan "
   "(mis. mengganti partisi baris menjadi blok 2D, atau menambah reduksi) menyentuh struktur data dan alur kontrol. Sebaliknya Pthreads menawarkan transparansi total: tidak ada perilaku tersembunyi dari runtime."),
 P("4.3 Bottleneck dan Amdahl's Law", h2),
 P("Amdahl's Law menyatakan speedup maksimum S(p) = 1 / (f + (1 - f)/p) dengan f adalah fraksi serial program. Bagian serial pada program ini adalah: "
   "inisialisasi data, transpos B (hanya varian transpose), pembuatan/penggabungan thread, dan <i>load imbalance</i> pada blok terakhir. "
   "Karena kernel inti mendominasi waktu (O(N<super>3</super>) dibanding O(N<super>2</super>) untuk bagian serial), f secara teori sangat kecil dan speedup ideal mendekati linear; "
   "batas praktisnya justru datang dari <b>bandwidth memori bersama</b> dan <b>cache bersama</b>, yang tidak tercakup model Amdahl.")]
if amdahl_ok:
    rows = [["Pendekatan", "Varian", f"f (Karp-Flatt, p={p_est})"] + [f"S({p}) prediksi / ukur" for p in threads if p > p_est] if any(p > p_est for p in threads)
            else ["Pendekatan", "Varian", f"f (Karp-Flatt, p={p_est})", "Speedup ukur"]]
    for ap_ in ("pthreads", "openmp"):
        for v in VARS:
            f = karp(ap_, v, n0, p_est)
            if f is None: continue
            f = max(f, 0.0)
            if any(p > p_est for p in threads):
                extra = [f"{1/(f+(1-f)/p):.2f} / {row(ap_, v, n0, p)['speedup']:.2f}" for p in threads if p > p_est]
            else:
                extra = [f"{row(ap_, v, n0, p_est)['speedup']:.2f}"]
            rows.append([ap_, v, f"{f:.3f}"] + extra)
    story += [P(f"Fraksi serial efektif diestimasi dengan metrik Karp-Flatt, e = (1/S - 1/p) / (1 - 1/p), dari speedup terukur pada p = {p_est} "
                f"(thread terbanyak yang tidak melebihi jumlah core fisik, {cores}); lalu dipakai untuk memprediksi speedup pada p lebih besar (Tabel 4). "
                "Nilai e mencakup semua sumber inefisiensi (bandwidth, overhead, imbalance), bukan hanya bagian serial murni."),
              table(rows, colw=[2.8 * cm, 2.4 * cm, 3.8 * cm] + [3.5 * cm] * (len(rows[0]) - 3)),
              P("Tabel 4. Estimasi fraksi serial efektif dan prediksi speedup (N = %d)." % n0, cap)]
else:
    rows = [["Fraksi serial f", "S(2)", "S(4)", "S(8)", "S(maks, p&rarr;&infin;)"]]
    for f in (0.01, 0.05, 0.10, 0.25):
        rows.append([f"{f:.0%}"] + [f"{1/(f+(1-f)/p):.2f}" for p in (2, 4, 8)] + [f"{1/f:.0f}"])
    story += [P(f"<b>Keterbatasan pengukuran:</b> mesin yang menghasilkan data laporan ini hanya memiliki {cores} core fisik, sehingga fraksi serial efektif "
                "tidak dapat diestimasi dari data (metrik Karp-Flatt memerlukan p &gt; 1 pada core fisik yang nyata). Sebagai gantinya Tabel 4 memberikan "
                "batas teoretis Amdahl untuk beberapa nilai f. Jalankan <font face='Courier'>make bench</font> pada mesin multi-core untuk mendapatkan estimasi empiris."),
              table(rows, colw=[3.2 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 4 * cm]),
              P("Tabel 4. Batas speedup Amdahl untuk berbagai fraksi serial.", cap)]

story += [P("4.4 Pembahasan Anomali", h2),
          P("Berikut temuan yang terdeteksi otomatis dari data pengukuran dan penjelasannya:")] + B(anom)
story += [P("<b>Perbandingan Pthreads vs OpenMP.</b> " +
            f"Rata-rata geometrik rasio waktu Pthreads/OpenMP terhadap seluruh konfigurasi paralel adalah {gm:.3f}. " +
            ("Kedua pendekatan menunjukkan kinerja yang setara dalam batas derau pengukuran (selisih rata-rata &lt; 5%), yang wajar karena keduanya memakai pembagian blok baris "
             "yang sama dan kernel inti yang sama; perbedaan performa sebenarnya hampir seluruhnya ditentukan oleh pola akses memori, bukan oleh pustaka threading."
             if abs(gm - 1) < 0.05 else
             ("Pthreads secara rata-rata lebih cepat" if gm < 1 else "OpenMP secara rata-rata lebih cepat") +
             f" sekitar {100*abs(1-gm):.0f}%, namun selisih ini harus dibaca bersama simpangan baku pada Tabel 1."))]
story += [P("4.5 Trade-off Kemudahan vs Kontrol", h2),
 table([["Aspek", "Pthreads", "OpenMP"],
        ["Usaha menulis", "Tinggi: partisi, struct argumen, create/join, error handling manual", "Rendah: 1-2 direktif pada kode serial"],
        ["Kontrol", "Penuh: pembagian kerja, affinity, prioritas, pola sinkronisasi kustom, thread pool sendiri", "Terbatas pada clause (schedule, collapse, proc_bind) dan perilaku runtime"],
        ["Risiko bug", "Lebih tinggi (race, deadlock, kebocoran thread)", "Lebih rendah, tetapi kesalahan scope (shared/private) sulit terlihat; default(none) membantu"],
        ["Portabilitas", "POSIX; Windows memerlukan lapisan tambahan", "Standar bahasa lintas platform; bergantung dukungan compiler"],
        ["Kemampuan lanjutan", "Fleksibel untuk pola non-regular (pipeline, producer-consumer)", "Tersedia task, reduction, SIMD, offload; paling cocok untuk loop data-parallel"],
        ["Debugging/serial fallback", "Tidak ada; kode selalu paralel", "Dapat dikompilasi serial tanpa -fopenmp"]],
       colw=[3 * cm, 6.5 * cm, 6.5 * cm]),
 P("Untuk perkalian matriks, beban kerja yang seragam dan loop teratur membuat OpenMP memberi hasil setara dengan usaha yang jauh lebih kecil. "
   "Kontrol ekstra Pthreads baru bernilai bila diperlukan pola yang tidak dapat diungkapkan sebagai <i>parallel for</i>.")]

# 5. KESIMPULAN
story += [P("5. Kesimpulan", h1),
 P(f"Perkalian matriks ber-presisi ganda berhasil diimplementasikan dalam versi serial, Pthreads, dan OpenMP dengan empat varian akses memori; seluruh hasil "
   f"terverifikasi {'benar' if all_ok else '(lihat peringatan)'} terhadap selftest 10&times;10 dan referensi serial. Temuan utama:"),
 *B([f"<b>Pola akses memori lebih menentukan daripada pilihan pustaka threading.</b> Pada serial N = {n0}, i-k-j {cache_ratio[n0]:.2f}x lebih cepat dari i-j-k; " +
     (f"kedua pendekatan paralel memberi waktu yang setara (rasio geometrik Pthreads/OpenMP = {gm:.3f}) untuk kernel yang sama." if abs(gm-1)<0.05 else f"rasio geometrik waktu Pthreads/OpenMP = {gm:.3f} untuk kernel yang sama."),
     f"<b>Skalabilitas dibatasi hardware.</b> Speedup tidak dapat melampaui jumlah core fisik ({cores} pada mesin uji) dan, pada mesin multi-core, "
     "dibatasi bandwidth/cache bersama; ini perlu dicek memakai estimasi fraksi serial efektif (Tabel 4).",
     f"<b>Kompleksitas kode berbeda tajam:</b> paralelisasi OpenMP memerlukan kurang dari 5 baris tambahan, Pthreads sekitar {LOC['pthreads'][1]} baris pada lapisan paralel."]),
 P("<b>Rekomendasi penggunaan.</b> Gunakan <b>OpenMP</b> untuk komputasi data-parallel yang teratur (loop bersarang, reduksi, operasi matriks/array): "
   "waktu pengembangan singkat, kode mudah dirawat, dan performa setara. Gunakan <b>Pthreads</b> bila membutuhkan kontrol penuh: pola konkuren non-regular "
   "(pipeline, producer-consumer, server multi-thread), thread pool atau affinity kustom, atau lingkungan tanpa dukungan OpenMP."),
 P("<b>Pembelajaran.</b> (1) Optimasi serial (cache locality) harus dilakukan sebelum paralelisasi, karena ia memberi peningkatan yang tidak bergantung jumlah core. "
   "(2) Pengukuran yang valid memerlukan ulangan, wall-clock timer, dan pelaporan variansi; selisih kecil tidak bermakna. (3) Hasil paralel harus selalu diverifikasi "
   "terhadap acuan serial. (4) Keterbatasan perangkat keras (core fisik, bandwidth) harus dipertimbangkan saat menafsirkan speedup.")]

# 6. PUSTAKA
refs = [
 "Amdahl, G. M. (1967). Validity of the single processor approach to achieving large scale computing capabilities. <i>Proc. AFIPS Spring Joint Computer Conference</i>, 483-485.",
 "Butenhof, D. R. (1997). <i>Programming with POSIX Threads</i>. Addison-Wesley.",
 "Chapman, B., Jost, G., &amp; van der Pas, R. (2008). <i>Using OpenMP: Portable Shared Memory Parallel Programming</i>. MIT Press.",
 "Drepper, U. (2007). <i>What Every Programmer Should Know About Memory</i>. Red Hat, Inc.",
 "Hennessy, J. L., &amp; Patterson, D. A. (2017). <i>Computer Architecture: A Quantitative Approach</i> (6th ed.). Morgan Kaufmann.",
 "Karp, A. H., &amp; Flatt, H. P. (1990). Measuring parallel processor performance. <i>Communications of the ACM</i>, 33(5), 539-543.",
 "OpenMP Architecture Review Board. (2021). <i>OpenMP Application Programming Interface, Version 5.2</i>. https://www.openmp.org",
 "Pacheco, P. (2011). <i>An Introduction to Parallel Programming</i>. Morgan Kaufmann.",
 "The Open Group. (2018). <i>POSIX.1-2017 (IEEE Std 1003.1): Threads</i>. https://pubs.opengroup.org/onlinepubs/9699919799/"]
story += [P("6. Daftar Pustaka", h1)] + [P(f"[{i}] {r}", ParagraphStyle("r", parent=body, leftIndent=18, firstLineIndent=-18, alignment=0)) for i, r in enumerate(refs, 1)]

def footer(c, d):
    c.saveState(); c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
    c.drawCentredString(A4[0] / 2, 1.2 * cm, f"{NAMA} - {NIM}   |   Halaman {d.page}"); c.restoreState()

out = os.path.join(ROOT, "report", "laporan.pdf")
doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                        title="Perkalian Matriks Paralel: Pthreads vs OpenMP", author=NAMA)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("Laporan ->", out)
