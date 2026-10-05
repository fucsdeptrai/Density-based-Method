"""Ride Pickup Hotspot Explorer — phan tich phan cum hotspot don khach.

Chia 2 lop:
  - `data`, `filters`, `dbscan`, `kde`, `summaries`, `map_layers`: logic thuan
    Python, khong import Streamlit -> chay duoc tu notebook, script, pytest.
  - `app.py` (o thu muc goc): chi dieu phoi UI.

Khong dung `StandardScaler` tren lat/lon. Moi do tinh tren toa do phang
`x_m`, `y_m` (met) da chieu san o tang preprocessing.
"""

from .data import DATASETS, available_datasets, dataset_info, load_dataset
from .dbscan import DBSCANResult, run_dbscan
from .filters import FilterSpec, filter_pickups, weekday_options
from .kde import KDEResult, run_kde
from .map_layers import build_map
from .summaries import cluster_table, page_metrics

__all__ = [
    "DATASETS",
    "DBSCANResult",
    "FilterSpec",
    "KDEResult",
    "build_map",
    "cluster_table",
    "dataset_info",
    "filter_pickups",
    "load_dataset",
    "page_metrics",
    "run_dbscan",
    "run_kde",
    "weekday_options",
]