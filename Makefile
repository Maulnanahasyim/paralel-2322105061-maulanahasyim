# Makefile - Perkalian Matriks Paralel (Pthreads vs OpenMP)
# Pemakaian:
#   make            build semua (serial, pthreads, openmp)
#   make test       verifikasi correctness (selftest 10x10 + banding dgn referensi)
#   make bench      benchmark lengkap -> results/results.csv
#   make analyze    tabel + grafik dari results.csv
#   make report NAMA="Nama" NIM="123456"   bikin report/laporan.pdf
#   make clean
CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -std=gnu11
LDLIBS  = -lm
BIN     = bin

all: $(BIN)/serial $(BIN)/pthreads $(BIN)/openmp

$(BIN):
	mkdir -p $(BIN)

$(BIN)/serial: src/serial.c src/common.h | $(BIN)
	$(CC) $(CFLAGS) $< -o $@ $(LDLIBS)

$(BIN)/pthreads: src/pthreads.c src/common.h | $(BIN)
	$(CC) $(CFLAGS) -pthread $< -o $@ $(LDLIBS)

$(BIN)/openmp: src/openmp.c src/common.h | $(BIN)
	$(CC) $(CFLAGS) -fopenmp $< -o $@ $(LDLIBS)

# Verifikasi: tiap program menjalankan selftest 10x10 lalu membandingkan
# hasil N=1000 dengan referensi (kolom terakhir CSV: verified=1).
test: all
	@mkdir -p results
	@for v in ijk ikj transpose tiled; do \
	  for t in 1 2 4 8; do \
	    $(BIN)/pthreads 1000 $$t $$v 1 2>/dev/null | awk -F, -v t=$$t -v v=$$v '{print "pthreads",v,"T="t,"verified="$$7}'; \
	    $(BIN)/openmp   1000 $$t $$v 1 2>/dev/null | awk -F, -v t=$$t -v v=$$v '{print "openmp  ",v,"T="t,"verified="$$7}'; \
	  done; \
	  $(BIN)/serial 1000 1 $$v 1 2>/dev/null | awk -F, -v v=$$v '{print "serial  ",v,"T=1","verified="$$7}'; \
	done | tee results/verification.txt

bench: all
	python3 scripts/run_bench.py

analyze:
	python3 scripts/analyze.py

report: analyze
	python3 scripts/make_report.py --nama "$(NAMA)" --nim "$(NIM)"

clean:
	rm -rf $(BIN)

.PHONY: all test bench analyze report clean
