#!/usr/bin/env python3
"""Draw the fixed 1 km Manhattan grid and the two train-selected cells."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Polygon as PlotPolygon, Rectangle
from shapely.geometry import box, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from preprocess import EARTH_R, to_metric  # noqa: E402

OUT = ROOT / "docs"
OUT.mkdir(parents=True, exist_ok=True)
ORIGIN = json.loads((ROOT / "outputs" / "preprocess_report.json").read_text())["full"]["projection"]
LAT0 = np.radians(ORIGIN["lat0"])
LON0 = np.radians(ORIGIN["lon0"])


def inverse(x_m: float, y_m: float) -> tuple[float, float]:
    """Inverse of the spherical azimuthal equidistant projection in preprocess.py."""
    rho = np.hypot(x_m, y_m)
    if rho == 0:
        return ORIGIN["lat0"], ORIGIN["lon0"]
    c = rho / EARTH_R
    lat = np.arcsin(np.cos(c) * np.sin(LAT0) + y_m * np.sin(c) * np.cos(LAT0) / rho)
    lon = LON0 + np.arctan2(
        x_m * np.sin(c),
        rho * np.cos(LAT0) * np.cos(c) - y_m * np.sin(LAT0) * np.sin(c),
    )
    return float(np.degrees(lat)), float(np.degrees(lon))


def project(lon, lat, z=None):
    lon, lat = np.atleast_1d(lon), np.atleast_1d(lat)
    xy = to_metric(lat, lon, ORIGIN["lat0"], ORIGIN["lon0"]) / 1000
    return xy[:, 0], xy[:, 1]


def draw_shape(ax, geom, *, facecolor: str, edgecolor: str, lw: float, zorder: int):
    polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polygons:
        if poly.is_empty:
            continue
        ax.add_patch(PlotPolygon(
            np.asarray(poly.exterior.coords), closed=True,
            facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, zorder=zorder,
        ))


def card(fig, y: float, title: str, color: str, cell: tuple[int, int], description: str):
    x, width, height = 0.70, 0.265, 0.235
    fig.add_artist(FancyBboxPatch(
        (x, y), width, height, transform=fig.transFigure,
        boxstyle="round,pad=0.012,rounding_size=0.015",
        linewidth=1.2, edgecolor="#d5dfe6", facecolor="white",
    ))
    fig.text(x + 0.018, y + 0.184, title, fontsize=17, weight="bold", color=color)
    fig.text(x + 0.018, y + 0.142, description, fontsize=10, color="#475569")
    ix, iy = cell
    center = inverse((ix + 0.5) * 1000, (iy + 0.5) * 1000)
    fig.text(x + 0.018, y + 0.097, f"Ô lưới: ({ix}, {iy}) · 1 × 1 km", fontsize=11, color="#172b3a")
    fig.text(x + 0.018, y + 0.058, f"Tâm: {center[0]:.6f}, {center[1]:.6f}", fontsize=11, color="#172b3a")
    fig.text(x + 0.018, y + 0.023, "Vĩ độ, kinh độ (WGS84)", fontsize=9, color="#64748b")


def main() -> None:
    df = pd.read_parquet(
        ROOT / "data" / "processed" / "full.parquet",
        columns=["pickup_time", "borough", "month", "dow", "hour", "x_m", "y_m"],
    )
    df = df[df["borough"] == "Manhattan"].copy()
    df["ix"] = np.floor(df["x_m"] / 1000).astype("int32")
    df["iy"] = np.floor(df["y_m"] / 1000).astype("int32")
    train = df[df["month"].between(4, 6)]
    test = df[df["month"].between(7, 9)]

    def windows(frame):
        morning = frame[(frame["dow"] < 4) & frame["hour"].between(6, 8)]
        night = frame[(frame["dow"] >= 5) & frame["hour"].between(0, 2)]
        return morning, night

    morning_train, night_train = windows(train)
    morning_test, night_test = windows(test)
    morning_counts = morning_train.groupby(["ix", "iy"]).size()
    night_counts = night_train.groupby(["ix", "iy"]).size()
    west = tuple(map(int, night_counts.idxmax()))
    eligible = morning_counts[morning_counts >= 5000]
    night_share = night_counts.reindex(eligible.index, fill_value=0) / len(night_train)
    east = tuple(map(int, ((eligible / len(morning_train)) / night_share).idxmax()))

    test_morning_counts = morning_test.groupby(["ix", "iy"]).size()
    test_night_counts = night_test.groupby(["ix", "iy"]).size()
    observed = (
        len(morning_test), len(night_test),
        int(test_morning_counts[east]), int(test_morning_counts[west]),
        int(test_night_counts[east]), int(test_night_counts[west]),
    )
    expected = (165507, 56014, 7997, 6393, 446, 7604)
    if observed != expected:
        raise ValueError(f"Số liệu không khớp slide: {observed} != {expected}")

    names = [("Vùng Tây", west, "#e85d4b", "Nhiều lượt đón đêm cuối tuần nhất"),
             ("Vùng Đông", east, "#087f9e", "Tỷ lệ sáng/đêm cao nhất")]
    features = []
    for name, (ix, iy), color, _ in names:
        corners = [inverse(x, y) for x, y in [
            (ix * 1000, iy * 1000), ((ix + 1) * 1000, iy * 1000),
            ((ix + 1) * 1000, (iy + 1) * 1000), (ix * 1000, (iy + 1) * 1000),
            (ix * 1000, iy * 1000),
        ]]
        features.append({
            "type": "Feature",
            "properties": {"name": name, "grid_ix": ix, "grid_iy": iy, "area_km2": 1},
            "geometry": {"type": "Polygon", "coordinates": [[[lon, lat] for lat, lon in corners]]},
        })
    (OUT / "pattern_manhattan_grid_cells.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2)
    )

    source = json.loads((ROOT / "data" / "raw" / "nyc_boroughs.geojson").read_text())
    boroughs = {
        feature["properties"]["BoroName"]: transform(project, shape(feature["geometry"]))
        for feature in source["features"]
    }
    manhattan = boroughs["Manhattan"].simplify(0.025, preserve_topology=True)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig = plt.figure(figsize=(13.33, 7.5), facecolor="white")
    fig.text(0.045, 0.94, "Lưới 1 km² tại Manhattan", fontsize=25, weight="bold", color="#172b3a")
    fig.text(0.045, 0.90, "Chọn hai ô bằng dữ liệu tháng 4–6/2014; giữ nguyên để kiểm chứng tháng 7–9/2014",
             fontsize=11.5, color="#526477")
    ax = fig.add_axes((0.045, 0.09, 0.345, 0.77))
    ax.set_facecolor("#e8f2f7")
    for name, geom in boroughs.items():
        if name != "Manhattan":
            draw_shape(ax, geom.simplify(0.04, preserve_topology=True),
                       facecolor="#edf0ef", edgecolor="#bed0da", lw=0.6, zorder=1)
    draw_shape(ax, manhattan, facecolor="#fafafa", edgecolor="#748c99", lw=0.9, zorder=2)
    for ix in range(-7, 7):
        for iy in range(-7, 17):
            clipped = manhattan.intersection(box(ix, iy, ix + 1, iy + 1))
            if not clipped.is_empty:
                draw_shape(ax, clipped, facecolor="none", edgecolor="#b9c7cf", lw=0.45, zorder=3)
    for name, (ix, iy), color, _ in names:
        ax.add_patch(Rectangle((ix, iy), 1, 1, linewidth=2.5, edgecolor=color,
                               facecolor=color, alpha=0.55, zorder=5))
        ax.text(ix + 0.5, iy + 0.5, "T" if name == "Vùng Tây" else "Đ",
                ha="center", va="center", fontsize=14, weight="bold", color="white", zorder=6)
    draw_shape(ax, manhattan, facecolor="none", edgecolor="#547484", lw=1.1, zorder=7)
    ax.set_xlim(-7, 6.5)
    ax.set_ylim(-7, 17)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.annotate("B", xy=(5.35, 15.6), xytext=(5.35, 13.8), ha="center", va="center",
                arrowprops={"arrowstyle": "-|>", "color": "#334e60", "lw": 1.5},
                fontsize=12, weight="bold", color="#334e60")
    ax.plot([-5.8, -3.8], [-6.4, -6.4], color="#334e60", lw=2)
    ax.text(-4.8, -6.1, "2 km", ha="center", color="#334e60", fontsize=10)

    fig.text(0.418, 0.79, "Cận cảnh hai ô", fontsize=13, weight="bold", color="#334e60")
    zoom = fig.add_axes((0.405, 0.24, 0.27, 0.53))
    zoom.set_facecolor("#e8f2f7")
    for name, geom in boroughs.items():
        if name != "Manhattan":
            draw_shape(zoom, geom.simplify(0.04, preserve_topology=True),
                       facecolor="#edf0ef", edgecolor="#bed0da", lw=0.6, zorder=1)
    draw_shape(zoom, manhattan, facecolor="#fafafa", edgecolor="#748c99", lw=0.9, zorder=2)
    for ix in range(-6, 5):
        for iy in range(-4, 9):
            clipped = manhattan.intersection(box(ix, iy, ix + 1, iy + 1))
            if not clipped.is_empty:
                draw_shape(zoom, clipped, facecolor="none", edgecolor="#aebfc9", lw=0.8, zorder=3)
    for name, (ix, iy), color, _ in names:
        zoom.add_patch(Rectangle((ix, iy), 1, 1, linewidth=2.7, edgecolor=color,
                                 facecolor=color, alpha=0.55, zorder=5))
        zoom.text(ix + 0.5, iy + 0.5, "T" if name == "Vùng Tây" else "Đ",
                  ha="center", va="center", fontsize=15, weight="bold", color="white", zorder=6)
    draw_shape(zoom, manhattan, facecolor="none", edgecolor="#547484", lw=1.2, zorder=7)
    zoom.set_xlim(-4.8, 3.6)
    zoom.set_ylim(-2.4, 6.2)
    zoom.set_aspect("equal")
    zoom.set_xticks([])
    zoom.set_yticks([])
    for spine in zoom.spines.values():
        spine.set_edgecolor("#c4d3dc")

    card(fig, 0.54, "VÙNG TÂY", "#d94c3a", west, "Đêm cuối tuần, 00:00–03:00")
    card(fig, 0.25, "VÙNG ĐÔNG", "#087f9e", east, "Sáng Thứ Hai–Năm, 06:00–09:00")
    fig.text(0.70, 0.13, "Mỗi ô rộng 1 × 1 km trong hệ tọa độ mét.", fontsize=9.5, color="#526477")
    fig.text(0.70, 0.103, "Chỉ tính lượt đón thuộc Manhattan.", fontsize=9.5, color="#526477")
    fig.text(0.045, 0.035, "Nguồn: Uber NYC 2014 · Ranh giới: NYC boroughs GeoJSON", fontsize=9, color="#718498")
    path = OUT / "pattern_manhattan_grid.png"
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"Tây {west}, Đông {east}; kiểm chứng {observed}")
    print(path)


if __name__ == "__main__":
    main()
