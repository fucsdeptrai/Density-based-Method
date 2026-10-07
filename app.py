"""Streamlit UI for freely querying one historical pickup context."""

from __future__ import annotations

from datetime import time, timedelta
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from streamlit_folium import st_folium  # noqa: E402

from hotspot.data import load_dataset  # noqa: E402
from hotspot.dbscan import HotspotAnalysis, analyze_hotspots  # noqa: E402
from hotspot.filters import (  # noqa: E402
    ENGLISH_WEEKDAYS,
    QueryTooLargeError,
    SpatialSelection,
    preview_context,
)
from hotspot.map_layers import build_hotspot_map, build_raw_map  # noqa: E402


DEFAULT_AREA = "Brooklyn"
DEFAULT_EPS_M = 70
DEFAULT_MIN_SAMPLES = 15
MAX_ANALYSIS_POINTS = 200_000

DAY_LABELS = {
    "Monday": "Thứ Hai",
    "Tuesday": "Thứ Ba",
    "Wednesday": "Thứ Tư",
    "Thursday": "Thứ Năm",
    "Friday": "Thứ Sáu",
    "Saturday": "Thứ Bảy",
    "Sunday": "Chủ Nhật",
}

AREA_VIEWS = {
    "Bronx": ((40.8448, -73.8648), 12),
    "Brooklyn": ((40.6782, -73.9442), 12),
    "EWR": ((40.6895, -74.1745), 13),
    "Manhattan": ((40.7831, -73.9712), 12),
    "Queens": ((40.7282, -73.7949), 11),
    "Staten Island": ((40.5795, -74.1502), 11),
}

st.set_page_config(
    page_title="Vùng đón khách ưu tiên trong lịch sử",
    page_icon="🗺️",
    layout="wide",
)


@st.cache_data(show_spinner="Đang tải dữ liệu pickup đã làm sạch…")
def cached_load() -> pd.DataFrame:
    return load_dataset("full")


def make_selection(borough: str | None, geometry_json: str | None) -> SpatialSelection:
    if geometry_json:
        return SpatialSelection(geometry_json=geometry_json)
    if borough:
        return SpatialSelection.for_borough(borough)
    raise ValueError("Hãy chọn một borough hoặc vẽ một vùng trên bản đồ")


@st.cache_data(show_spinner=False)
def cached_preview(
    borough: str | None,
    geometry_json: str | None,
    weekdays: tuple[str, ...],
    start_minute: int,
    window_minutes: int,
):
    return preview_context(
        cached_load(),
        spatial_selection=make_selection(borough, geometry_json),
        weekday_selection=weekdays,
        start_minute=start_minute,
        window_minutes=window_minutes,
    )


@st.cache_data(show_spinner="Đang tìm các vùng đón khách ưu tiên…")
def cached_analysis(
    borough: str | None,
    geometry_json: str | None,
    weekdays: tuple[str, ...],
    start_minute: int,
    window_minutes: int,
    eps_m: int,
    min_samples: int,
) -> HotspotAnalysis:
    return analyze_hotspots(
        cached_load(),
        spatial_selection=make_selection(borough, geometry_json),
        weekday_selection=weekdays,
        start_minute=start_minute,
        window_minutes=window_minutes,
        eps_m=eps_m,
        min_samples=min_samples,
        max_points=MAX_ANALYSIS_POINTS,
    )


@st.cache_data(show_spinner=False)
def cached_global_sample(max_points: int = 1_500) -> pd.DataFrame:
    pickups = cached_load()
    if len(pickups) <= max_points:
        return pickups
    return pickups.sample(max_points, random_state=0).sort_index()


def minute_value(value: time) -> int:
    return value.hour * 60 + value.minute


def time_window(start: time, end: time) -> tuple[int, int]:
    start_minute = minute_value(start)
    duration = (minute_value(end) - start_minute) % (24 * 60)
    return start_minute, duration or 24 * 60


def format_minute(minute: int) -> str:
    minute %= 24 * 60
    return f"{minute // 60:02d}:{minute % 60:02d}"


def window_label(start_minute: int, window_minutes: int) -> str:
    end = start_minute + window_minutes
    suffix = " (+1 ngày)" if end > 24 * 60 else ""
    return f"{format_minute(start_minute)}–{format_minute(end)}{suffix}"


def area_view(selection: SpatialSelection) -> tuple[tuple[float, float], int]:
    if selection.borough:
        return AREA_VIEWS.get(selection.borough, ((40.739, -73.974), 11))
    return (40.7128, -74.0060), 11


def drawing_geometry(map_state: dict | None) -> dict | None:
    if not map_state:
        return None
    drawing = map_state.get("last_active_drawing")
    if drawing is None:
        drawings = map_state.get("all_drawings") or []
        drawing = drawings[-1] if drawings else None
    if not drawing:
        return None
    geometry = drawing.get("geometry", drawing)
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    return geometry


def render_zone_list(analysis: HotspotAnalysis) -> None:
    st.subheader("Top 3 vùng ưu tiên")
    if analysis.top_zones.empty:
        st.warning(
            "Không có pickup nào đủ mật độ để tạo hotspot với cấu hình này. "
            "Đây vẫn là một kết quả hợp lệ; có thể điều chỉnh eps hoặc MinPts để khảo sát."
        )
        return

    for zone in analysis.top_zones.itertuples():
        st.markdown(
            f"**Hotspot {int(zone.rank)}**  \n"
            f"{int(zone.pickup_count):,} pickup lịch sử · "
            f"xuất hiện trong {int(zone.support_dates)}/{int(zone.available_matching_dates)} "
            f"ngày phù hợp · trung bình {zone.pickups_per_matching_date:.1f} "
            "pickup/ngày phù hợp"
        )


def render_analysis(analysis: HotspotAnalysis) -> None:
    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Pickup đã lọc", f"{analysis.n_points:,}")
    metric_b.metric("Hotspot tìm thấy", f"{analysis.n_clusters:,}")
    metric_c.metric("Tỷ lệ noise", f"{analysis.noise_percentage:.1f}%")

    if analysis.largest_cluster_percentage > 50:
        st.warning(
            "Một cụm chứa hơn một nửa số pickup đã lọc. Đây có thể là dấu hiệu "
            "density chaining/over-merging, không phải bằng chứng về một vùng chờ khổng lồ."
        )

    map_column, result_column = st.columns([2, 1], gap="large")
    center, zoom = area_view(analysis.spatial_selection)
    with map_column:
        st_folium(
            build_hotspot_map(analysis, center=center, zoom=zoom),
            height=620,
            use_container_width=True,
            key="hotspot-result-map",
            returned_objects=[],
        )
        st.caption(
            "Chấm màu là pickup thuộc hotspot; chấm xám là noise. Marker 1–3 là "
            "trọng tâm Top 3, không phải ranh giới DBSCAN. Đường xanh đứt nét, nếu có, "
            "chỉ là phạm vi lọc do người dùng vẽ."
        )

    with result_column:
        render_zone_list(analysis)
        st.caption(
            f"Bằng chứng được tổng hợp trên {analysis.available_matching_dates} ngày lịch sử "
            "phù hợp với các thứ đã chọn."
        )


st.title("Vùng đón khách ưu tiên trong lịch sử")
st.caption(
    "Tự chọn một khu vực và ngữ cảnh thời gian để kiểm tra hotspot pickup lịch sử. "
    "Kết quả không phải dữ liệu thời gian thực, dự báo nhu cầu hay đảm bảo có khách."
)

try:
    pickups = cached_load()
except (FileNotFoundError, ValueError) as exc:
    st.error(str(exc))
    st.code("bash scripts/download_data.sh\npython3 -m src.preprocess --full")
    st.stop()

available_areas = sorted(pickups["area"].dropna().astype(str).unique())
del pickups
if not available_areas:
    st.error("Dataset không có khu vực để phân tích.")
    st.stop()

with st.sidebar:
    st.header("1. Không gian")
    spatial_mode = st.radio(
        "Cách chọn khu vực",
        ["Theo borough", "Vẽ một vùng"],
        horizontal=True,
    )
    selected_borough = None
    if spatial_mode == "Theo borough":
        selected_borough = st.selectbox(
            "Borough",
            available_areas,
            index=(
                available_areas.index(DEFAULT_AREA)
                if DEFAULT_AREA in available_areas
                else 0
            ),
        )

    st.header("2. Thời gian lặp lại")
    weekdays = tuple(
        st.multiselect(
            "Ngày trong tuần",
            ENGLISH_WEEKDAYS,
            default=["Friday"],
            format_func=lambda day: DAY_LABELS[day],
        )
    )
    start_time = st.time_input(
        "Bắt đầu",
        value=time(18, 0),
        step=timedelta(minutes=15),
    )
    end_time = st.time_input(
        "Kết thúc",
        value=time(19, 0),
        step=timedelta(minutes=15),
        help="Giờ kết thúc sớm hơn giờ bắt đầu được hiểu là cửa sổ qua đêm.",
    )

    with st.expander("3. Cài đặt DBSCAN"):
        eps_m = st.slider(
            "eps — khoảng cách lân cận (mét)",
            min_value=20,
            max_value=200,
            value=DEFAULT_EPS_M,
            step=5,
        )
        min_samples = st.slider(
            "MinPts — hỗ trợ cục bộ tối thiểu",
            min_value=3,
            max_value=50,
            value=DEFAULT_MIN_SAMPLES,
        )

    st.divider()
    st.caption(
        "Noise chỉ có nghĩa là chưa đủ mật độ theo truy vấn và tham số hiện tại. "
        "App không tự điều chỉnh tham số để tạo kết quả đẹp."
    )

start_minute, window_minutes = time_window(start_time, end_time)
geometry_json = st.session_state.get("drawn_geometry_json")

if spatial_mode == "Vẽ một vùng":
    st.subheader("Vẽ đúng một vùng cần phân tích")
    st.write(
        "Dùng công cụ rectangle hoặc polygon ở góc trái bản đồ. "
        "Nếu vẽ hình mới, hình mới sẽ thay thế vùng trước đó."
    )
    current_selection = (
        SpatialSelection(geometry_json=geometry_json) if geometry_json else None
    )
    map_points = cached_global_sample()
    custom_preview = None
    if current_selection is not None and weekdays:
        try:
            custom_preview = cached_preview(
                None,
                geometry_json,
                weekdays,
                start_minute,
                window_minutes,
            )
            map_points = custom_preview.points
        except ValueError:
            pass
    center, zoom = (
        area_view(current_selection)
        if current_selection is not None
        else ((40.7128, -74.0060), 10)
    )
    map_state = st_folium(
        build_raw_map(
            map_points,
            center=center,
            zoom=zoom,
            total_points=(custom_preview.total_points if custom_preview else None),
            selection=current_selection,
            allow_draw=True,
        ),
        height=520,
        use_container_width=True,
        key=f"draw-region-map-{st.session_state.get('draw_revision', 0)}",
        returned_objects=["all_drawings", "last_active_drawing"],
    )
    geometry = drawing_geometry(map_state)
    if geometry is not None:
        try:
            new_selection = SpatialSelection.for_geometry(geometry)
        except ValueError as exc:
            st.warning(str(exc))
        else:
            geometry_json = new_selection.geometry_json
            if geometry_json != st.session_state.get("drawn_geometry_json"):
                st.session_state["drawn_geometry_json"] = geometry_json
                st.session_state["draw_revision"] = (
                    st.session_state.get("draw_revision", 0) + 1
                )
                st.rerun()
    if geometry_json and st.button("Xóa vùng đã vẽ"):
        st.session_state.pop("drawn_geometry_json", None)
        st.session_state["draw_revision"] = st.session_state.get("draw_revision", 0) + 1
        st.rerun()
else:
    selection = SpatialSelection.for_borough(selected_borough)
    center, zoom = area_view(selection)
    borough_preview = None
    if weekdays:
        try:
            borough_preview = cached_preview(
                selected_borough,
                None,
                weekdays,
                start_minute,
                window_minutes,
            )
        except ValueError as exc:
            st.warning(str(exc))
    st.subheader(
        f"Pickup thô · {selected_borough} · {window_label(start_minute, window_minutes)}"
    )
    st_folium(
        build_raw_map(
            borough_preview.points if borough_preview else pd.DataFrame(),
            center=center,
            zoom=zoom,
            total_points=(borough_preview.total_points if borough_preview else None),
        ),
        height=520,
        use_container_width=True,
        key="borough-preview-map",
        returned_objects=[],
    )

selection = None
if spatial_mode == "Theo borough":
    selection = SpatialSelection.for_borough(selected_borough)
elif geometry_json:
    try:
        selection = SpatialSelection(geometry_json=geometry_json)
    except ValueError as exc:
        st.warning(str(exc))

preview = None
if selection is not None and weekdays:
    try:
        preview = cached_preview(
            selection.borough,
            selection.geometry_json,
            weekdays,
            start_minute,
            window_minutes,
        )
    except ValueError as exc:
        st.warning(str(exc))

if not weekdays:
    st.warning("Chọn ít nhất một ngày trong tuần.")
elif selection is None:
    st.info("Vẽ một rectangle hoặc polygon để xác định phạm vi phân tích.")
elif preview is not None:
    st.write(
        f"Truy vấn hiện tại có **{preview.total_points:,} pickup** trên "
        f"**{preview.available_matching_dates} ngày phù hợp**."
    )
    if preview.total_points > MAX_ANALYSIS_POINTS:
        st.warning(
            f"Vượt ngưỡng chạy tương tác {MAX_ANALYSIS_POINTS:,} pickup. "
            "Hãy thu hẹp khu vực, ngày hoặc khung giờ; app không lấy mẫu âm thầm."
        )
    elif preview.total_points == 0:
        st.warning("Không có pickup nào khớp truy vấn hiện tại.")

can_analyze = bool(
    selection is not None
    and weekdays
    and preview is not None
    and 0 < preview.total_points <= MAX_ANALYSIS_POINTS
)
analyze_clicked = st.button(
    "Tìm vùng ưu tiên",
    type="primary",
    disabled=not can_analyze,
    use_container_width=True,
)

current_query = None
if selection is not None:
    current_query = {
        "borough": selection.borough,
        "geometry_json": selection.geometry_json,
        "weekdays": weekdays,
        "start_minute": start_minute,
        "window_minutes": window_minutes,
        "eps_m": eps_m,
        "min_samples": min_samples,
    }
if analyze_clicked:
    st.session_state["hotspot_query"] = current_query

saved_query = st.session_state.get("hotspot_query")
if saved_query is None:
    st.info("Chọn ngữ cảnh rồi bấm **Tìm vùng ưu tiên** để chạy DBSCAN.")
    st.stop()

if saved_query != current_query:
    st.info(
        "Bộ lọc đã thay đổi. Kết quả bên dưới vẫn thuộc lần phân tích gần nhất; "
        "bấm **Tìm vùng ưu tiên** để cập nhật."
    )

try:
    analysis = cached_analysis(**saved_query)
except QueryTooLargeError as exc:
    st.warning(str(exc))
    st.stop()
except ValueError as exc:
    st.warning(str(exc))
    st.stop()

day_text = ", ".join(DAY_LABELS[day] for day in analysis.weekday_selection)
st.markdown(
    f"### {analysis.spatial_selection.label} · {day_text} · "
    f"{window_label(analysis.start_minute, analysis.window_minutes)} · "
    f"eps {analysis.eps_m:.0f}m · MinPts {analysis.min_samples}"
)
render_analysis(analysis)
