"""Test cho bo loc khong gian/thoi gian tu do cua demo."""

from __future__ import annotations

import pandas as pd
import pytest

from hotspot import (
    QueryTooLargeError,
    SpatialSelection,
    analyze_hotspots,
    filter_context,
    preview_context,
)


def make_frame(rows: list[tuple[str, float, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pickup_datetime": pd.Timestamp(timestamp),
                "latitude": latitude,
                "longitude": longitude,
                "x_m": index * 2.0,
                "y_m": index * 2.0,
                "area": area,
            }
            for index, (timestamp, latitude, longitude, area) in enumerate(rows)
        ]
    )


def test_polygon_selection_uses_drawn_geometry_not_borough():
    pickups = make_frame(
        [
            ("2024-01-05 18:15", 40.680, -73.940, "Brooklyn"),
            ("2024-01-05 18:30", 40.681, -73.941, "Queens"),
            ("2024-01-05 18:45", 40.750, -73.980, "Manhattan"),
        ]
    )
    selection = SpatialSelection.for_geometry(
        {
            "type": "Polygon",
            "coordinates": [[
                [-73.95, 40.67],
                [-73.93, 40.67],
                [-73.93, 40.69],
                [-73.95, 40.69],
                [-73.95, 40.67],
            ]],
        }
    )

    filtered, _ = filter_context(
        pickups,
        spatial_selection=selection,
        weekday_selection=["Friday"],
        start_minute=18 * 60,
        window_minutes=60,
    )

    assert len(filtered) == 2
    assert set(filtered["area"]) == {"Brooklyn", "Queens"}


def test_borough_selection_is_case_insensitive_and_single():
    pickups = make_frame(
        [
            ("2024-01-05 18:00", 40.68, -73.94, "Brooklyn"),
            ("2024-01-05 18:00", 40.75, -73.98, "Manhattan"),
        ]
    )
    filtered, _ = filter_context(
        pickups,
        spatial_selection=SpatialSelection.for_borough("brooklyn"),
        weekday_selection=["Friday"],
        start_minute=18 * 60,
        window_minutes=60,
    )
    assert filtered["area"].tolist() == ["Brooklyn"]


def test_overnight_window_uses_start_day_as_context_date():
    pickups = make_frame(
        [
            ("2024-01-05 12:00", 40.68, -73.94, "Brooklyn"),
            ("2024-01-05 23:45", 40.68, -73.94, "Brooklyn"),
            ("2024-01-06 00:15", 40.68, -73.94, "Brooklyn"),
            ("2024-01-06 01:30", 40.68, -73.94, "Brooklyn"),
            ("2024-01-12 12:00", 40.68, -73.94, "Brooklyn"),
        ]
    )
    filtered, available_dates = filter_context(
        pickups,
        spatial_selection=SpatialSelection.for_borough("Brooklyn"),
        weekday_selection=["Friday"],
        start_minute=23 * 60 + 30,
        window_minutes=120,
    )

    assert filtered["pickup_datetime"].dt.strftime("%H:%M").tolist() == ["23:45", "00:15"]
    assert filtered["context_date"].astype(str).tolist() == ["2024-01-05", "2024-01-05"]
    assert available_dates == 2


def test_full_day_window_is_anchored_at_selected_start_time():
    pickups = make_frame(
        [
            ("2024-01-05 17:59", 40.68, -73.94, "Brooklyn"),
            ("2024-01-05 18:00", 40.68, -73.94, "Brooklyn"),
            ("2024-01-06 17:59", 40.68, -73.94, "Brooklyn"),
            ("2024-01-06 18:00", 40.68, -73.94, "Brooklyn"),
        ]
    )
    filtered, _ = filter_context(
        pickups,
        spatial_selection=SpatialSelection.for_borough("Brooklyn"),
        weekday_selection=["Friday"],
        start_minute=18 * 60,
        window_minutes=24 * 60,
    )

    assert filtered["pickup_datetime"].dt.strftime("%a %H:%M").tolist() == [
        "Fri 18:00",
        "Sat 17:59",
    ]


def test_preview_counts_all_points_but_returns_only_sample():
    pickups = make_frame(
        [(f"2024-01-05 18:{minute:02d}", 40.68, -73.94, "Brooklyn") for minute in range(10)]
    )
    preview = preview_context(
        pickups,
        spatial_selection=SpatialSelection.for_borough("Brooklyn"),
        weekday_selection=["Friday"],
        start_minute=18 * 60,
        window_minutes=60,
        max_preview_points=3,
    )
    assert preview.total_points == 10
    assert len(preview.points) == 3


def test_analysis_rejects_query_above_exact_limit():
    pickups = make_frame(
        [(f"2024-01-05 18:{minute:02d}", 40.68, -73.94, "Brooklyn") for minute in range(4)]
    )
    with pytest.raises(QueryTooLargeError) as error:
        analyze_hotspots(
            pickups,
            spatial_selection=SpatialSelection.for_borough("Brooklyn"),
            weekday_selection=["Friday"],
            start_minute=18 * 60,
            window_minutes=60,
            eps_m=30,
            min_samples=2,
            max_points=3,
        )
    assert error.value.point_count == 4
    assert error.value.point_limit == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"borough": "Brooklyn", "geometry_json": "{}"},
        {"borough": None, "geometry_json": None},
    ],
)
def test_spatial_selection_requires_exactly_one_mode(kwargs):
    with pytest.raises(ValueError):
        SpatialSelection(**kwargs)


def test_time_inputs_must_use_fifteen_minute_steps():
    pickups = make_frame(
        [("2024-01-05 18:00", 40.68, -73.94, "Brooklyn")]
    )
    with pytest.raises(ValueError, match="15 phut"):
        filter_context(
            pickups,
            spatial_selection=SpatialSelection.for_borough("Brooklyn"),
            weekday_selection=["Friday"],
            start_minute=18 * 60 + 1,
            window_minutes=60,
        )
