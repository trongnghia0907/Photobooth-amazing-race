# Event Live Gallery — AMAZING RACE 2026

Trang trình chiếu riêng **/event-display**, độc lập với Host Dashboard và trang ảnh QR. Không có gallery/slideshow sự kiện trước thay đổi này; gallery cũ chỉ dành cho Host. Tính năng mới tái sử dụng FastAPI, SQLite, session_finals và composite đã lưu; không có database hay dịch vụ lưu ảnh thứ hai.

## Chạy và mở màn hình

Tại thư mục repository:

~~~powershell
Set-Location '<path-to-repository>'
& backend/.venv/Scripts/python.exe scripts/run_host.py --build
~~~

Nếu server cũ đang chạy, dừng bằng Ctrl+C rồi chạy lại để áp dụng migration 008. Không xóa runtime/DB hoặc ảnh. Giữ nguyên runtime và thông tin Host cũ. Không cần dependency mới; camera/máy in dùng cấu hình hiện có. Nếu đang thử webcam, thêm --camera uvc_demo như hướng dẫn camera hiện tại.

1. Trên laptop mở **http://localhost:8000/admin** và đăng nhập Host.
2. Trong **Màn hình sự kiện**, bấm **Tạo / đổi mã màn hình**. Xác nhận việc thu hồi mã cũ. Mã mới chỉ hiện một lần trong phiên Host này; giữ riêng cho người vận hành, không đưa vào URL.
3. Mở **http://localhost:8000/event-display** trong browser profile riêng hoặc cửa sổ InPrivate/Incognito dành cho màn hình; nhập mã. Không đăng nhập Host trong profile đó.
4. Ban đầu màn hình chờ trống. Khách bấm **Xác nhận, chiếu ảnh & nhận QR**; composite mới được publish sau khi lưu thành công, không cần duyệt từng ảnh.

Vite development cũng proxy /event-display đến backend, nhưng bản chạy sự kiện nên dùng launcher/bản build. Với LAN, dùng profile LAN và IP laptop theo [hướng dẫn Windows](WINDOWS_EVENT_GUIDE.md); máy trình chiếu mở **http://IP-LAPTOP:8000/event-display**, nhập mã riêng, không cần ghép kiosk. HTTP LAN chỉ để thử trên mạng tin cậy. Khi dùng HTTPS riêng, mở cùng origin HTTPS nội bộ và /event-display; cookie production yêu cầu HTTPS.

## Duyệt và ẩn ảnh

Chính sách auto-publish mặc định bật, nhưng vẫn yêu cầu consent trên đúng composite. Nút **Xác nhận, chiếu ảnh & nhận QR** gửi consent rõ ràng; các thao tác xác nhận/recovery khác không tự cấp consent. Host có thể tắt bằng `EVENT_GALLERY_AUTO_PUBLISH=false`. Ảnh riêng tư lịch sử không được quét để publish; retry sau khi chốt hoặc sau khi Host ẩn không tái publish. Drive upload được xếp job độc lập, không cần SYNCED để dùng ảnh local an toàn.

Với ảnh cũ cần duyệt riêng hoặc khi muốn ẩn ảnh, trong Host → Các phiên chụp → **Xem phiên / In lại**:

- Kiểm tra composite cuối của đúng khách.
- Chọn **Khách đã đồng ý trình chiếu** hoặc **Có ủy quyền phù hợp của sự kiện**.
- Tích xác nhận đã có đồng ý/ủy quyền hợp lệ cho ảnh này, rồi bấm **Duyệt trình chiếu**. Nút chưa hoạt động khi thiếu lựa chọn hoặc xác nhận.
- Bấm **Ẩn khỏi màn hình** để gỡ riêng quyền trình chiếu. Composite gốc, QR, trang Guest và job in được giữ nguyên. Có thể duyệt lại sau khi xác nhận.

Host gallery có nhãn đã duyệt/chưa duyệt. Trạng thái duyệt không phụ thuộc in ảnh hay việc có mã QR: chỉ composite đã chốt bền vững mới đủ điều kiện, thêm duyệt mới được trình chiếu. Không dùng bản in chèn QR làm nguồn ảnh màn hình. Một session có một item màn hình; duyệt lặp không tạo item, token QR hay ảnh mới.

## Máy chiếu / LED 16:9

Kết nối HDMI/USB-C hoặc bộ xử lý LED như màn hình ngoài Windows. Nhấn **Win+P → Extend (Mở rộng)**. Đặt độ phân giải 16:9 phù hợp thiết bị, ví dụ 1920×1080. Kéo cửa sổ Event Live Gallery sang màn hình ngoài; giữ Host Dashboard trên laptop. Tránh Duplicate nếu cần thao tác Host riêng tư.

Màn hình có đúng bốn ô cố định ở bốn góc, giữ vùng giữa trống. Ảnh mới lấp ô trống trước, sau đó thay ảnh nằm lâu nhất trong cùng ô, fade out/in khoảng 500 ms. Không có toolbar, slideshow hoặc đổi ảnh theo timer. Ảnh giữ tỉ lệ, không crop hay kéo giãn.

Dùng **F11** trên Chrome/Edge để fullscreen; Escape/F11 thoát tùy browser.

## Tự cập nhật, mất kết nối và khóa

Màn hình poll mỗi **2,5 giây sau khi request trước kết thúc**, timeout 5 giây. Không cần Refresh. Ảnh mới publish hoặc ảnh bị ẩn cập nhật ở lượt poll tiếp theo. Sidebar Guest dùng feed đã publish và tự cập nhật khoảng 5 giây.

Khi mất kết nối, màn hình giữ bố cục/ảnh hiện tại, báo đang kết nối lại và tự thử tiếp. Sau reconnect, ảnh thu hồi được gỡ và ảnh mới được xử lý tuần tự, không trùng. Backend restart cùng runtime giữ trạng thái publish và cookie còn hạn.

Host **Tạo / đổi mã màn hình** thu hồi cookie màn hình cũ. **Tắt truy cập màn hình** vô hiệu hóa mã và mọi phiên trình chiếu; không xóa ảnh hoặc quyết định publish. Sau bật lại cần nhập mã mới. Cookie hết hạn sau 12 giờ.

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

Test dùng database riêng và ảnh mô phỏng; chưa thử máy chiếu/LED và mạng tại hội trường. Màn hình chỉ hiển thị bốn ảnh, lấy feed tối đa 100 ảnh để khôi phục cập nhật sau mất mạng; chưa có nhiều sự kiện/playlist. Các phiên mới qua nút công bố rõ ràng tự publish; Host vẫn có quyền ẩn/thu hồi.
