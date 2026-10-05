# Ride Pickup Hotspot Explorer — Implementation Plan

## 1. Purpose

Build a small local web demo for a Data Mining presentation on **density-based methods**. The user selects a time window from historical Uber pickup data in New York City and sees where pickup activity is dense.

The demo must make this distinction clear:

- **DBSCAN** is the primary density-based clustering method. It outputs clusters and noise.
- **KDE** is a density-estimation comparison view. It shows a continuous demand surface; it is not presented as a clustering algorithm by itself.

The result represents **historical pickup hotspots**, not real-time driver dispatch advice or a demand forecast.

## 2. Scope and non-goals

### In scope

- Load the already-preprocessed Uber TLC FOIL pickup dataset.
- Filter pickups by selected day(s) of week and time window.
- Run DBSCAN with meaningful controls in metres (`eps_m`, `min_samples`).
- Show clustered pickup points, noise points, and a ranked hotspot summary.
- Show a KDE density view on the exact same filtered points.
- Provide a clean Streamlit interface suitable for a 5–10 minute live demo.
- Cache data and computations enough that normal interactions remain responsive.

### Explicitly out of scope

- No FastAPI/backend service, database, authentication, deployment, or multi-user support.
- No K-Means, hierarchical clustering, H3, Getis-Ord, road-network snapping, or real-time data.
- No claim that the app recommends an exact street position for a driver.
- No fake circular or convex-hull hotspot boundaries for DBSCAN.
- Do not redo the preprocessing pipeline unless a required output column is absent.

## 3. Input data contract

The implementation should find and inspect the existing preprocessed artifact rather than assume a hard-coded filename. It must preserve the original columns where available and require at least:

| Logical field | Expected source field | Notes |
|---|---|---|
| pickup timestamp | `Date/Time` or normalized equivalent | Parse as a datetime once when loading. |
| latitude | `Lat` or normalized equivalent | Decimal degrees. |
| longitude | `Lon` or normalized equivalent | Decimal degrees. |

Recommended normalized columns in memory:

```text
pickup_datetime, latitude, longitude, weekday, hour, x_m, y_m
```

Use the preprocessing output as the source of truth. If projected coordinates are absent, calculate them in the analysis module using **EPSG:32618 (UTM zone 18N)** so DBSCAN uses metres directly. Do not z-score latitude/longitude.

The default demo slice should be chosen from the available data after a quick exploratory check. A sensible starting candidate is weekday, 18:00–20:00, Manhattan/central NYC, but do not hard-code it if the processed dataset uses a different geographic filter.

## 4. User-visible behavior

### Main journey

1. The page loads with a sensible default time window and DBSCAN parameters.
2. The user changes the days of week and start/end hours.
3. The user adjusts `eps_m` and `min_samples`, then clicks **Analyze hotspots**.
4. The map shows:
   - faint raw pickup points;
   - DBSCAN clusters in distinct colors;
   - noise in gray;
   - one marker at each cluster centroid;
   - no artificial polygon enclosing a cluster.
5. The user can switch to the **KDE density** tab to see the continuous-density view for the same filtered pickups.
6. A ranked table/cards list the top clusters by pickup count and density.

### Required UI controls

- Days of week: multiselect, default to weekdays.
- Start hour and end hour: integer selectors or a range slider.
- `eps_m`: slider or numeric input, labelled in metres.
- `min_samples`: slider or numeric input.
- One explicit **Analyze hotspots** button so sliders do not accidentally rerun expensive work.
- Tab or radio selector: `DBSCAN clusters` / `KDE density`.

### Required result fields

For each DBSCAN hotspot, calculate and display:

```text
cluster_id
pickup_count
centroid_latitude
centroid_longitude
approximate_area_km2 (optional if robustly computed)
pickup_density (only when area is available)
```

At page level, display:

```text
filtered_pickups
number_of_clusters
noise_count
noise_percentage
analysis_runtime_seconds
```

## 5. Architecture

Use a **single Streamlit process**. Keep analysis code independent from Streamlit so it can be tested from a notebook or Python script.

```text
project/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   └── <existing preprocessed pickup artifact>
├── src/
│   └── hotspot/
│       ├── __init__.py
│       ├── data.py
│       ├── filters.py
│       ├── dbscan.py
│       ├── kde.py
│       ├── summaries.py
│       └── map_layers.py
├── notebooks/
│   └── 01_baseline_experiments.ipynb
└── tests/
    ├── test_filters.py
    ├── test_dbscan.py
    └── test_summaries.py
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `data.py` | Locate, load, normalize and cache the processed dataset. |
| `filters.py` | Apply weekday/hour/geographic filters without mutating source data. |
| `dbscan.py` | Run DBSCAN on projected metre coordinates and return labels plus metadata. |
| `kde.py` | Fit `KernelDensity`, score a spatial grid, and generate density/contour output. |
| `summaries.py` | Build cluster-level metrics and ranked hotspot tables. |
| `map_layers.py` | Convert result DataFrames/contours to map-ready layers. |
| `app.py` | UI orchestration only; it must not contain clustering logic. |

Recommended stack:

```text
Python 3.11+
streamlit
pandas
numpy
scikit-learn
pyproj
pydeck or another performant Streamlit-compatible map layer
matplotlib/scipy for KDE contour extraction
pytest
```

Use `st.cache_data` for dataset loading and filtered slices, and `st.cache_resource` only for genuinely reusable resources. Never cache a result without including every clustering parameter in its cache key.

## 6. Modeling details

### DBSCAN

```python
DBSCAN(eps=eps_m, min_samples=min_samples, metric="euclidean")
```

This assumes `x_m` and `y_m` are UTM metre coordinates. Use labels `-1` as noise. Exclude noise from the hotspot ranking, but show its count and percentage.

The implementation must not silently run DBSCAN on raw degree coordinates with a metre-valued `eps`.

Start the baseline exploration with a small grid such as:

```text
eps_m:       75, 100, 150
min_samples: 10, 20, 30
```

Choose default parameters only after looking at the map and reporting the choice in the README. Defaults are demo defaults, not universal optimum values.

### KDE

Fit KDE on the same projected coordinates used by DBSCAN. Evaluate it on a bounded 2-D grid derived from the filtered slice. Render the result as a density heatmap or contour overlay.

Expose one `bandwidth_m` control if it can be implemented without making the UI crowded. Otherwise use a documented default bandwidth and retain the implementation as a comparison view.

Do not describe every high-density KDE pixel as an individual cluster. If a ranked KDE hotspot list is shown, define it explicitly using a threshold and connected high-density region logic.

## 7. Implementation order: vertical slices

### Slice 1 — Reproducible DBSCAN baseline

**Goal:** prove that the existing processed data can yield credible clusters before building UI.

Tasks:

- Locate the processed data and document its actual schema.
- Implement the loader, normalization and time filtering.
- Implement projected coordinates and a pure `run_dbscan` function.
- Create `notebooks/01_baseline_experiments.ipynb` or an equivalent script.
- Generate a static map/plot for at least three parameter combinations.

Acceptance criteria:

- The same data and parameters produce the same labels.
- `eps_m` is demonstrably interpreted in metres.
- The output reports points, clusters and noise.
- One default demo configuration is selected from observed output.

### Slice 2 — DBSCAN web vertical slice

**Goal:** a presenter can choose a time window and show cluster/noise output in the browser.

Tasks:

- Create Streamlit layout and sidebar controls.
- Wire the controls to the filtering and `run_dbscan` functions.
- Render clustered/raw/noise points with a readable legend.
- Add page-level metrics and a Top 3 hotspot table.
- Add caching and an explicit Analyze button.

Acceptance criteria:

- The demo works from `streamlit run app.py` without a separate server.
- Changing a parameter and clicking Analyze changes the result.
- Noise is visibly distinguished from clusters.
- The app remains usable on the chosen default slice.

### Slice 3 — KDE comparison view

**Goal:** show that a continuous density estimate answers a related but different question.

Tasks:

- Implement a testable KDE function on the filtered projected points.
- Generate a bounded grid and a map-ready heatmap/contour result.
- Add the KDE tab/view, preserving the exact selected filters.
- Add a concise on-screen note: `KDE visualizes density; DBSCAN creates discrete clusters and noise.`

Acceptance criteria:

- Switching views does not change the selected dataset/time filter.
- KDE reacts to bandwidth when that control is exposed.
- The legend specifies what the density color scale means.

### Slice 4 — Demo polish and reliability

Tasks:

- Make labels Vietnamese or consistently bilingual for the presentation.
- Add help text explaining `eps`, `MinPts`, noise and KDE bandwidth.
- Test at least three prepared scenarios: morning, evening, and late night.
- Capture fallback screenshots for the default scenario and one parameter-change scenario.
- Write a short README with setup/run instructions and known limitations.

Acceptance criteria:

- A new machine can install dependencies and run the app from the README.
- No result claims real-time demand, causality, or a guaranteed driver recommendation.
- The presenter can complete the prepared demo in under ten minutes.

## 8. Presentation script supported by the app

1. **Problem:** many pickup points do not directly show where demand concentrates.
2. **Filter:** choose weekday, 18:00–20:00 (or the selected default scenario).
3. **DBSCAN:** explain colored groups, gray noise, `eps` in metres and `MinPts` as minimum local support.
4. **Interaction:** change `eps` once to show that nearby dense groups can merge or separate.
5. **KDE:** switch view to show density continuously rather than assigning every point a discrete cluster.
6. **Conclusion:** DBSCAN is useful when dense groups and noise matter; KDE is useful when the goal is a smooth intensity map.

## 9. Guardrails for the coding agent

- Do not add a REST API, database, auth flow, cloud deployment, or unrelated UI pages.
- Do not replace DBSCAN with K-Means just because it is easier to visualize.
- Do not use `StandardScaler` on latitude/longitude for the spatial distance calculation.
- Do not draw a circle or convex hull and claim it is the exact DBSCAN boundary.
- Do not state that `Base` means a driver, passenger type, or demand level; it is only an associated Uber base code.
- Prefer a working, readable local demo over an elaborate architecture.
- If the preprocessed file's schema differs from this plan, adapt the loader and document the actual mapping instead of guessing.

## 10. Definition of done

The work is complete when all of the following are true:

- A local Streamlit app runs with the preprocessed Uber pickup data.
- The user can filter by time and run DBSCAN with visible cluster/noise results.
- The app includes a KDE density comparison for the same filtered data.
- The DBSCAN implementation uses a spatial metric in metres correctly.
- The app surfaces an understandable Top 3 hotspot summary.
- The repository has a concise README and the presenter has fallback screenshots.
