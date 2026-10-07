"""Behavior tests qua interface phan tich hotspot hoan chinh."""

from __future__ import annotations

import pandas as pd
import pytest

from hotspot import analyze_hotspots


def make_pickups() -> pd.DataFrame:
    rows: list[dict] = []

    def add(date: str, x: float, count: int, *, area: str = "Brooklyn") -> None:
        for offset in range(count):
            rows.append(
                {
                    "pickup_datetime": pd.Timestamp(f"{date} 18:{offset:02d}:00"),
                    "latitude": 40.68 + x / 1_000_000,
                    "longitude": -73.94,
                    "x_m": x + offset,
                    "y_m": float(offset),
                    "area": area,
                }
            )

    # Cum A lap lai tren hai thu Sau.
    add("2024-01-05", 0, 2)
    add("2024-01-12", 0, 2)
    # Cum B co nhieu pickup hon nhung chi xuat hien mot ngay.
    add("2024-01-05", 500, 5)
    # Ngoai ngu canh: khac area va dung tai bien ket thuc 19:00.
    add("2024-01-05", 0, 3, area="Queens")
    rows.append(
        {
            "pickup_datetime": pd.Timestamp("2024-01-12 19:00:00"),
            "latitude": 40.68,
            "longitude": -73.94,
            "x_m": 0.0,
            "y_m": 0.0,
            "area": "Brooklyn",
        }
    )
    return pd.DataFrame(rows)


@pytest.fixture
def analysis():
    return analyze_hotspots(
        make_pickups(),
        area="Brooklyn",
        weekday_selection=["Friday"],
        start_hour=18,
        window_minutes=60,
        eps_m=30,
        min_samples=2,
    )


def test_filters_area_weekday_and_half_open_time_window(analysis):
    assert analysis.n_points == 9
    assert analysis.available_matching_dates == 2
    assert set(analysis.points["area"]) == {"Brooklyn"}
    assert analysis.points["pickup_datetime"].dt.hour.eq(18).all()


def test_ranks_recurring_zone_before_one_off_larger_zone(analysis):
    first, second = analysis.zones.iloc[0], analysis.zones.iloc[1]
    assert first["support_dates"] == 2
    assert first["pickup_count"] == 4
    assert second["support_dates"] == 1
    assert second["pickup_count"] == 5


def test_returns_exact_evidence_and_map_ready_labels(analysis):
    assert analysis.n_clusters == 2
    assert analysis.n_noise == 0
    assert len(analysis.points["cluster_id"]) == analysis.n_points
    assert set(
        [
            "pickup_count",
            "support_dates",
            "available_matching_dates",
            "pickups_per_matching_date",
            "centroid_latitude",
            "centroid_longitude",
        ]
    ).issubset(analysis.zones.columns)
    assert (analysis.zones["available_matching_dates"] == 2).all()


def test_invalid_or_empty_context_has_clear_error():
    with pytest.raises(ValueError, match="Khong co pickup"):
        analyze_hotspots(
            make_pickups(),
            area="Bronx",
            weekday_selection=["Friday"],
            start_hour=18,
            window_minutes=60,
            eps_m=30,
            min_samples=2,
        )
