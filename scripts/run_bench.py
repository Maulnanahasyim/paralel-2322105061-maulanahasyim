#!/usr/bin/env python3
"""run_bench.py - Benchmark sistematis serial / pthreads / openmp.

Menjalankan semua kombinasi (pendekatan x varian x N x thread), tiap
konfigurasi diulang --reps kali, lalu menyimpan ke results/results.csv.
Informasi mesin disimpan ke results/env.json (dipakai di laporan).

Contoh:  python3 scripts/run_bench.py --sizes 1000 1500 --reps 5
         python3 scripts/run_bench.py --quick      (cepat, untuk uji coba)
"""
import argparse, json, os, platform, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""

def collect_env():
    lscpu = sh("lscpu")
    def g(key):
        m = re.search(rf"^{key}:\s*(.+)$", lscpu, re.M)
        return m.group(1).strip() if m else "?"
    logical = os.cpu_count()
    try:
        tps, cps, sockets = int(g("Thread\\(s\\) per core")), int(g("Core\\(s\\) per socket")), int(g("Socket\\(s\\)"))
        physical = cps * sockets
    except ValueError:
        tps, physical = 1, logical
    return {
        "cpu": g("Model name"), "logical_cpus": logical, "physical_cores": physical,
        "threads_per_core": tps, "l1d": g("L1d cache"), "l2": g("L2 cache"), "l3": g("L3 cache"),
        "os": platform.platform(), "gcc": sh("gcc --version | head -1"),
        "mem": sh("grep MemTotal /proc/meminfo | awk '{printf \"%.1f GB\", $2/1048576}'"),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 1500])
    ap.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4, 8])
    ap.add_argument("--variants", nargs="+", default=["ijk", "ikj", "transpose", "tiled"])
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--quick", action="store_true", help="N=1000, 3 reps")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "results.csv"))
    a = ap.parse_args()
    if a.quick: a.sizes, a.reps = [1000], 3

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    env = collect_env(); env.update(reps=a.reps, sizes=a.sizes, threads=a.threads)
    json.dump(env, open(os.path.join(ROOT, "results", "env.json"), "w"), indent=2)
    print("Mesin:", env["cpu"], f"| {env['physical_cores']} core fisik / {env['logical_cpus']} logical")

    configs = []
    for n in a.sizes:
        for v in a.variants:
            configs.append(("serial", v, n, 1))
            for ap_ in ("pthreads", "openmp"):
                for t in a.threads: configs.append((ap_, v, n, t))
    with open(a.out, "w") as f:
        f.write("approach,variant,N,threads,rep,seconds,verified\n")
        t0 = time.time()
        for i, (prog, v, n, t) in enumerate(configs, 1):
            r = subprocess.run([os.path.join(ROOT, "bin", prog), str(n), str(t), v, str(a.reps)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit(f"GAGAL {prog} {v} N={n} T={t}: {r.stderr}")
            f.write(r.stdout); f.flush()
            print(f"[{i}/{len(configs)}] {prog:8s} {v:9s} N={n} T={t}  ({time.time()-t0:.0f}s)", flush=True)
    print("Selesai ->", a.out)

if __name__ == "__main__":
    main()
