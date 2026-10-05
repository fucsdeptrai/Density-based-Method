"""Test cho lop ve hinh (matplotlib, offline)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless: khong mo cua so khi chay pytest

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from hotspot.dbscan import run_dbscan
from hotspot.figures import (
    cluster_color,
    load_borough_rings,
    plot_borough_distribution,
    plot_eps_sweep,
    plot_hotspot_map,
    plot_clusters,
    plot_parameter_tradeoff,
    projection_origin,
)


@pytest.fixture
def frame() -> pd.DataFrame:
    """Ba cum nho bien tach xa nhau, kem cot borough."""
    rows = []
    for seed, cx in enumerate((0.0, 3000.0, 6000.0)):
        rng = np.random.default_rng(seed)
        xs, ys = rng.normal(0, 40, 30), rng.normal(0, 40, 30)
        for dx, dy in zip(xs, ys):
            rows.append(
                {
                    "x_m": cx + dx,
                    "y_m": dy,
                    "latitude": 40.74 + cx * 1e-5,
                    "longitude": -73.97,
                    "borough": "Manhattan",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def rings() -> dict:
    """Hai quan vuong don gian, o he toa do met."""
    def square(x0, y0, size=4000):
        return [
            np.array([
                [x0, y0], [x0 + size, y0], [x0 + size, y0 + size],
                [x0, y0 + size], [x0, y0],
            ])
        ]

    return {"Manhattan": square(0, 0), "Brooklyn": square(3000, 0)}


# --------------------------------------------------------------------------- #
# Mau
# --------------------------------------------------------------------------- #
def test_cluster_color_cycles_instead_of_crashing():
    """So cum rat lon khong duoc lam IndexError."""
    for label in (0, 11, 12, 999, -1):
        assert cluster_color(label).startswith("#")


def test_cluster_color_is_stable():
    assert cluster_color(3) == cluster_color(3)


# --------------------------------------------------------------------------- #
# Nap polygon nen — khoa lai loi he toa do
# --------------------------------------------------------------------------- #
def test_projection_origin_reads_report(tmp_path):
    report = tmp_path / "preprocess_report.json"
    report.write_text('{"full": {"projection": {"lat0": 40.5, "lon0": -73.9}}}')
    assert projection_origin(report) == (40.5, -73.9)


def test_projection_origin_missing_report_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        projection_origin(tmp_path / "khong_co.csv")


def test_load_borough_rings_requires_projection_args():
    """Thieu lat0/lon0 phai bao loi ngay, khong ve sai he toa do."""
    import inspect

    params = inspect.signature(load_borough_rings).parameters
    assert "lat0" in params and "lon0" in params


def test_rings_must_share_coordinate_system_with_data(tmp_path, frame):
    """Regression: polygon lat/lon ve chung he toa do met voi du lieu.

    Neu ve polygon o toa do DO (nhu geojson tho) cung du lieu o x_m/y_m,
    nen se nam ngoai khung hinh va bia dat khong bao gio hien ra.
    """
    geo = tmp_path / "nyc_boroughs.geojson"
    geo.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature",'
        '"properties":{"BoroName":"Manhattan"},'
        '"geometry":{"type":"Polygon","coordinates":'
        '[[[-73.98,40.75],[-73.97,40.75],[-73.97,40.76],[-73.98,40.76],[-73.98,40.75]]]}}]}'
    )

    rings = load_borough_rings(tmp_path, lat0=40.74, lon0=-73.97)
    ring = rings["Manhattan"][0]

    # Toa do phai la MET: dai ~1 km, khong phai ~0.01 do
    span = float(np.ptp(ring[:, 0]))
    assert 500 < span < 2000, f"dai polygon = {span}, co ve sai he toa do (do lai?)"

    # Va phai trung gan voi khung cua du lieu
    assert abs(ring[:, 0].min()) < 20_000
    assert frame["x_m"].min() < ring[:, 0].max()


def test_missing_geojson_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_borough_rings(tmp_path, lat0=40.0, lon0=-74.0)


# --------------------------------------------------------------------------- #
# Ve
# --------------------------------------------------------------------------- #
def test_plot_clusters_runs(frame, rings):
    fig, ax = plt.subplots()
    result = run_dbscan(frame, eps_m=800, min_samples=5)
    plot_clusters(ax, frame, result, rings, annotate_top=2)
    fig.savefig("/tmp/_test_plot.png")  # dam bao render that
    plt.close(fig)


def test_plot_clusters_with_no_clusters(frame, rings):
    fig, ax = plt.subplots()
    result = run_dbscan(frame, eps_m=1, min_samples=9999)
    plot_clusters(ax, frame, result, rings, annotate_top=3)
    plt.close(fig)


def test_plot_eps_sweep_same_data_across_panels(frame, rings):
    fig, results = plot_eps_sweep(
        frame, [50, 200, 400], 5, rings, ncols=3, focus=(-1000, 7000, -1500, 1500)
    )
    assert len(results) == 3
    # eps tang -> so cum khong tang
    assert results[0].n_clusters >= results[-1].n_clusters
    # Moi panel cung so diem (chi doi eps)
    assert len({r.n_points for r in results}) == 1
    plt.close(fig)


def test_plot_eps_sweep_hides_unused_panels(frame, rings):
    fig, _ = plot_eps_sweep(frame, [50, 100], 5, rings, ncols=4)
    visible = [ax.get_visible() for ax in fig.axes]
    assert visible.count(True) == 2
    plt.close(fig)


def test_plot_hotspot_map(frame, rings):
    result = run_dbscan(frame, eps_m=800, min_samples=5)
    fig = plot_hotspot_map(frame, result, rings, title="t", subtitle="s", annotate_top=2)
    fig.savefig("/tmp/_test_hotspot.png")
    plt.close(fig)


def test_plot_parameter_tradeoff(frame, rings):
    fig, data = plot_parameter_tradeoff(frame, [100, 300], 5, min_pts_list=[5, 15])
    assert len(data) == 4
    assert set(data.columns) >= {"eps_m", "MinPts", "n_clusters", "noise_pct"}
    plt.close(fig)


def test_plot_borough_distribution(frame):
    fig, counts = plot_borough_distribution(frame)
    assert counts["Số chuyến"].sum() == len(frame)
    assert abs(counts["Tỉ lệ (%)"].sum() - 100) < 0.5
    plt.close(fig)


def test_borough_labels_clipped_outside_view(frame, rings):
    """Ten quan nam ngoai khung hinh phai bi bo qua."""
    fig, ax = plt.subplots()
    ax.set_xlim(-10_000, 10_000)
    ax.set_ylim(-10_000, -5_000)  # khong chua quan nao
    from hotspot.figures import borough_labels

    borough_labels(ax, rings, clip_to_view=True)
    assert not ax.texts, "van con chu ve o ngoai khung hinh"
    plt.close(fig)


def test_borough_labels_shown_inside_view(rings):
    fig, ax = plt.subplots()
    ax.set_xlim(-1000, 8000)
    ax.set_ylim(-1000, 3000)
    from hotspot.figures import borough_labels

    borough_labels(ax, rings, clip_to_view=True)
    assert len(ax.texts) >= 1
    plt.close(fig)