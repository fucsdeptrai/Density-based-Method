#!/usr/bin/env python3
"""Ảnh zoom cụ thể — cho thấy hotspot thật ở cấu hình chạy được.

Vì sao cần nhóm ảnh này: các biểu đồ tổng hợp (đường cong, heatmap) chỉ nói
"có bao nhiêu cụm", không cho thấy các cụm **ở đâu** và có tách được không.

Xuất vào outputs/zoom/:
    z1_brooklyn_cum.png      Brooklyn, 10 cụm lớn nhất, có nhãn tọa độ
    z2_mat_do.png            Cùng khu vực, 3 mức mật độ — thấy cụm dính vào nhau
    z3_manhattan_zoom.png    Manhattan thu nhỏ 20k điểm, eps 70m
    z4_queens_cum.png        Queens
    z5_tiem_dung.png         Downtown Brooklyn, từng điểm đón vẽ từng điểm
    ban_do_<khu>.html        bản đồ folium (có đường phố thật) để mở riêng
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hotspot import FilterSpec, cluster_table, filter_pickups, load_dataset, run_dbscan
from hotspot.figures import (
    CLUSTER_COLORS,
    cluster_color,
    draw_boroughs,
    load_borough_rings,
    projection_origin,
)

OUT = ROOT / "outputs" / "zoom"
OUT.mkdir(parents=True, exist_ok=True)

MIN_PTS = 15
# Cấu hình CHẠY ĐƯỢC, lấy từ notebook 04:
#   eps 60-80 m, dưới ~40k điểm, bỏ Manhattan
BEST_EPS = 70
POINTS = 30_000
SEED = 42

DASH = (-0.05, 0.05)


def frame(ax, rings, zoom=None, title="", subtitle=""):
    draw_boroughs(ax, rings)
    if zoom:
        ax.set_xlim(zoom[0], zoom[1])
        ax.set_ylim(zoom[2], zoom[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor("#bbbbbb")
    if title:
        ax.set_title(title, fontsize=12.5, weight="bold", pad=10)
    if subtitle:
        ax.text(0.5, -0.012, subtitle, transform=ax.transAxes, ha="center",
                va="top", fontsize=9, color="#555555")


def m2km(v_m):
    return v_m / 1000.0


def bounds_of(df, pad_m=700, q=1.0):
    """Khung nhin lay theo phan vi du lieu — KHONG doan tay tung con so.

    Doan tay da lam anh Brooklyn lech sang Manhattan o lan ve truoc, nen
    o day luong tu chinh du lieu.

    `q` la phan vi cat o hai dau. Polygon Brooklyn keo dai xuong Coney
    Island, nen dung phan vi de cat phan vo day.
    """
    x_lo, x_hi = np.percentile(df["x_m"], [q, 100 - q])
    y_lo, y_hi = np.percentile(df["y_m"], [q, 100 - q])
    return (x_lo - pad_m, x_hi + pad_m, y_lo - pad_m, y_hi + pad_m)


def scale_bar(ax, length_m=2000):
    """Thang do giup nguoi xem do duoc tam ly cach."""
    if length_m < 1000:
        label = f"{length_m} m"
    else:
        label = f"{length_m / 1000:g} km"
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bx = x0 + (x1 - x0) * 0.06
    by = y0 + (y1 - y0) * 0.05
    ax.plot([bx, bx + length_m], [by, by], color="black", lw=3.5,
            solid_capstyle="butt", zorder=20)
    ax.text(bx + length_m / 2, by + (y1 - y0) * 0.015, label,
            ha="center", va="bottom", fontsize=10, weight="bold", zorder=20,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))


# --------------------------------------------------------------------------- #
def z1_brooklyn(data, rings, window):
    bk = window[window["borough"] == "Brooklyn"]
    sample = bk.sample(min(POINTS, len(bk)), random_state=SEED)
    res = run_dbscan(sample, BEST_EPS, MIN_PTS)
    table = cluster_table(sample, res)
    n = len(sample)
    big = table[table["pickup_count"] >= 0.01 * n]

    fig, ax = plt.subplots(figsize=(13, 12))
    frame(ax, rings,
          zoom=bounds_of(sample, q=4.0),
          title=f"Brooklyn — {len(sample):,} điểm · eps={BEST_EPS} m · MinPts={MIN_PTS}",
          subtitle=f"{res.n_clusters} cụm · cụm lớn nhất chiếm "
                   f"{100 * table['pickup_count'].iloc[0] / table['pickup_count'].sum():.0f}% dữ liệu")

    lab = sample.assign(_l=res.labels)
    ax.scatter(lab[lab._l == -1]["x_m"], lab[lab._l == -1]["y_m"],
               s=0.8, c="#9aa0a6", alpha=0.20, linewidths=0, zorder=3)
    for cid in res.cluster_labels:
        sel = lab[lab._l == cid]
        ax.scatter(sel["x_m"], sel["y_m"], s=1.6, c=cluster_color(cid),
                   alpha=0.85, linewidths=0, zorder=4)

    for _, row in big.iterrows():
        cid = int(row["cluster_id"])
        ax.scatter(row["centroid_x_m"], row["centroid_y_m"], marker="*", s=260,
                   c=cluster_color(cid), edgecolors="black", linewidths=0.8, zorder=6)
        ax.annotate(
            f"#{cid}  {int(row['pickup_count']):,} chuyến",
            (row["centroid_x_m"], row["centroid_y_m"]),
            textcoords="offset points", xytext=(15, 11), fontsize=10.5, weight="bold",
            zorder=7, bbox=dict(boxstyle="round,pad=0.32", fc="white",
                                ec=cluster_color(cid), lw=1.6, alpha=0.96),
            arrowprops=dict(arrowstyle="-", color=cluster_color(cid), lw=1.6),
        )
    ax.text(0.015, 0.985, "★ trọng tâm cụm", transform=ax.transAxes, va="top",
            fontsize=11, color="#333333",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc", alpha=0.9))
    scale_bar(ax)
    fig.tight_layout()
    fig.savefig(OUT / "z1_brooklyn_cum.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  z1_brooklyn_cum.png — {res.n_clusters} cụm, {len(big)} cụm ≥1%")
    return sample, res


def z2_density(data, rings, window):
    """Cùng khu vực, 3 mức mật độ. Đây là ảnh chứng minh nguyên nhân gốc."""
    bk = window[window["borough"] == "Brooklyn"]
    levels = [10_000, 30_000, min(120_000, len(bk))]
    zoom = bounds_of(bk, q=4.0)  # CHUNG mot khung nhin cho ca 3 panel
    fig, axes = plt.subplots(1, len(levels), figsize=(8.5 * len(levels), 10.5))

    print("\n  Mat do trong cung khu vuc Brooklyn:")
    for ax, n in zip(axes, levels):
        sample = bk.sample(min(n, len(bk)), random_state=SEED)
        res = run_dbscan(sample, BEST_EPS, MIN_PTS)
        table = cluster_table(sample, res)
        top = (100 * table["pickup_count"].iloc[0] / table["pickup_count"].sum()
               if table["pickup_count"].sum() else 100.0)
        useful = int((table["pickup_count"] >= 0.01 * len(sample)).sum())

        lab = sample.assign(_l=res.labels)
        frame(ax, rings, zoom=zoom,
              title=f"{len(sample):,} điểm",
              subtitle=f"{res.n_clusters} cụm · cụm lớn nhất {top:.0f}% · {useful} cụm ≥1%")
        ax.scatter(lab[lab._l == -1]["x_m"], lab[lab._l == -1]["y_m"],
                   s=0.7, c="#9aa0a6", alpha=0.18, linewidths=0, zorder=3)
        for cid in res.cluster_labels:
            sel = lab[lab._l == cid]
            ax.scatter(sel["x_m"], sel["y_m"], s=1.3, c=cluster_color(cid),
                       alpha=0.85, linewidths=0, zorder=4)
        print(f"    {len(sample):>7,} diem: {res.n_clusters:>4} cum, top {top:5.1f}%, "
              f"{useful:>3} cum >=1%")

    fig.suptitle(f"Cùng khu vực Brooklyn, cùng eps={BEST_EPS} m — chỉ khác số điểm đưa vào",
                 fontsize=14, weight="bold")
    plt.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(OUT / "z2_mat_do.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  z2_mat_do.png")


def z3_manhattan(data, rings, window):
    mn = window[window["borough"] == "Manhattan"]
    sample = mn.sample(min(POINTS, len(mn)), random_state=SEED)
    res = run_dbscan(sample, BEST_EPS, MIN_PTS)
    table = cluster_table(sample, res)
    top = 100 * table["pickup_count"].iloc[0] / table["pickup_count"].sum()

    fig, ax = plt.subplots(figsize=(11, 14))
    frame(ax, rings, zoom=bounds_of(sample, q=1.0),
          title=f"Manhattan thu nho — {len(sample):,} điểm (từ 165.707) · eps={BEST_EPS} m",
          subtitle=f"{res.n_clusters} cụm · cụm lớn nhất {top:.0f}% — vẫn là MỘT khối")
    lab = sample.assign(_l=res.labels)
    ax.scatter(lab[lab._l == -1]["x_m"], lab[lab._l == -1]["y_m"],
               s=0.8, c="#9aa0a6", alpha=0.20, linewidths=0, zorder=3)
    for cid in res.cluster_labels:
        sel = lab[lab._l == cid]
        ax.scatter(sel["x_m"], sel["y_m"], s=1.5, c=cluster_color(cid),
                   alpha=0.85, linewidths=0, zorder=4)
    fig.tight_layout()
    fig.savefig(OUT / "z3_manhattan_zoom.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  z3_manhattan_zoom.png — {len(sample):,} diem, {res.n_clusters} cum, top {top:.0f}%")


def z4_queens(data, rings, window):
    q = window[window["borough"] == "Queens"]
    if len(q) < 2000:
        print("  [bo qua] Queens qua it diem")
        return
    sample = q.sample(min(POINTS, len(q)), random_state=SEED)
    res = run_dbscan(sample, BEST_EPS, MIN_PTS)
    table = cluster_table(sample, res)
    big = table[table["pickup_count"] >= 0.01 * len(sample)]

    fig, ax = plt.subplots(figsize=(13, 12))
    frame(ax, rings, zoom=bounds_of(sample, q=3.0),
          title=f"Queens — {len(sample):,} điểm · eps={BEST_EPS} m",
          subtitle=f"{res.n_clusters} cụm · cụm lớn nhất "
                   f"{100 * table['pickup_count'].iloc[0] / table['pickup_count'].sum():.0f}%"
                   f" · {len(big)} cụm ≥1%")
    lab = sample.assign(_l=res.labels)
    ax.scatter(lab[lab._l == -1]["x_m"], lab[lab._l == -1]["y_m"],
               s=0.8, c="#9aa0a6", alpha=0.20, linewidths=0, zorder=3)
    for cid in res.cluster_labels:
        sel = lab[lab._l == cid]
        ax.scatter(sel["x_m"], sel["y_m"], s=1.6, c=cluster_color(cid),
                   alpha=0.85, linewidths=0, zorder=4)
    for _, row in big.iterrows():
        cid = int(row["cluster_id"])
        ax.scatter(row["centroid_x_m"], row["centroid_y_m"], marker="*", s=230,
                   c=cluster_color(cid), edgecolors="black", linewidths=0.8, zorder=6)
        ax.annotate(f"#{cid}  {int(row['pickup_count']):,}",
                    (row["centroid_x_m"], row["centroid_y_m"]),
                    textcoords="offset points", xytext=(14, 10), fontsize=10, weight="bold",
                    zorder=7,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=cluster_color(cid),
                              lw=1.5, alpha=0.96),
                    arrowprops=dict(arrowstyle="-", color=cluster_color(cid), lw=1.5))
    fig.tight_layout()
    fig.savefig(OUT / "z4_queens_cum.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  z4_queens_cum.png — {res.n_clusters} cụm, {len(big)} cụm ≥1%")


def z5_individual(data, rings, window):
    """Một cụm duy nhất, vẽ TỪNG điểm — thấy rõ chúng là chuyến đón thật."""
    bk = window[window["borough"] == "Brooklyn"]
    sample = bk.sample(min(POINTS, len(bk)), random_state=SEED)
    res = run_dbscan(sample, BEST_EPS, MIN_PTS)
    table = cluster_table(sample, res)
    biggest = int(table["cluster_id"].iloc[0])

    sel_mask = res.labels == biggest
    sel = sample[sel_mask]
    cx, cy = float(sel["x_m"].mean()), float(sel["y_m"].mean())
    half = 420  # ban kin ~420 m -> nhin thay tung diem

    fig, ax = plt.subplots(figsize=(11, 11))
    # Ve nen TRUOC, va chi ve o vung zoom. o day khong dung frame() vi
    # frame() ve nen len tren (zorder=1) ma diem cung zorder=4 -> OK,
    # nhung nen mau nuoc lam cham bi chim khi nho khung lai.
    draw_boroughs(ax, rings)
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor("#bbbbbb")
    ax.set_title(f"Chi tiết cụm #{biggest} — {len(sel):,} chuyến trong bán kính ~{half} m",
                 fontsize=12.5, weight="bold", pad=10)
    ax.text(0.5, -0.012, "Mỗi chấm là MỘT chuyến đón thật. Khoảng trống = nơi không có khách.",
            transform=ax.transAxes, ha="center", va="top", fontsize=9.5, color="#555555")

    # Vien trang day duat giup cham noi bat tren nen xanh
    ax.scatter(sel["x_m"], sel["y_m"], s=15, c=cluster_color(biggest),
               alpha=0.95, linewidths=0.5, edgecolors="white", zorder=6)
    scale_bar(ax, length_m=100)
    ax.annotate(f"trọng tâm\n{len(sel):,} chuyến", (cx, cy),
                textcoords="offset points", xytext=(14, 14), fontsize=11, weight="bold",
                zorder=8,
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=cluster_color(biggest), lw=1.8),
                arrowprops=dict(arrowstyle="->", color=cluster_color(biggest), lw=1.8))
    fig.tight_layout()
    fig.savefig(OUT / "z5_tiem_dung.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  z5_tiem_dung.png — cụm #{biggest}: {len(sel):,} diem trong {2*half} m")


def z6_folium(data, window):
    """Bản đồ folium có đường phố thật — mở bằng trình duyệt."""
    from hotspot.map_layers import build_dbscan_map

    for borough, eps in [("Brooklyn", 60), ("Queens", 60), ("Manhattan", 70)]:
        d = window[window["borough"] == borough]
        if len(d) < 2000:
            continue
        s = d.sample(min(POINTS, len(d)), random_state=SEED)
        res = run_dbscan(s, eps, MIN_PTS)
        m = build_dbscan_map(s, res, max_points_per_cluster=900, max_noise_points=2500)
        path = OUT / f"ban_do_{borough}.html"
        m.save(path)
        print(f"  {path.name} — {res.n_clusters} cụm ({path.stat().st_size / 1e6:.1f} MB)")


def main():
    print("=" * 68)
    print("ANH ZOOM CU THE")
    print("=" * 68)

    df = load_dataset("full")
    lat0, lon0 = projection_origin(ROOT / "outputs" / "preprocess_report.json")
    rings = load_borough_rings(ROOT / "data" / "raw", lat0, lon0)
    print(f"Cau hinh: eps={BEST_EPS} m, MinPts={MIN_PTS}, toi da {POINTS:,} diem/khu vuc")

    window = filter_pickups(df, FilterSpec(weekdays=(0, 1, 2, 3, 4), hour_start=18, hour_end=20))
    print(f"Ca diem Th 2-6, 18-20h: {len(window):,} diem")
    print()

    z1_brooklyn(df, rings, window)
    z2_density(df, rings, window)
    z3_manhattan(df, rings, window)
    z4_queens(df, rings, window)
    z5_individual(df, rings, window)
    z6_folium(df, window)

    print()
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name:26s} {p.stat().st_size / 1e6:6.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())