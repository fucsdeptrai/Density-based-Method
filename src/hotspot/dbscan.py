"""DBSCAN tren toa do phang don vi met.

Quan trong: `eps` phai la MET. Module nay khong bao gio chay DBSCAN tren
toa do do voi gia tri eps la met — `run_dbscan` chi nhan `x_m`/`y_m`.
Khong dung `StandardScaler`: chuan hoa pha vo ranh gioi khong gian.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

# Gia tri ngoai dai cua DBSCAN cho diem nhieu
NOISE_LABEL = -1


@dataclass
class DBSCANResult:
    """Ket qua phan cum kem thong tin cham va bien do."""

    labels: np.ndarray
    n_points: int
    eps_m: float
    min_samples: int
    runtime_seconds: float
    coords_m: np.ndarray = field(repr=False)
    centroids: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def noise_mask(self) -> np.ndarray:
        return self.labels == NOISE_LABEL

    @property
    def cluster_labels(self) -> np.ndarray:
        """Nhan cum, KHONG bao gom noise."""
        return np.array(sorted(set(self.labels) - {NOISE_LABEL}), dtype=int)

    @property
    def n_clusters(self) -> int:
        return int(self.cluster_labels.size)

    @property
    def n_noise(self) -> int:
        return int(self.noise_mask.sum())

    @property
    def noise_pct(self) -> float:
        return 100 * self.n_noise / self.n_points if self.n_points else 0.0


def run_dbscan(
    df: pd.DataFrame,
    eps_m: float,
    min_samples: int,
    *,
    point_cap: int | None = None,
    seed: int = 42,
) -> DBSCANResult:
    """Chay DBSCAN tren `x_m`, `y_m` (met).

    Tham so
    -------
    eps_m : ban kinh toi da, **don vi met**. 100 = 100 m.
    min_samples : so diem toi thieu trong ban kinh de coi la cum (goi la MinPts
        trong bai bao). Dem ca chinh diem do.
    point_cap : neu dat, lay mau ngau nhien toi da con diem de app khong bi
        treo tren ca lon. Seed co dinh nen ket qua lap lai duoc.
    """
    import time

    if eps_m <= 0:
        raise ValueError(f"eps_m phai > 0, nhan {eps_m}")
    if min_samples < 1:
        raise ValueError(f"min_samples phai >= 1, nhan {min_samples}")

    if len(df) == 0:
        raise ValueError("Khong co diem nao sau khi loc — kiem tra lai khoang gio")

    work = df
    if point_cap and len(df) > point_cap:
        idx = np.random.default_rng(seed).choice(len(df), point_cap, replace=False)
        work = df.iloc[np.sort(idx)]

    coords = work[["x_m", "y_m"]].to_numpy(dtype="float64")

    start = time.perf_counter()
    labels = DBSCAN(eps=float(eps_m), min_samples=int(min_samples), metric="euclidean").fit_predict(
        coords
    )
    runtime = time.perf_counter() - start

    result = DBSCANResult(
        labels=labels,
        n_points=len(work),
        eps_m=float(eps_m),
        min_samples=int(min_samples),
        runtime_seconds=runtime,
        coords_m=coords,
    )
    result.centroids = compute_centroids(work, result)
    return result


CENTROID_COLUMNS = {
    "cluster_id": "int64",
    "centroid_x_m": "float64",
    "centroid_y_m": "float64",
    "centroid_latitude": "float64",
    "centroid_longitude": "float64",
    "pickup_count": "int64",
}


def compute_centroids(df: pd.DataFrame, result: DBSCANResult) -> pd.DataFrame:
    """Trung tam hinh hoc cua tung cum (khong tinh ca noise).

    Tinh theo toa do phang roi chuyen lai lat/lon de ve len ban do.

    Khi khong co cum nao, tra DataFrame rong NEN KHAI BAO KIEU DU LIEU. Neu
    de kieu mac dinh (object), moi ham ben ngoai nhu `.nlargest()` se nem
    TypeError khi goi tren bang rong.
    """
    if result.n_clusters == 0:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in CENTROID_COLUMNS.items()})

    frame = df.iloc[: len(result.labels)].copy()
    frame["_label"] = result.labels

    grouped = frame[frame["_label"] != NOISE_LABEL].groupby("_label")
    out = grouped.agg(
        centroid_x_m=("x_m", "mean"),
        centroid_y_m=("y_m", "mean"),
        centroid_latitude=("latitude", "mean"),
        centroid_longitude=("longitude", "mean"),
        pickup_count=("x_m", "size"),
    ).reset_index()
    out = out.rename(columns={"_label": "cluster_id"})
    return out.sort_values("cluster_id").reset_index(drop=True)