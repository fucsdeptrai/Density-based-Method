"""Tong hop ket qua: bang xep hang hotspot + chi so o cap trang."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dbscan import DBSCANResult

EARTH_R = 6_371_000.0


def _convex_hull_area_m2(x: np.ndarray, y: np.ndarray) -> float:
    """Dien tich bao convex bang thuat toan monotone chain (O(n log n)).

    Chi dung de *dien tich uoc luong* de tinh mat do — KHONG dung ve ranh gioi
    cum len ban do. Ranh gioi DBSCAN khong phai hinh hoc nao.
    """
    if len(x) < 3:
        return float("nan")

    pts = np.column_stack([x, y])
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]
    if np.allclose(pts, pts[0]):
        return 0.0

    def half(points: np.ndarray) -> np.ndarray:
        out: list[np.ndarray] = []
        for p in points:
            while len(out) >= 2:
                a, b = out[-2], out[-1]
                if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) <= 0:
                    out.pop()
                else:
                    break
            out.append(p)
        return np.array(out)

    lower, upper = half(pts), half(pts[::-1])
    hull = np.vstack([lower[:-1], upper[:-1]])
    if len(hull) < 3:
        return 0.0

    # Shoelace
    x0, y0 = hull[:, 0], hull[:, 1]
    return float(abs(np.dot(x0, np.roll(y0, -1)) - np.dot(y0, np.roll(x0, -1))) / 2)


def cluster_table(df: pd.DataFrame, result: DBSCANResult, *, with_area: bool = True) -> pd.DataFrame:
    """Bang xep rank cum theo so chuyen.

    Khong bao gio khoang hang `-1` (noise) vao bang — noise chi duoc bao cao
    o cap trang bang `page_metrics`.
    """
    table = result.centroids.copy()
    if table.empty:
        return table

    if with_area:
        frame = df.iloc[: len(result.labels)]
        frame = frame.assign(_label=result.labels)
        areas = {
            int(label): _convex_hull_area_m2(g["x_m"].to_numpy(), g["y_m"].to_numpy())
            for label, g in frame[frame["_label"] != -1].groupby("_label")
        }
        table["area_km2"] = table["cluster_id"].map(areas) / 1e6
        # Mat do = chuyen / km^2. Dien tich bao convex uoc luong nen mat do
        # nay cung la uoc luong — dung de SO SANH, khong dung bao cao cong thuc
        # voi bang chay.
        with np.errstate(divide="ignore", invalid="ignore"):
            table["pickup_per_km2"] = np.where(
                table["area_km2"] > 0, table["pickup_count"] / table["area_km2"], np.nan
            )

    table = table.sort_values("pickup_count", ascending=False).reset_index(drop=True)
    table.insert(0, "rank", range(1, len(table) + 1))
    return table


def page_metrics(df: pd.DataFrame, result: DBSCANResult) -> dict:
    """Chi so o cap trang cho app hien thi."""
    hours = 0.0
    if "hour" in df.columns and "weekday" in df.columns:
        # So gio thuc te trong khoang da chon — dung de tinh chuyen/gio
        span = df["hour"].max() - df["hour"].min() + 1
        n_days = df["weekday"].nunique()
        hours = span * n_days

    return {
        "filtered_pickups": int(result.n_points),
        "number_of_clusters": result.n_clusters,
        "noise_count": result.n_noise,
        "noise_percentage": round(result.noise_pct, 2),
        "analysis_runtime_seconds": round(result.runtime_seconds, 3),
        "eps_m": result.eps_m,
        "min_samples": result.min_samples,
        "sampled": bool(result.n_points < len(df)),
        "window_hours": hours,
        "pickups_per_hour": round(result.n_points / hours, 1) if hours else None,
    }