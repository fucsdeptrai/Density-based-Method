# Ride Pickup Hotspot Explorer

Ứng dụng Streamlit cho phép kiểm tra một câu hỏi trên dữ liệu Uber NYC lịch sử:

> Với một khu vực và ngữ cảnh thời gian do người dùng chọn, những vùng nhỏ nào có hoạt động pickup đủ dày và lặp lại để đáng xem xét làm vị trí chờ?

Kết quả là bằng chứng pickup lịch sử, không phải dữ liệu thời gian thực, dự báo nhu cầu chưa được phục vụ hay cam kết tài xế sẽ có khách.

## Chạy ứng dụng

Yêu cầu Python 3.11+.

```bash
pip install -r requirements.txt
bash scripts/download_data.sh
python3 -m src.preprocess --full
streamlit run app.py
```

Nếu `data/processed/full.parquet` đã có sẵn thì chỉ cần lệnh cuối.

## Luồng demo

Người dùng tạo một truy vấn duy nhất:

1. Chọn một borough, hoặc vẽ một rectangle/polygon trên bản đồ.
2. Chọn tùy ý các thứ trong tuần.
3. Chọn giờ bắt đầu và kết thúc theo bước 15 phút. Khoảng giờ có thể đi qua nửa đêm; hai giờ giống nhau nghĩa là đủ 24 giờ.
4. Điều chỉnh `eps` và `MinPts` nếu cần, rồi bấm **Tìm vùng ưu tiên**.
5. Đọc số pickup, số hotspot, tỷ lệ noise và bằng chứng recurrence của Top 3.

Mặc định là Brooklyn, Thứ Sáu, 18:00–19:00, `eps=70m`, `MinPts=15`. Đây chỉ là điểm bắt đầu có thể thay đổi hoàn toàn, không phải cấu hình tối ưu chung.

Ứng dụng không tự tuning để tạo kết quả đẹp. Truy vấn không có cluster, nhiều noise hoặc có dấu hiệu over-merging vẫn được hiển thị trung thực. Nếu phạm vi vượt 200.000 pickup, app yêu cầu thu hẹp thay vì âm thầm lấy mẫu.

## Cách phân tích hoạt động

```text
một borough hoặc một polygon
        + weekday + khoảng giờ
                    ↓
       DBSCAN trên (x_m, y_m)
                    ↓
tổng hợp pickup + ngày hỗ trợ + trọng tâm
                    ↓
xếp hạng theo ngày hỗ trợ, pickup/ngày, tổng pickup
```

- Polygon chỉ là phạm vi lọc do người dùng vẽ, không phải ranh giới DBSCAN.
- DBSCAN chỉ nhận `x_m`, `y_m` đã chiếu sang mét; không chạy `eps` theo mét trên kinh/vĩ độ và không z-score tọa độ.
- Với cửa sổ qua đêm, pickup sau 00:00 được tính cho ngày bắt đầu của ngữ cảnh.
- Noise nghĩa là pickup chưa thuộc vùng đủ dày trong truy vấn hiện tại, không có nghĩa là không có nhu cầu.

Logic chính độc lập với Streamlit:

```text
app.py                     điều phối UI và cache
src/hotspot/data.py        đọc và chuẩn hóa artifact
src/hotspot/filters.py     borough/polygon và thời gian lặp lại
src/hotspot/dbscan.py      analyze_hotspots và DBSCAN
src/hotspot/summaries.py   recurrence và xếp hạng Top 3
src/hotspot/map_layers.py  lớp điểm, vùng lọc và marker Folium
tests/                     filter, mét, polygon, recurrence và ranking
```

Chạy kiểm chứng:

```bash
pytest -q
```

Sinh screenshot fallback bằng:

```bash
streamlit run app.py --server.port 8899 --server.headless true
python3 scripts/capture_screenshots.py
```

## Giới hạn

- Dữ liệu chỉ bao phủ 04/2014–09/2014 và phản ánh pickup đã quan sát, không phản ánh cung xe hay nhu cầu không được phục vụ.
- Số ngày hỗ trợ là bằng chứng recurrence sau khi phân cụm, không phải confidence score.
- DBSCAN không tạo polygon hay ranh giới bám đường phố. Marker centroid cũng không phải một điểm chờ chính xác.
- Kết quả nhạy với `eps`, `MinPts`, phạm vi và mật độ dữ liệu; app cảnh báo nếu một cụm chứa hơn 50% pickup.

Các notebook, hình và script thử nghiệm cũ chỉ là chẩn đoán offline, không thuộc workflow chính của ứng dụng.
