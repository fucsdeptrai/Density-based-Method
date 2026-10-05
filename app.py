"""Ride Pickup Hotspot Explorer — Streamlit app.

Chay:  streamlit run app.py

App KHONG chua logic phan cum — moi thu goi tu `src.hotspot`. Muc dich la
giup moi thay doi tham so roi bam "Phan tich" moi chay lai.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from streamlit_folium import st_folium  # noqa: E402

from hotspot import (  # noqa: E402
    DATASETS,
    FilterSpec,
    run_dbscan,
    run_kde,
    weekday_options,
)
from hotspot.data import available_datasets, load_dataset  # noqa: E402
from hotspot.filters import filter_pickups  # noqa: E402
from hotspot.map_layers import build_dbscan_map, build_kde_map  # noqa: E402
from hotspot.summaries import cluster_table, page_metrics  # noqa: E402

# Tham so chon san cho buoi thuyet trinh. Chi la gia tri MAC DINH — nguoi
# dung doi duoc, va README ghi ro day khong phai gia tri toi uu chung.
DEFAULT_EPS_M = 100
DEFAULT_MIN_SAMPLES = 15
DEFAULT_BANDWIDTH_M = 100

# So diem toi da. DBSCAN nhanh (200k ~2s) nhưng KDE chậm theo O(n x grid^2):
# 200k diem + luoi 180x180 mat ~53s. Dùng cap riêng cho KDE de tab chuyen
# nhanh khong bi treo. Khi bi cap, app hien thi canh bao.
POINT_CAP_DBSCAN = 200_000
POINT_CAP_KDE = 30_000
KDE_GRID = 160

# Ban do ve toi da diem theo cum. MarkerCluster the cum + nhieu thi phai ve
# CA HAI, nen cao hon muc hien thi.
MAX_POINTS_PER_CLUSTER = 400
MAX_NOISE_POINTS = 2_000
MAX_RAW_POINTS = 1_200

st.set_page_config(
    page_title="Hotspot don khach — Density-based",
    page_icon="🗺️",
    layout="wide",
)

# Tâm bản đồ theo vùng phân tích. Dùng OSM tile nen khong can API key.
REGION_CENTER = {
    "manhattan": (40.739, -73.974, 12),
    "bronx": (40.85, -73.87, 11),
    "queens": (40.73, -73.79, 11),
    "brooklyn": (40.68, -73.95, 11),
    # Zoom 12: dataset "full" trai rong ca 5 quan + EWR, zoom 11 keo man hinh
    # ra toi Hackensack/Newark nen cuc du khai quang.
    "full": (40.739, -73.974, 12),
}

st.title("Xác định hotspot đón khách — phương pháp density-based")
st.caption(
    "Dữ liệu Uber NYC 4/2014–9/2014. Kết quả là **hotspot lịch sử**, "
    "không phải dự báo nhu cầu hay khuyến nghị vị trí cho tài xế."
)


@st.cache_data(show_spinner="Đang tải dữ liệu…")
def cached_load(name: str) -> pd.DataFrame:
    return load_dataset(name)


@st.cache_data(show_spinner="Đang lọc…")
def cached_filter(name: str, weekdays: tuple[int, ...], h0: int, h1: int) -> pd.DataFrame:
    return filter_pickups(cached_load(name), FilterSpec(weekdays, h0, h1))


@st.cache_data(show_spinner="Đang chạy DBSCAN…")
def cached_dbscan(name: str, weekdays: tuple[int, ...], h0: int, h1: int, eps: int, mpts: int):
    df = cached_filter(name, weekdays, h0, h1)
    return df, run_dbscan(df, eps, mpts, point_cap=POINT_CAP_DBSCAN)


@st.cache_data(show_spinner="Đang uoc luong KDE…")
def cached_kde(name: str, weekdays: tuple[int, ...], h0: int, h1: int, bw: int):
    df = cached_filter(name, weekdays, h0, h1)
    return df, run_kde(df, bw, grid_size=KDE_GRID, point_cap=POINT_CAP_KDE)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("1. Dataset")

    choices = available_datasets()
    if not choices:
        st.error(
            "Chưa có dataset trong `data/processed/`.\n\n"
            "```bash\nbash scripts/download_data.sh\npython -m src.preprocess --full\n```"
        )
        st.stop()

    dataset = st.selectbox(
        "Chọn dataset",
        choices,
        format_func=lambda n: DATASETS[n]["label"],
        help="`full` = mọi ngày, mọi giờ (chọn được tự do). "
        "Các dataset còn lại đã cắt sẵn theo ca nên bộ lọc sẽ không có tác dụng.",
    )
    st.caption(DATASETS[dataset]["description"])

    st.header("2. Khoảng thời gian")
    day_labels = dict(weekday_options())
    days = st.multiselect(
        "Ngày trong tuần",
        options=[d for d, _ in weekday_options()],
        default=[0, 1, 2, 3, 4],
        format_func=lambda d: day_labels[d],
    )
    h0 = st.slider("Giờ bắt đầu", 0, 23, 18)
    h1 = st.slider("Giờ kết thúc", 1, 24, 20)

    st.header("3. Tham số")
    eps_m = st.slider(
        "eps — bán kính lân cận (mét)",
        20, 400, DEFAULT_EPS_M, step=5,
        help="Hai điểm cách nhau ≤ eps mét thì được coi là lân cận. "
        "Tăng → các cụm gần nhau có thể dính lại; giảm → tách nhỏ hơn, nhiều noise hơn.",
    )
    min_samples = st.slider(
        "MinPts — số điểm tối thiểu",
        2, 100, DEFAULT_MIN_SAMPLES,
        help="Cần tối thiểu bao nhiêu điểm trong bán kính eps thì hình thành một cụm. "
        "Ý nghĩa nghiệp vụ: 'ít nhất MinPts chuyến đón trong eps mét thì coi là vùng đón'.",
    )
    bandwidth_m = st.slider(
        "KDE — bandwidth (mét)",
        20, 400, DEFAULT_BANDWIDTH_M, step=5,
        help="Độ rộng kernel. Nhỏ → chi tiết, nhiều đỉnh; lớn → mặt độ mượt, các cụm dính lại.",
    )
    hot_pct = st.slider(
        "KDE — ngưỡng vùng nóng (%)", 50, 99, 90,
        help="Đường viền bao quanh các vùng có mật độ thuộc top (100 − ngưỡng)% .",
    )

    if st.button("Phân tích hotspot", type="primary", use_container_width=True):
        # Luu vao session_state: nut Streamlit chi tra True trong lan chay
        # sinh ra cua chinh no. Component st_folium tao mot lan chay lai,
        # nen luu lai de ket qua khong bien mat ngay sau khi ve ban do.
        st.session_state["analyze"] = True
        st.session_state["last_params"] = (
            dataset, tuple(sorted(days)), h0, h1, eps_m, min_samples, bandwidth_m, hot_pct
        )

    # Dung lai tham so cua lan bam gan nhat cho ca hai tab
    analyze = st.session_state.get("analyze", False)
    if analyze and st.session_state.get("last_params"):
        dataset, days, h0, h1, eps_m, min_samples, bandwidth_m, hot_pct = st.session_state[
            "last_params"
        ]

    st.divider()
    with st.expander("Giải thích nhanh"):
        st.markdown(
            "- **Cụm (cluster)**: vùng có mật độ điểm đón cao → hotspot.\n"
            "- **Nhiễu (noise)**: điểm lẻ lưa, không thuộc cụm nào → bị loại.\n"
            "- **eps** đơn vị **mét**, nhờ đã chiếu toạ độ sang hệ phẳng (`x_m`, `y_m`).\n"
            "- Toạ độ lat/lon **không** được chuẩn hoá (z-score) — làm vỡ ranh giới không gian.\n"
            "- Ranh giới cụm không vẽ thành hình: ranh giới DBSCAN không phải hình học nào."
        )

if not analyze:
    st.info("Chọn khoảng thời gian rồi bấm **Phân tích hotspot** ở cột bên trái.")
    # Khong dung .to_markdown() — can them `tabulate`, va app phai chay duoc
    # ngay sau `pip install -r requirements.txt`.
    df_all = cached_load(dataset)
    per_day = (
        df_all.groupby("weekday")
        .size()
        .reindex(range(7), fill_value=0)
        .rename(index=dict(weekday_options()))
        .rename("So chuyen")
        .to_frame()
        .T
    )
    st.markdown(f"**Tổng quan dataset** — {len(df_all):,} điểm đón hợp lệ.")
    st.dataframe(per_day, use_container_width=True)
    st.stop()

# --------------------------------------------------------------------------- #
# Chay phan tich
# --------------------------------------------------------------------------- #
if not days:
    st.warning("Chọn ít nhất một ngày trong tuần.")
    st.stop()

try:
    df, result = cached_dbscan(dataset, tuple(sorted(days)), h0, h1, eps_m, min_samples)
except ValueError as exc:
    st.warning(str(exc))
    st.stop()

metrics = page_metrics(df, result)

tab_map, tab_kde, tab_table = st.tabs(["Cụm DBSCAN", "Mật độ KDE", "Bảng số liệu"])

with tab_map:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Điểm đón", f"{metrics['filtered_pickups']:,}")
    c2.metric("Số cụm", metrics["number_of_clusters"])
    c3.metric("Nhiễu", f"{metrics['noise_count']:,}")
    c4.metric("Tỉ lệ nhiễu", f"{metrics['noise_percentage']}%")
    c5.metric("Thời gian chạy", f"{metrics['analysis_runtime_seconds']}s")

    if metrics["sampled"]:
        st.caption(
            f"⚠️ Số điểm lớn nên đã lấy mẫu ngẫu nhiên còn "
            f"{metrics['filtered_pickups']:,} điểm để giữ app phản hồi nhanh."
        )

    st.subheader(f"Bản đồ — {h0:02d}:00–{h1:02d}:00")
    lat_c, lon_c, zoom_c = REGION_CENTER.get(dataset, REGION_CENTER["full"])
    st_folium(
        build_dbscan_map(
            df,
            result,
            center=(lat_c, lon_c),
            zoom=zoom_c,
            max_raw_points=MAX_RAW_POINTS,
            max_noise_points=MAX_NOISE_POINTS,
            max_points_per_cluster=MAX_POINTS_PER_CLUSTER,
        ),
        height=620,
        use_container_width=True,
    )
    st.caption(
        "Chấm xám mảnh = điểm đón thô · chấm màu = cụm · cờ = trọng tâm cụm · "
        "xám đậm trong cụm riêng = nhiễu. Số trên cụm là số điểm **thật**, "
        "dù điểm vẽ trên bản đồ chỉ là mẫu để bản đồ không bị treo."
    )

with tab_kde:
    st.info(
        "KDE hiển thị **mật độ liên tục**; DBSCAN tạo **cụm rời rạc và nhiễu**. "
        "Cùng bộ điểm, hai cách trả lời hai câu hỏi khác nhau."
    )
    try:
        _, kde = cached_kde(dataset, tuple(sorted(days)), h0, h1, bandwidth_m)
    except ValueError as exc:
        st.warning(str(exc))
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Bandwidth", f"{kde.bandwidth_m:.0f} m")
        m2.metric("Mật độ đỉnh", f"{kde.peak_density:.2e}")
        m3.metric("Số điểm ước lượng", f"{len(kde.coords_m):,}")
        st_folium(
            build_kde_map(df, kde, hot_pct=hot_pct),
            height=620,
            use_container_width=True,
        )

with tab_table:
    table = cluster_table(df, result)
    if table.empty:
        st.warning("Không tìm thấy cụm nào — giảm `eps` hoặc giảm `MinPts`.")
    else:
        st.subheader("Top hotspot theo số chuyến đón")
        show = table.head(10).copy()
        show["centroid_latitude"] = show["centroid_latitude"].round(5)
        show["centroid_longitude"] = show["centroid_longitude"].round(5)
        for col in ("area_km2", "pickup_per_km2"):
            if col in show.columns:
                show[col] = show[col].round(3)
        st.dataframe(
            show,
            hide_index=True,
            use_container_width=True,
            column_config={
                "rank": "Hạng",
                "cluster_id": "Cụm",
                "pickup_count": "Số chuyến",
                "centroid_latitude": "Vĩ độ",
                "centroid_longitude": "Kinh độ",
                "area_km2": "Diện tích (km²)",
                "pickup_per_km2": "Chuyến/km²",
            },
        )
        st.caption(
            "Diện tích ước lượng bằng **bao lồi** để tính mật độ — chỉ dùng để **so sánh**, "
            "không phải ranh giới thật của cụm. Ranh giới DBSCAN không phải hình học nào."
        )
        if metrics["pickups_per_hour"]:
            st.caption(
                f"Khoảng đang xem ≈ {metrics['window_hours']:.0f} giờ × "
                f"{len(days)} ngày → trung bình {metrics['pickups_per_hour']:,.0f} chuyến/giờ."
            )

with st.expander("Thông số đang dùng"):
    st.json(
        {
            "dataset": DATASETS[dataset]["label"],
            "ngay_trong_tuan": [weekday_options()[d][1] for d in sorted(days)],
            "khoang_gio": f"{h0:02d}:00-{h1:02d}:00",
"eps_m": eps_m,
                "min_samples": min_samples,
                "point_cap_dbscan": POINT_CAP_DBSCAN,
                "point_cap_kde": POINT_CAP_KDE,
                **metrics,
        }
    )