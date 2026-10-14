# Ride Pickup Hotspot Explorer

Ứng dụng React + FastAPI cho phép kiểm tra một câu hỏi trên dữ liệu Uber NYC lịch sử:

> Với một khu vực và ngữ cảnh thời gian do người dùng chọn, những vùng nhỏ nào có hoạt động pickup đủ dày và lặp lại để đáng xem xét làm vị trí chờ?

Kết quả là bằng chứng pickup lịch sử, không phải dữ liệu thời gian thực, dự báo nhu cầu chưa được phục vụ hay cam kết tài xế sẽ có khách.

## Chạy ứng dụng

Yêu cầu Python 3.11+ và Node.js 20.19+ hoặc 22.12+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix frontend
bash scripts/download_data.sh
.venv/bin/python -m src.preprocess --full
bash scripts/download_offline_map.sh
npm run build --prefix frontend
.venv/bin/python -m uvicorn hotspot.api:app --app-dir src --host 127.0.0.1 --port 8899
```

Nếu `data/processed/full.parquet` đã có sẵn, có thể bỏ qua bước tải và xử lý dữ liệu chuyến đi. Lệnh tải bản đồ tạo `data/maps/nyc.pmtiles` một lần khi có Internet; file này không được đưa vào Git. Có thể sao chép file đó từ máy khác nếu mạng trên máy chạy app yếu. Sau khi đã có dữ liệu và build frontend, chỉ cần lệnh Uvicorn cuối cùng để chạy ứng dụng.

Mở `http://localhost:8899` trên chính máy chạy app. Sau bước chuẩn bị, nền đường phố, dữ liệu chuyến đi và phân tích đều hoạt động khi ngắt Internet. Nền bản đồ dùng [Protomaps](https://docs.protomaps.com/basemaps/downloads) từ dữ liệu OpenStreetMap và giữ ghi công OpenStreetMap trên giao diện. Nếu thiếu file bản đồ, ứng dụng sẽ báo trên trang; các thao tác phân tích vẫn dùng được.

Khi phát triển giao diện, chạy Uvicorn ở cổng 8899 và `npm run dev --prefix frontend`; Vite chuyển tiếp `/api` đến FastAPI.

## Luồng demo

Người dùng tạo một truy vấn duy nhất:

1. Chọn một borough, hoặc vẽ một rectangle/polygon trên bản đồ.
2. Chọn tùy ý các thứ trong tuần.
3. Chọn giờ bắt đầu và kết thúc theo bước 15 phút. Khoảng giờ có thể đi qua nửa đêm; hai giờ giống nhau nghĩa là đủ 24 giờ.
4. Chọn số ngày phù hợp gần nhất cần gộp (1–30 ngày, mặc định 5); app liệt kê chính xác các ngày được dùng.
5. Điều chỉnh `eps` và `MinPts` nếu cần, rồi bấm **Tìm vùng ưu tiên**.
6. Đọc số pickup, số hotspot, tỷ lệ noise và bằng chứng recurrence. Chọn **Top K** từ 1–10 để đổi số vùng tô nổi mà không chạy lại DBSCAN.

Mặc định là Brooklyn, Thứ Sáu, 18:00–19:00, `eps=70m`, `MinPts=15`. Đây chỉ là điểm bắt đầu có thể thay đổi hoàn toàn, không phải cấu hình tối ưu chung.

Ứng dụng không tự tuning để tạo kết quả đẹp. Truy vấn không có cluster, nhiều noise hoặc có dấu hiệu over-merging vẫn được hiển thị trung thực. Nếu phạm vi vượt 200.000 pickup, app yêu cầu thu hẹp thay vì âm thầm lấy mẫu.

## Cách phân tích hoạt động

```text
một borough hoặc một polygon
        + weekday + khoảng giờ
                    ↓
       DBSCAN trên (x_m, y_m)
                    ↓
tổng hợp pickup + ngày hỗ trợ + ô mật độ cao nhất
                    ↓
xếp hạng theo ngày hỗ trợ, pickup/ngày, tổng pickup
```

- Polygon chỉ là phạm vi lọc do người dùng vẽ, không phải ranh giới DBSCAN.
- DBSCAN chỉ nhận `x_m`, `y_m` đã chiếu sang mét; không chạy `eps` theo mét trên kinh/vĩ độ và không z-score tọa độ.
- Với cửa sổ qua đêm, pickup sau 00:00 được tính cho ngày bắt đầu của ngữ cảnh.
- Người dùng chọn từ 1–30 ngày phù hợp gần nhất; mặc định 5 ngày để giảm density chaining do tích lũy cả sáu tháng.
- Bản đồ chỉ tô nổi Top K do người dùng chọn; các cụm khác vẫn được tính nhưng hiển thị mờ.
- Noise nghĩa là pickup chưa thuộc vùng đủ dày trong truy vấn hiện tại, không có nghĩa là không có nhu cầu.

Logic phân tích độc lập với giao diện:

```text
frontend/                  React + TypeScript, bản đồ Leaflet, bộ lọc và Top K
src/hotspot/api.py         API FastAPI và dữ liệu bản đồ lấy mẫu
src/hotspot/data.py        đọc và chuẩn hóa artifact
src/hotspot/filters.py     borough/polygon và thời gian lặp lại
src/hotspot/dbscan.py      analyze_hotspots và DBSCAN
src/hotspot/summaries.py   recurrence và xếp hạng hotspot
src/hotspot/map_layers.py  Folium cho script chẩn đoán offline
tests/                     test logic phân tích và HTTP API
frontend/tests/            test luồng trình duyệt
```

Chạy kiểm chứng:

```bash
.venv/bin/python -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
```

Test trình duyệt và script chụp ảnh dùng Chrome đã cài trên máy chạy test.

Sinh screenshot fallback bằng:

```bash
.venv/bin/python -m uvicorn hotspot.api:app --app-dir src --host 127.0.0.1 --port 8899
.venv/bin/python scripts/capture_screenshots.py
```

## Giới hạn

- Dữ liệu chỉ bao phủ 04/2014–09/2014 và phản ánh pickup đã quan sát, không phản ánh cung xe hay nhu cầu không được phục vụ.
- Số ngày hỗ trợ là bằng chứng recurrence sau khi phân cụm, không phải confidence score.
- DBSCAN không tạo polygon hay ranh giới bám đường phố. Marker là một pickup trong ô `eps` dày nhất, không phải một điểm chờ chính xác.
- Kết quả nhạy với `eps`, `MinPts`, phạm vi và mật độ dữ liệu; app cảnh báo nếu một cụm chứa hơn 50% pickup.

Các notebook, hình và script thử nghiệm cũ chỉ là chẩn đoán offline, không thuộc workflow chính của ứng dụng. Xem [notebook so sánh K-Means và DBSCAN](notebooks/05_so_sanh_kmeans_dbscan.ipynb) để chạy hai thuật toán trên cùng lượt đón đã lọc.
