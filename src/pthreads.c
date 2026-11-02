/*
 * pthreads.c - Perkalian matriks paralel dengan POSIX Threads (eksplisit).
 *
 * Strategi:
 *  - Domain decomposition per BARIS C: thread t mengerjakan blok baris
 *    [r0, r1). Sisa pembagian (N % T) disebar 1 baris ke thread awal
 *    supaya beban seimbang.
 *  - A, B, Bt: hanya dibaca (shared read-only). C: tiap thread menulis
 *    baris yang berbeda -> TIDAK ada data race, TIDAK perlu mutex.
 *  - Satu-satunya sinkronisasi: pthread_join (barrier implisit di akhir).
 *  - Transpose B (varian transpose) dikerjakan serial sebelum thread dibuat.
 */
#include <pthread.h>
#include "common.h"

/* PAR-BEGIN (dipakai script untuk menghitung LOC lapisan paralel) */
typedef struct {
    int v, N, r0, r1;
    const double *A, *B, *Bt;
    double *C;
} task_t;

/* Fungsi yang dijalankan tiap thread */
static void *worker(void *arg) {
    task_t *t = (task_t *)arg;
    mm_rows(t->v, t->A, t->B, t->Bt, t->C, t->N, t->r0, t->r1);
    return NULL;
}

static void matmul(int v, const double *A, const double *B, double *C, int N, int T) {
    double *Bt = NULL;
    if (v == V_TR) { Bt = alloc_mat(N); transpose_mat(B, Bt, N); }
    if (T > N) T = N;                       /* jangan lebih banyak thread dari baris */

    pthread_t *th = malloc(sizeof(pthread_t) * T);
    task_t *tasks = malloc(sizeof(task_t) * T);
    int base = N / T, extra = N % T, row = 0;

    for (int t = 0; t < T; t++) {           /* bagi workload + buat thread */
        int cnt = base + (t < extra ? 1 : 0);
        tasks[t] = (task_t){v, N, row, row + cnt, A, B, Bt, C};
        row += cnt;
        if (pthread_create(&th[t], NULL, worker, &tasks[t]) != 0) {
            fprintf(stderr, "pthread_create gagal\n"); exit(4);
        }
    }
    for (int t = 0; t < T; t++)             /* tunggu semua selesai */
        pthread_join(th[t], NULL);

    free(th); free(tasks); free(Bt);
}
/* PAR-END */

int main(int argc, char **argv) { return bench_main(argc, argv, "pthreads", matmul); }
