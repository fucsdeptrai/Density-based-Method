# Quy trình từ dữ liệu thô đến ứng dụng tìm khu vực đón khách

Tài liệu này ghi lại quy trình **đang có trong repository**: lấy dữ liệu, kiểm tra và xử lý, thử nghiệm khai phá dữ liệu, rồi đưa kết quả vào ứng dụng React + FastAPI. Đầu ra là các khu vực có nhiều **lượt đón đã ghi nhận trong quá khứ** theo bộ lọc người dùng chọn. Đây không phải dự báo nhu cầu hay dữ liệu khách đang chờ theo thời gian thực.

```text
6 CSV Uber 04–09/2014 + ranh giới 5 quận NYC
    → kiểm tra và làm sạch tọa độ
    → chiếu tọa độ sang mét, lưu full.parquet
    → lọc khu vực + ngày + khung giờ theo yêu cầu
    → DBSCAN, tổng hợp và xếp hạng khu vực
    → FastAPI trả kết quả, React hiển thị bản đồ
```

## 1. Thu thập dữ liệu

Nguồn chính là [bộ dữ liệu Uber TLC FOIL do FiveThirtyEight công bố](https://github.com/fivethirtyeight/uber-tlc-foil-response). Sáu file `uber-raw-data-{apr,may,jun,jul,aug,sep}14.csv` chứa các lượt đón từ tháng 4 đến tháng 9 năm 2014. Mỗi dòng có `Date/Time` (thời điểm đón), `Lat`, `Lon` (tọa độ điểm đón) và `Base` (mã đơn vị). Tổng số dòng thô theo báo cáo xử lý là **4.534.327**.

Script [`scripts/download_data.sh`](scripts/download_data.sh) tải sáu file vào `data/raw/`, kiểm tra số dòng dự kiến của từng tháng rồi mới đổi tên file tải tạm. Script cũng tải `nyc_boroughs.geojson` từ [bản sao ranh giới 5 quận](https://github.com/dwillis/nyc-maps/blob/master/boroughs.geojson). File GeoJSON này là nguồn ranh giới được code sử dụng; đây là bản sao trên GitHub, không phải endpoint NYC Open Data trực tiếp.

Repository còn có dữ liệu Uber năm 2015 và bảng taxi zone phục vụ khảo sát trong notebook. Chúng **không** đi vào `full.parquet` và không được ứng dụng dùng để phân cụm, vì dữ liệu 2015 chỉ có mã `locationID`, không có cặp kinh/vĩ độ của từng lượt đón như sáu file năm 2014.

## 2. Khảo sát và xử lý dữ liệu

[`notebooks/01_eda_overview.ipynb`](notebooks/01_eda_overview.ipynb) khảo sát quy mô, schema, chất lượng tọa độ, phân bố theo giờ/ngày và không gian. Bước này chỉ ra vì sao cần lọc tọa độ lỗi, chọn ngữ cảnh thời gian và đo khoảng cách bằng mét. Logic xử lý dùng lại được nằm trong [`src/preprocess.py`](src/preprocess.py); [`notebooks/02_preprocessing.ipynb`](notebooks/02_preprocessing.ipynb) trình bày và kiểm tra từng bước.

Quy trình tạo dữ liệu cho ứng dụng:

1. Đọc sáu CSV, đổi tên cột thành `pickup_time`, `lat`, `lon`, `base`, thêm `source` là tháng nguồn và chuyển thời gian/tọa độ sang kiểu dữ liệu phù hợp.
2. Tạo các đặc trưng thời gian như giờ, thứ trong tuần và ngày lịch để phục vụ khảo sát và lọc dữ liệu.
3. Loại điểm thiếu tọa độ, điểm `(0, 0)` và điểm ngoài **polygon 5 quận NYC cộng vùng hộp quanh sân bay EWR**. EWR là ngoại lệ được giữ lại dù thuộc New Jersey. Bounding box NYC chỉ được dùng làm chỉ số kiểm tra, không phải quy tắc lọc chính.
4. Gán nhãn quận hoặc `EWR` cho các điểm hợp lệ. Chiếu kinh/vĩ độ sang tọa độ phẳng `x_m`, `y_m` bằng phép chiếu azimuthal equidistant để khoảng cách đầu vào của DBSCAN có đơn vị mét. Notebook đã đối chiếu sai số phép chiếu với khoảng cách haversine.
5. Với lệnh `--full`, giữ **mọi ngày và mọi giờ** sau khi làm sạch, không lấy mẫu; lưu `data/processed/full.parquet`. Báo cáo số dòng và các bước lọc được ghi vào `outputs/preprocess_report.json`.

Theo [`outputs/preprocess_report.json`](outputs/preprocess_report.json) của lần xử lý hiện có: **4.534.327** dòng đầu vào → loại **85.286** dòng ngoài vùng hợp lệ → **4.449.041** điểm trong `full.parquet`. Báo cáo này là số liệu của artifact hiện có; chạy lại với nguồn hoặc tùy chọn khác có thể cho số liệu khác. Các CSV theo bốn ca cố định trong `data/processed/` là đầu ra phục vụ thử nghiệm offline, không phải dữ liệu mà web app đang tải.

## 3. Khai phá dữ liệu và lựa chọn phương pháp

Bài toán là tìm các nhóm điểm đón gần nhau trong một khu vực và khung giờ đã chọn, khi **chưa biết trước số nhóm**. Ứng dụng dùng DBSCAN trên cặp tọa độ phẳng `(x_m, y_m)` với khoảng cách Euclid:

- `eps_m`: bán kính lân cận, tính bằng mét;
- `min_samples`: số điểm tối thiểu trong lân cận để hình thành vùng đủ dày;
- nhãn `-1`: điểm chưa thuộc nhóm đủ dày với bộ lọc và tham số hiện tại.

Không chạy khoảng cách mét trực tiếp trên kinh/vĩ độ dạng độ, và không chuẩn hóa z-score hai trục tọa độ. Các thử nghiệm `eps`, `MinPts`, k-distance, so sánh DBSCAN với KDE và độ nhạy tham số nằm trong [`notebooks/03_baseline_dbscan.ipynb`](notebooks/03_baseline_dbscan.ipynb). [`notebooks/04_tim_khung_gio_va_eps.ipynb`](notebooks/04_tim_khung_gio_va_eps.ipynb) kiểm tra hiện tượng **gộp quá rộng**: ở nơi có mật độ rất cao như Manhattan, nhiều điểm nối thành một nhóm lớn dù đổi khung giờ. Notebook thử thay đổi lượng điểm, phạm vi và `eps` để chỉ ra giới hạn này. Các con số mặc định ghi trong notebook là kết quả của từng thí nghiệm; cấu hình **ứng dụng hiện tại** được đọc từ frontend: `eps = 70 m`, `min_samples = 15`, tối đa 5 ngày phù hợp.

Khi có kết quả DBSCAN, [`src/hotspot/summaries.py`](src/hotspot/summaries.py) tính cho từng nhóm: tổng lượt đón, số ngày có điểm đón, lượt đón trung bình trên mỗi ngày phù hợp và vị trí đánh dấu trên bản đồ. Thứ tự xếp hạng là **số ngày có điểm đón**, rồi **lượt đón trung bình/ngày**, rồi **tổng lượt đón** (đều giảm dần). Điểm đánh dấu là một lượt đón trong ô tọa độ dày nhất của nhóm, không phải ranh giới hay vị trí đón khách chính xác. Phần thống kê ngày vẫn được tính để xếp hạng, dù giao diện hiện không liệt kê từng ngày hay tỷ lệ ngày của mỗi khu vực.

## 4. Đưa quy trình vào ứng dụng

[`src/hotspot/data.py`](src/hotspot/data.py) đọc `full.parquet`, chuẩn hóa tên cột trong bộ nhớ và kiểm tra các cột cần thiết. [`src/hotspot/api.py`](src/hotspot/api.py) dùng FastAPI; dữ liệu được nạp một lần và dùng lại cho các yêu cầu tiếp theo.

1. **Thiết lập tìm kiếm:** React trong [`frontend/src/main.tsx`](frontend/src/main.tsx) cho chọn một quận hoặc vẽ một vùng trên bản đồ, chọn thứ trong tuần, giờ bắt đầu/kết thúc theo bước 15 phút và số ngày phù hợp gần nhất từ 1 đến 30. Hai giờ giống nhau nghĩa là cửa sổ 24 giờ; cửa sổ có thể qua nửa đêm.
2. **Xem trước:** `POST /api/preview` gọi [`src/hotspot/filters.py`](src/hotspot/filters.py) để lọc đúng ngữ cảnh và đếm **toàn bộ** lượt đón phù hợp. Chỉ các điểm vẽ trên bản đồ xem trước mới được lấy mẫu tối đa 1.500 điểm. Với cửa sổ qua nửa đêm, lượt đón sau 00:00 được gán về ngày bắt đầu của cửa sổ.
3. **Phân cụm:** khi người dùng bấm tìm kiếm, `POST /api/analyze` lọc lại từ dữ liệu đầy đủ rồi chạy [`src/hotspot/dbscan.py`](src/hotspot/dbscan.py). Nếu có trên **200.000** điểm phù hợp, API yêu cầu thu hẹp bộ lọc; ứng dụng không âm thầm lấy mẫu đầu vào DBSCAN.
4. **Trả kết quả:** API gửi tổng lượt đón, số nhóm, tỷ lệ điểm ngoài nhóm, tối đa 10 nhóm xếp hạng và các lớp điểm **đã lấy mẫu riêng để vẽ bản đồ**. Frontend tô nổi số khu vực người dùng chọn từ 1 đến 10 mà không chạy lại DBSCAN. Vùng do người dùng vẽ chỉ là phạm vi lọc, không phải ranh giới nhóm do DBSCAN tạo ra.

FastAPI phục vụ cả `/api/*` và frontend đã build trên cùng cổng. Bản đồ dùng Leaflet/OpenStreetMap ở trình duyệt; việc lọc và phân cụm chạy trên máy chủ. Ứng dụng hiện tại là React + FastAPI, còn các bản đồ Folium và hình trong `src/hotspot/map_layers.py`, `src/hotspot/figures.py` là công cụ chẩn đoán offline.

## 5. Tái tạo và kiểm chứng

Từ thư mục gốc repository, sau khi cài Python 3.11+ và Node.js theo [`README.md`](README.md):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix frontend
bash scripts/download_data.sh
.venv/bin/python -m src.preprocess --full
npm run build --prefix frontend
.venv/bin/python -m uvicorn hotspot.api:app --app-dir src --host 0.0.0.0 --port 8899
```

Máy chạy app mở `http://localhost:8899`; máy khác cùng mạng mở `http://<IP-LAN-của-máy-chạy-app>:8899`. `0.0.0.0` là địa chỉ **lắng nghe** của server, không phải URL để nhập trên máy khác. Nếu đã có `data/processed/full.parquet`, có thể bỏ qua hai bước tải và xử lý dữ liệu.

Kiểm chứng tự động:

```bash
.venv/bin/python -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
```

Các test Python kiểm tra làm sạch, lọc, DBSCAN, thống kê và API; test trình duyệt kiểm tra luồng chọn bộ lọc, vẽ vùng và xem kết quả. Kết quả chỉ phản ánh các lượt đón đã quan sát trong giai đoạn 04–09/2014. Tỷ lệ điểm ngoài nhóm hoặc một nhóm quá lớn là thông tin về **dữ liệu và tham số hiện tại**, không chứng minh nơi đó không có khách hay tài xế chắc chắn sẽ có khách.
