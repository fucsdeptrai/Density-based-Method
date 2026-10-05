"""Tim, doc va chuan hoa dataset da xu ly.

Khong ghi ten file cu the — suy ra tu file trong `data/processed/`.Neu thieu
cot bat buoc thi nem loi ro rang thay vi doan.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Cot bat buoc sau khi chuan hoa. `x_m`/`y_m` la toa do phang don vi met,
# nua mat neu co.
REQUIRED = ["pickup_datetime", "latitude", "longitude"]
METRE_COLS = ["x_m", "y_m"]

# Ten cot trong `data/processed/*.csv` -> ten chuan hoa trong bo nho
COLUMN_MAP = {
    "pickup_time": "pickup_datetime",
    "Date/Time": "pickup_datetime",
    "lat": "latitude",
    "Lat": "latitude",
    "lon": "longitude",
    "Lon": "longitude",
}

# Cac dataset ma app cho chon. Gia tri None = file khong co mo ta rieng.
DATASETS: dict[str, dict] = {
    "full": {
        "file": "full.parquet",
        "label": "Day du — moi ngay, moi gio",
        "description": "4.449.041 diem hop le, chua cat theo ca. Dung khi can "
        "tu chon khoang gio khac nhau.",
    },
    "ca_diem_t7_manhattan": {
        "file": "ca_diem_t7_manhattan.csv",
        "label": "Ca diem toi — Thu Bay 17-19h (Manhattan)",
        "description": "65.367 diem. Kich ban chinh de thuyet trinh.",
    },
    "ca_diem_t7_toan_bo": {
        "file": "ca_diem_t7_toan_bo.csv",
        "label": "Ca diem toi — Thu Bay 17-19h (5 quan)",
        "description": "85.997 diem. So sanh mat do giua cac quan.",
    },
    "ca_sang_t2_manhattan": {
        "file": "ca_sang_t2_manhattan.csv",
        "label": "Ca sang di lam — Thu Hai 8-10h (Manhattan)",
        "description": "38.123 diem. Doi chieu voi ca toi.",
    },
    "dem_thu7_manhattan": {
        "file": "dem_thu7_manhattan.csv",
        "label": "Khu vuc dem — Thu Bay 0-4h (Manhattan)",
        "description": "49.752 diem. Club, san bay, chuyen xe dem.",
    },
}


def repo_root() -> Path:
    """Thu muc goc chua `data/processed/`."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "processed").is_dir():
            return parent
    raise FileNotFoundError("Khong tim thay data/processed/ — chay: python -m src.preprocess")


def available_datasets(data_dir: Path | None = None) -> list[str]:
    """Ten dataset co thuc su ton tai tren dia."""
    directory = data_dir or repo_root() / "data" / "processed"
    return [name for name, meta in DATASETS.items() if (directory / meta["file"]).exists()]


def dataset_info(name: str) -> dict:
    if name not in DATASETS:
        raise KeyError(f"Dataset '{name}' khong ton tai. Chon: {sorted(DATASETS)}")
    return DATASETS[name]


def load_dataset(name: str = "full", data_dir: Path | None = None) -> pd.DataFrame:
    """Doc dataset va chuan hoa ten cot.

    Returns
    -------
    DataFrame co it nhat `pickup_datetime`, `latitude`, `longitude`; va
    `x_m`, `y_m` khi file da co san (khong tu chieu lai — lop nay khong
    phu thuoc thu vien hinh hoc).
    """
    info = dataset_info(name)
    directory = Path(data_dir) if data_dir else repo_root() / "data" / "processed"
    path = directory / info["file"]

    if not path.exists():
        raise FileNotFoundError(
            f"Khong thay {path}.\n"
            "Chay:  bash scripts/download_data.sh && python -m src.preprocess --full"
        )

    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} thieu cot bat buoc {missing}")

    df = df.copy()
    df["pickup_datetime"] = pd.to_datetime(df["pickup_datetime"])
    df["latitude"] = df["latitude"].astype("float64")
    df["longitude"] = df["longitude"].astype("float64")

    # Dac trung thoi gian — dung de loc, khong sua vao du lieu nguon.
    if "weekday" not in df.columns:
        df["weekday"] = df["pickup_datetime"].dt.dayofweek
    if "hour" not in df.columns:
        df["hour"] = df["pickup_datetime"].dt.hour

    if not all(c in df.columns for c in METRE_COLS):
        raise ValueError(
            f"{path.name} thieu cot toa do phang {METRE_COLS}.\n"
            "Chay lai: python -m src.preprocess --full"
        )

    return df