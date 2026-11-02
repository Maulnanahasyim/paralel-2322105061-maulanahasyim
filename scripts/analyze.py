#!/usr/bin/env python3
"""analyze.py - Olah results/results.csv menjadi tabel ringkasan & grafik.

Keluaran (folder results/):
  summary.csv            mean, std, speedup, efficiency tiap konfigurasi
  fig_time.png           waktu eksekusi vs thread
  fig_speedup.png        speedup vs thread (+ garis ideal)
  fig_efficiency.png     efficiency vs thread
  fig_cache.png          perbandingan varian kernel pada serial (cache locality)
Speedup = T_serial(varian sama, N sama) / T_paralel ; Efficiency = Speedup / T.
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")

def load():
    df = pd.read_csv(os.path.join(RES, "results.csv"))
    g = df.groupby(["approach", "variant", "N", "threads"])["seconds"]
    s = g.agg(["mean", "std", "min", "count"]).reset_index()
    s["std"] = s["std"].fillna(0.0)
    ser = s[s.approach == "serial"].set_index(["variant", "N"])["mean"]
    s["t_serial"] = [ser.get((v, n), float("nan")) for v, n in zip(s.variant, s.N)]
    s["speedup"] = s.t_serial / s["mean"]
    s["efficiency"] = s.speedup / s.threads
    ver = df.groupby(["approach", "variant", "N", "threads"])["verified"].min().reset_index()
    s = s.merge(ver, on=["approach", "variant", "N", "threads"])
    return df, s

COL = {"pthreads": "tab:blue", "openmp": "tab:red"}
VARS = ["ijk", "ikj", "transpose", "tiled"]

def grid(s, n, ycol, ylabel, fname, ideal=False, title=""):
    fig, axes = plt.subplots(2, 2, figsize=(9, 7))
    for ax, v in zip(axes.flat, VARS):
        d = s[(s.N == n) & (s.variant == v)]
        for ap in ("pthreads", "openmp"):
            x = d[d.approach == ap].sort_values("threads")
            if len(x): ax.errorbar(x.threads, x[ycol], yerr=x["std"] if ycol == "mean" else None,
                                   marker="o", capsize=3, label=ap, color=COL[ap])
        if ideal:
            ts = sorted(d[d.approach != "serial"].threads.unique())
            if ts: ax.plot(ts, ts if ycol == "speedup" else [1] * len(ts), "k--", alpha=.5, label="ideal")
        ax.set_title(f"varian {v}"); ax.set_xlabel("jumlah thread"); ax.set_ylabel(ylabel)
        ax.set_xscale("log", base=2); ax.set_xticks(sorted(d.threads.unique())); ax.set_xticklabels(sorted(d.threads.unique()))
        ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.suptitle(f"{title} (N={n})"); fig.tight_layout()
    fig.savefig(os.path.join(RES, fname), dpi=150); plt.close(fig)

def main():
    df, s = load()
    s.to_csv(os.path.join(RES, "summary.csv"), index=False)
    n0 = int(s.N.min())  # ukuran utama untuk grafik
    grid(s, n0, "mean", "waktu (detik)", "fig_time.png", title="Waktu eksekusi")
    grid(s, n0, "speedup", "speedup", "fig_speedup.png", ideal=True, title="Speedup")
    grid(s, n0, "efficiency", "efficiency", "fig_efficiency.png", ideal=True, title="Efficiency")
    # cache locality: serial per varian
    ser = s[s.approach == "serial"]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    sizes = sorted(ser.N.unique()); w = 0.8 / max(1, len(sizes))
    for i, n in enumerate(sizes):
        d = ser[ser.N == n].set_index("variant").reindex(VARS)
        ax.bar([j + i * w for j in range(4)], d["mean"], w, yerr=d["std"], capsize=3, label=f"N={n}")
    ax.set_xticks([j + w * (len(sizes) - 1) / 2 for j in range(4)]); ax.set_xticklabels(VARS)
    ax.set_ylabel("waktu serial (detik)"); ax.set_title("Efek cache locality (serial)")
    ax.legend(); ax.grid(axis="y", alpha=.3); fig.tight_layout()
    fig.savefig(os.path.join(RES, "fig_cache.png"), dpi=150); plt.close(fig)
    bad = s[s.verified == 0]
    print("Verifikasi:", "SEMUA BENAR" if bad.empty else f"ADA YANG SALAH:\n{bad}")
    print("Ringkasan ->", os.path.join(RES, "summary.csv"))

if __name__ == "__main__":
    main()
