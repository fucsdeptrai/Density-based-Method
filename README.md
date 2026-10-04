# Ứng dụng 2: Xác định hotspot đón khách (Density-based Method)

> **Trạng thái:** Draft — đang hoàn thiện nội dung và kết quả thực nghiệm.

## A. Problem

Tài xế phải đợi ở những vị trí không có hành khách → thời gian chờ (idle time) tăng, chi phí vận hành tăng.
Mục tiêu: **tìm các vùng có mật độ yêu cầu đón khách cao** để tài xế đứng đúng chỗ.

## B. Data

| Nguồn | Mô tả |
|---|---|
| NYC TLC Trip Record Data | Chuyến taxi, pickup datetime + pickup location (lat/long) |
| Uber Pickup Data | Chuyến rideshare, pickup time + pickup location |

Trường dữ liệu dùng chung:

- `pickup_latitude`, `pickup_longitude` — toạ độ điểm đón
- `pickup_datetime` — thời gian đón (lọc theo khung giờ)
- (tùy chọn) `passenger_count`, `trip_distance` — phân tích theo nhóm khách

## C. Preprocessing

1. **Lọc toạ độ lỗi**: bỏ `0, 0`, giá trị `null`/trống, và ngoài biên giới hợp lệ của thành phố.
2. **Tính khoảng cách thật**: dùng **haversine** (đơn vị mét) thay cho Euclid trên độ — vì lon/lat không cùng thang đo.
3. **Cắt khung giờ**: giới hạn theo giờ cao điểm / theo ngày trong tuần, phục vụ đặt trạm theo ca.
4. **Không z-score toạ độ**: chuẩn hoá toạ độ sẽ phá vỡ ranh giới không gian (khoảng cách và hướng trên bản đồ), nên giữ nguyên toạ độ thật và chuyển sang đơn vị mét khi tính eps.

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