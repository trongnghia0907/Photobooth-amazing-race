# Event Live Gallery — AMAZING RACE 2026

Trang trình chiếu riêng **/event-display**, độc lập với Host Dashboard và trang ảnh QR. Không có gallery/slideshow sự kiện trước thay đổi này; gallery cũ chỉ dành cho Host. Tính năng mới tái sử dụng FastAPI, SQLite, session_finals và composite đã lưu; không có database hay dịch vụ lưu ảnh thứ hai.

## Chạy và mở màn hình

Tại thư mục repository:

~~~powershell
Set-Location 'D:\Bách Khoa\bÊN LỀ\amazing race 2026\Ptb\OSA_BOOTH_CODEX_STARTER_DOCS'
& backend/.venv/Scripts/python.exe scripts/run_host.py --build
~~~

Nếu server cũ đang chạy, dừng bằng Ctrl+C rồi chạy lại để áp dụng migration 008. Không xóa runtime/DB hoặc ảnh. Giữ nguyên runtime và thông tin Host cũ. Không cần dependency mới; camera/máy in dùng cấu hình hiện có. Nếu đang thử webcam, thêm --camera uvc_demo như hướng dẫn camera hiện tại.

1. Trên laptop mở **http://localhost:8000/admin** và đăng nhập Host.
2. Trong **Màn hình sự kiện**, bấm **Tạo / đổi mã màn hình**. Xác nhận việc thu hồi mã cũ. Mã mới chỉ hiện một lần trong phiên Host này; giữ riêng cho người vận hành, không đưa vào URL.
3. Mở **http://localhost:8000/event-display** trong browser profile riêng hoặc cửa sổ InPrivate/Incognito dành cho màn hình; nhập mã. Không đăng nhập Host trong profile đó.
4. Ban đầu màn hình chờ trống. Tạo ảnh từ booth, chốt/lưu thành công, rồi Host duyệt theo phần dưới.

Vite development cũng proxy /event-display đến backend, nhưng bản chạy sự kiện nên dùng launcher/bản build. Với LAN, dùng profile LAN và IP laptop theo [hướng dẫn Windows](WINDOWS_EVENT_GUIDE.md); máy trình chiếu mở **http://IP-LAPTOP:8000/event-display**, nhập mã riêng, không cần ghép kiosk. HTTP LAN chỉ để thử trên mạng tin cậy. Khi dùng HTTPS riêng, mở cùng origin HTTPS nội bộ và /event-display; cookie production yêu cầu HTTPS.

## Duyệt và ẩn ảnh

Mặc định **không ảnh nào được duyệt**, kể cả ảnh đã có trước khi nâng cấp.

Trong Host → Các phiên chụp → **Xem phiên / In lại**:

- Kiểm tra composite cuối của đúng khách.
- Chọn **Khách đã đồng ý trình chiếu** hoặc **Có ủy quyền phù hợp của sự kiện**.
- Tích xác nhận đã có đồng ý/ủy quyền hợp lệ cho ảnh này, rồi bấm **Duyệt trình chiếu**. Nút chưa hoạt động khi thiếu lựa chọn hoặc xác nhận.
- Bấm **Ẩn khỏi màn hình** để gỡ riêng quyền trình chiếu. Composite gốc, QR, trang Guest và job in được giữ nguyên. Có thể duyệt lại sau khi xác nhận.

Host gallery có nhãn đã duyệt/chưa duyệt. Trạng thái duyệt không phụ thuộc in ảnh hay việc có mã QR: chỉ composite đã chốt bền vững mới đủ điều kiện, thêm duyệt mới được trình chiếu. Không dùng bản in chèn QR làm nguồn ảnh màn hình. Một session có một item màn hình; duyệt lặp không tạo item, token QR hay ảnh mới.

## Máy chiếu / LED 16:9

Kết nối HDMI/USB-C hoặc bộ xử lý LED như màn hình ngoài Windows. Nhấn **Win+P → Extend (Mở rộng)**. Đặt độ phân giải 16:9 phù hợp thiết bị, ví dụ 1920×1080. Kéo cửa sổ Event Live Gallery sang màn hình ngoài; giữ Host Dashboard trên laptop. Tránh Duplicate nếu cần thao tác Host riêng tư.

Chọn **Tường ảnh** để xem tối đa 9 ảnh mới nhất trong khung 16:9; ảnh vừa được duyệt được đặt lớn ở đầu. Chọn **Slideshow** để luân phiên tối đa 60 ảnh được duyệt gần nhất, với nhịp 5/8/12 giây. Ảnh mới được ưu tiên ngay khi feed cập nhật. Ảnh portrait/landscape giữ tỉ lệ, không bị crop hoặc kéo giãn.

Bấm **Toàn màn hình** sau khi chọn chế độ; hoặc dùng **F11** trên Chrome/Edge. Escape/F11 thoát tùy browser. Nếu browser từ chối Fullscreen API, dùng F11 thủ công. Fullscreen không tự được bật khi chưa có thao tác người dùng.

## Tự cập nhật, mất kết nối và khóa

Màn hình poll mỗi **2,5 giây sau khi request trước kết thúc**, timeout 5 giây. Không cần Refresh. Ảnh mới được duyệt hoặc ảnh bị ẩn sẽ cập nhật ở lượt poll tiếp theo. Slideshow tự đổi ảnh và không bị reset mỗi lần poll khi danh sách không đổi.

Khi mất kết nối, màn hình tạm ẩn ảnh, báo đang kết nối lại và tự thử tiếp. Khi backend restart cùng runtime, mã/trạng thái duyệt/cookie màn hình còn hạn được giữ; màn hình tự phục hồi mà không reload. Không có offline photo cache để tiếp tục chiếu ảnh có thể vừa bị Host ẩn.

**Khóa màn hình** thu hồi riêng cookie của màn hình hiện tại và xóa ảnh khỏi trang. Host **Tạo / đổi mã màn hình** thu hồi tất cả cookie màn hình cũ. **Tắt truy cập màn hình** vô hiệu hóa mã và tất cả phiên trình chiếu; không xóa ảnh hoặc quyết định duyệt. Sau bật lại cần nhập mã mới. Cookie hết hạn sau 12 giờ; nhập lại mã đang dùng, hoặc Host tạo mã mới nếu không còn giữ mã.

## Quyền truy cập và dữ liệu

Mã màn hình do Host tạo là ngẫu nhiên, chỉ hash được lưu trong SQLite. Cookie màn hình riêng, HttpOnly, SameSite Strict, Path=/event-display, Secure khi production. Mở khóa có custom header chống cross-origin form và giới hạn 5 lần/phút/IP. Mọi thao tác Host giữ nguyên xác thực/CSRF và giới hạn truy cập laptop ở bản build.

Feed chỉ trả id trình chiếu riêng, URL ảnh có bảo vệ, kích thước và thời điểm duyệt. Không trả session ID, share token, owner token, đường dẫn storage, link tải, ảnh nguồn, thông tin Host hoặc print-ready có QR. Media kiểm tra quyền hiện tại và trạng thái duyệt, không chỉ dựa vào việc biết URL; ảnh bị ẩn trả 404, thiếu quyền trả 401. Phản hồi no-store/no-referrer/noindex; CSP không cho script/ảnh bên thứ ba. Người có quyền xem vẫn có thể chụp màn hình/lưu những pixel đã xem; ẩn ảnh không thu hồi được bản sao trước đó.

**Cổng ảnh public app.public_main và cấu hình Cloudflare chỉ phục vụ /p**, không chứa /event-display, Host hoặc API sự kiện. Không đổi tunnel sang port 8000 để mở màn hình này. Đây là ngoại lệ trình chiếu **có hạn chế quyền**, không phải gallery công khai trên Internet.

Migration 008 chỉ thêm metadata và quyền truy cập; không tự duyệt hay xóa ảnh cũ. Duyệt lưu cơ sở, người duyệt và thời điểm; ẩn lưu thời điểm ẩn. Backup offline hiện có tự bao gồm các bảng này. Chính sách working assets, QR một ảnh/một token và recovery của các phase trước giữ nguyên.

## Kiểm thử và giới hạn

~~~powershell
Set-Location backend
& .venv/Scripts/python.exe -m pytest tests -q
Set-Location ../frontend
npm.cmd test
npm.cmd run build:host
$env:CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
npm.cmd run test:e2e -- --config playwright.event-display.config.js
Set-Location ..
~~~

Xem [kết quả kiểm thử và file thay đổi](EVENT_LIVE_GALLERY_VERIFICATION.md). Test dùng database riêng và ảnh mô phỏng; chưa thử máy chiếu/LED, dây cáp, Wi-Fi phòng hội trường hoặc browser của thiết bị hiển thị thực tế. Cần kiểm tra tại địa điểm trước sự kiện. Màn hình giới hạn 60 ảnh gần nhất, chưa có chia nhiều sự kiện/playlist hoặc moderation tự động; Host duyệt thủ công từng ảnh.
