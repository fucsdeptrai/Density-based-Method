"""Test cho DBSCAN — trong do kiem chung `eps` la MET."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hotspot.dbscan import NOISE_LABEL, analyze_hotspots, run_dbscan


def make_frame(x: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x_m": np.asarray(x, dtype="float64"),
            "y_m": np.asarray(y, dtype="float64"),
            "latitude": 40.7,
            "longitude": -73.9,
        }
    )


@pytest.fixture
def two_clusters() -> pd.DataFrame:
    """Hai cum tach biet: cum A quanh (0, 0), cum B quanh (500, 0), ban kinh ~20 m."""
    rng = np.random.default_rng(0)
    jitter_a = rng.normal(0, 15, 12)
    jitter_b = rng.normal(0, 15, 12)
    return make_frame(
        np.r_[jitter_a, 500 + jitter_b],
        np.r_[jitter_a * 0.5, jitter_b * 0.5],
    )


def test_finds_two_separated_clusters(two_clusters):
    res = run_dbscan(two_clusters, eps_m=100, min_samples=5)
    assert res.n_clusters == 2
    assert res.n_noise == 0
    assert res.n_points == 24


def test_eps_is_metres_not_degrees(two_clusters):
    """Cum cach nhau 500 m: eps=100 m tach, eps=600 m gop lai.

    Do khoang cach that giua 2 diem, khong do toa do do — `x_m`, `y_m` da
    la met. Neu `eps` bi doc nham la DO THI DO, 100 se la ~11 000 km va hai
    cum se gop lai o ca hai nganh. Test nay bat loi do.
    """
    near = run_dbscan(two_clusters, eps_m=100, min_samples=5)
    far = run_dbscan(two_clusters, eps_m=600, min_samples=5)

    assert near.n_clusters == 2
    assert far.n_clusters == 1


def test_gap_of_exactly_eps_is_merged():
    """Hai diem cach nhau DUNG bang eps -> chung cum (dinh nghia <= eps)."""
    frame = make_frame([0.0, 100.0], [0.0, 0.0])
    res = run_dbscan(frame, eps_m=100, min_samples=2)
    assert res.n_clusters == 1


def test_sparse_points_become_noise():
    frame = make_frame([0, 10_000, 20_000], [0, 0, 0])
    res = run_dbscan(frame, eps_m=100, min_samples=2)
    assert res.n_clusters == 0
    assert res.n_noise == 3
    assert res.noise_pct == 100.0


def test_labels_length_matches_points(two_clusters):
    res = run_dbscan(two_clusters, eps_m=100, min_samples=5)
    assert len(res.labels) == len(two_clusters)


def test_noise_label_excluded_from_cluster_labels(two_clusters):
    frame = pd.concat(
        [two_clusters, make_frame([50_000], [50_000])], ignore_index=True
    )
    res = run_dbscan(frame, eps_m=100, min_samples=5)
    assert NOISE_LABEL not in res.cluster_labels
    assert res.n_noise == 1


def test_deterministic_same_labels(two_clusters):
    a = run_dbscan(two_clusters, eps_m=100, min_samples=5).labels
    b = run_dbscan(two_clusters, eps_m=100, min_samples=5).labels
    np.testing.assert_array_equal(a, b)


def test_point_cap_deterministic_and_smaller(two_clusters):
    a = run_dbscan(two_clusters, eps_m=100, min_samples=3, point_cap=10)
    b = run_dbscan(two_clusters, eps_m=100, min_samples=3, point_cap=10)
    np.testing.assert_array_equal(a.labels, b.labels)
    assert a.n_points == 10


def test_centroid_of_known_points():
    frame = make_frame([0, 100, 200], [0, 100, 200])
    res = run_dbscan(frame, eps_m=150, min_samples=2)
    row = res.centroids.iloc[0]
    assert row["centroid_x_m"] == pytest.approx(100.0)
    assert row["pickup_count"] == 3


def test_runtime_recorded(two_clusters):
    assert run_dbscan(two_clusters, eps_m=100, min_samples=5).runtime_seconds >= 0


@pytest.mark.parametrize("eps, mpts", [(0, 5), (-1, 5), (100, 0), (100, -3)])
def test_invalid_params_raise(two_clusters, eps, mpts):
    with pytest.raises(ValueError):
        run_dbscan(two_clusters, eps_m=eps, min_samples=mpts)


def test_empty_frame_raises():
    with pytest.raises(ValueError, match="Khong co diem"):
        run_dbscan(make_frame([], []), eps_m=100, min_samples=5)


def test_min_samples_counts_the_point_itself():
    """min_samples=1 -> 1 diem cung la cum (ban kinh tinh ca chinh no)."""
    frame = make_frame([0.0, 5_000.0], [0.0, 0.0])
    res = run_dbscan(frame, eps_m=50, min_samples=1)
    assert res.n_clusters == 2
    assert res.n_noise == 0


def recurring_frame() -> pd.DataFrame:
    rows = []
    for date in ("2024-01-05", "2024-01-12", "2024-01-19"):
        for offset in (0.0, 1.0, 2.0):
            rows.append(
                {
                    "pickup_datetime": pd.Timestamp(f"{date} 18:15"),
                    "area": "Brooklyn",
                    "x_m": offset,
                    "y_m": offset,
                    "latitude": 40.70 + offset * 1e-6,
                    "longitude": -73.90,
                }
            )
    for date in ("2024-01-05", "2024-01-12"):
        for offset in (0.0, 1.0, 2.0):
            rows.append(
                {
                    "pickup_datetime": pd.Timestamp(f"{date} 18:30"),
                    "area": "Brooklyn",
                    "x_m": 100 + offset,
                    "y_m": offset,
                    "latitude": 40.71 + offset * 1e-6,
                    "longitude": -73.91,
                }
            )
    rows.extend(
        [
            {
                "pickup_datetime": pd.Timestamp("2024-01-05 18:45"),
                "area": "Brooklyn",
                "x_m": 1_000.0,
                "y_m": 1_000.0,
                "latitude": 40.72,
                "longitude": -73.92,
            },
            {
                "pickup_datetime": pd.Timestamp("2024-01-26 09:00"),
                "area": "Brooklyn",
                "x_m": 2_000.0,
                "y_m": 2_000.0,
                "latitude": 40.73,
                "longitude": -73.93,
            },
        ]
    )
    return pd.DataFrame(rows)


def test_analyze_hotspots_returns_ranked_recurring_zones():
    analysis = analyze_hotspots(
        recurring_frame(),
        area="Brooklyn",
        weekday_selection=["Friday"],
        start_hour=18,
        window_minutes=60,
        eps_m=5,
        min_samples=2,
    )

    assert analysis.n_points == 16
    assert analysis.n_clusters == 2
    assert analysis.n_noise == 1
    assert analysis.available_matching_dates == 4
    assert analysis.top_zones["support_dates"].tolist() == [3, 2]
    assert analysis.top_zones["pickup_count"].tolist() == [9, 6]
    assert analysis.top_zones["pickups_per_matching_date"].tolist() == [2.25, 1.5]


def test_analyze_hotspots_reports_largest_cluster_share():
    analysis = analyze_hotspots(
        recurring_frame(),
        area="Brooklyn",
        weekday_selection=["Friday"],
        start_hour=18,
        window_minutes=60,
        eps_m=5,
        min_samples=2,
    )
    assert analysis.largest_cluster_percentage == pytest.approx(100 * 9 / 16)


def test_analyze_hotspots_rejects_empty_context():
    with pytest.raises(ValueError, match="Khong co pickup"):
        analyze_hotspots(
            recurring_frame(),
            area="Queens",
            weekday_selection=["Friday"],
            start_hour=18,
            window_minutes=60,
            eps_m=5,
            min_samples=2,
        )
