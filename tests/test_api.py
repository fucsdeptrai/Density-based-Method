"""HTTP behavior of the local hotspot application."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from hotspot.api import create_app


@pytest.fixture
def client(tmp_path):
    rows = [
        {
            "pickup_time": "2024-01-05 18:00:00",
            "lat": 40.68,
            "lon": -73.94,
            "x_m": 0.0,
            "y_m": 0.0,
            "borough": "Brooklyn",
        },
        {
            "pickup_time": "2024-01-05 18:15:00",
            "lat": 40.75,
            "lon": -73.98,
            "x_m": 500.0,
            "y_m": 500.0,
            "borough": "Manhattan",
        },
    ]
    pd.DataFrame(rows).to_parquet(tmp_path / "full.parquet")
    with TestClient(create_app(data_dir=tmp_path, serve_frontend=False)) as app_client:
        yield app_client


def test_bootstrap_lists_areas_and_map_reference_points(client):
    response = client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json() == {
        "areas": ["Brooklyn", "Manhattan"],
        "points": [[40.68, -73.94], [40.75, -73.98]],
    }


def test_preview_counts_matching_pickups_and_returns_map_points(client):
    response = client.post(
        "/api/preview",
        json={
            "selection": {"borough": "Brooklyn"},
            "weekdays": ["Friday"],
            "max_matching_dates": 5,
            "start_minute": 1080,
            "window_minutes": 60,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_points": 1,
        "available_matching_dates": 1,
        "matching_dates": ["2024-01-05"],
        "points": [[40.68, -73.94]],
    }


def test_analyze_returns_ranked_zones_and_sampled_map_layers(tmp_path):
    rows = []
    for cluster in range(4):
        dates = ["2024-01-05", "2024-01-12"] if cluster == 0 else ["2024-01-05"]
        for date in dates:
            for offset in range(3):
                rows.append(
                    {
                        "pickup_time": f"{date} 18:0{offset}:00",
                        "lat": 40.68 + cluster * 0.01,
                        "lon": -73.94 + offset * 0.00001,
                        "x_m": float(cluster * 500 + offset),
                        "y_m": float(offset),
                        "borough": "Brooklyn",
                    }
                )
    pd.DataFrame(rows).to_parquet(tmp_path / "full.parquet")
    query = {
        "selection": {"borough": "Brooklyn"},
        "weekdays": ["Friday"],
        "max_matching_dates": 5,
        "start_minute": 1080,
        "window_minutes": 60,
        "eps_m": 30,
        "min_samples": 3,
    }

    with TestClient(create_app(data_dir=tmp_path, serve_frontend=False)) as app_client:
        response = app_client.post("/api/analyze", json=query)

    assert response.status_code == 200
    result = response.json()
    assert result["n_points"] == 15
    assert result["n_clusters"] == 4
    assert result["noise_percentage"] == 0
    assert result["matching_dates"] == ["2024-01-05", "2024-01-12"]
    assert [zone["rank"] for zone in result["zones"]] == [1, 2, 3, 4]
    assert result["zones"][0]["support_dates"] == 2
    assert result["zones"][0]["pickup_count"] == 6
    assert len(result["map"]["ranked"]) == 4
    assert len(result["map"]["ranked"][0]["points"]) == 6


def test_analyze_explains_when_the_exact_point_limit_is_exceeded(tmp_path):
    count = 200_001
    pd.DataFrame({
        "pickup_time": ["2024-01-05 18:00:00"] * count,
        "lat": [40.68] * count,
        "lon": [-73.94] * count,
        "x_m": [0.0] * count,
        "y_m": [0.0] * count,
        "borough": ["Brooklyn"] * count,
    }).to_parquet(tmp_path / "full.parquet")

    with TestClient(create_app(data_dir=tmp_path, serve_frontend=False)) as app_client:
        response = app_client.post("/api/analyze", json={
            "selection": {"borough": "Brooklyn"},
            "weekdays": ["Friday"],
            "max_matching_dates": 5,
            "start_minute": 1080,
            "window_minutes": 60,
            "eps_m": 70,
            "min_samples": 15,
        })

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "QUERY_TOO_LARGE"
    assert "200,000" in response.json()["detail"]["message"]


def test_built_frontend_and_api_share_one_origin(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Hotspot explorer</h1>")

    with TestClient(create_app(serve_frontend=True, frontend_dir=tmp_path)) as app_client:
        page = app_client.get("/")
        api = app_client.get("/openapi.json")

    assert page.status_code == 200
    assert "Hotspot explorer" in page.text
    assert api.status_code == 200
    assert "/api/analyze" in api.json()["paths"]


def test_missing_dataset_returns_setup_instruction(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, serve_frontend=False)) as app_client:
        response = app_client.get("/api/bootstrap")

    assert response.status_code == 503
    assert "src.preprocess --full" in response.json()["detail"]["message"]
