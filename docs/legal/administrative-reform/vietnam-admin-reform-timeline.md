# Sổ Tay Lịch Sử Cải Cách Địa Giới Hành Chính Việt Nam (Vietnam Administrative Reform Timeline)

> Tài liệu tham khảo hệ thống (System Memory) giải thích các điểm đứt gãy dữ liệu (discontinuities) về mã địa lý (`City_Id`, `District_Id`, `Ward_Id`) và cấu trúc địa chỉ trong cơ sở dữ liệu của Cổng thông tin Quốc gia về Đăng ký Doanh nghiệp (DKKD.gov).

---

## 1. Bản Đồ Tổng Quan Các Lần Cải Cách Đứt Gãy (Discontinuity Map)

Hệ thống mã ID địa lý của DKKD không sử dụng mã tiêu chuẩn GSO (Tổng cục Thống kê) mà sử dụng hệ thống ID tự tăng/đặc thù của Bộ Kế hoạch và Đầu tư (nay thuộc Bộ Tài chính quản lý). Do đó, mỗi đợt sáp nhập hoặc chia tách đơn vị hành chính đều tạo ra các thay đổi lớn về phân bổ dữ liệu:

| Năm Cải Cách | Văn Bản Pháp Lý | Loại Thay Đổi | Tác Động Dữ Liệu DKKD |
|---|---|---|---|
| **1976** | Nghị quyết Quốc hội | Sáp nhập tỉnh quy mô lớn (Hậu giải phóng) | *Không ảnh hưởng* (DKKD chưa số hóa dữ liệu trước năm 1990) |
| **1991** | Nghị quyết Quốc hội | Chia tách tỉnh đợt 1 (Tái lập tỉnh cũ) | Điểm sàn thời gian số hóa, một số doanh nghiệp cũ đăng ký lại có ngày lập mờ nhạt |
| **1997** | Nghị quyết Quốc hội | Chia tách tỉnh đợt 2 (Tái lập tỉnh & thành phố trực thuộc TW) | Xác lập các tỉnh cốt lõi (Quảng Nam - Đà Nẵng, Sông Bé thành Bình Dương/Bình Phước) |
| **2004** | Quyết định 124/2004/QĐ-TTg | Chia tách tỉnh đợt 3 (Đắk Lắk, Lai Châu, Cần Thơ) | Chuẩn hóa hệ mã tỉnh ban đầu trên DKKD trước thời kỳ số hóa tập trung |
| **2008** | Nghị quyết 15/2008/QH12 | Sáp nhập Hà Tây + Mê Linh vào Hà Nội | **Đứt gãy dữ liệu đợt 1:** Mã Hà Tây cũ bị xóa, toàn bộ doanh nghiệp chuyển vùng sang mã Hà Nội |
| **2025** | Nghị quyết 202/2025/QH15 & Luật 72/2025/QH15 | Sáp nhập 63 → 34 tỉnh/thành phố; Bãi bỏ chính quyền cấp huyện | **Đứt gãy dữ liệu đợt 2 (Lớn nhất lịch sử):** Sáp nhập 29 tỉnh; Cột `District_Id` trống trên các bản ghi đăng ký mới |

---

## 2. Chi Tiết Các Mốc Đứt Gãy Quan Trọng Đối Với DKKD

### Mốc 2008: Hà Tây sáp nhập vào Hà Nội (Hiệu lực 01/08/2008)
*   **Chi tiết địa giới:** Sáp nhập toàn bộ tỉnh Hà Tây, huyện Mê Linh (tỉnh Vĩnh Phúc) và 4 xã thuộc huyện Lương Sơn (tỉnh Hòa Bình) vào Thành phố Hà Nội.
*   **Ảnh hưởng dữ liệu:**
    *   Mã địa lý tỉnh Hà Tây cũ biến mất khỏi hệ thống đăng ký mới.
    *   Các doanh nghiệp thành lập trước 08/2008 tại Hà Tây được ánh xạ tự động (auto-mapped) sang Hà Nội, dẫn đến việc phân tích lịch sử mở cửa của các chuỗi (như Co.op Food, WinMart) đăng ký tại khu vực này bị lệch vùng địa giới cũ.
    *   Các địa chỉ cũ ghi "Hà Tây" trong trường `Ho_Address` vẫn được giữ nguyên dạng chuỗi thô, nhưng mã tỉnh (`City_Id`) đã đổi sang mã của Hà Nội.

### Mốc 2025: Sáp Nhập 63 → 34 Tỉnh & Bãi Bỏ Cấp Huyện (Hiệu lực 01/07/2025)
Đây là đợt cải cách sâu rộng nhất, ảnh hưởng trực tiếp đến toàn bộ kiến trúc tìm kiếm và phân tích phân khúc thị trường của DKKD:

#### A. Sáp nhập tỉnh (63 xuống 34) theo Nghị quyết 202/2025/QH15
Toàn bộ ranh giới và mã tỉnh (`City_Id`) của 29 tỉnh bị sáp nhập sẽ đổi sang mã của tỉnh mới. Danh sách sáp nhập chi tiết:
1.  **Hà Giang + Tuyên Quang** $\rightarrow$ **Tuyên Quang**
2.  **Yên Bái + Lào Cai** $\rightarrow$ **Lào Cai**
3.  **Bắc Kạn + Thái Nguyên** $\rightarrow$ **Thái Nguyên**
4.  **Vĩnh Phúc + Hòa Bình + Phú Thọ** $\rightarrow$ **Phú Thọ**
5.  **Bắc Giang + Bắc Ninh** $\rightarrow$ **Bắc Ninh**
6.  **Thái Bình + Hưng Yên** $\rightarrow$ **Hưng Yên**
7.  **Hải Phòng + Hải Dương** $\rightarrow$ **Hải Phòng**
8.  **Hà Nam + Nam Định + Ninh Bình** $\rightarrow$ **Ninh Bình**
9.  **Quảng Bình + Quảng Trị** $\rightarrow$ **Quảng Trị**
10. **Đà Nẵng + Quảng Nam** $\rightarrow$ **Đà Nẵng**
11. **Kon Tum + Quảng Ngãi** $\rightarrow$ **Quảng Ngãi**
12. **Bình Định + Gia Lai** $\rightarrow$ **Gia Lai**
13. **Ninh Thuận + Khánh Hòa** $\rightarrow$ **Khánh Hòa**
14. **Đắk Nông + Bình Thuận + Lâm Đồng** $\rightarrow$ **Lâm Đồng**
15. **Phú Yên + Đắk Lắk** $\rightarrow$ **Đắk Lắk**
16. **TP. Hồ Chí Minh + Bà Rịa - Vũng Tàu + Bình Dương** $\rightarrow$ **TP. Hồ Chí Minh**
17. **Bình Phước + Đồng Nai** $\rightarrow$ **Đồng Nai**
18. **Long An + Tây Ninh** $\rightarrow$ **Tây Ninh**
19. **TP. Cần Thơ + Sóc Trăng + Hậu Giang** $\rightarrow$ **TP. Cần Thơ**
20. **Bến Tre + Trà Vinh + Vĩnh Long** $\rightarrow$ **Vĩnh Long**
21. **Tiền Giang + Đồng Tháp** $\rightarrow$ **Đồng Tháp**
22. **Bạc Liêu + Cà Mau** $\rightarrow$ **Cà Mau**
23. **Kiên Giang + An Giang** $\rightarrow$ **An Giang**
24. **11 Tỉnh/Thành phố giữ nguyên (Không thực hiện sáp nhập):** Cao Bằng, Điện Biên, Hà Tĩnh, Lai Châu, Lạng Sơn, Nghệ An, Quảng Ninh, Thanh Hóa, Sơn La, Hà Nội và thành phố Huế (được nâng cấp từ tỉnh Thừa Thiên Huế).

#### B. Bãi bỏ cấp Huyện (District) theo Luật 72/2025/QH15
*   **Nội dung:** Khoản 3 Điều 51 của Luật 72 chính thức bãi bỏ cấp chính quyền huyện. Hệ thống hành chính Việt Nam chuyển sang mô hình **02 cấp chính quyền** (Cấp Tỉnh và Cấp Xã/Phường).
*   **Ảnh hưởng dữ liệu DKKD:**
    *   Trường `District_Id` bị để trống hoặc trả về giá trị mặc định cho toàn bộ các doanh nghiệp đăng ký mới từ ngày 01/07/2025 trở đi.
    *   Hệ thống định vị địa lý (Geographic Resolution) không thể dựa vào `District_Id` để phân tích mật độ cửa hàng theo Quận/Huyện cho các cửa hàng mở mới sau mốc này.
    *   **Giải pháp xử lý:** Bộ tiền xử lý dữ liệu (`postprocess.py`) và module tra cứu địa giới (`geo_lookup.py`) phải tự động phân tích cú pháp (parse) chuỗi địa chỉ thô `Ho_Address` để trích xuất Quận/Huyện lịch sử dựa trên danh sách địa giới toàn quốc tích hợp sẵn (`geo_lookup.json`).

---

## 3. Các Quy Tắc Nhận Diện Địa Danh & Diacritics Trong Thuật Toán Cào (Scraping Rules)

### Quy tắc Accent Placement (Độ nhạy tone mark của Solr)
Hệ thống Solr cũ của DKKD coi các vị trí đặt dấu thanh khác nhau trên các nguyên âm đôi/ba là các từ khóa tìm kiếm hoàn toàn khác biệt. Cần quét cả 2 biến thể:
*   **Kiểu cũ (Dấu đặt trên âm chính đầu):** `HÓA` (Ví dụ: `BÁCH HÓA XANH`), `HÒA`, `HÒA BÌNH`.
*   **Kiểu mới (Dấu đặt trên nguyên âm cuối):** `HOÁ` (Ví dụ: `BÁCH HOÁ XANH`), `HOÀ`, `HOÀ BÌNH`.
*   **Quy tắc cào:** Luôn cấu hình `brand_regex` và `spelling_variants` bao gồm cả hai hình thức đặt dấu này.

### Tránh Tìm Kiếm Theo Địa Chỉ Thô
*   DKKD không đánh chỉ mục (index) trường `Ho_Address` cho việc tìm kiếm tự do trên Solr.
*   Quét theo từ khóa địa chỉ (Ví dụ: `1003 Bình Giã`) sẽ trả về **0 kết quả**.
*   **Quy tắc thay thế:** Chỉ quét địa lý gián tiếp bằng cách ghép tên thương hiệu với tên tỉnh/thành phố hoặc sử dụng dãy branch của mã số thuế (`parent_mst`).

---

## 4. Hướng Dẫn Mapping Dữ Liệu Lịch Sử Cho Phân Tích Chuỗi

Khi phân tích mật độ cửa hàng lịch sử của các thương hiệu bán lẻ, nghiên cứu viên cần lưu ý:
1.  **Nhóm sáp nhập Hà Nội (2008):** Toàn bộ cửa hàng tại Hà Tây cũ nay có mã `City_Id` trùng với Hà Nội. Cần dựa vào trường quận/huyện trong `Ho_Address` (như Hà Đông, Sơn Tây, Ba Vì, Chương Mỹ, Hoài Đức...) để tách biệt vùng Hà Tây lịch sử.
2.  **Nhóm siêu đô thị Đông Nam Bộ (2025):** Việc sáp nhập Bình Dương và Bà Rịa - Vũng Tàu vào TP. Hồ Chí Minh khiến cho mã `City_Id` của TP. HCM tăng vọt và gộp toàn bộ khu kinh tế trọng điểm phía Nam. Cần dùng geo-parsing để phân rã lại 3 thực thể tỉnh/thành phố cũ nhằm mục đích so sánh số liệu lịch sử trước 2025.
3.  **Hồi tố ngày thành lập:** Các doanh nghiệp đăng ký trước 2025 ở các tỉnh bị giải thể sẽ tự động được cập nhật mã `City_Id` mới của tỉnh sáp nhập tương ứng khi truy vấn trực tiếp qua API tìm kiếm DKKD.
