"""Loc pickup theo khong gian va ngu canh thoi gian lap lai."""

from __future__ import annotations

from dataclasses import dataclass
import json

import numpy as np
import pandas as pd
from shapely import contains_xy
from shapely.geometry import shape

# 0 = Thu Hai ... 6 = Chu Nhat (khop pandas .dt.dayofweek)
WEEKDAY_NAMES = ["Th 2", "Th 3", "Th 4", "Th 5", "Th 6", "Th 7", "CN"]
ENGLISH_WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def weekday_options() -> list[tuple[int, str]]:
    """Danh sach (gia tri, nhan) cho Streamlit multiselect."""
    return list(enumerate(WEEKDAY_NAMES))


@dataclass(frozen=True)
class FilterSpec:
    """Contract cu cho cac notebook diagnostic theo gio tron."""

    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    hour_start: int = 18
    hour_end: int = 20

    def validate(self) -> None:
        if not self.weekdays:
            raise ValueError("Chon it nhat mot ngay trong tuan")
        if len(self.weekdays) > len(set(self.weekdays)):
            raise ValueError(f"Ngay trong tuan bi trung: {self.weekdays}")
        if any(not 0 <= d <= 6 for d in self.weekdays):
            raise ValueError(f"Ngay trong tuan phai trong 0..6, nhan {self.weekdays}")
        if not 0 <= self.hour_start <= 23:
            raise ValueError(f"hour_start phai trong 0..23, nhan {self.hour_start}")
        if not 1 <= self.hour_end <= 24:
            raise ValueError(f"hour_end phai trong 1..24, nhan {self.hour_end}")
        if self.hour_end <= self.hour_start:
            raise ValueError(
                f"hour_end ({self.hour_end}) phai lon hon hour_start ({self.hour_start})"
            )

    def describe(self) -> str:
        days = ", ".join(WEEKDAY_NAMES[d] for d in sorted(self.weekdays))
        return f"{days} | {self.hour_start:02d}:00-{self.hour_end:02d}:00"


def filter_pickups(df: pd.DataFrame, spec: FilterSpec) -> pd.DataFrame:
    """Contract cu: loc theo thu va khoang gio tron, khong mutate input."""
    spec.validate()
    mask = df["weekday"].isin(spec.weekdays) & df["hour"].between(
        spec.hour_start, spec.hour_end - 1
    )
    return df.loc[mask].copy().reset_index(drop=True)


@dataclass(frozen=True)
class SpatialSelection:
    """Dung mot borough HOAC mot Polygon/MultiPolygon GeoJSON."""

    borough: str | None = None
    geometry_json: str | None = None

    def __post_init__(self) -> None:
        if bool(self.borough) == bool(self.geometry_json):
            raise ValueError("Chon dung mot borough hoac mot vung ve")
        if self.borough is not None and not self.borough.strip():
            raise ValueError("Borough khong duoc de trong")
        if self.geometry_json is not None:
            geometry = self.geometry
            if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError("Vung ve phai la rectangle hoac polygon")
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError("Vung ve khong hop le")

    @classmethod
    def for_borough(cls, borough: str) -> SpatialSelection:
        return cls(borough=borough)

    @classmethod
    def for_geometry(cls, geometry: dict) -> SpatialSelection:
        if geometry.get("type") == "Feature":
            geometry = geometry.get("geometry") or {}
        encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":"))
        return cls(geometry_json=encoded)

    @property
    def geometry(self):
        if self.geometry_json is None:
            return None
        return shape(json.loads(self.geometry_json))

    @property
    def label(self) -> str:
        return self.borough or "Vùng tùy chọn"


class QueryTooLargeError(ValueError):
    """Truy van hop le nhung qua lon cho DBSCAN tuong tac."""

    def __init__(self, point_count: int, point_limit: int) -> None:
        self.point_count = point_count
        self.point_limit = point_limit
        super().__init__(
            f"Truy van co {point_count:,} pickup, vuot nguong {point_limit:,}. "
            "Hay thu hep khu vuc, ngay hoac khung gio."
        )


@dataclass
class ContextPreview:
    points: pd.DataFrame
    total_points: int
    available_matching_dates: int
    matching_dates: tuple[str, ...]


def _resolve_selection(
    spatial_selection: SpatialSelection | None,
    area: str | None,
) -> SpatialSelection:
    if spatial_selection is not None and area is not None:
        raise ValueError("Khong truyen dong thoi spatial_selection va area")
    if spatial_selection is not None:
        return spatial_selection
    if area is not None:
        return SpatialSelection.for_borough(area)
    raise ValueError("Can chon mot borough hoac ve mot vung")


def _resolve_start_minute(start_minute: int | None, start_hour: int | None) -> int:
    if start_minute is not None and start_hour is not None:
        raise ValueError("Khong truyen dong thoi start_minute va start_hour")
    if start_minute is None:
        if start_hour is None:
            raise ValueError("Can chon gio bat dau")
        start_minute = start_hour * 60
    if not 0 <= start_minute < 24 * 60 or start_minute % 15:
        raise ValueError("Gio bat dau phai theo buoc 15 phut trong mot ngay")
    return int(start_minute)


def _weekday_indices(weekday_selection: list[str] | tuple[str, ...]) -> set[int]:
    if not weekday_selection:
        raise ValueError("Chon it nhat mot ngay trong tuan")
    lookup = {name.casefold(): index for index, name in enumerate(ENGLISH_WEEKDAYS)}
    unknown = [name for name in weekday_selection if name.casefold() not in lookup]
    if unknown:
        raise ValueError(f"Ngay trong tuan khong hop le: {unknown}")
    return {lookup[name.casefold()] for name in weekday_selection}


def matching_dates_for_context(
    pickups: pd.DataFrame,
    weekday_selection: list[str] | tuple[str, ...],
    max_matching_dates: int | None = None,
) -> tuple[str, ...]:
    """Cac ngay lich gan nhat khop thu da chon trong pham vi dataset."""
    if "pickup_datetime" not in pickups.columns:
        raise ValueError("Du lieu thieu cot bat buoc: ['pickup_datetime']")
    if max_matching_dates is not None and max_matching_dates < 1:
        raise ValueError("So ngay phu hop toi da phai lon hon 0")

    weekdays = _weekday_indices(weekday_selection)
    timestamps = pd.to_datetime(pickups["pickup_datetime"])
    calendar_dates = pd.DatetimeIndex(timestamps.dt.normalize().unique()).sort_values()
    matching = calendar_dates[calendar_dates.dayofweek.isin(weekdays)]
    if max_matching_dates is not None:
        matching = matching[-max_matching_dates:]
    return tuple(date.strftime("%Y-%m-%d") for date in matching)


def _validate_columns(pickups: pd.DataFrame) -> None:
    required = {
        "pickup_datetime",
        "latitude",
        "longitude",
        "x_m",
        "y_m",
        "area",
    }
    missing = sorted(required - set(pickups.columns))
    if missing:
        raise ValueError(f"Du lieu thieu cot bat buoc: {missing}")


def _spatial_mask(
    pickups: pd.DataFrame,
    selection: SpatialSelection,
    candidate_mask: pd.Series,
) -> pd.Series:
    if selection.borough is not None:
        values = {
            str(value).casefold(): value for value in pickups["area"].dropna().unique()
        }
        selected = values.get(selection.borough.casefold())
        if selected is None:
            return pd.Series(False, index=pickups.index)
        return pickups["area"].eq(selected)

    positions = np.flatnonzero(candidate_mask.to_numpy())
    mask = np.zeros(len(pickups), dtype=bool)
    if len(positions):
        candidate = pickups.iloc[positions]
        mask[positions] = contains_xy(
            selection.geometry,
            candidate["longitude"].to_numpy(dtype="float64"),
            candidate["latitude"].to_numpy(dtype="float64"),
        )
    return pd.Series(mask, index=pickups.index)


def _context_mask(
    pickups: pd.DataFrame,
    *,
    spatial_selection: SpatialSelection,
    weekday_selection: list[str] | tuple[str, ...],
    start_minute: int,
    window_minutes: int,
    max_matching_dates: int | None = None,
) -> tuple[pd.Series, pd.Series, tuple[str, ...]]:
    _validate_columns(pickups)
    weekdays = _weekday_indices(weekday_selection)
    if not 15 <= window_minutes <= 24 * 60 or window_minutes % 15:
        raise ValueError("Do dai khung gio phai tu 15 phut den 24 gio, theo buoc 15 phut")

    timestamps = pd.to_datetime(pickups["pickup_datetime"])
    minute_of_day = timestamps.dt.hour * 60 + timestamps.dt.minute
    offset_from_start = (minute_of_day - start_minute) % (24 * 60)
    time_mask = offset_from_start.lt(window_minutes)

    # Cua so qua nua dem duoc gan ve ngay bat dau cua ngu canh.
    context_dates = timestamps.dt.normalize() - pd.to_timedelta(
        minute_of_day.lt(start_minute).astype("int8"), unit="D"
    )
    weekday_mask = context_dates.dt.dayofweek.isin(weekdays)

    # Mau so phan anh do phu ngay cua toan dataset, khong phu thuoc viec
    # khu vuc dang chon co pickup hay khong.
    matching_dates = matching_dates_for_context(
        pickups,
        weekday_selection,
        max_matching_dates=max_matching_dates,
    )
    coverage_mask = context_dates.isin(pd.to_datetime(matching_dates))
    temporal_mask = time_mask & weekday_mask & coverage_mask
    spatial_mask = _spatial_mask(pickups, spatial_selection, temporal_mask)
    return temporal_mask & spatial_mask, context_dates, matching_dates


def _materialize(
    pickups: pd.DataFrame,
    positions: np.ndarray,
    context_dates: pd.Series,
) -> pd.DataFrame:
    filtered = pickups.iloc[positions].copy()
    dates = context_dates.iloc[positions].dt.date.to_numpy()
    filtered["context_date"] = dates
    # `date` duoc giu de summaries cu va moi cung dung mot nguon recurrence.
    filtered["date"] = dates
    return filtered.reset_index(drop=True)


def preview_context(
    pickups: pd.DataFrame,
    *,
    spatial_selection: SpatialSelection | None = None,
    area: str | None = None,
    weekday_selection: list[str] | tuple[str, ...],
    start_minute: int | None = None,
    start_hour: int | None = None,
    window_minutes: int,
    max_preview_points: int = 1_500,
    max_matching_dates: int | None = None,
) -> ContextPreview:
    """Dem chinh xac va chi lay mau co dinh cho ban do preview."""
    selection = _resolve_selection(spatial_selection, area)
    start = _resolve_start_minute(start_minute, start_hour)
    mask, context_dates, matching_dates = _context_mask(
        pickups,
        spatial_selection=selection,
        weekday_selection=weekday_selection,
        start_minute=start,
        window_minutes=window_minutes,
        max_matching_dates=max_matching_dates,
    )
    positions = np.flatnonzero(mask.to_numpy())
    total = len(positions)
    if total > max_preview_points:
        positions = np.sort(
            np.random.default_rng(0).choice(positions, max_preview_points, replace=False)
        )
    return ContextPreview(
        points=_materialize(pickups, positions, context_dates),
        total_points=total,
        available_matching_dates=len(matching_dates),
        matching_dates=matching_dates,
    )


def filter_context(
    pickups: pd.DataFrame,
    *,
    spatial_selection: SpatialSelection | None = None,
    area: str | None = None,
    weekday_selection: list[str] | tuple[str, ...],
    start_minute: int | None = None,
    start_hour: int | None = None,
    window_minutes: int,
    max_points: int | None = None,
    max_matching_dates: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Loc mot ngu canh lap lai ma khong sua DataFrame nguon."""
    selection = _resolve_selection(spatial_selection, area)
    start = _resolve_start_minute(start_minute, start_hour)
    mask, context_dates, matching_dates = _context_mask(
        pickups,
        spatial_selection=selection,
        weekday_selection=weekday_selection,
        start_minute=start,
        window_minutes=window_minutes,
        max_matching_dates=max_matching_dates,
    )
    positions = np.flatnonzero(mask.to_numpy())
    if max_points is not None and len(positions) > max_points:
        raise QueryTooLargeError(len(positions), max_points)
    return _materialize(pickups, positions, context_dates), len(matching_dates)
