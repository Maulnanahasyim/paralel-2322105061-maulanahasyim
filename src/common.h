/*
 * common.h - Utilitas bersama untuk semua implementasi perkalian matriks.
 *
 * Isi:
 *   - Timer wall-clock (CLOCK_MONOTONIC)
 *   - Inisialisasi matriks pseudo-random (srand(42) -> reproducible)
 *   - Empat varian kernel perkalian matriks (ijk, ikj, transpose, tiled)
 *   - Verifikasi: selftest 10x10 (bisa dihitung manual) + bandingkan dgn referensi
 *   - bench_main(): driver bersama sehingga serial/pthreads/openmp
 *     hanya perlu mengimplementasikan fungsi matmul().
 *
 * Layout memori: matriks N x N disimpan row-major dalam array 1D,
 * elemen (i,j) = M[i*N + j].
 *
 * Penggunaan program:  ./prog N THREADS VARIAN REPS
 *   VARIAN : ijk | ikj | transpose | tiled
 * Keluaran CSV di stdout:
 *   pendekatan,varian,N,threads,rep,detik,verified
 */
#ifndef COMMON_H
#define COMMON_H

#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

/* ---- Varian kernel ---- */
enum { V_IJK = 0, V_IKJ, V_TR, V_TILE, V_COUNT };
static const char *VNAME[V_COUNT] = {"ijk", "ikj", "transpose", "tiled"};
#define BS 64 /* ukuran blok (tile) untuk varian tiled */

/* Tanda tangan fungsi yang diimplementasikan tiap pendekatan */
typedef void (*mm_fn)(int variant, const double *A, const double *B,
                      double *C, int N, int T);

/* Timer wall-clock dalam detik. (clock() TIDAK dipakai karena mengukur
 * CPU-time total semua thread, bukan waktu nyata.) */
static inline double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static inline int parse_variant(const char *s) {
    for (int v = 0; v < V_COUNT; v++)
        if (strcmp(s, VNAME[v]) == 0) return v;
    return -1;
}

/* Alokasi matriks N x N, rata 64 byte (ukuran cache line) */
static inline double *alloc_mat(int N) {
    size_t bytes = (size_t)N * N * sizeof(double);
    bytes = (bytes + 63) & ~(size_t)63; /* aligned_alloc butuh kelipatan alignment */
    double *p = aligned_alloc(64, bytes);
    if (!p) { fprintf(stderr, "alokasi gagal\n"); exit(2); }
    return p;
}

/* Isi A lalu B dengan nilai acak [0,1] memakai srand(42) */
static inline void init_matrices(double *A, double *B, int N) {
    srand(42);
    for (size_t i = 0; i < (size_t)N * N; i++) A[i] = (double)rand() / RAND_MAX;
    for (size_t i = 0; i < (size_t)N * N; i++) B[i] = (double)rand() / RAND_MAX;
}

/* Bt = transpose(B). Dikerjakan serial di semua pendekatan agar adil
 * (bagian serial ini relevan untuk analisis Amdahl). */
static inline void transpose_mat(const double *B, double *Bt, int N) {
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++) Bt[(size_t)j * N + i] = B[(size_t)i * N + j];
}

/*
 * mm_rows: hitung baris C[r0 .. r1-1] dengan varian tertentu (kode SERIAL
 * inti). Dipakai oleh serial.c dan pthreads.c (tiap thread memanggil ini
 * untuk blok barisnya sendiri). Bt hanya dipakai varian transpose.
 * Setiap baris C hanya ditulis oleh satu pemanggil -> bebas race condition.
 */
static inline void mm_rows(int v, const double *A, const double *B,
                           const double *Bt, double *C, int N, int r0, int r1) {
    switch (v) {
    case V_IJK: /* B diakses per KOLOM (stride N) -> cache-unfriendly */
        for (int i = r0; i < r1; i++)
            for (int j = 0; j < N; j++) {
                double sum = 0.0;
                for (int k = 0; k < N; k++) sum += A[(size_t)i*N+k] * B[(size_t)k*N+j];
                C[(size_t)i*N+j] = sum;
            }
        break;
    case V_IKJ: /* semua akses sekuensial per baris -> cache-friendly */
        for (int i = r0; i < r1; i++) {
            for (int j = 0; j < N; j++) C[(size_t)i*N+j] = 0.0;
            for (int k = 0; k < N; k++) {
                double a = A[(size_t)i*N+k];
                for (int j = 0; j < N; j++) C[(size_t)i*N+j] += a * B[(size_t)k*N+j];
            }
        }
        break;
    case V_TR: /* dot product dua baris (A[i,:] dan Bt[j,:]) */
        for (int i = r0; i < r1; i++)
            for (int j = 0; j < N; j++) {
                double sum = 0.0;
                for (int k = 0; k < N; k++) sum += A[(size_t)i*N+k] * Bt[(size_t)j*N+k];
                C[(size_t)i*N+j] = sum;
            }
        break;
    case V_TILE: /* loop tiling/blocking di atas urutan i-k-j */
        for (int i = r0; i < r1; i++)
            for (int j = 0; j < N; j++) C[(size_t)i*N+j] = 0.0;
        for (int kk = 0; kk < N; kk += BS)
            for (int jj = 0; jj < N; jj += BS) {
                int kmax = kk + BS < N ? kk + BS : N;
                int jmax = jj + BS < N ? jj + BS : N;
                for (int i = r0; i < r1; i++)
                    for (int k = kk; k < kmax; k++) {
                        double a = A[(size_t)i*N+k];
                        for (int j = jj; j < jmax; j++)
                            C[(size_t)i*N+j] += a * B[(size_t)k*N+j];
                    }
            }
        break;
    }
}

/* Bandingkan dua matriks dengan toleransi relatif/absolut. 1 = sama. */
static inline int mat_equal(const double *X, const double *Y, size_t n, double tol) {
    for (size_t i = 0; i < n; i++) {
        double d = fabs(X[i] - Y[i]);
        if (d > tol * (1.0 + fabs(Y[i]))) return 0;
    }
    return 1;
}

/*
 * Selftest 10x10 dengan hasil yang dapat dihitung manual:
 *  Tes 1: A[i][k] = i+1, B[k][j] = j+1
 *         C[i][j] = sum_{k=0..9} (i+1)(j+1) = 10*(i+1)*(j+1)
 *         contoh: C[0][0]=10, C[9][9]=1000, C[2][4]=150
 *  Tes 2: A = matriks identitas -> C harus sama dengan B.
 * Mengembalikan 1 jika lulus.
 */
static inline int selftest_10x10(mm_fn mm, int v, int T) {
    const int n = 10;
    double *A = alloc_mat(n), *B = alloc_mat(n), *C = alloc_mat(n);
    int ok = 1;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) { A[i*n+j] = i + 1; B[i*n+j] = j + 1; }
    mm(v, A, B, C, n, T);
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            if (fabs(C[i*n+j] - 10.0 * (i + 1) * (j + 1)) > 1e-12) ok = 0;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) { A[i*n+j] = (i == j); B[i*n+j] = i * 10 + j; }
    mm(v, A, B, C, n, T);
    for (int i = 0; i < n * n; i++)
        if (fabs(C[i] - B[i]) > 1e-12) ok = 0;
    free(A); free(B); free(C);
    return ok;
}

/* Driver bersama: parsing argumen, selftest, verifikasi, timing berulang. */
static inline int bench_main(int argc, char **argv, const char *name, mm_fn mm) {
    if (argc < 5) {
        fprintf(stderr, "Pemakaian: %s N THREADS VARIAN(ijk|ikj|transpose|tiled) REPS\n", argv[0]);
        return 1;
    }
    int N = atoi(argv[1]), T = atoi(argv[2]), reps = atoi(argv[4]);
    int v = parse_variant(argv[3]);
    if (N < 1 || T < 1 || reps < 1 || v < 0) { fprintf(stderr, "argumen tidak valid\n"); return 1; }

    if (!selftest_10x10(mm, v, T)) {
        fprintf(stderr, "[%s/%s] SELFTEST 10x10 GAGAL\n", name, VNAME[v]);
        return 3;
    }
    fprintf(stderr, "[%s/%s] selftest 10x10 OK\n", name, VNAME[v]);

    double *A = alloc_mat(N), *B = alloc_mat(N), *C = alloc_mat(N), *R = alloc_mat(N);
    init_matrices(A, B, N);

    /* Referensi: kernel tiled serial (cepat), dihitung di luar pengukuran */
    mm_rows(V_TILE, A, B, NULL, R, N, 0, N);

    for (int r = 0; r < reps; r++) {
        memset(C, 0, (size_t)N * N * sizeof(double));
        double t0 = now_sec();
        mm(v, A, B, C, N, T);
        double t1 = now_sec();
        int ok = mat_equal(C, R, (size_t)N * N, 1e-9);
        printf("%s,%s,%d,%d,%d,%.6f,%d\n", name, VNAME[v], N, T, r, t1 - t0, ok);
        fflush(stdout);
    }
    free(A); free(B); free(C); free(R);
    return 0;
}

#endif /* COMMON_H */
