# Perkalian Matriks Paralel: Pthreads vs OpenMP

Tugas Pemrograman Paralel. Perkalian matriks `C = A x B` (tipe `double`, N >= 1000,
`srand(42)`) dengan tiga implementasi: **serial** (baseline), **POSIX Threads** (manual) dan
**OpenMP** (compiler directive), masing-masing dengan 4 varian akses memori:

| Varian | Teknik |
|---|---|
| `ijk` | loop standar, B diakses per kolom (cache-unfriendly) |
| `ikj` | B dan C diakses per baris (cache-friendly) |
| `transpose` | transpos B dulu, lalu dot-product baris x baris |
| `tiled` | loop tiling/blocking 64x64 |

## Struktur
```
src/common.h    kernel serial, timer, init srand(42), selftest 10x10, driver
src/serial.c    baseline serial
src/pthreads.c  paralel Pthreads (partisi baris, pthread_create/join)
src/openmp.c    paralel OpenMP (#pragma omp parallel for schedule(static))
scripts/        run_bench.py (benchmark), analyze.py (tabel+grafik), make_report.py (PDF)
results/        results.csv, summary.csv, env.json, grafik *.png
report/         laporan.pdf
Makefile
```

## Requirement
`gcc` (dengan OpenMP), `make`, `python3` + `pandas matplotlib reportlab`
(`pip install pandas matplotlib reportlab`). Windows: gunakan WSL atau MSYS2.

## Compile
```
make            # menghasilkan bin/serial, bin/pthreads, bin/openmp
```

## Run (satu program)
```
./bin/<serial|pthreads|openmp> N THREADS VARIAN REPS
./bin/pthreads 1000 4 ikj 5      # contoh: N=1000, 4 thread, varian ikj, 5 ulangan
```
Keluaran CSV: `pendekatan,varian,N,threads,rep,detik,verified`.
Setiap run otomatis menjalankan selftest 10x10 (hasil manual: `C[i][j]=10(i+1)(j+1)`
dan tes matriks identitas) lalu memverifikasi hasil N besar terhadap referensi.

## Verifikasi
```
make test       # semua kombinasi harus "verified=1"
```

## Benchmark, grafik, laporan
```
make bench                                  # thread 1,2,4,8; N=1000 & 1500; 5 ulangan
python3 scripts/run_bench.py --quick        # versi cepat (N=1000, 3 ulangan)
make analyze                                # summary.csv + grafik di results/

```
Seluruh angka di laporan dihitung dari `results/` pada mesin yang menjalankan `make bench`,
jadi **jalankan `make bench` di mesin multi-core milik sendiri** sebelum `make report`.
Tutup aplikasi berat lain selama benchmark.

## Catatan
- Timer: `clock_gettime(CLOCK_MONOTONIC)` (wall-clock), bukan `clock()`.
- Flag kompilasi sama untuk semua versi: `-O2`.
