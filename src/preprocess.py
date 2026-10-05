"""Preprocessing cho bai "Xac dinh hotspot don khach" (density-based / DBSCAN).

Module nay la nguon su that nhat: ca notebook EDA, notebook clustering va CLI
 deu goi cac ham o day, khong copy-paste. Moi ham:

  - khong mutate tham so dau vao (bat bien)
  - ghi so dong vao/ra vao `report` de truy vet
  - co `assert` cho tinh dung dac (khong chi print)

Mot so quy uoc bat buoc cho nghiep vu:
  - KHONG z-score toa do lat/lon (se pha vung khong gian)
  - Tinh moi do trong he phang don vi MET, khong dung Euclid tren do
  - Frame phang dung phieu azimuthal equidistant, sai so < 0.001% tren
    toan bo NYC (do so bang cach cua cell kiem chung trong 01_eda_overview)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

EARTH_R = 6_371_000.0

# Bounding box thanh pho New York. CHI dung lam chi so QC va fallback khi
# khong co file polygon — khong con la quy tac loai chinh.
# (xem `RegionMask` va muc "Quy tac vung hop le")
NYC_BBOX = (40.4774, -74.2591, 40.9176, -73.7004)  # lat_min, lon_min, lat_max, lon_max

# Ranh gioi hanh chinh 5 quan cua NYC. Day la quy tac loc chinh vi:
#   - co y nghia hanh chinh -> bao cao hotspot theo quan duoc
#   - loai sach diem ngoai khoi o ngoai bien (tu ~1.8 km den 190 km)
# Do khac biet so voi bbox: loai them 90.521 diem, trong do 45.772 la
# Jersey City/Hoboken (ben kia song Hudson) va 36.003 la EWR.
BOROUGHS_FILE = "nyc_boroughs.geojson"

# EWR (Newark Liberty) nam o New Jersey — khong thuoc 5 borough NYC nhung la
# san bay don khach lon (36.003 chuyen). Hop nhat bang hop 5 km quanh san bay.
# Do do o day dung HOP (bounding box) chu khong phai polygon vi khong co
# polygon san bay san co trong du lieu.
EWR_BOX = (-74.30, 40.64, -74.10, 40.75)  # lon_min, lat_min, lon_max, lat_max

MONDAY, SATURDAY = 0, 5

PEAK_HOURS = (17, 19)  # khoang 17:00-19:00 (gio 18 khong thuoc khoang nay)
MORNING_HOURS = (8, 10)
NIGHT_HOURS = (0, 4)

# pandas dayofweek: 0 = Thu Hai ... 5 = Thu Bay, 6 = Chu Nhat
DOW_LABELS = {
    0: "Thu Hai",
    1: "Thu Ba",
    2: "Thu Tu",
    3: "Thu Nam",
    4: "Thu Sau",
    5: "Thu Bay",
    6: "Chu Nhat",
}


@dataclass(frozen=True)
class PreprocessConfig:
    """Cau hinh mot 'ca' phan tich — dau vao cua `build`."""

    name: str
    hours: tuple[int, int] = PEAK_HOURS  # [start, end) theo gio
    dow: tuple[int, ...] = (SATURDAY,)  # 0 = Thu Hai ... 6 = Chu Nhat
    region: str | None = "manhattan"  # ten vung phan tich, xem REGIONS
    sample_n: int | None = None
    seed: int = 42
    raw_files: tuple[str, ...] | None = None  # None = tat ca file *14.csv

    def describe(self) -> str:
        h0, h1 = self.hours
        days = ", ".join(DOW_LABELS[d] for d in self.dow)
        return f"{self.name}: {days} {h0:02d}:00-{h1:02d}:00"


SCENARIOS: dict[str, PreprocessConfig] = {
    "ca_diem_t7_manhattan": PreprocessConfig(
        name="ca_diem_t7_manhattan", hours=PEAK_HOURS, dow=(SATURDAY,), region="manhattan"
    ),
    "ca_diem_t7_toan_bo": PreprocessConfig(
        name="ca_diem_t7_toan_bo", hours=PEAK_HOURS, dow=(SATURDAY,), region="nyc"
    ),
    "ca_sang_t2_manhattan": PreprocessConfig(
        name="ca_sang_t2_manhattan", hours=MORNING_HOURS, dow=(MONDAY,), region="manhattan"
    ),
    "dem_thu7_manhattan": PreprocessConfig(
        name="dem_thu7_manhattan", hours=NIGHT_HOURS, dow=(SATURDAY,), region="manhattan"
    ),
}

RAW_COLUMNS = ["Date/Time", "Lat", "Lon", "Base"]
OUT_COLUMNS = [
    "pickup_time",
    "lat",
    "lon",
    "base",
    "source",
    "x_m",
    "y_m",
    "hour",
    "dow",
    "borough",
]


# --------------------------------------------------------------------------- #
# 1. Nap du lieu tho
# --------------------------------------------------------------------------- #
def load_raw(data_dir: Path, files: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Doc cac file CSV thang, chuan hoa ten cot va kieu du lieu.

    Ghi chu: mot so dong co them giay ('... 0:03:00') nen dung format="mixed".
    """
    data_dir = Path(data_dir)
    if files is None:
        paths = sorted(data_dir.glob("*14.csv"))
    else:
        paths = [data_dir / f for f in files]
    if not paths:
        raise FileNotFoundError(
            f"Khong tim thay file du lieu trong {data_dir}. Chay: bash scripts/download_data.sh"
        )

    frames = []
    for path in paths:
        chunk = pd.read_csv(
            path,
            usecols=RAW_COLUMNS,
            dtype={"Lat": "float64", "Lon": "float64", "Base": "category"},
        )
        chunk = chunk.rename(columns={"Date/Time": "pickup_time", "Lat": "lat", "Lon": "lon"})
        chunk["pickup_time"] = pd.to_datetime(chunk["pickup_time"], format="mixed", dayfirst=False)
        chunk["source"] = path.stem.replace("uber-raw-data-", "")
        frames.append(chunk)
        print(f"  doc {path.name:12s} {len(chunk):>10,} dong")

    out = pd.concat(frames, ignore_index=True)
    return out[["pickup_time", "lat", "lon", "Base", "source"]].rename(
        columns={"Base": "base"}
    )


# --------------------------------------------------------------------------- #
# 2. Vung hop le: polygon 5 borough + ngoai le EWR
# --------------------------------------------------------------------------- #
class RegionMask:
    """Quy tac xac dinh diem don nam trong vung nghiep vu.

    Vung hop le = 5 borough NYC (polygon hanh chinh) + hop 5 km quanh EWR.

    Do do tren toan bo 4.534.327 diem cua du lieu:
        bbox NYC thuan ......... giu 4.502.415
        5 borough polygon ...... giu 4.411.894  (loai 90.521)
        + hop EWR .............. giu 4.449.041  (them lai 37.147)

    Polygon la tap con cua bbox: khong bo diem nao nam trong polygon ma
    lai nam ngoai bbox. 90.521 diem bi loai gom 45.772 diem Jersey
    City/Hoboken va ~21.000 diem rai rac tren bien. Xem README muc
    "Quy tac vung hop le" truoc khi mo rong pham vi.
    """

    def __init__(self, data_dir: Path, include_ewr: bool = True):
        self.data_dir = Path(data_dir)
        self.include_ewr = include_ewr
        self._cache: dict[str, shapely.geometry.base.BaseGeometry] = {}

    def boroughs(self) -> dict[str, shapely.geometry.base.BaseGeometry]:
        """Dict {ten quan: polygon}. Doc file geojson (2.9 MB, 95 vong)."""
        if not self._cache:
            import json

            path = self.data_dir / BOROUGHS_FILE
            if not path.exists():
                raise FileNotFoundError(
                    f"Thieu {path}. Chay: bash scripts/download_data.sh"
                )
            geo = json.loads(path.read_text())
            self._cache = {f["properties"]["BoroName"]: shape(f["geometry"]) for f in geo["features"]}
        return self._cache

    @property
    def all_boroughs(self) -> shapely.geometry.base.BaseGeometry:
        """Hop nhat 5 quan thanh mot polygon don le."""
        if not hasattr(self, "_union"):
            self._union = unary_union(list(self.boroughs().values()))
        return self._union

    @property
    def valid_region(self) -> shapely.geometry.base.BaseGeometry:
        """Vung hop le dung de KIEM TRA gia tri (diem co nam trong pham vi nghiep vu khong)."""
        if not hasattr(self, "_valid"):
            parts = [self.all_boroughs]
            if self.include_ewr:
                lon_min, lat_min, lon_max, lat_max = EWR_BOX
                parts.append(shapely.geometry.box(lon_min, lat_min, lon_max, lat_max))
            self._valid = unary_union(parts)
        return self._valid

    def inside(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Mask vector hoa: True neu diem nam trong vung hop le."""
        return shapely.contains_xy(self.valid_region, lon, lat)

    def label(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Ten quan cho tung diem; 'EWR' cho hop san bay, 'ngoai_vung' cho phan con lai.

        Diem nam tren bien do (borrowed cap) co the khong khop quan nao —
        gan 'ngoai_vung' thay vi ban None de moi do duong su dung duoc.
        """
        out = np.full(len(lat), "ngoai_vung", dtype=object)
        for name, geom in self.boroughs().items():
            out[shapely.contains_xy(geom, lon, lat)] = name
        if self.include_ewr:
            lon_min, lat_min, lon_max, lat_max = EWR_BOX
            in_ewr = (
                (lon > lon_min) & (lon < lon_max) & (lat > lat_min) & (lat < lat_max)
            )
            out[in_ewr] = "EWR"
        return out


# Vung dung cho PHAN TICH — khac voi `valid_region` (vung hop le de kiem tra).
# "nyc" = 5 borough, KHONG gom EWR: kich ban nay dung de so sanh mat do giua
# cac quan nen phai cung mot pham vi cho ca 5 quan.
# Muon dua EWR vao kich ban, dung region="valid" (xem region_geometry).
REGIONS = ("valid", "nyc", "manhattan", "bronx", "queens", "brooklyn", "staten_island")


def region_geometry(name: str | None, mask: RegionMask) -> shapely.geometry.base.BaseGeometry | None:
    """Polygon cua vung phan tich. None = khong gioi han them (van dung valid_region)."""
    if name is None:
        return None
    if name == "valid":
        return mask.valid_region
    if name == "nyc":
        return mask.all_boroughs
    key = name.replace("_", " ").title()
    geoms = mask.boroughs()
    if key not in geoms:
        raise KeyError(f"Vung '{name}' khong ton tai. Chon: {REGIONS} hoac None")
    return geoms[key]


def coordinate_masks(
    df: pd.DataFrame,
    bbox: tuple[float, float, float, float] = NYC_BBOX,
    mask: RegionMask | None = None,
) -> dict[str, pd.Series]:
    """Tra ve cac mask loi toa do.

    `ngoai_vung_bo_anh` la mask LOAI THAT SU (dunga polygon).
    `ngoai_bien_gioi` chi la chi so QC, khong dung de loc — xem README.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    lat, lon = df["lat"], df["lon"]
    out = {
        "thieu_toa_do": lat.isna() | lon.isna(),
        "toa_do_0_0": (lat == 0) & (lon == 0),
        "ngoai_bien_gioi": ~(
            lat.between(lat_min, lat_max) & lon.between(lon_min, lon_max)
        ),
    }
    if mask is not None:
        # Diem thieu toa do se ra False o contains_xy -> gan True de chắc chắn bi loai
        bad_null = out["thieu_toa_do"] | out["toa_do_0_0"]
        inside = mask.inside(lat.fillna(0).to_numpy(), lon.fillna(0).to_numpy())
        out["ngoai_vung_bo_anh"] = pd.Series(~inside, index=df.index) | bad_null
    return out


def clean_coordinates(
    df: pd.DataFrame,
    mask: RegionMask | None = None,
    report: dict | None = None,
) -> pd.DataFrame:
    """Loai diem khong dung toa do: thieu, (0, 0), hoac ngoai vung hop le.

    Diem (0, 0) la vi tri GPS mac dinh khi loi -> nam o Guinea, khong phai NYC.
    Neu `mask` la None thi fallback sang kiem tra theo bbox (chi so QC).
    """
    masks = coordinate_masks(df, NYC_BBOX, mask)
    # Chi 3 mask nay loai that su; `ngoai_bien_gioi` chi de bao cao
    reject_keys = ["thieu_toa_do", "toa_do_0_0"] + (
        ["ngoai_vung_bo_anh"] if "ngoai_vung_bo_anh" in masks else ["ngoai_bien_gioi"]
    )
    bad = np.logical_or.reduce([masks[k].to_numpy() for k in reject_keys])

    if report is not None:
        step = {"vao": len(df), "ra": int((~bad).sum())}
        for key, m in masks.items():
            step[key] = int(m.sum())
        step["bi_loai_tong"] = int(bad.sum())
        step["quy_tac"] = (
            f"polygon_5_borough{'_va_EWR' if mask and mask.include_ewr else ''}"
            if mask
            else "bbox"
        )
        report["toi_buoc_loc_toa_do"] = step

    return df.loc[~bad].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 3. Dac trung thoi gian
# --------------------------------------------------------------------------- #
def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Thoi gian + cac dac trung dung duoc cho viec cat khung gio/ngay."""
    out = df.copy()
    out["hour"] = out["pickup_time"].dt.hour
    out["dow"] = out["pickup_time"].dt.dayofweek
    out["date"] = out["pickup_time"].dt.date
    out["month"] = out["pickup_time"].dt.month
    out["is_weekend"] = out["dow"] >= 5
    out["is_peak"] = out["hour"].between(PEAK_HOURS[0], PEAK_HOURS[1] - 1)
    return out


# --------------------------------------------------------------------------- #
# 4. Chieu sang he phang don vi met
# --------------------------------------------------------------------------- #
def to_metric(
    lat: np.ndarray,
    lon: np.ndarray,
    lat0: float,
    lon0: float,
    radius: float = EARTH_R,
) -> np.ndarray:
    """Chieu azimuthal equidistant (mat cau) sang he phang, don vi MET.

    Da so sanh 3 phep chieu tren du lieu that:
        equirectangular cos(lat0)      max sai so ~0.18%
        equirectangular cos(lat)       max sai so ~0.16%
        azimuthal equidistant          max sai so ~0.00015%   <- chon cach nay

    Do phieu nay kinh diem, sai so rat nho ngay ca o 60 km, nen doc
    `eps` theo met cho truc tiep va khong phai chinh lai.
    """
    la = np.radians(lat)
    lo = np.radians(lon - lon0)
    la0 = np.radians(lat0)
    cos_c = np.sin(la0) * np.sin(la) + np.cos(la0) * np.cos(la) * np.cos(lo)
    c = np.arccos(np.clip(cos_c, -1.0, 1.0))
    k = np.where(c < 1e-12, 1.0, c / np.sin(np.where(c < 1e-12, 1.0, c)))
    x = radius * k * np.cos(la) * np.sin(lo)
    y = radius * k * (np.cos(la0) * np.sin(la) - np.sin(la0) * np.cos(la) * np.cos(lo))
    return np.column_stack([x, y])


def haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Khoang cach truc tiep (met) giua hai diem, vector hoa ca hai dau vao."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def projection_error(
    coords: np.ndarray,
    df: pd.DataFrame,
    lat0: float,
    lon0: float,
    n_pairs: int = 20_000,
    seed: int = 42,
    min_distance_m: float = 100.0,
) -> dict[str, float]:
    """Do sai so gia khoang cach Euclid tren he phang va khoang cach haversine.

    Chi xet cac cap diem cach nhau >= `min_distance_m`: sai so tuong doi bay
    len khi hai diem gan nhau, trong khi thu do cua bai la thuoc dia 100 m.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    i, j = rng.integers(0, n, n_pairs), rng.integers(0, n, n_pairs)
    lat = df["lat"].to_numpy()
    lon = df["lon"].to_numpy()
    d_true = haversine_m(lat[i], lon[i], lat[j], lon[j])
    d_proj = np.hypot(coords[i, 0] - coords[j, 0], coords[i, 1] - coords[j, 1])

    far = d_true >= min_distance_m
    rel = np.abs(d_proj[far] - d_true[far]) / d_true[far]
    return {
        "n_pairs": int(far.sum()),
        "mean_pct": float(rel.mean() * 100),
        "p99_pct": float(np.percentile(rel, 99) * 100),
        "max_pct": float(rel.max() * 100),
    }


# --------------------------------------------------------------------------- #
# 5. Cat khung gio / ngay / vung
# --------------------------------------------------------------------------- #
def filter_window(
    df: pd.DataFrame,
    hours: tuple[int, int] = PEAK_HOURS,
    dow: tuple[int, ...] = (SATURDAY,),
    region: shapely.geometry.base.BaseGeometry | None = None,
    report: dict | None = None,
) -> pd.DataFrame:
    """Cat theo gio [start, end), ngay trong tuan va (neu co) vung phan tich.

    `region` la polygon. Dung polygon thay vi bbox de ranh gioi bam dung
    dia hinh — bbox cat cut diem don o mep vung (vd: cau Brooklyn, ven song).
    """
    h0, h1 = hours
    mask = df["hour"].between(h0, h1 - 1) & df["dow"].isin(dow)

    if region is not None:
        lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
        mask &= pd.Series(shapely.contains_xy(region, lon, lat), index=df.index)

    out = df.loc[mask]
    if report is not None:
        report["cat_khung_gio_ngay_vung"] = {"vao": len(df), "ra": len(out)}
    return out.reset_index(drop=True)


def sample_points(
    df: pd.DataFrame,
    n: int | None,
    seed: int = 42,
    report: dict | None = None,
) -> pd.DataFrame:
    """Lay mau ngau nhien co seed cot dinh (de ket qua lap lai duoc)."""
    if n is None or len(df) <= n:
        if report is not None:
            report["lay_mau"] = {"vao": len(df), "ra": len(df), "n_yeu_cau": n}
        return df
    idx = np.random.default_rng(seed).choice(len(df), n, replace=False)
    out = df.iloc[np.sort(idx)]
    if report is not None:
        report["lay_mau"] = {"vao": len(df), "ra": len(out), "n_yeu_cau": n}
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 6. Pipeline day du
# --------------------------------------------------------------------------- #
@dataclass
class BuildResult:
    points: pd.DataFrame
    coords: np.ndarray
    report: dict = field(default_factory=dict)

    @property
    def lat0(self) -> float:
        return float(self.report["projection"]["lat0"])

    @property
    def lon0(self) -> float:
        return float(self.report["projection"]["lon0"])


def prepare_raw(
    data_dir: Path,
    raw_files: tuple[str, ...] | None = None,
    verbose: bool = True,
    region_mask: RegionMask | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Buoc dung chung cho moi kich ban: doc + loc toa do loi + them dac trung thoi gian.

    Tach rieng de khi chay nhieu kich ban thi chi doc du lieu MOT LAN
    (6 file ~750 MB, doc lai 4 lan ton~3 phut thua).
    """
    raw = load_raw(data_dir, raw_files)
    report: dict = {"raw": {"dong": len(raw), "files": list(raw_files or ["*14.csv"])}}

    mask = region_mask or RegionMask(data_dir)
    with_time = add_time_features(raw)
    clean = clean_coordinates(with_time, mask, report)
    if verbose:
        step = report["toi_buoc_loc_toa_do"]
        print(
            f"  loc toa do ({step['quy_tac']}): {step['vao']:,} -> {len(clean):,}"
            f"  (loai {step['ngoai_vung_bo_anh']:,} ngoai vung)"
        )
    return clean, report


def build(
    config: PreprocessConfig,
    data_dir: Path,
    report: dict | None = None,
    verbose: bool = True,
    prepared: pd.DataFrame | None = None,
    shared_report: dict | None = None,
    region_mask: RegionMask | None = None,
) -> BuildResult:
    """Chay chuoi xu ly cho mot ca. Tra ve diem + toa do phang (met).

    `prepared` cho phep dung lai ket qua cua `prepare_raw` giữa nhiều ca
    (xem `build_all`) thay vì đọc lại đĩa.
    """
    report = {} if report is None else report
    rep = report.setdefault(config.name, {})
    if shared_report:
        rep.update(shared_report)

    if verbose:
        print(f"\n=== {config.describe()} ===")

    mask = region_mask or RegionMask(data_dir)
    clean = (
        prepare_raw(data_dir, config.raw_files, verbose=False)[0] if prepared is None else prepared
    )
    rep.setdefault("raw", {"dong": len(clean)})
    rep.setdefault(
        "toi_buoc_loc_toa_do",
        {"vao": rep["raw"]["dong"], "ra": len(clean), "bi_loai_tong": rep["raw"]["dong"] - len(clean)},
    )

    windowed = filter_window(
        clean, config.hours, config.dow, region_geometry(config.region, mask), rep
    )
    sampled = sample_points(windowed, config.sample_n, config.seed, rep)

    lat0, lon0 = float(clean["lat"].mean()), float(clean["lon"].mean())
    coords = to_metric(sampled["lat"].to_numpy(), sampled["lon"].to_numpy(), lat0, lon0)

    err = projection_error(coords, sampled, lat0, lon0, seed=config.seed)
    assert err["max_pct"] < 0.001, f"phieu sai {err['max_pct']:.4f}% — khong dung duoc cho eps"

    rep["projection"] = {
        "lat0": lat0,
        "lon0": lon0,
        "loi_max_pct": err["max_pct"],
        "loi_p99_pct": err["p99_pct"],
        "n_cap_kiem_chung": err["n_pairs"],
    }

    out = sampled.assign(x_m=coords[:, 0], y_m=coords[:, 1])
    out["borough"] = mask.label(out["lat"].to_numpy(), out["lon"].to_numpy())
    out = out[OUT_COLUMNS]

    by_borough = out["borough"].value_counts().to_dict()
    rep["ket_qua"] = {
        "n_diem": len(out),
        "n_toa_do_lat_khac_nhau": int(np.unique(sampled["lat"]).size),
        "khoang_gio": list(config.hours),
        "ngay_trong_tuan": list(config.dow),
        "vung": config.region or "khong gioi han",
        "theo_quan": {k: int(v) for k, v in by_borough.items()},
    }

    assert out["lat"].notna().all() and out["lon"].notna().all(), "con toa do thieu"
    assert len(out) > 0, "khong con diem sau khi loc"
    assert "ngoai_vung" not in out["borough"].values, "con diem ngoai vung hop le"

    if verbose:
        top = ", ".join(f"{k}={v:,}" for k, v in list(by_borough.items())[:3])
        print(f"  -> {len(out):,} diem ({config.region or 'khong gioi han'}) | {top}")

    return BuildResult(points=out, coords=coords, report=report)


def build_all(
    configs: list[PreprocessConfig],
    data_dir: Path,
    report: dict | None = None,
    include_ewr: bool = True,
) -> list[BuildResult]:
    """Chay nhieu ca, chi doc du lieu tho mot lan."""
    raw_files = {c.raw_files for c in configs}
    if len(raw_files) > 1:
        raise ValueError("build_all chi ho tro cac ca cung bo du lieu tho")

    region_mask = RegionMask(data_dir, include_ewr=include_ewr)
    prepared, shared = prepare_raw(data_dir, configs[0].raw_files, region_mask=region_mask)
    results = [
        build(
            c,
            data_dir,
            report=report,
            prepared=prepared,
            shared_report=shared,
            region_mask=region_mask,
        )
        for c in configs
    ]
    return results


def build_full(
    data_dir: Path,
    sample_n: int | None = None,
    seed: int = 42,
    include_ewr: bool = True,
    verbose: bool = True,
) -> BuildResult:
    """Xuat dataset DAY DU (moi ngay, moi gio) cho app chon tu do thoi gian.

    4 kich ban trong `SCENARIOS` deu da cat theo ca nen app khong the tu doi
    ngay/gio. Dataset nay giu toan bo diem hop le (~4.45M) de app loc tiep.
    """
    region_mask = RegionMask(data_dir, include_ewr=include_ewr)
    clean, report = prepare_raw(data_dir, verbose=verbose, region_mask=region_mask)

    sampled = sample_points(clean, sample_n, seed, report)
    lat0, lon0 = float(clean["lat"].mean()), float(clean["lon"].mean())
    coords = to_metric(sampled["lat"].to_numpy(), sampled["lon"].to_numpy(), lat0, lon0)

    out = sampled.assign(x_m=coords[:, 0], y_m=coords[:, 1])
    out["borough"] = region_mask.label(out["lat"].to_numpy(), out["lon"].to_numpy())

    report["projection"] = {"lat0": lat0, "lon0": lon0}
    report["ket_qua"] = {"n_diem": len(out), "vung": "full (khong cat gio)"}

    assert len(out) > 0, "khong con diem sau khi loc"
    if verbose:
        print(f"  full dataset: {len(out):,} diem")
    return BuildResult(points=out, coords=coords, report=report)


# --------------------------------------------------------------------------- #
# 7. CLI
# --------------------------------------------------------------------------- #
def save_result(result: BuildResult, out_dir: Path) -> Path:
    """Luu CSV (de doc lai tu notebook) va JSON bao cao QC."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{result.report.get('scenario', 'dataset')}.csv"
    result.points.to_csv(csv_path, index=False)
    return csv_path


def load_processed(path: str | Path) -> pd.DataFrame:
    """Doc lai dataset da xu ly (data/processed/<ca>.csv) cho notebook clustering."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} chua ton tai. Chay: python -m src.preprocess")
    df = pd.read_csv(path, parse_dates=["pickup_time"])
    missing = set(OUT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path} thieu cot {sorted(missing)}")
    return df[OUT_COLUMNS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preprocessing du lieu Uber NYC cho DBSCAN")
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        help="Chay 1 kich ban. Bo co sao de chay het cac kich ban.",
    )
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--report", default="outputs/preprocess_report.json")
    parser.add_argument("--sample-n", type=int, default=None, help="Gioi han so diem dau vao")
    parser.add_argument(
        "--no-ewr",
        action="store_true",
        help="Chi giu 5 borough NYC, loai ca san bay EWR o New Jersey",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Xuat them dataset DAY DU (moi ngay, moi gio) ra file.parquet cho app",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_reports: dict = {}

    if args.full:
        # Dataset day dung cho app: app tu chon ngay/gio nen can tat ca diem
        print("\n=== Xuat dataset day du (cho app) ===")
        full = build_full(
            Path(args.data_dir),
            sample_n=args.sample_n,
            include_ewr=not args.no_ewr,
        )
        all_reports["full"] = {"scenario": "full", **full.report}
        full_path = out_dir / "full.parquet"
        full.points.to_parquet(full_path, index=False)
        print(f"  -> luu {full_path} ({full_path.stat().st_size / 1e6:.1f} MB)")

    if args.scenario is None and not args.full:
        names = sorted(SCENARIOS)
    else:
        names = [args.scenario] if args.scenario else []

    configs = []
    for name in names:
        config = SCENARIOS[name]
        if args.sample_n is not None:
            config = PreprocessConfig(**{**asdict(config), "sample_n": args.sample_n})
        configs.append(config)

    if configs:
        results = build_all(
            configs, Path(args.data_dir), report=all_reports, include_ewr=not args.no_ewr
        )
        for name, result in zip(names, results):
            all_reports[name]["scenario"] = name
            path = out_dir / f"{name}.csv"
            result.points.to_csv(path, index=False)
            print(f"  -> luu {path} ({path.stat().st_size / 1e6:.1f} MB)")

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(all_reports, indent=2, ensure_ascii=False))
    print(f"\nBao cao QC: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())