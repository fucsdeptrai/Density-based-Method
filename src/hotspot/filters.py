"""Loc diem don theo ngay trong tuan va khung gio — khong sua du lieu nguon."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# 0 = Thu Hai ... 6 = Chu Nhat (khop pandas .dt.dayofweek)
WEEKDAY_NAMES = ["Th 2", "Th 3", "Th 4", "Th 5", "Th 6", "Th 7", "CN"]


def weekday_options() -> list[tuple[int, str]]:
    """Danh sach (gia tri, nhan) cho Streamlit multiselect."""
    return list(enumerate(WEEKDAY_NAMES))


@dataclass(frozen=True)
class FilterSpec:
    """Mo ta khoang thoi gian can xem.

    `hour_end` la exclusive: `(18, 20)` = 18h, 19h (khong phai 20h).
    """

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
    """Tra ve DataFrame moi chua diem trong khoang gio.

    Khong bao gio sua `df` — tra ve `.copy()` de an toan khi nguoi goi tien
    cac bien trung gian.
    """
    spec.validate()

    mask = df["weekday"].isin(spec.weekdays) & df["hour"].between(
        spec.hour_start, spec.hour_end - 1
    )
    return df.loc[mask].copy().reset_index(drop=True)