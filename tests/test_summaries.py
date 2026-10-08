"""Test cho bang tong hop va chi so cap trang."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hotspot.dbscan import run_dbscan
from hotspot.summaries import cluster_table, page_metrics, summarize_hotspots


@pytest.fixture
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for cx in (0.0, 400.0):
        for dx, dy in zip(rng.normal(0, 15, 20), rng.normal(0, 15, 20)):
            rows.append(
                {
                    "x_m": cx + dx,
                    "y_m": dx * 0.0 + dy,
                    "latitude": 40.7 + cx * 1e-5,
                    "longitude": -73.9,
                    "weekday": 0,
                    "hour": 18,
                }
            )
    # 3 diem la bang nhau (nhieu)
    for _ in range(3):
        rows.append(
            {"x_m": 90_000.0, "y_m": 90_000.0, "latitude": 41.5,
             "longitude": -73.0, "weekday": 0, "hour": 18}
        )
    return pd.DataFrame(rows)


@pytest.fixture
def result(frame):
    return run_dbscan(frame, eps_m=100, min_samples=5)


def test_metrics_keys_and_types(frame, result):
    m = page_metrics(frame, result)
    assert m["filtered_pickups"] == len(frame)
    assert m["number_of_clusters"] == result.n_clusters
    assert m["noise_count"] + sum(
        frame.shape[0] - result.n_noise for _ in [0]
    ) == frame.shape[0]
    assert isinstance(m["noise_percentage"], float)
    assert m["analysis_runtime_seconds"] >= 0


def test_noise_percentage_consistent(frame, result):
    m = page_metrics(frame, result)
    assert m["noise_percentage"] == pytest.approx(
        100 * result.n_noise / result.n_points, abs=0.01
    )


def test_table_excludes_noise(frame, result):
    table = cluster_table(frame, result)
    assert -1 not in set(table["cluster_id"])
    assert (table["pickup_count"].sum() + result.n_noise) == result.n_points


def test_table_sorted_by_count_desc(frame, result):
    table = cluster_table(frame, result)
    counts = table["pickup_count"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_rank_starts_at_one(frame, result):
    assert list(cluster_table(frame, result)["rank"]) == list(
        range(1, len(result.cluster_labels) + 1)
    )


def test_area_positive_for_spread_cluster(frame, result):
    table = cluster_table(frame, result)
    assert (table["area_km2"] > 0).all()
    # 20 diem trong ban kinh ~15 m -> ~0.001 km^2. Cho phep rong rai.
    assert (table["area_km2"] < 1.0).all()


def test_density_matches_count_over_area(frame, result):
    table = cluster_table(frame, result)
    expected = table["pickup_count"] / table["area_km2"]
    np.testing.assert_allclose(table["pickup_per_km2"].to_numpy(), expected.to_numpy())


def test_table_without_area(frame, result):
    table = cluster_table(frame, result, with_area=False)
    assert "area_km2" not in table.columns
    assert "pickup_per_km2" not in table.columns


def test_convex_hull_area_of_square():
    """Doi 1 km x 1 km -> 1 km^2."""
    from hotspot.summaries import _convex_hull_area_m2

    x = np.array([0.0, 1000.0, 1000.0, 0.0])
    y = np.array([0.0, 0.0, 1000.0, 1000.0])
    assert _convex_hull_area_m2(x, y) / 1e6 == pytest.approx(1.0)


def test_convex_hull_area_too_few_points():
    from hotspot.summaries import _convex_hull_area_m2

    assert np.isnan(_convex_hull_area_m2(np.array([0.0, 1.0]), np.array([0.0, 1.0])))


def test_convex_hull_area_collinear_points_is_zero():
    from hotspot.summaries import _convex_hull_area_m2

    x = np.array([0.0, 10.0, 20.0])
    y = np.array([0.0, 0.0, 0.0])
    assert _convex_hull_area_m2(x, y) == 0.0


def test_empty_result_gives_empty_table(frame):
    result = run_dbscan(frame, eps_m=1, min_samples=999)
    table = cluster_table(frame, result)
    assert table.empty
    assert "pickup_count" in table.columns


def test_recurring_summary_ranks_support_dates_before_pickup_count():
    labeled = pd.DataFrame(
        {
            "cluster_id": [0, 0, 0, 1, 1, 1, 1, 1, -1],
            "date": [
                "2024-01-05",
                "2024-01-12",
                "2024-01-19",
                "2024-01-05",
                "2024-01-05",
                "2024-01-05",
                "2024-01-12",
                "2024-01-12",
                "2024-01-05",
            ],
            "latitude": [40.7] * 9,
            "longitude": [-73.9] * 9,
        }
    )

    table = summarize_hotspots(labeled, available_matching_dates=4)

    assert table["cluster_id"].tolist() == [0, 1]
    assert table["support_dates"].tolist() == [3, 2]
    assert table["pickup_count"].tolist() == [3, 5]
    assert table["pickups_per_matching_date"].tolist() == [0.75, 1.25]
    assert -1 not in table["cluster_id"].tolist()


def test_recurring_summary_empty_result_has_stable_schema():
    labeled = pd.DataFrame(
        {
            "cluster_id": [-1],
            "date": ["2024-01-05"],
            "latitude": [40.7],
            "longitude": [-73.9],
        }
    )
    table = summarize_hotspots(labeled, available_matching_dates=1)
    assert table.empty
    assert list(table.columns) == [
        "rank",
        "cluster_id",
        "pickup_count",
        "support_dates",
        "available_matching_dates",
        "pickups_per_matching_date",
        "centroid_latitude",
        "centroid_longitude",
        "marker_latitude",
        "marker_longitude",
    ]


def test_summary_places_marker_in_densest_cell_not_at_cluster_centroid():
    labeled = pd.DataFrame(
        {
            "cluster_id": [0] * 6,
            "date": ["2024-01-05"] * 6,
            "x_m": [0.0, 5.0, 10.0, 15.0, 1_000.0, 1_010.0],
            "y_m": [0.0] * 6,
            "latitude": [40.7000, 40.7001, 40.7002, 40.7003, 40.7100, 40.7101],
            "longitude": [-73.9000, -73.9001, -73.9002, -73.9003, -73.9100, -73.9101],
        }
    )

    table = summarize_hotspots(
        labeled,
        available_matching_dates=1,
        marker_cell_m=100,
    )

    assert table.iloc[0]["marker_latitude"] < 40.701
    assert table.iloc[0]["marker_longitude"] > -73.901
