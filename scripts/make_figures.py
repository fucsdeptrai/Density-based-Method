#!/usr/bin/env python3
"""Sinh tat ca hinh bam va animation cho bai thuyet trinh.

Chay:
    python scripts/make_figures.py

Xuat vao outputs/figures/:
    fig1_eps_sweep.png        anh tinh 8 gia tri eps — anh chinh cho slide
    fig2_eps_sweep.gif        animation quet eps 30 -> 300 m
    fig3_hotspot_ca_diem.png  ban do lon, co nhan top 3 cum
    fig4_tradeoff.png         so cum / %nhieu / %cum-lon-nhat theo eps
    fig5_borough.png          phan bo chuyen theo quan
    bang_hotspot.csv          bang xep rank cum (kem so lieu de dan vao slide)

Khong can mang: nen la polygon 5 quan tu nyc_boroughs.geojson.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")  # headless: khong mo cua so

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hotspot import FilterSpec, cluster_table, filter_pickups, load_dataset, run_dbscan
from hotspot.figures import (
    animate_eps_sweep,
    load_borough_rings,
    plot_borough_distribution,
    plot_eps_sweep,
    plot_hotspot_map,
    plot_parameter_tradeoff,
    projection_origin,
)

OUT = ROOT / "outputs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "data" / "raw"

MIN_SAMPLES = 15
DEFAULT_EPS_M = 100
EPS_LIST = [30, 50, 75, 100, 150, 200, 250, 300]
GIF_EPS = [30, 45, 60, 80, 100, 130, 170, 220, 300]
GIF_POINTS = 12_000
GRID_POINTS = 120_000

# Khung zoom (met) cho luoi quet: loi Manhattan + phan dong cua Brooklyn/Queens.
# Tinh tu toa do cua chinh dataset de khong do ma may phai nhin.
NYC_CORE_M = (-14_000, 22_000, -11_000, 13_000)


def banner(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def main() -> int:
    banner("1/5  Nap du lieu")
    df = load_dataset("full")

    # Polygon nen phai dung CHUNG he toa do met voi du lieu. lay lat0/lon0
    # tu bao cao preprocessing — neu tu doan, nen se nam ngoai khung hinh.
    lat0, lon0 = projection_origin(ROOT / "outputs" / "preprocess_report.json")
    rings = load_borough_rings(DATA, lat0, lon0)
    print(f"  {len(df):,} diem | {len(rings)} quan: {', '.join(rings)}")
    print(f"  tam phieu lat0={lat0:.5f} lon0={lon0:.5f} (lay tu bao cao preprocessing)")

    # Kiem chung: polygon phai nam trong cung dai do voi du lieu
    all_ring = np.vstack([r for polys in rings.values() for r in polys])
    inside = (
        df["x_m"].min() - 6000 < all_ring[:, 0].min()
        and all_ring[:, 0].max() < df["x_m"].max() + 6000
    )
    print(f"  kiem chung nen: polygon x [{all_ring[:, 0].min():,.0f} .. "
          f"{all_ring[:, 0].max():,.0f}] | du lieu x [{df['x_m'].min():,.0f} .. "
          f"{df['x_m'].max():,.0f}] -> {'OK' if inside else 'SAI HE TOA DO'}")

    # Ca dung chung cho tat ca hinh: thu Bay 17-19h (gio cao diem)
    spec = FilterSpec(weekdays=(5,), hour_start=17, hour_end=19)
    sub = filter_pickups(df, spec)
    print(f"  {spec.describe()}: {len(sub):,} diem")

    # Ca cuoi tuan chi co ~86k diem — khong du de lay 120k mau
    n_grid = min(GRID_POINTS, len(sub))
    n_gif = min(GIF_POINTS, len(sub))
    rng = np.random.default_rng(42)
    grid_df = sub.iloc[np.sort(rng.choice(len(sub), n_grid, replace=False))]
    gif_df = sub.iloc[np.sort(rng.choice(len(sub), n_gif, replace=False))]
    print(f"  anh luoi lay {len(grid_df):,} diem | GIF lay {len(gif_df):,} diem")

    # ------------------------------------------------------------------ #
    banner("2/5  Hinh 1 — luoi quet eps")
    # Zoom vao lõi NYC (Manhattan + Brooklyn + Queens) de panel lon va de thay
    # cum tach/dinh. Toan bo 5 quan lam hinh 1 rieng.
    fig, sweep_res = plot_eps_sweep(
        grid_df,
        EPS_LIST,
        MIN_SAMPLES,
        rings,
        subtitle=f"Ca điểm Thứ 7 17–19h · MinPts = {MIN_SAMPLES} · "
        f"{len(grid_df):,} điểm · xám = nhiễu bị loại · cùng dữ liệu, chỉ đổi eps",
        ncols=4,
        focus=NYC_CORE_M,
    )
    path = OUT / "fig1_eps_sweep.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {path.name}")

    # ------------------------------------------------------------------ #
    banner("3/5  Hinh 2 — animation quet eps (GIF)")
    gif_path = OUT / "fig2_eps_sweep.gif"
    animate_eps_sweep(
        gif_df, GIF_EPS, MIN_SAMPLES, rings, gif_path, fps=2, dpi=100
    )
    size_mb = gif_path.stat().st_size / 1e6
    print(f"  -> {gif_path.name} ({size_mb:.1f} MB)")

    # ------------------------------------------------------------------ #
    banner("4/5  Hinh 3 — ban do lon ca diem + bang xep rank")
    res = run_dbscan(grid_df, DEFAULT_EPS_M, MIN_SAMPLES)
    print(f"  eps={DEFAULT_EPS_M} m, MinPts={MIN_SAMPLES}: "
          f"{res.n_clusters} cum, {res.noise_pct:.1f}% nhieu")

    fig = plot_hotspot_map(
        grid_df,
        res,
        rings,
        title=f"Hotspot đón khách — ca điểm Thứ 7 17–19h (eps={DEFAULT_EPS_M} m, MinPts={MIN_SAMPLES})",
        subtitle=f"{res.n_clusters} cụm · {res.noise_pct:.1f}% nhiễu · "
        f"ngôi sao = trọng tâm cụm · số trên nhãn = số chuyến thật",
        annotate_top=3,
    )
    path = OUT / "fig3_hotspot_ca_diem.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {path.name}")

    table = cluster_table(grid_df, res)
    csv_path = OUT / "bang_hotspot.csv"
    table.round(4).to_csv(csv_path, index=False)
    print(f"  -> {csv_path.name} ({len(table)} cum)")
    print()
    print(table.head(8)[["rank", "cluster_id", "pickup_count", "pickup_per_km2"]]
          .round(2).to_string(index=False))

    # ------------------------------------------------------------------ #
    banner("5/5  Hinh 4 + 5 — doi thuan doi tham so va phan bo theo quan")
    fig, data = plot_parameter_tradeoff(
        grid_df, EPS_LIST, MIN_SAMPLES, min_pts_list=[10, 15, 30]
    )
    path = OUT / "fig4_tradeoff.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {path.name}")
    print()
    print(data[data.MinPts == MIN_SAMPLES].to_string(index=False))

    fig, counts = plot_borough_distribution(sub)
    path = OUT / "fig5_borough.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {path.name}")
    print()
    print(counts.to_string())

    banner("Xong")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name:28s} {p.stat().st_size / 1e6:6.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())