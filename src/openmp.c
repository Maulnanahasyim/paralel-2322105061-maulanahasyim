/*
 * openmp.c - Perkalian matriks paralel dengan OpenMP (compiler directive).
 *
 * Strategi:
 *  - "#pragma omp parallel for schedule(static)" pada loop terluar (baris i).
 *    Iterasi dibagi rata & kontigu antar thread (mirip pembagian manual
 *    pada Pthreads).
 *  - Scope variabel eksplisit dengan default(none):
 *      shared  : A, B, Bt, C, N   (A,B,Bt read-only; C ditulis per-baris unik)
 *      private : indeks loop & akumulator (i, j, k, sum, ...)
 *  - Tidak ada sinkronisasi manual; barrier implisit di akhir parallel for.
 */
#include <omp.h>
#include "common.h"

/* PAR-BEGIN (dipakai script untuk menghitung LOC lapisan paralel) */
static void matmul(int v, const double *A, const double *B, double *C, int N, int T) {
    omp_set_num_threads(T);
    int i, j, k, ii, jj, kk;
    double sum;
    double *Bt = NULL;
    if (v == V_TR) { Bt = alloc_mat(N); transpose_mat(B, Bt, N); }

    switch (v) {
    case V_IJK:
        #pragma omp parallel for schedule(static) default(none) shared(A, B, C, N) private(i, j, k, sum)
        for (i = 0; i < N; i++)
            for (j = 0; j < N; j++) {
                sum = 0.0;
                for (k = 0; k < N; k++) sum += A[(size_t)i*N+k] * B[(size_t)k*N+j];
                C[(size_t)i*N+j] = sum;
            }
        break;
    case V_IKJ:
        #pragma omp parallel for schedule(static) default(none) shared(A, B, C, N) private(i, j, k)
        for (i = 0; i < N; i++) {
            for (j = 0; j < N; j++) C[(size_t)i*N+j] = 0.0;
            for (k = 0; k < N; k++) {
                double a = A[(size_t)i*N+k];
                for (j = 0; j < N; j++) C[(size_t)i*N+j] += a * B[(size_t)k*N+j];
            }
        }
        break;
    case V_TR:
        #pragma omp parallel for schedule(static) default(none) shared(A, Bt, C, N) private(i, j, k, sum)
        for (i = 0; i < N; i++)
            for (j = 0; j < N; j++) {
                sum = 0.0;
                for (k = 0; k < N; k++) sum += A[(size_t)i*N+k] * Bt[(size_t)j*N+k];
                C[(size_t)i*N+j] = sum;
            }
        break;
    case V_TILE: /* paralelkan blok-baris (ii); tiap iterasi = BS baris */
        #pragma omp parallel for schedule(static) default(none) shared(A, B, C, N) private(ii, jj, kk, i, j, k)
        for (ii = 0; ii < N; ii += BS) {
            int imax = ii + BS < N ? ii + BS : N;
            for (i = ii; i < imax; i++)
                for (j = 0; j < N; j++) C[(size_t)i*N+j] = 0.0;
            for (kk = 0; kk < N; kk += BS)
                for (jj = 0; jj < N; jj += BS) {
                    int kmax = kk + BS < N ? kk + BS : N;
                    int jmax = jj + BS < N ? jj + BS : N;
                    for (i = ii; i < imax; i++)
                        for (k = kk; k < kmax; k++) {
                            double a = A[(size_t)i*N+k];
                            for (j = jj; j < jmax; j++)
                                C[(size_t)i*N+j] += a * B[(size_t)k*N+j];
                        }
                }
        }
        break;
    }
    free(Bt);
}
/* PAR-END */

int main(int argc, char **argv) { return bench_main(argc, argv, "openmp", matmul); }
