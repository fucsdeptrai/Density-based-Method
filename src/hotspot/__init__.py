"""Pure analysis modules for the historical pickup hotspot demo."""

from .data import DATASETS, available_datasets, dataset_info, load_dataset
from .dbscan import DBSCANResult, HotspotAnalysis, analyze_hotspots, run_dbscan
from .filters import (
    ContextPreview,
    FilterSpec,
    QueryTooLargeError,
    SpatialSelection,
    filter_context,
    filter_pickups,
    preview_context,
    weekday_options,
)
from .kde import KDEResult, run_kde
from .map_layers import build_hotspot_map, build_raw_map
from .summaries import cluster_table, page_metrics, summarize_hotspots

__all__ = [
    "DATASETS",
    "DBSCANResult",
    "FilterSpec",
    "HotspotAnalysis",
    "KDEResult",
    "ContextPreview",
    "QueryTooLargeError",
    "SpatialSelection",
    "analyze_hotspots",
    "available_datasets",
    "build_hotspot_map",
    "build_raw_map",
    "cluster_table",
    "dataset_info",
    "filter_context",
    "filter_pickups",
    "load_dataset",
    "page_metrics",
    "preview_context",
    "run_dbscan",
    "run_kde",
    "summarize_hotspots",
    "weekday_options",
]
