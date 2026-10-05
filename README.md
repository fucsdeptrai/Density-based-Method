# Ứng dụng 2: Xác định hotspot đón khách (Density-based Method)

> **Trạng thái:** Đã có EDA + preprocessing chạy thật trên dữ liệu. Phần clustering (DBSCAN) đang viết.

## Cấu trúc repo & cách chạy

```
notebooks/01_eda_overview.ipynb      EDA tổng quát (chất lượng dữ liệu, thời gian, không gian, k-distance)
notebooks/02_preprocessing.ipynb     Chạy từng bước preprocessing, minh bạch số dòng vào/ra
src/preprocess.py                    NGUỒN SỰ THẬT của preprocessing — cả 2 notebook đều import, không copy-paste
scripts/download_data.sh             Tải dữ liệu thô + ranh giới 5 quận (~750 MB)
requirements.txt                     Cài đặt: pip install -r requirements.txt
data/raw/                            Dữ liệu thô + nyc_boroughs.geojson (gitignored)
data/processed/                      Dữ liệu đã xử lý, 1 file/kịch bản (gitignored)
outputs/                             Ảnh + báo cáo QC (gitignored)
```

```bash
pip install -r requirements.txt     # 0. cài thư viện
bash scripts/download_data.sh       # 1. tải dữ liệu thô + geojson (~750 MB)
python -m src.preprocess           # 2. xử lý cả 4 kịch bản (~75 giây)
python -m src.preprocess --scenario ca_diem_t7_manhattan   # hoặc từng ca
python -m src.preprocess --no-ewr  # bỏ ngoại lệ sân bay Newark
```

### 4 kịch bản phân tích

| Kịch bản | Khung giờ | Vùng | Số điểm | Dùng để |
|---|---|---|---|---|
| `ca_diem_t7_manhattan` | Thứ 7, 17–19h | Manhattan | 65 367 | Ca điểm tối nhất — kịch bản chính |
| `ca_diem_t7_toan_bo` | Thứ 7, 17–19h | 5 quận | 85 997 | So sánh phân bố mật độ giữa các quận |
| `ca_sang_t2_manhattan` | Thứ 2, 8–10h | Manhattan | 38 123 | Ca sáng đi làm, đối chiếu với ca tối |
| `dem_thu7_manhattan` | Thứ 7, 0–4h | Manhattan | 49 752 | Vùng hạ nghỉ (club, sân bay) |

### Quy tắc vùng hợp lệ

**Hai khái niệm dễ nhầm — phân biệt rõ:**

| Khái niệm | Ý nghĩa | Nơi dùng |
|---|---|---|
| `RegionMask.valid_region` | Vùng hợp lệ để **kiểm tra** điểm đón | `clean_coordinates` (lọc) |
| `region` trong config | Vùng **phân tích** — nơi tìm hotspot | `filter_window` (cắt) |

Vùng hợp lệ = **polygon hành chính 5 quận NYC** + **hộp 5 km quanh sân bay EWR** (Newark Liberty, 36 003 chuyến — nằm ở New Jersey nên không thuộc quận nào).

Kịch bản `ca_diem_t7_toan_bo` dùng `region="nyc"` (đúng 5 borough, **không** gồm EWR) vì cần cùng một phạm vi cho cả 5 quận thì mới so sánh mật độ được. Dùng `region="valid"` nếu muốn đưa EWR vào.

Đo trên toàn bộ 4.534.327 chuyến:

| Quy tắc | Giữ lại | Ghi chú |
|---|---|---|
| bbox (cách cũ) | 4 502 415 | Hình chữ nhật, không có ý nghĩa hành chính |
| 5 quận polygon | 4 411 894 | Loại sạch điểm ngoài khơi |
| **polygon + EWR (đang dùng)** | **4 449 041** | +37 147 điểm sân bay Newark |

Polygon 5 quận là tập con của bbox: không quận nào vượt biên. Điểm bị loại thêm gồm **45 772 điểm Jersey City/Hoboken** (bờ Hudson, cách Manhattan 2 km qua cầu) và khoảng 5 500 điểm ngoài khơi / bờ biển.

> **Cần bàn trước khi nộp bài:** Jersey City/Hoboken là vùng đông dân làm việc thật. Loại là đúng nếu phạm vi nghiên cứu chỉ là NYC; nếu muốn vùng điều phố liên quận thì phải thêm hành lang NJ vào `RegionMask`.

### Kết quả preprocessing đã kiểm chứng

| Bước | Kết quả |
|---|---|
| Đọc 6 file tháng 4–9/2014 | 4 534 327 chuyến |
| Lọc theo polygon 5 quận + EWR | loại 85 286 dòng (1.88%), **giữ lại 4 449 041** |
| Cắt khung giờ × ngày × vùng | 38 123 – 85 997 điểm/kịch bản |
| Chiếu sang toạ độ phẳng | azimuthal equidistant, sai số max **0.000134%** |

Đo thử 3 phương án chiếu (20 000 cặp ngẫu nhiên, đo trong notebook):

| Phương án | Sai số trung bình | Sai số max |
|---|---|---|
| equirectangular `cos(lat0)` | 0.013% | 0.178% |
| equirectangular `cos(lat)` | 0.009% | 0.160% |
| **azimuthal equidistant** | **0.000002%** | **0.00015%** |

→ Chỉ phương án cuối cho phép đọc `eps` là **mét thật** mà không phải hiệu chỉnh tay. Chi tiết ở `notebooks/02_preprocessing.ipynb`.

## A. Problem

Tài xế phải đợi ở những vị trí không có hành khách → thời gian chờ (idle time) tăng, chi phí vận hành tăng.
Mục tiêu: **tìm các vùng có mật độ yêu cầu đón khách cao** để tài xế đứng đúng chỗ.

## B. Data

Nguồn: [FiveThirtyEight — uber-tlc-foil-response](https://github.com/fivethirtyeight/uber-tlc-foil-response/tree/master/uber-trip-data)
(Uber trips NYC, 4/2014 – 6/2015). Tải lại bằng `bash scripts/download_data.sh`.

| File | Số chuyến | Khoảng thời gian | Schema |
|---|---|---|---|
| `uber-raw-data-apr14.csv` | 564 516 | 04/2014 | `Date/Time, Lat, Lon, Base` |
| `uber-raw-data-may14.csv` | 652 435 | 05/2014 | như trên |
| `uber-raw-data-jun14.csv` | 663 844 | 06/2014 | như trên |
| `uber-raw-data-jul14.csv` | 796 121 | 07/2014 | như trên |
| `uber-raw-data-aug14.csv` | 829 275 | 08/2014 | như trên |
| `uber-raw-data-sep14.csv` | 1 028 136 | 09/2014 | như trên |
| `uber-raw-data-janjune-15.csv` | 14 270 479 | 01–06/2015 | `Dispatching_base_num, Pickup_date, Affiliated_base_num, locationID` |
| `taxi-zone-lookup.csv` | 265 | — | `LocationID, Borough, Zone` |

**Lưu ý quan trọng về schema:**
- 6 file `*-14.csv` có **lat/long trực tiếp** → dùng được cho DBSCAN ngay.
- File `jan-june-15.csv` **không có lat/long**, chỉ có `locationID`. File `taxi-zone-lookup.csv` trong repo này **cũng không có cột lat/lon** → không map được sang toạ độ.
  → Với file này chỉ dùng được phân tích **theo vùng (taxi zone)** (đếm số chuyến theo `locationID` / borough), hoặc phải join với bảng tra toạ độ khác.
  → Vì vậy phần còn lại của bài dùng **6 file tháng 4–9/2014** làm dữ liệu chính cho hotspot.

## C. Preprocessing

1. **Lọc toạ độ lỗi**: bỏ `0, 0`, giá trị `null`/trống, và điểm nằm ngoài **polygon hành chính 5 quận + EWR**. Đo được 85 286 dòng (1.88%). Dùng polygon thay bbox vì bbox có hình chữ nhật không có ý nghĩa hành chính, giữ lại cả điểm ở giữa sông lẫn ngoài khơi.
2. **Tính khoảng cách thật**: dùng **haversine** (đơn vị mét) thay cho Euclid trên độ — vì lon/lat không cùng thang đo. Để chạy DBSCAN, chiếu sang **hệ phẳng đơn vị mét** bằng *azimuthal equidistant* (sai số đo được < 0.0002%).
3. **Cắt khung giờ**: giới hạn theo giờ cao điểm / theo ngày trong tuần, phục vụ đặt trạm theo ca.
4. **Không z-score toạ độ**: chuẩn hoá toạ độ sẽ phá vỡ ranh giới không gian (khoảng cách và hướng trên bản đồ), nên giữ nguyên toạ độ thật và chuyển sang đơn vị mét khi tính eps.

5. **Gắn nhãn quận**: mỗi điểm được gán tên quận (Manhattan/Brooklyn/Queens/Bronx/Staten Island/EWR) → phân tích hotspot theo quận không cần join lại dữ liệu.

Toàn bộ xử lý nằm trong `src/preprocess.py`, có số dòng vào/ra từng bước và `assert` kiểm chứng. Chi tiết: `notebooks/02_preprocessing.ipynb`.

## D. Các phương pháp được xem xét

| Phương pháp | Ý tưởng |
|---|---|
| K-Means | Chia không gian thành k cụm vuông, điểm trung tâm làm trạm |
| Hierarchical clustering | Cây phân cấp, chọn số cụm theo dendrogram |
| Grid / H3 | Chia lưới đều (lat/long) hoặc lưới hex H3, mỗi ô là một vùng |
| KDE | Ước lượng mật độ xác suất bằng kernel, tìm vùng mật độ cao |
| Getis-Ord Gi\* | Chỉ số nóng (hotspot) theo thống kê không gian trên từng ô lưới |
| **DBSCAN** | Cụm theo mật độ, không cần biết trước số cụm, giữ điểm nhiễu riêng |

## E. Vì sao chọn phương pháp density-based (DBSCAN)

- **Hình dạng bất kỳ**: hotspot ven sông, góc phố hay khu phiếu đều là vùng lõi rỗng — K-Means với cụm hình tròn/ellipsoid không bám được.
- **Không cần biết trước số hotspot**: đây là ẩn số nghiệp vụ, đặt `k` trước là giả định sai.
- **Tự tách chuyến rải rác**: các chuyến đơn lẻ giữa khu vực bị gắn nhãn **noise** và bị loại, thay vì bị kéo vào cụm gần nhất.
- **Tham số diễn giải được nghiệp vụ**: `eps = 100 m` nghĩa là "các chuyến đón cách nhau dưới 100m thì coi là cùng một điểm đón"; `MinPts` nghĩa là "tối thiểu bao nhiêu chuyến trong bán kính đó thì coi là vùng đón" — hai con số này trao được cho vận hành để hiểu và tinh chỉnh.

## F. Cách áp dụng

```
điểm đón (haversine, lọc giờ)
        │
        ▼
  DBSCAN(eps = 100 m, MinPts = N)
        │
        ├── core points → mở rộng → CỤM  (mỗi cụm = 1 hotspot)
        └── border + noise → bị loại khỏi danh sách trạm
        │
        ▼
Chuyển mỗi cụm thành ĐA GIÓN vùng đón
   (convex hull / buffer 100m + alpha-shape để bám đường phố)
        │
        ▼
Gắn nhãn hotspot lên bản đồ + đếm số chuyến/h giờ theo từng vùng
```

Bước chuyển cụm thành đa giác là bắt buộc để đưa vào bản đồ điều phối: driver cần một **vùng** có viền rõ, không phải một danh sách rời rạc toạ độ.

## G. Kết quả

| Nhãn DBSCAN | Ý nghĩa | Xử lý |
|---|---|---|
| **Cụm (cluster)** | Vùng đón khách, đủ mật độ | Đánh dấu là hotspot, sinh đa giôn vùng đón |
| **Noise** | Chuyến rải rác, không tạo vùng | Loại khỏi bản đồ đặt trạm |

Thứ tự ưu tiên các hotspot: theo **số chuyến mỗi giờ** (chuyến/giờ) thay vì tổng số chuyến — vì hotspot nhỏ nhưng giao thông dày vẫn hữu ích hơn khu rộng nhưng vắng.

<!-- KẾT QUẢ THỰC NGHIỆM (chèn sau khi chạy): số cụm tìm được, bảng top hotspot, bản đồ, so sánh với K-Means/KDE -->

## H. Ưu điểm

- **Ranh giới bám đường phố**: vùng đón thực tế là dải kéo dài theo vỉa hè / điểm dừng xe buýt; DBSCAN + đa giôn bám theo hình dạng đó, không ép vào hình tròn.
- **Tham số diễn giải được**: quy đổi trực tiếp ra mét và số chuyến, vận hành tự điều chỉnh được theo khu vực.
- **Không cần chọn số hotspot trước**, tự nhiên tách vùng theo mức mật độ.
- **Tự lọc nhiễu** thay vì gán nhãn cho mọi chuyến lẻ.

## I. Nhược điểm

- **Mật độ khác nhau giữa các quận**: một `eps` duy nhất cho cả thành phố sẽ **quá nhạy** ở khu đông và **quá chặt** ở khu vựt — trung tâm Manhatan bị phân mảnh thành nhiều cụm nhỏ, ngoại ô bị gộp làm một. Cần chạy `eps` theo quận hoặc dùng tham số thích ứng.
- **Sai metric**: nếu dùng khoảng cách Euclid trên lat/long hoặc chuẩn hoá sai, kết quả sai hoàn toàn — phải dùng haversine và đơn vị mét.
- **Không real-time**: DBSCAN không hỗ trợ cập nhật dần, chạy lại từ đầu mỗi lần dữ liệu thay đổi. Chưa phù hợp điều phối theo giây/phút; cần định kỳ (theo ca/ngày) và có thể cần biến thể tăng dần.
- **Nhạy với `MinPts`**: MinPts quá cao loại mất hotspot thật ở vùng yếu, quá thấp thì nhiễu gộp thành cụm giả.

## J. Các phương pháp thay thế

| Thay thế | Khi nào chọn |
|---|---|
| **KDE** | Cần **mức độ mật độ** (density value) chứ không chỉ là vùng, ví dụ để vẽ bản đồ nhiệt liên tục hoặc chọn vùng theo ngưỡng 70% mật độ. Nhược điểm: cần chọn bandwidth, kết quả phụ thuộc grid. |
| **H3 / lưới** | Cần **vùng có tâm hình học ổn định để đặt trạm** và muốn các vùng có diện tích so sánh được, có thể đếm "số chuyến trên mỗi ô" ổn định theo thời gian để theo dõi xu hướng. Nhược điểm: ranh giới cắt ngang đường phố, độ phân giải cố định không co theo mật độ. |
| **Getis-Ord Gi\*** | Cần **kiểm định thống kê** xem vùng nào *thực sự* nóng hơn ngẫu nhiên (p-value), hợp khi báo cáo cho quản lý hoặc so sánh giữa các khu vực. Nhược điểm: cần chọn lưới và tham số lân cận. |
| **K-Means** | Khi nghiệp vụ **bắt buộc đặt đúng N trạm** (N do nhân sự / hợp đồng / phân bổ xe quyết định, ví dụ 200 trạm). Nhược điểm: cụm hình cầu, không bám đường phố, khiến mọi chuyến lẻ cũng phải gán vào một trạm. |

## Hướng mở rộng

- Chạy `eps` theo quận / theo grid H3 để xử lý chênh lệch mật độ giữa khu vực.
- So sánh với KDE và Getis-Ord trên cùng tập dữ liệu, đo bằng **Silhouette** + đối chiếu số trạm thực tế.
- Thay đổi `eps` (50 / 100 / 200 m) để khảo sát độ nhạy.
- Chuẩn hoá theo **số chuyến mỗi giờ** và theo **diện tích vùng** thay vì tổng số chuyến.

---

# Ứng dụng web demo (Streamlit)

Kế hoạch chi tiết: [`HOTSPOT_DEMO_IMPLEMENTATION_PLAN.md`](HOTSPOT_DEMO_IMPLEMENTATION_PLAN.md)

## Chạy

```bash
pip install -r requirements.txt
bash scripts/download_data.sh          # du lieu tho (~750 MB)
python -m src.preprocess --full       # 4 kich ban + full.parquet (~90 MB)
streamlit run app.py                  # mo http://localhost:8501
```

> `full.parquet` là bắt buộc cho app: 4 file kịch bản CSV đã cắt sẵn theo ca nên bộ lọc ngày/giờ sẽ không có tác dụng.

## Kiến trúc

```
app.py                      chi dieu phoi UI — KHONG chua logic phan cum
src/hotspot/
  ├── data.py               tim + doc + chuan hoa dataset (tu suy ra ten file)
  ├── filters.py            loc theo ngay/gio, khong mutate du lieu nguon
  ├── dbscan.py             DBSCAN tren x_m/y_m (met)
  ├── kde.py                KernelDensity + luoi uoc luong
  ├── summaries.py          bang xep rank cum + chi so cap trang
  └── map_layers.py         chuyen ket qua thanh lop folium
tests/                      42 test cho filters / dbscan / summaries
notebooks/03_baseline_dbscan.ipynb   quet eps x MinPts, chon tham so mac dinh
scripts/capture_screenshots.py       chup fallback (dung Chrome san co)
outputs/screenshots/                3 kich ban da chup
```

Logic phân cụm nằm trong `src/hotspot/` nên chạy được từ notebook, script hay pytest — không phụ thuộc Streamlit.

## Tham số mặc định và căn cứ

| Tham số | Mặc định | Căn cứ (đo trong `03_baseline_dbscan.ipynb`) |
|---|---|---|
| `eps` | **100 m** | 131 cụm, 6.3% nhiễu. Tách chi tiết hơn 150 m |
| `MinPts` | **15** | tương đương "ít nhất 15 chuyến trong 100 m là một vùng đón" |
| KDE bandwidth | **100 m** | cùng thang đo với `eps` nên hai tab so sánh được |
| Giới hạn điểm DBSCAN | 200 000 | 1.7s thay vì 11.5s; app ghi rõ khi bị lấy mẫu |
| Giới hạn điểm KDE | 30 000 | KDE chậm O(n × grid²): 30k là 3s, 200k là 53s |

Đây là **giá trị mặc định cho demo**, không phải giá trị tối ưu chung.

## Những gì app cố ý KHÔNG làm

| Không làm | Vì sao |
|---|---|
| Vẽ đa giác bao quanh cụm | Ranh giới DBSCAN không phải hình học nào. Bao lồi/vòng tròn sẽ vẽ sai ranh giới thật |
| Dùng `StandardScaler` trên lat/lon | Phá vỡ ranh giới không gian. Mọi khoảng cách tính trên `x_m`/`y_m` đã là mét |
| Vẽ đủ mọi điểm lên bản đồ | 200k marker sinh file HTML ~260 MB, trình duyệt treo. Giới hạn số điểm vẽ, **số liệu trong bảng vẫn là số thật** |
| Áp API key cho bản đồ | Dùng tile OSM — demo chạy được cả khi không có key |

## Giới hạn đã biết

**Cụm lớn nhất chiếm 84–88% dữ liệu ở mọi giá trị tham số đã thử** (50–300 m). Không phải lỗi cấu hình: Manhattan có mật độ điểm đón cao liên tục nên ở bán kính vài trăm mét các điểm nối thành một mạng liên thông.

- Với câu hỏi *"khu nào đông?"* → kết quả đúng: 1 cụm lớn = Manhattan.
- Với câu hỏi *"đứng ở đâu?"* → phải giảm `eps` xuống vài chục mét. **Chưa làm trong phạm vi này.**

Nói "DBSCAN tìm được 131 hotspot" mà không kèm cụm lớn nhất chiếm 87% là con số sai.

Ngoài ra:

- App lấy mẫu 200 000 điểm nên số cụm có thể lệch vài so với chạy đủ 472 170 điểm.
- Diện tích `area_km2` tính bằng **bao lồi** chỉ để tính mật độ so sánh — không phải ranh giới cụm.
- Kết quả là **hotspot lịch sử** 4/2014–9/2014. Không phải dự báo nhu cầu, không phải khuyến nghị vị trí cho tài xế.
- Chưa so sánh định lượng với K-Means.

## Kịch bản demo 10 phút

1. Mở app, giữ mặc định (Thứ 2–6, 18–20h, eps=100, MinPts=15) → 131 cụm, 6.3% nhiễu.
2. **Kéo `eps` từ 100 xuống 50** → số cụm nhảy lên 215. Giải thích: bán kính nhỏ tách các vùng gần nhau.
3. **Tăng `MinPts` lên 30** → cụm còn 87, nhiễu tăng. Giải thích: đòi nhiều chứng cứ hơn thì nhiều điểm thành nhiễu.
4. Sang tab **Mật độ KDE** → mặt mật độ liên tục, không có ranh giới, không có "nhiễu".
5. Kéo `bandwidth` KDE từ 100 lên 250 → các đỉnh dính lại, mất chi tiết.

**Fallback nếu app chết:** `outputs/screenshots/` có 3 ảnh đã chụp (mặc định, `eps=50`, `MinPts=30`). Các bản đồ tĩnh đầy đủ: `outputs/baseline_ca_diem_thu7.html` và 2 ca còn lại.

## Test

```bash
python -m pytest        # 42 test
```

Trong đó có `test_eps_is_metres_not_degrees` — dựng hai cụm cách nhau 500 m, kiểm chứng `eps=100` tách và `eps=600` gộp. Nếu `eps` bị đọc nhầm là độ thì cả hai nhánh đều cho kết quả giống nhau và test bắt được lỗi đó.