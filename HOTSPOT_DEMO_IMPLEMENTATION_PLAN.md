# Ride Pickup Hotspot Explorer

## Revised implementation plan for the coding agent

## 1. Product thesis

This is **not** a generic DBSCAN visualizer and it is not a real-time dispatch system.

The product answers one concrete decision question:

> Given one selected borough or one user-drawn region and a recurring time context, which small areas have historically shown enough repeated pickup activity to be worth prioritizing as waiting zones?

A driver cannot act on thousands of raw pickup dots. The application converts historical pickups into a short, ranked list of **historical priority zones**. It must say `historical pickup hotspot`, never claim a guaranteed customer or real-time demand forecast.

## 2. Why DBSCAN is the method used

Each raw record is a pickup event with a latitude, longitude and timestamp. A useful waiting zone should be a locally dense, spatially connected set of pickup events—not merely a point that happens to be close to a centroid.

DBSCAN is appropriate because:

- the number of waiting zones is unknown in advance;
- street-level pickup patterns can be irregular rather than circular;
- isolated pickup events should not automatically become a recommended zone;
- `eps` can be interpreted as a spatial tolerance in metres;
- `MinPts` can be interpreted as the minimum local evidence required before calling a place dense.

Important limitations to preserve in copy and README:

- DBSCAN detects density in **observed historical pickups**, not unserved demand or current vehicle supply;
- noise means `not part of a sufficiently dense hotspot under this query and these parameters`, not `no demand`;
- DBSCAN does not generate road-following boundaries or polygons itself.

## 3. The demo claim

The web demo must demonstrate this claim:

> A hotspot is useful only in context. The app lets the user freely change one spatial region and one recurring time window, then rerun the same analysis instead of showing only preselected successful cases.

Do **not** use `10% → 20% → 100% of arbitrary points` as the main demo. That only demonstrates sensitivity to sample size, not why a driver would use the product.

The existing 10k/30k/full-data maps may be retained as an offline diagnostic or a limitation slide. They are not the primary application workflow.

## 4. Core user journey

### Default scenario

Use a real, reproducible default scenario chosen from the cleaned dataset, for example:

```text
Area: Brooklyn
Recurring context: Friday
Time window: 18:00–19:00
Spatial tolerance: eps = 70 m
Minimum local support: MinPts = <selected after baseline experiments>
```

Do not hard-code this exact scenario if the available preprocessed file uses a different subset. Inspect the data and choose a high-activity, presentation-friendly scenario.

### User flow

1. User selects one borough or draws one region, then chooses weekdays and a time window in 15-minute steps.
2. The app pools historical pickup events that match the selected context.
3. The user sees the raw pickup map and understands why raw points are not actionable.
4. User clicks **Find priority zones**.
5. DBSCAN runs on the filtered points and displays clusters, noise and a Top 3 ranked zone list.
6. User changes the region or time window and reruns the single query to inspect how the result changes.
7. Empty, noisy and over-merged outputs remain visible instead of being hidden or automatically tuned away.

## 5. Historical recurrence, not one-off density

The app should make a strong distinction between a one-off dense night and a recurring waiting zone.

For every DBSCAN cluster, calculate at minimum:

```text
pickup_count                    # number of matching historical pickups
support_dates                   # number of distinct calendar dates contributing pickup events
available_matching_dates        # denominator for the query context
pickups_per_matching_date       # pickup_count / available_matching_dates
centroid_latitude
centroid_longitude
```

The app may rank zones primarily by:

1. `support_dates` descending;
2. `pickups_per_matching_date` descending;
3. `pickup_count` descending.

The UI should phrase this as evidence, for example:

```text
Hotspot 1
312 historical pickups
Observed on 4 of 4 matching Fridays
78 average pickups per matching Friday
```

Do not invent a confidence score unless there is a documented formula.

## 6. Input and preprocessing contract

Preprocessing has already been completed. Treat the existing cleaned output as the source of truth; do not rebuild its pipeline unless a required field is missing.

The loader must inspect the actual schema, then normalize these logical fields:

| Logical field | Typical source name | Requirement |
|---|---|---|
| timestamp | `Date/Time` / `pickup_datetime` | Parsed datetime |
| latitude | `Lat` / `latitude` | Decimal degrees |
| longitude | `Lon` / `longitude` | Decimal degrees |
| area | existing subset or derived area flag | Brooklyn for the first MVP |

Create derived columns only in memory:

```text
date
weekday_name
hour
x_m
y_m
```

Project coordinates to a metre-based CRS before DBSCAN. For New York City, use an appropriate local UTM projection such as EPSG:32618, or use correctly implemented haversine distances. Never use a metre-valued `eps` directly on longitude/latitude degrees and do not z-score the geographic coordinates.

## 7. DBSCAN analysis contract

Implement a pure, testable function:

```python
analyze_hotspots(
    pickups: pd.DataFrame,
    spatial_selection: SpatialSelection,
    weekday_selection: list[str],
    start_minute: int,
    window_minutes: int,
    eps_m: float,
    min_samples: int,
) -> HotspotAnalysis
```

The function must:

1. filter to the selected recurring context, including windows that cross midnight;
2. apply exactly one borough or one user-drawn Polygon/MultiPolygon filter;
3. run DBSCAN on projected `(x_m, y_m)` coordinates;
4. label `-1` as noise;
5. create cluster-level summaries and ranking values;
6. return map-ready points plus result metadata.

Suggested implementation:

```python
DBSCAN(eps=eps_m, min_samples=min_samples, metric="euclidean")
```

Start baseline tuning with the experimental values already available (`eps=70m` is a candidate). Keep `MinPts` fixed while comparing `eps`; document the selected defaults from observed outputs. If one cluster contains an unhelpfully large share of all points, treat that as an over-merging warning, not automatic evidence of one giant waiting zone.

## 8. UI requirements

Build a single local Streamlit app. Do not build a REST API, database, login system, deployment flow or separate frontend.

### Controls

- Spatial mode: choose exactly one borough, or draw exactly one rectangle/polygon.
- Weekday multiselect with no preset grouping restriction.
- Start/end time inputs in 15-minute steps, including overnight windows.
- `eps` in metres and `MinPts` under an **Advanced settings** expander.
- One explicit **Find priority zones** button.
- One query/result at a time; no mandatory comparison panel.
- Reject queries above 200,000 pickups with a clear narrowing message; do not silently sample DBSCAN input.

### Primary map

The map is the dominant view. Render:

- raw pickup events as small, low-opacity dots;
- DBSCAN cluster events in distinguishable colors;
- noise in muted gray;
- a labeled centroid marker for each Top 3 cluster.

Do not draw a circle, convex hull or polygon and call it the DBSCAN boundary. A future geographic region layer may be added only if it is explicitly labeled as post-processing.

### Result panel

Show exactly the values that support the decision:

```text
filtered pickups
clusters found
noise percentage
Top 3 priority zones
pickup count and support dates per zone
```

Avoid generic dashboard cards, invented quality scores, unrelated charts and model-training language.

## 9. Optional time animation

Animation is optional polish, not the primary implementation risk.

If implemented, it must move through **real contextual windows** rather than arbitrary data percentages:

```text
Friday 17:00–18:00 → Friday 18:00–19:00 → Friday 19:00–20:00
```

Keep the window duration, `eps` and `MinPts` fixed during playback. Cache or precompute each frame for smooth presentation. A manual time slider is acceptable and safer than autoplay.

Do not portray this as incremental DBSCAN learning. Each frame is a new DBSCAN analysis on a different time-filtered event set.

## 10. Diagnostic data-volume view (non-MVP)

The existing three-panel comparison (10,000 / 30,000 / full points with fixed `eps=70m`) can be retained only as a diagnostic explaining sample-size sensitivity and density chaining.

If it is shown:

- keep `eps` **and** `MinPts` fixed;
- make each smaller sample a nested subset of the next using one fixed random permutation and seed;
- never imply that the colors identify the same cluster across frames;
- describe it as a parameter/coverage diagnostic, not a driver recommendation.

## 11. Implementation structure

```text
project/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   └── <existing cleaned pickup artifact>
├── src/hotspot/
│   ├── __init__.py
│   ├── data.py          # load and normalize cleaned artifact
│   ├── filters.py       # area, weekday and time-window selection
│   ├── dbscan.py        # analyze_hotspots and DBSCAN execution
│   ├── summaries.py     # recurrence and Top 3 ranking
│   └── map_layers.py    # map-ready point and centroid layers
├── notebooks/
│   └── 01_hotspot_baseline.ipynb
└── tests/
    ├── test_filters.py
    ├── test_dbscan.py
    └── test_summaries.py
```

Use `st.cache_data` for data loading and analysis results. Ensure all filters and DBSCAN parameters are part of the cached function inputs. Do not recompute on every slider movement; use the Analyze button.

## 12. Vertical slices

### Slice 1 — Prove the decision scenario offline

Build the loader and the pure DBSCAN analysis function. In the notebook:

- inspect date coverage and select a default scenario;
- test several parameter combinations;
- create a raw-points-versus-clusters result for the default query;
- verify that the Top 3 summaries have sensible counts and distinct-date support.

**Done when:** the team can explain exactly which historical events created each ranked zone.

### Slice 2 — Working driver-question web flow

Build one Streamlit page:

```text
choose recurring context → Find priority zones → map + Top 3 results
```

**Done when:** a user can answer `Where are the historically recurring pickup zones for this context?` without reading code or inspecting raw CSV.

### Slice 3 — Free context exploration

Allow the presenter to change the borough or draw a single custom region, select arbitrary weekdays and a 15-minute-step time window, then rerun the analysis.

**Done when:** the presenter can show successful, sparse and noisy contexts without editing code or relying on fixed scenarios.

### Slice 4 — Polish and resilience

- Add concise explanations of `eps`, `MinPts` and noise.
- Add loading/error states for empty filters and too-few-point selections.
- Prepare fallback screenshots for the two chosen contexts.
- Write README setup/run instructions and explicit limitations.

**Done when:** the 5–10 minute demo can run locally without manual file edits or unplanned parameter tuning.

## 13. Live presentation script supported by the web

1. **Decision:** `A driver should not choose a waiting place from a cloud of raw pickup points.`
2. **Context:** select the prepared area, day condition and 18:00–19:00.
3. **Analysis:** run DBSCAN; point out clusters and gray noise.
4. **Decision output:** show the Top 3 recurring historical zones, including their support dates.
5. **Context change:** switch to a later hour and show that the priority zones change.
6. **Caveat:** explain that this is historical pickup evidence, not a real-time guarantee.

## 14. Definition of done

The revised demo is complete only when:

- the app answers a concrete waiting-zone question, not merely visualizes clusters;
- DBSCAN runs with a correct metre-based spatial distance;
- output zones expose repeated historical support, not only total point count;
- users can freely rerun one query for different real spatial and temporal contexts;
- raw points, clusters and noise are visually distinct;
- no claim says DBSCAN learns incrementally, creates road-following boundaries or predicts current demand;
- the app runs locally with one documented command and has fallback screenshots.
