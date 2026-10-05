"""Test cho loc thoi gian."""

from __future__ import annotations

import pandas as pd
import pytest

from hotspot.filters import WEEKDAY_NAMES, FilterSpec, filter_pickups


@pytest.fixture
def sample() -> pd.DataFrame:
    """2 diem/ngay, gio 0..23 -> 14 dong, bien tiet de kiem tra bien."""
    rows = []
    for day in range(7):
        for hour in (0, 9, 18, 19):
            rows.append(
                {
                    "weekday": day,
                    "hour": hour,
                    "latitude": 40.7,
                    "longitude": -73.9,
                    "x_m": 0.0,
                    "y_m": float(day * 24 + hour),
                }
            )
    return pd.DataFrame(rows)


def test_range_is_half_open(sample):
    """(18, 20) phai lay 18h va 19h, khong lay 20h."""
    out = filter_pickups(sample, FilterSpec(weekdays=(0,), hour_start=18, hour_end=20))
    assert sorted(out["hour"].unique()) == [18, 19]
    assert len(out) == 2


def test_single_day_filter(sample):
    out = filter_pickups(sample, FilterSpec(weekdays=(3,), hour_start=0, hour_end=24))
    assert set(out["weekday"]) == {3}
    assert len(out) == 4


def test_multiple_days(sample):
    out = filter_pickups(sample, FilterSpec(weekdays=(0, 1, 2), hour_start=0, hour_end=24))
    assert set(out["weekday"]) == {0, 1, 2}
    assert len(out) == 12


def test_does_not_mutate_source(sample):
    before = sample.copy()
    filter_pickups(sample, FilterSpec(weekdays=(1,), hour_start=8, hour_end=10))
    pd.testing.assert_frame_equal(sample, before)


def test_returns_copy_not_view(sample):
    out = filter_pickups(sample, FilterSpec(weekdays=(0,), hour_start=0, hour_end=24))
    assert out is not sample
    out.loc[:, "hour"] = 99
    assert sample["hour"].max() != 99


def test_empty_selection_returns_empty_frame(sample):
    out = filter_pickups(sample, FilterSpec(weekdays=(0,), hour_start=20, hour_end=21))
    assert len(out) == 0
    assert "hour" in out.columns  # van giu dung schema


@pytest.mark.parametrize(
    "spec",
    [
        FilterSpec(weekdays=(), hour_start=0, hour_end=24),
        FilterSpec(weekdays=(7,), hour_start=0, hour_end=24),
        FilterSpec(weekdays=(0,), hour_start=-1, hour_end=24),
        FilterSpec(weekdays=(0,), hour_start=10, hour_end=10),
        FilterSpec(weekdays=(0,), hour_start=12, hour_end=8),
        FilterSpec(weekdays=(0,), hour_start=0, hour_end=25),
    ],
)
def test_invalid_specs_raise(spec, sample):
    with pytest.raises(ValueError):
        filter_pickups(sample, spec)


def test_describe_lists_day_names():
    assert FilterSpec(weekdays=(0, 5), hour_start=17, hour_end=19).describe() == (
        f"{WEEKDAY_NAMES[0]}, {WEEKDAY_NAMES[5]} | 17:00-19:00"
    )


def test_index_is_reset(sample):
    out = filter_pickups(sample, FilterSpec(weekdays=(2,), hour_start=0, hour_end=24))
    assert list(out.index) == list(range(len(out)))