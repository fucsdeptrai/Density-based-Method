"""KDE — uoc luong mat do lien tuc, dung lam SO SANH voi DBSCAN.

KDE khong tao cum roi tach; no tra ve mot mat do tai moi vi tri trong luoi.
`bandwidth_m` la tham so chinh, cung don vi met.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.neighbors import KernelDensity


@dataclass
class KDEResult:
    """Mat do uoc luong tren luoi vuong."""

    grid_x: np.ndarray  # hoa so cot, met
    grid_y: np.ndarray  # hoa so hang, met
    density: np.ndarray  # (len(grid_y), len(grid_x))
    bandwidth_m: float
    runtime_seconds: float
    coords_m: np.ndarray = field(repr=False)
    bounds_m: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def peak_density(self) -> float:
        return float(self.density.max()) if self.density.size else 0.0

    def percentile_mask(self, pct: float) -> np.ndarray:
        """Vung co mat do >= phan viem `pct` — dinh nghia "vung nong" cho KDE."""
        if not 0 < pct < 100:
            raise ValueError(f"pct phai trong (0, 100), nhan {pct}")
        return self.density >= np.percentile(self.density, pct)


def run_kde(
    df: pd.DataFrame,
    bandwidth_m: float = 100.0,
    grid_size: int = 200,
    *,
    point_cap: int | None = None,
    seed: int = 42,
    padding_m: float = 300.0,
) -> KDEResult:
    """Uoc luong mat do bang kernel Gaussian tren cung toa do phang voi DBSCAN.

    Tham so
    -------
    bandwidth_m : do rong kernel, **met**. Nho -> nhieu cum nho chi tiet hon;
        lon -> mat do bi lam muot.
    grid_size : so o tren moi truc cua luoi uoc luong.
    padding_m : noi dem cac diem vao khung luoi (met).
    """
    import time

    if bandwidth_m <= 0:
        raise ValueError(f"bandwidth_m phai > 0, nhan {bandwidth_m}")
    if len(df) == 0:
        raise ValueError("Khong co diem nao sau khi loc — kiem tra lai khoang gio")

    work = df
    if point_cap and len(df) > point_cap:
        idx = np.random.default_rng(seed).choice(len(df), point_cap, replace=False)
        work = df.iloc[np.sort(idx)]

    coords = work[["x_m", "y_m"]].to_numpy(dtype="float64")
    x_min, y_min = coords.min(axis=0)
    x_max, y_max = coords.max(axis=0)

    grid_x = np.linspace(x_min - padding_m, x_max + padding_m, grid_size)
    grid_y = np.linspace(y_min - padding_m, y_max + padding_m, grid_size)
    mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
    grid_points = np.column_stack([mesh_x.ravel(), mesh_y.ravel()])

    start = time.perf_counter()
    kde = KernelDensity(kernel="gaussian", bandwidth=bandwidth_m).fit(coords)
    density = np.exp(kde.score_samples(grid_points)).reshape(grid_size, grid_size)
    runtime = time.perf_counter() - start

    return KDEResult(
        grid_x=grid_x,
        grid_y=grid_y,
        density=density,
        bandwidth_m=float(bandwidth_m),
        runtime_seconds=runtime,
        coords_m=coords,
        bounds_m=(x_min, y_min, x_max, y_max),
    )