"""Chuyen ket qua thanh lop ban do cho folium.

Khong ve da giac bao quanh cum: ranh gioi DBSCAN khong phai hinh hoc nao,
ve vong tron hay convex hull se doc sai nghiep vu. Chi ve:
  - diem tho (mo)
  - diem theo cum (dac mau)
  - diem nhieu (xam)
  - marker tai trung tam cum
"""

from __future__ import annotations

import json

import folium
import numpy as np
import pandas as pd
from folium.plugins import Draw

from .dbscan import DBSCANResult, HotspotAnalysis
from .filters import SpatialSelection
from .kde import KDEResult

DEFAULT_CENTER = (40.739, -73.974)  # trung tam kich thuoc du lieu
DEFAULT_ZOOM = 11

# 12 mau phan biet duoc tren nen sang; phai doc duoc tren may chiếu
CLUSTER_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
    "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324",
]


def cluster_color(label: int) -> str:
    return CLUSTER_COLORS[int(label) % len(CLUSTER_COLORS)]


def _base_map(center: tuple[float, float], zoom: int) -> folium.Map:
    # Tile OSM khong can API key — quan trong cho buoi thuyet trinh offline
    return folium.Map(
        location=[center[0], center[1]],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )


def _fit_bounds(points: np.ndarray | None, fallback: tuple[float, float]) -> tuple[float, float]:
    """Trung tam ban do theo trung binh toa do cua tap diem.

    Dung trung binh thay vi `fit_bounds` cua folium: ban do phai bao phu
    het vung quan tam, khong phai chi khu vuc trung binh.
    """
    if points is None or len(points) == 0:
        return fallback
    return (float(points[:, 0].mean()), float(points[:, 1].mean()))


def _sample_positions(size: int, limit: int, seed: int) -> np.ndarray:
    if size <= limit:
        return np.arange(size)
    return np.sort(np.random.default_rng(seed).choice(size, limit, replace=False))


def _add_selection_overlay(m: folium.Map, selection: SpatialSelection | None) -> None:
    if selection is None or selection.geometry_json is None:
        return
    folium.GeoJson(
        json.loads(selection.geometry_json),
        name="Pham vi nguoi dung chon",
        style_function=lambda _: {
            "color": "#2563eb",
            "weight": 3,
            "fillColor": "#60a5fa",
            "fillOpacity": 0.08,
            "dashArray": "7,5",
        },
        tooltip="Pham vi loc do nguoi dung ve — khong phai ranh gioi DBSCAN",
    ).add_to(m)


def _fit_custom_selection(m: folium.Map, selection: SpatialSelection | None) -> None:
    if selection is None or selection.geometry_json is None:
        return
    min_lon, min_lat, max_lon, max_lat = selection.geometry.bounds
    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=(20, 20))


def build_raw_map(
    points: pd.DataFrame,
    *,
    center: tuple[float, float] = DEFAULT_CENTER,
    zoom: int = DEFAULT_ZOOM,
    max_points: int = 1_500,
    total_points: int | None = None,
    selection: SpatialSelection | None = None,
    allow_draw: bool = False,
) -> folium.Map:
    """Ban do diem tho truoc khi nguoi dung yeu cau phan tich."""
    m = _base_map(center, zoom)
    shown = _sample_positions(len(points), max_points, seed=0)
    for row in points.iloc[shown].itertuples():
        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=2,
            color=None,
            weight=0,
            fill=True,
            fill_color="#4b5563",
            fill_opacity=0.25,
        ).add_to(m)
    _add_selection_overlay(m, selection)
    _fit_custom_selection(m, selection)
    if allow_draw:
        Draw(
            export=False,
            draw_options={
                "polyline": False,
                "circle": False,
                "circlemarker": False,
                "marker": False,
                "polygon": {"allowIntersection": False},
                "rectangle": True,
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(m)
    if total_points is None:
        count_text = f"hien thi <b>{len(shown):,}</b> diem tham khao"
    else:
        count_text = f"hien thi <b>{len(shown):,}/{total_points:,}</b>"
    legend = (
        f"Diem pickup tho: {count_text}. Bam <b>Tim vung uu tien</b> de chuyen "
        "dam may diem thanh danh sach ngan."
    )
    m.get_root().html.add_child(folium.Element(f"<p style='font-size:12px'>{legend}</p>"))
    return m


def build_hotspot_map(
    analysis: HotspotAnalysis,
    *,
    center: tuple[float, float] = DEFAULT_CENTER,
    zoom: int = DEFAULT_ZOOM,
    max_raw_points: int = 1_000,
    max_noise_points: int = 1_000,
    max_points_per_cluster: int = 250,
    max_other_cluster_points: int = 500,
) -> folium.Map:
    """Ban do quyet dinh: diem tho, cum, noise va marker Top 3."""
    points = analysis.points
    m = _base_map(center, zoom)
    _add_selection_overlay(m, analysis.spatial_selection)
    _fit_custom_selection(m, analysis.spatial_selection)

    raw_positions = _sample_positions(len(points), max_raw_points, seed=0)
    for row in points.iloc[raw_positions].itertuples():
        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=1.5,
            color=None,
            weight=0,
            fill=True,
            fill_color="#4b5563",
            fill_opacity=0.15,
        ).add_to(m)

    noise = points[points["cluster_id"] == -1]
    noise_positions = _sample_positions(len(noise), max_noise_points, seed=1)
    for row in noise.iloc[noise_positions].itertuples():
        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=2,
            color=None,
            weight=0,
            fill=True,
            fill_color="#808080",
            fill_opacity=0.55,
            tooltip="Noise: chua du mat do theo cau hinh nay",
        ).add_to(m)

    clustered = points[points["cluster_id"] != -1]
    top_cluster_ids = set(analysis.top_zones["cluster_id"].astype(int))
    other_clusters = clustered[~clustered["cluster_id"].isin(top_cluster_ids)]
    other_positions = _sample_positions(
        len(other_clusters), max_other_cluster_points, seed=2
    )
    for row in other_clusters.iloc[other_positions].itertuples():
        folium.CircleMarker(
            location=[row.latitude, row.longitude],
            radius=2,
            color=None,
            weight=0,
            fill=True,
            fill_color="#64748b",
            fill_opacity=0.3,
            tooltip="Hotspot ngoài Top 3",
        ).add_to(m)

    top_points = clustered[clustered["cluster_id"].isin(top_cluster_ids)]
    for cluster_id, group in top_points.groupby("cluster_id", sort=True):
        color = cluster_color(int(cluster_id))
        positions = _sample_positions(
            len(group), max_points_per_cluster, seed=int(cluster_id) + 2
        )
        for row in group.iloc[positions].itertuples():
            folium.CircleMarker(
                location=[row.latitude, row.longitude],
                radius=2.5,
                color=color,
                weight=0,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=f"Cum {int(cluster_id)}",
            ).add_to(m)

    for row in analysis.top_zones.itertuples():
        evidence = (
            f"Hotspot {row.rank}: {row.pickup_count:,} pickup lich su; "
            f"xuat hien {row.support_dates}/{row.available_matching_dates} ngay phu hop"
        )
        folium.Marker(
            location=[row.marker_latitude, row.marker_longitude],
            icon=folium.DivIcon(
                html=(
                    "<div style='background:#111827;color:white;border:2px solid white;"
                    "border-radius:50%;width:28px;height:28px;line-height:24px;"
                    f"text-align:center;font-weight:700'>{int(row.rank)}</div>"
                )
            ),
            tooltip=evidence,
        ).add_to(m)

    legend = (
        f"<b>{analysis.n_clusters}</b> hotspot lich su | "
        f"noise <b>{analysis.noise_percentage:.1f}%</b> | "
        f"eps=<b>{analysis.eps_m:.0f}m</b> | MinPts=<b>{analysis.min_samples}</b>. "
        "Chi Top 3 duoc to mau; cac cum con lai duoc lam mo. "
        "So lieu xep hang dung toan bo diem; ban do chi lay mau de hien thi."
    )
    m.get_root().html.add_child(folium.Element(f"<p style='font-size:12px'>{legend}</p>"))
    return m


def build_dbscan_map(
    df: pd.DataFrame,
    result: DBSCANResult,
    *,
    center: tuple[float, float] = DEFAULT_CENTER,
    zoom: int = DEFAULT_ZOOM,
    show_raw: bool = True,
    max_raw_points: int = 2_000,
    max_noise_points: int = 2_000,
    max_points_per_cluster: int = 400,
    raw_opacity: float = 0.25,
) -> folium.Map:
    """Ban do DBSCAN: cum + nhieu + trung tam (khong ve da giac ranh gioi)."""
    frame = df.iloc[: len(result.labels)]
    lat = frame["latitude"].to_numpy()
    lon = frame["longitude"].to_numpy()

    center = _fit_bounds(np.column_stack([lat, lon]), center)
    m = _base_map(center, zoom)
    from folium.plugins import MarkerCluster

    # Lop diem tho mo (gioi han de khong lam treo trinh duyet)
    if show_raw and len(lat) > max_raw_points:
        idx = np.random.default_rng(0).choice(len(lat), max_raw_points, replace=False)
        shown, shown_count = idx, len(idx)
    else:
        shown, shown_count = np.arange(len(lat)), len(lat)

    for i in shown:
        folium.Circle(
            location=[float(lat[i]), float(lon[i])],
            radius=1.5,
            color=None,
            weight=0,
            fill=True,
            fill_color="#555555",
            fill_opacity=raw_opacity,
            tooltip="",
        ).add_to(m)

    # Nhieu: ve mot MarkerCluster de khong tao hang chuc nghin DOM node
    noise_lat, noise_lon = lat[result.noise_mask], lon[result.noise_mask]
    if len(noise_lat):
        from folium.plugins import MarkerCluster

        cluster = MarkerCluster(name="Nhieu (khong thuoc cum nao)").add_to(m)
        for i in np.random.default_rng(1).choice(
            len(noise_lat), min(len(noise_lat), max_noise_points), replace=False
        ):
            folium.CircleMarker(
                location=[float(noise_lat[i]), float(noise_lon[i])],
                radius=2,
                color="#6b6b6b",
                weight=0,
                fill=True,
                fill_color="#8a8a8a",
                fill_opacity=0.7,
            ).add_to(cluster)

    # Cum: mot MarkerCluster theo mau cum. Gioi han so diem ve cho tung cum —
    # ve het 200k diem tao file HTML ~260 MB, trinh duyet khong chiu noi.
    for label in result.cluster_labels:
        sel = result.labels == label
        c_lat, c_lon = lat[sel], lon[sel]
        if len(c_lat) == 0:
            continue
        color = cluster_color(int(label))
        group = MarkerCluster(name=f"Cum {label} ({len(c_lat):,} diem)").add_to(m)

        shown_idx = (
            np.arange(len(c_lat))
            if len(c_lat) <= max_points_per_cluster
            else np.random.default_rng(int(label) + 2).choice(
                len(c_lat), max_points_per_cluster, replace=False
            )
        )
        for i in shown_idx:
            folium.CircleMarker(
                location=[float(c_lat[i]), float(c_lon[i])],
                radius=2.5,
                color=color,
                weight=0,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                tooltip=f"Cum {int(label)}",
            ).add_to(group)

    # Trung tam cum
    for _, row in result.centroids.iterrows():
        label = int(row["cluster_id"])
        folium.Marker(
            location=[row["centroid_latitude"], row["centroid_longitude"]],
            icon=folium.Icon(color="white", icon_color=cluster_color(label), prefix="fa", icon="circle"),
            tooltip=f"Trung tam cum {label}",
        ).add_to(m)

    cluster_total = int((~result.noise_mask).sum())
    legend = (
        f"Cum: <b>{result.n_clusters}</b> ({cluster_total:,} diem) &nbsp;|&nbsp; "
        f"Nhieu: <b>{result.n_noise:,}</b> ({result.noise_pct:.1f}%) &nbsp;|&nbsp; "
        f"eps=<b>{result.eps_m:.0f} m</b> &nbsp;|&nbsp; MinPts=<b>{result.min_samples}</b><br>"
        f"Diem tho hien thi <b>{shown_count:,}/{len(lat):,}</b> de ban do khong bi treo. "
        f"Diem mau chi lay mau de ve — so lieu dung o bang \"Bang so lieu\"."
    )
    m.get_root().html.add_child(folium.Element(f"<p style='font-size:12px'>{legend}</p>"))
    return m


def build_kde_map(
    df: pd.DataFrame,
    kde: KDEResult,
    *,
    center: tuple[float, float] = DEFAULT_CENTER,
    zoom: int = DEFAULT_ZOOM,
    hot_pct: float = 90.0,
) -> folium.Map:
    """Ban do mat do KDE: heatmap + vung nong >= phan viem `hot_pct`.

    Luoi mat do o toa do phang (met); chuyen sang lat/lon de ve len OSM.
    """
    frame = df.iloc[: len(kde.coords_m)]
    center = _fit_bounds(
        np.column_stack([frame["latitude"].to_numpy(), frame["longitude"].to_numpy()]), center
    )
    m = _base_map(center, zoom)

    # Chuyen luoi met -> lat/lon
    # Luoi la 1D theo tung truc (x, y). Do do moi o la 2D [len(y), len(x)]
    # va HeatMap can danh sach (lat, lon, value) theo thu tu ravel.
    lat0 = float(frame["latitude"].mean())
    lon0 = float(frame["longitude"].mean())
    lat_1d = lat0 + (kde.grid_y - kde.grid_y.mean()) / 111_320.0
    lon_1d = lon0 + (kde.grid_x - kde.grid_x.mean()) / (
        111_320.0 * np.cos(np.radians(lat0))
    )
    lat_grid, lon_grid = np.meshgrid(lat_1d, lon_1d, indexing="ij")

    heat = folium.plugins.HeatMap(
        np.column_stack([lat_grid.ravel(), lon_grid.ravel(), kde.density.ravel()]),
        min_opacity=0.15,
        radius=6,
        blur=10,
        gradient={0.0: "#2c7fb8", 0.5: "#fee391", 1.0: "#d7301f"},
    )
    m.add_child(heat)

    # Duong dong vi muc mat do cao — vung nong theo nghinhgia
    contour = kde.peak_density
    if contour > 0:
        threshold = float(np.percentile(kde.density, hot_pct))
        level = np.array([threshold])
        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            cs = ax.contour(lon_grid, lat_grid, kde.density, levels=level)
            for path in cs.get_paths():
                verts = path.vertices
                if len(verts) >= 3:
                    folium.PolyLine(
                        locations=[[float(v[0]), float(v[1])] for v in verts],
                        color="#7a0177",
                        weight=2,
                        fill=False,
                        tooltip=f"Vung nong (top {100 - hot_pct:.0f}% mat do)",
                    ).add_to(m)
            plt.close(fig)
        except ImportError:
            pass

    legend = (
        f"KDE: mat do lien tuc, bandwidth={kde.bandwidth_m:.0f} m &nbsp;|&nbsp; "
        f"duong tim = vung nong top {100 - hot_pct:.0f}% &nbsp;|&nbsp; "
        f"{len(kde.coords_m):,} diem"
    )
    m.get_root().html.add_child(folium.Element(f"<p style='font-size:12px'>{legend}</p>"))
    return m


def build_map(*args, **kwargs):
    """Alias de gom import mot cho ca app."""
    return build_dbscan_map(*args, **kwargs)
