/*
 * serial.c - Baseline SERIAL perkalian matriks C = A x B.
 * Dipakai sebagai acuan waktu (T_serial) dan acuan kebenaran.
 * Argumen THREADS diabaikan (selalu 1 thread).
 */
#include "common.h"

static void matmul(int v, const double *A, const double *B, double *C, int N, int T) {
    (void)T;
    double *Bt = NULL;
    if (v == V_TR) { Bt = alloc_mat(N); transpose_mat(B, Bt, N); }
    mm_rows(v, A, B, Bt, C, N, 0, N);
    free(Bt);
}

int main(int argc, char **argv) { return bench_main(argc, argv, "serial", matmul); }
