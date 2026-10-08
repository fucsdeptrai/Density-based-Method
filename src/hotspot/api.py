"""HTTP interface for the historical pickup explorer."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .data import load_dataset
from .dbscan import analyze_hotspots
from .filters import QueryTooLargeError, SpatialSelection, preview_context


class SpatialInput(BaseModel):
    borough: str | None = None
    geometry: dict | None = None

    def to_selection(self) -> SpatialSelection:
        if self.geometry is not None and self.borough is None:
            return SpatialSelection.for_geometry(self.geometry)
        if self.borough is not None and self.geometry is None:
            return SpatialSelection.for_borough(self.borough)
        raise ValueError("Chọn đúng một borough hoặc một vùng vẽ")


class ContextQuery(BaseModel):
    selection: SpatialInput
    weekdays: list[str]
    max_matching_dates: int = Field(ge=1, le=30)
    start_minute: int = Field(ge=0, lt=1440)
    window_minutes: int = Field(ge=15, le=1440)


class AnalysisQuery(ContextQuery):
    eps_m: int = Field(ge=20, le=200)
    min_samples: int = Field(ge=3, le=50)


def map_points(frame) -> list[list[float]]:
    return frame[["latitude", "longitude"]].values.tolist()


def sampled_points(frame, limit: int, seed: int) -> list[list[float]]:
    if len(frame) > limit:
        frame = frame.sample(limit, random_state=seed).sort_index()
    return map_points(frame)


def create_app(
    *,
    data_dir: Path | None = None,
    serve_frontend: bool = True,
    frontend_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Historical pickup hotspots")
    load_lock = Lock()
    analysis_lock = Lock()

    @lru_cache(maxsize=1)
    def load_pickups():
        try:
            return load_dataset("full", data_dir=data_dir)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=503, detail={"code": "DATA_UNAVAILABLE", "message": str(exc)}) from exc

    def pickups():
        with load_lock:
            return load_pickups()

    @app.get("/api/bootstrap")
    def bootstrap():
        frame = pickups()
        areas = sorted(frame["area"].dropna().astype(str).unique().tolist())
        sample = frame if len(frame) <= 1_500 else frame.sample(1_500, random_state=0).sort_index()
        points = map_points(sample)
        return {"areas": areas, "points": points}

    @app.post("/api/preview")
    def preview(query: ContextQuery):
        try:
            result = preview_context(
                pickups(),
                spatial_selection=query.selection.to_selection(),
                weekday_selection=query.weekdays,
                max_matching_dates=query.max_matching_dates,
                start_minute=query.start_minute,
                window_minutes=query.window_minutes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_QUERY", "message": str(exc)}) from exc
        return {
            "total_points": result.total_points,
            "available_matching_dates": result.available_matching_dates,
            "matching_dates": result.matching_dates,
            "points": map_points(result.points),
        }

    @app.post("/api/analyze")
    def analyze(query: AnalysisQuery):
        try:
            with analysis_lock:
                result = analyze_hotspots(
                    pickups(),
                    spatial_selection=query.selection.to_selection(),
                    weekday_selection=query.weekdays,
                    max_matching_dates=query.max_matching_dates,
                    start_minute=query.start_minute,
                    window_minutes=query.window_minutes,
                    eps_m=query.eps_m,
                    min_samples=query.min_samples,
                    max_points=200_000,
                )
        except QueryTooLargeError as exc:
            raise HTTPException(status_code=400, detail={"code": "QUERY_TOO_LARGE", "message": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_QUERY", "message": str(exc)}) from exc

        points = result.points
        ranked = []
        for zone in result.zones.head(10).itertuples():
            cluster_id = int(zone.cluster_id)
            group = points[points["cluster_id"] == cluster_id]
            ranked.append({
                "rank": int(zone.rank),
                "cluster_id": cluster_id,
                "points": sampled_points(group, 250, cluster_id + 2),
            })
        top_ids = {item["cluster_id"] for item in ranked}
        other = points[(points["cluster_id"] != -1) & ~points["cluster_id"].isin(top_ids)]
        noise = points[points["cluster_id"] == -1]
        return {
            "n_points": result.n_points,
            "n_clusters": result.n_clusters,
            "noise_percentage": result.noise_percentage,
            "largest_cluster_percentage": result.largest_cluster_percentage,
            "matching_dates": result.matching_dates,
            "available_matching_dates": result.available_matching_dates,
            "zones": result.zones.head(10).to_dict(orient="records"),
            "map": {
                "raw": sampled_points(points, 1_000, 0),
                "noise": sampled_points(noise, 1_000, 1),
                "other": sampled_points(other, 500, 2),
                "ranked": ranked,
            },
        }

    if serve_frontend:
        directory = frontend_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist"
        app.frontend("/", directory=directory, check_dir=False)

    return app


app = create_app()
