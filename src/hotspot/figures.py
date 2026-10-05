"""Ve anh bang matplotlib — khong can Streamlit, khong can mang.

O day dung `nyc_boroughs.geojson` lam nen de ve ranh gioi hanh chinh 5 quan.
Khong ve duong phot (tile OSM) de hinh chay duoc **offline** va khong can
API key.

Moi toa do deu ve trong he phang `x_m`/`y_m` cua preprocessing, nen truc tung
la met va khong bi meo — nguoi xem do duoc truc tiep quy mo cua `eps`.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.lines import Line2D
from shapely.geometry import shape

from .dbscan import DBSCANResult, run_dbscan

BOROUGHS_FILE = "nyc_boroughs.geojson"
BOROUGHS_COLORS = {
    "Manhattan": "#f6c99a",
    "Brooklyn": "#8ec4e8",
    "Queens": "#8fd0a8",
    "Bronx": "#f2a6a6",
    "Staten Island": "#c9b0e8",
}

# 12 mau doc duoc tren nen sang va tren may chieu
CLUSTER_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
    "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324",
]

NOISE_COLOR = "#9aa0a6"

# Mau nen: nuoc xanh nhat, dat la mau quan. Ve mau dat DUC (khong trong suot)
# de duoc nhin ra la ban do — neu de trong suot, hang nghin diem xam se xoa
# sach nen va hinh ra mot dam mau cham.
WATER_COLOR = "#cfe3f2"
LAND_EDGE = "#2f3e4e"


def cluster_color(label: int) -> str:
    return CLUSTER_COLORS[int(label) % len(CLUSTER_COLORS)]


# --------------------------------------------------------------------------- #
# Nen: ranh gioi 5 quan
# --------------------------------------------------------------------------- #
def load_borough_rings(
    data_dir: str | Path,
    lat0: float,
    lon0: float,
) -> dict[str, list[np.ndarray]]:
    """Doc geojson va CHIEU sang cung he toa do met voi du lieu.

    Tra {ten quan: [mang toa do, ...]} theo thu tu X, Y.

    `lat0`/`lon0` phai khop tham so ma preprocessing dung. Doc tu
    `outputs/preprocess_report.json` (khoa "full" -> "projection").
    Neu khong khop, polygon se nam ngoai khung hinh va nen se bien mat —
    nen ham nay KHONG tu chon lat0/lon0 ma doi hinh du khong bao gio dung.
    """
    from preprocess import to_metric

    path = Path(data_dir) / BOROUGHS_FILE
    if not path.exists():
        raise FileNotFoundError(f"Thieu {path}. Chay: bash scripts/download_data.sh")

    out: dict[str, list[np.ndarray]] = {}
    for feat in json.loads(path.read_text())["features"]:
        name = feat["properties"]["BoroName"]
        geom = shape(feat["geometry"])
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        rings = []
        for poly in polys:
            for ring in [poly.exterior, *poly.interiors]:
                coords = np.asarray(ring.coords)
                xy = to_metric(coords[:, 1], coords[:, 0], lat0, lon0)
                rings.append(xy)
        out[name] = rings
    return out


def projection_origin(report_path: str | Path) -> tuple[float, float]:
    """Doc (lat0, lon0) tu bao cao cua preprocessing."""
    path = Path(report_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Thieu {path}. Chay: python -m src.preprocess --full"
        )
    proj = json.loads(path.read_text())["full"]["projection"]
    return float(proj["lat0"]), float(proj["lon0"])


def draw_boroughs(ax, rings: dict[str, list[np.ndarray]]) -> None:
    """To nen cac quan — mat dat DUC, vien dam. Dat nen truoc khi ve diem."""
    ax.set_facecolor(WATER_COLOR)
    for name, polys in rings.items():
        fill = BOROUGHS_COLORS.get(name, "#eeeeee")
        for i, poly in enumerate(polys):
            ax.fill(poly[:, 0], poly[:, 1], facecolor=fill, edgecolor=LAND_EDGE,
                    linewidth=1.8 if i == 0 else 0.6, zorder=1, alpha=0.95)


def borough_labels(
    ax,
    rings: dict[str, list[np.ndarray]],
    fontsize: int = 10,
    *,
    clip_to_view: bool = False,
) -> None:
    """Ten quan o giua polygon lon nhat. Bo qua quan qua nho de khong dong chu.

    `clip_to_view=True` bo qua ten quan nam ngoai khung hinh — can khi zoom
    vao mot vung con, neu khong chu se tran ra panel ben canh.
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    for name, polys in rings.items():
        big = max(polys, key=len)
        # NumPy 2 da xoa ndarray.ptp() -> phai dung np.ptp()
        if np.ptp(big[:, 1]) <= 2000 or np.ptp(big[:, 0]) <= 2000:
            continue
        cx, cy = big[:, 0].mean(), big[:, 1].mean()
        if clip_to_view and not (x0 < cx < x1 and y0 < cy < y1):
            continue
        ax.text(cx, cy, name, ha="center", va="center", fontsize=fontsize,
                color="#333333", zorder=2, weight="bold",
                path_effects=[pe.withStroke(linewidth=3, foreground="white")])


# --------------------------------------------------------------------------- #
# Ve mot khung hinh DBSCAN
# --------------------------------------------------------------------------- #
def plot_clusters(
    ax,
    df: pd.DataFrame,
    result: DBSCANResult,
    rings: dict[str, list[np.ndarray]],
    *,
    max_points_per_cluster: int = 900,
    max_noise: int = 2_500,
    point_size: float = 1.6,
    annotate_top: int = 0,
) -> None:
    draw_boroughs(ax, rings)

    frame = df.iloc[: len(result.labels)]
    x = frame["x_m"].to_numpy()
    y = frame["y_m"].to_numpy()

    # Nhieu ve truoc, xam va rat mo — chi de thay hinh dang chung cua du lieu
    noise = result.noise_mask
    ax.scatter(x[noise], y[noise], s=0.5, c=NOISE_COLOR, alpha=0.18,
               linewidths=0, zorder=3)

    rng = np.random.default_rng(42)
    for label in result.cluster_labels:
        sel = result.labels == label
        xs, ys = x[sel], y[sel]
        if len(xs) > max_points_per_cluster:
            idx = rng.choice(len(xs), max_points_per_cluster, replace=False)
            xs, ys = xs[idx], ys[idx]
        ax.scatter(xs, ys, s=point_size, c=cluster_color(label), alpha=0.85,
                   linewidths=0, zorder=4)

    if annotate_top and not result.centroids.empty:
        top = result.centroids.nlargest(min(annotate_top, len(result.centroids)), "pickup_count")
        for _, row in top.iterrows():
            label = int(row["cluster_id"])
            ax.scatter(row["centroid_x_m"], row["centroid_y_m"], marker="*", s=210,
                       c=cluster_color(label), edgecolors="black", linewidths=0.7,
                       zorder=6)
            # Nhan dat sang trai/phai cho khong de len cum khac
            ax.annotate(
                f"#{label} · {int(row['pickup_count']):,} chuyến",
                (row["centroid_x_m"], row["centroid_y_m"]),
                textcoords="offset points", xytext=(14, 10), fontsize=9.5,
                weight="bold", color="black", zorder=7,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=cluster_color(label),
                          lw=1.4, alpha=0.95),
                arrowprops=dict(arrowstyle="-", color=cluster_color(label), lw=1.4),
            )


def _finalize(ax, title: str, subtitle: str = "") -> None:
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor("#bbbbbb")
    ax.set_title(title, fontsize=11.5, weight="bold", pad=6)
    if subtitle:
        ax.text(0.5, -0.02, subtitle, transform=ax.transAxes, ha="center",
                va="top", fontsize=8.5, color="#555555")


# --------------------------------------------------------------------------- #
# Hinh 1: luoi quet eps — anh tinh cho slide
# --------------------------------------------------------------------------- #
def plot_eps_sweep(
    df: pd.DataFrame,
    eps_list: list[int],
    min_samples: int,
    rings: dict[str, list[np.ndarray]],
    *,
    title: str = "Ảnh hưởng của eps — cùng dữ liệu, chỉ đổi bán kính lân cận",
    subtitle: str = "",
    ncols: int = 4,
    focus: tuple[float, float, float, float] | None = None,
    show_borough_labels: bool = True,
) -> tuple[plt.Figure, list[DBSCANResult]]:
    """Luoi anh: moi panel mot gia tri eps, cung mot tap diem.

    `focus` = (x_min, x_max, y_min, y_max) theo met de zoom vao vung can xem.
    Khong doi data giua cac panel nen moi thay doi chay hoan toan tu `eps`.
    """
    nrows = int(np.ceil(len(eps_list) / ncols))
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(4.3 * ncols, 4.9 * nrows), squeeze=False
    )
    flat = [ax for row in axes for ax in row]

    results = []
    for ax, eps in zip(flat, eps_list):
        res = run_dbscan(df, eps, min_samples)
        results.append(res)
        plot_clusters(ax, df, res, rings)
        if focus:
            ax.set_xlim(focus[0], focus[1])
            ax.set_ylim(focus[2], focus[3])
        if show_borough_labels:
            # Dat gioi truoc do lenh nay de loc duoc ten quan ra ngoai khung
            borough_labels(ax, rings, fontsize=9, clip_to_view=True)
        _finalize(
            ax,
            f"eps = {eps} m",
            f"{res.n_clusters} cụm · {res.noise_pct:.1f}% nhiễu",
        )
    for ax in flat[len(eps_list):]:
        ax.set_visible(False)

    handles = [
        Line2D([], [], marker="o", ls="", color=CLUSTER_COLORS[0], label="Cụm",
               markersize=7, markerfacecolor=CLUSTER_COLORS[0]),
        Line2D([], [], marker="o", ls="", color=NOISE_COLOR,
               label="Nhiễu (điểm bị loại)", markersize=7),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False,
               fontsize=11, bbox_to_anchor=(0.5, -0.005))

    # Khoang trong cho tieu de + phu de + chu giai thich, RO khi ve anh
    fig.tight_layout(rect=(0, 0.035, 1, 0.90), h_pad=2.6, w_pad=1.2)
    fig.suptitle(title, fontsize=15, weight="bold", y=0.985)
    if subtitle:
        fig.text(0.5, 0.935, subtitle, ha="center", fontsize=10.5, color="#444444")
    return fig, results


# --------------------------------------------------------------------------- #
# Hinh 2: animation quet eps — GIF
# --------------------------------------------------------------------------- #
def animate_eps_sweep(
    df: pd.DataFrame,
    eps_list: list[int],
    min_samples: int,
    rings: dict[str, list[np.ndarray]],
    out_path: str | Path,
    *,
    fps: int = 2,
    dpi: int = 110,
    tail: int = 2,
) -> list[DBSCANResult]:
    """Ghi GIF: cac cum tach nho roi dan dinh lai khi eps tang.

    Dung so diem goc nho (vai nghin) de moi khung ve duoc nhanh — neu ve
    200.000 diem moi khung, GIF se rat nang va nguoi xem phai doi.

    Kh dung `FuncAnimation` cua matplotlib: API do phai khoi tao qua
    `setup()` va de bi sai khi goi thuong. Voi GIF ta tu ve tung khung
    bang PIL, gon hon va khong phu thuoc phien ban matplotlib.
    """
    from io import BytesIO

    from PIL import Image

    fig, ax = plt.subplots(figsize=(7.4, 8.2))

    def render(res: DBSCANResult) -> Image.Image:
        ax.clear()
        draw_boroughs(ax, rings)
        borough_labels(ax, rings)
        plot_clusters(ax, df, res, rings, max_points_per_cluster=350,
                      max_noise=900, point_size=1.3)
        _finalize(
            ax, f"eps = {res.eps_m:.0f} m",
            f"{res.n_clusters} cum · {res.noise_pct:.1f}% nhieu · MinPts={res.min_samples}",
        )
        buf = BytesIO()
        fig.savefig(buf, dpi=dpi, format="png", bbox_inches="tight")
        buf.seek(0)
        return Image.open(buf).convert("P", palette=Image.ADAPTIVE)

    # Tinh het truoc: GIF co toc do on dinh, khong co khung nao "dung lai"
    results = []
    frames: list[Image.Image] = []
    for eps in eps_list:
        res = run_dbscan(df, eps, min_samples)
        results.append(res)
        frames.append(render(res))
        print(f"  khung eps={eps} m: {res.n_clusters} cum, {res.noise_pct:.1f}% nhieu")

    if tail:
        # Giu khung cuoi them mot luc cho nguoi xem kip
        frames = frames + [frames[-1]] * 2

    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
    )
    plt.close(fig)
    return results


# --------------------------------------------------------------------------- #
# Hinh 3: mot ban do lon, co nhan top cum
# --------------------------------------------------------------------------- #
def plot_hotspot_map(
    df: pd.DataFrame,
    result: DBSCANResult,
    rings: dict[str, list[np.ndarray]],
    *,
    title: str,
    subtitle: str = "",
    annotate_top: int = 3,
    figsize: tuple[float, float] = (13, 14),
    pad_m: float = 1_500,
    show_borough_labels: bool = True,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=figsize)
    plot_clusters(ax, df, result, rings, max_points_per_cluster=1600,
                  max_noise=6000, point_size=2.0, annotate_top=annotate_top)

    if show_borough_labels:
        borough_labels(ax, rings, fontsize=12)

    # Crop theo du lieu + vien, dung aspect bang nhau de khong meo
    frame = df.iloc[: len(result.labels)]
    x, y = frame["x_m"].to_numpy(), frame["y_m"].to_numpy()
    ax.set_xlim(x.min() - pad_m, x.max() + pad_m)
    ax.set_ylim(y.min() - pad_m, y.max() + pad_m)

    _finalize(ax, title, subtitle)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# Hinh 4: duong doi thuan doi tham so
# --------------------------------------------------------------------------- #
def plot_parameter_tradeoff(
    df: pd.DataFrame,
    eps_list: list[int],
    min_samples: int,
    *,
    min_pts_list: list[int] | None = None,
) -> tuple[plt.Figure, pd.DataFrame]:
    """So cum / %nhieu / %diem-trong-cum-lon-nhat theo eps (va MinPts)."""
    from .summaries import cluster_table

    min_pts_list = min_pts_list or [min_samples]
    rows = []
    for mp in min_pts_list:
        for eps in eps_list:
            res = run_dbscan(df, eps, mp)
            table = cluster_table(df, res, with_area=False)
            total = table["pickup_count"].sum() if len(table) else 0
            rows.append(
                {
                    "eps_m": eps,
                    "MinPts": mp,
                    "n_clusters": res.n_clusters,
                    "noise_pct": round(res.noise_pct, 2),
                    "top_share_pct": round(100 * table["pickup_count"].iloc[0] / total, 1)
                    if total else None,
                    "runtime_s": round(res.runtime_seconds, 2),
                }
            )
    data = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    for mp in min_pts_list:
        sub = data[data.MinPts == mp]
        axes[0].plot(sub.eps_m, sub.n_clusters, marker="o", label=f"MinPts={mp}")
        axes[1].plot(sub.eps_m, sub.noise_pct, marker="s", label=f"MinPts={mp}")
        axes[2].plot(sub.eps_m, sub.top_share_pct, marker="^", label=f"MinPts={mp}")

    for ax, ylab, title in zip(
        axes,
        ["Số cụm", "Tỉ lệ nhiễu (%)", "Cụm lớn nhất chiếm (%)"],
        ["Số cụm tìm được", "Tỉ lệ điểm bị loại", "Một cụm chiếm bao nhiêu % dữ liệu"],
    ):
        ax.set_xlabel("eps (mét)")
        ax.set_ylabel(ylab)
        ax.set_title(title, fontsize=11.5)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9)
    plt.tight_layout()
    return fig, data


# --------------------------------------------------------------------------- #
# Hinh 5: phan bo theo quan + bang xep rank
# --------------------------------------------------------------------------- #
def plot_borough_distribution(df: pd.DataFrame) -> tuple[plt.Figure, pd.DataFrame]:
    counts = (
        df["borough"].value_counts().rename_axis("Quận").to_frame("Số chuyến")
        .sort_values("Số chuyến", ascending=False)
    )
    counts["Tỉ lệ (%)"] = (counts["Số chuyến"] / counts["Số chuyến"].sum() * 100).round(2)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    colors = [BOROUGHS_COLORS.get(q, "#cccccc") for q in counts.index]
    axes[0].bar(counts.index, counts["Số chuyến"], color=colors)
    for i, v in enumerate(counts["Số chuyến"]):
        axes[0].annotate(f"{int(v):,}", (i, v), ha="center", va="bottom", fontsize=9)
    axes[0].set_title("Số chuyến đón theo quận")
    axes[0].set_ylabel("Số chuyến")
    axes[0].tick_params(axis="x", rotation=25)

    axes[1].barh(counts.index[::-1], counts["Số chuyến"][::-1], color=colors[::-1])
    axes[1].set_title("Cùng dữ liệu — xếp ngược để dễ so sánh")
    axes[1].set_xlabel("Số chuyến")

    fig.tight_layout()
    return fig, counts