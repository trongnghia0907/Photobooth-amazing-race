# Thử QR trên điện thoại bằng 4G/5G

## Sửa lỗi QR vẫn trỏ localhost (cập nhật 2026-10-31)

Tunnel demo cũ chạy trên 8010/8011 và storage riêng, nên không đổi QR của Host
8000. Script Windows giờ mặc định gắn vào **Host đang chạy**, cùng storage;
không khởi tạo Host thứ hai, không thay mật khẩu, không tạo ảnh mẫu trong storage thật.

```powershell
# Terminal 1: chạy Host như thường lệ, nhập đúng thông tin cũ.
& .\backend\.venv\Scripts\python.exe .\scripts\run_host.py
# Terminal 2: dừng tunnel demo cũ nếu đang chạy, rồi gắn tunnel vào Host 8000.
.\scripts\stop_mobile_qr_demo.ps1
.\scripts\start_mobile_qr_demo.ps1
```

Nếu Host dùng storage/env khác, truyền đúng cấu hình:

```powershell
.\scripts\start_mobile_qr_demo.ps1 -HostPort 8000 -PublicPort 8001 -StorageRoot 'D:\PhotoboothData' -EnvFile '.\deployment\local.env'
```

Host cần bản backend mới có `runtime_id`, development hoặc rehearsal.
Quick Tunnel không tự đổi cấu hình Event/production. Public gateway chỉ đọc cùng
storage, giữ nguyên Drive mode của Host và không chạy camera/printer/upload worker.
`-RequireDrive` yêu cầu Host đã bật Drive; không tự tắt Drive để khởi động tunnel.
Nếu không có ảnh đã xác nhận/chia sẻ, tunnel có thể sẵn sàng nhưng kiểm tra tải ảnh
sẽ phải chờ phiên đầu tiên; script không tự tạo token hoặc xác nhận ảnh khách.

QR được tự kiểm tra mỗi 5 giây bằng GET. URL HTTPS mới thay origin, giữ nguyên
token. Giao diện hiển thị localhost, đang kết nối, HTTPS công khai hoặc mất tunnel.
Supervisor kiểm tra gateway qua HTTPS mỗi 10 giây; lease hết hạn tối đa 35 giây
nếu mất tiến trình. Khởi động lại tunnel sẽ tạo hostname mới; QR trên màn hình tự
cập nhật. QR đã in trước đó vẫn chứa hostname cũ.

Ảnh đang chờ Drive không được coi là sẵn sàng; không sửa quyền chia sẻ Google
Drive. Link ảnh luôn trỏ website `/p/{token}`, không trỏ Google Drive.

Để dùng lại **demo riêng** (8010/8011, không phải dữ liệu Host 8000):

```powershell
.\scripts\start_mobile_qr_demo.ps1 -StandaloneDemo
```

Các hướng dẫn 8010 phía dưới áp dụng cho `-StandaloneDemo`.

## Bắt đầu trên Windows

Từ thư mục repository:

```powershell
.\scripts\start_mobile_qr_demo.ps1
```

Script kiểm tra/cài gói chính thức Cloudflare.cloudflared nếu cần, tạo demo Rehearsal riêng, kiểm tra isolation local trước khi mở tunnel và lấy URL HTTPS thật từ cloudflared. Chạy Start lần nữa khi demo đang hoạt động sẽ trả lại cùng phiên, không mở tunnel thứ hai.

- Photobooth: http://localhost:8010/booth
- Host Dashboard demo: http://localhost:8010/admin
- Public photo gateway: chỉ loopback 127.0.0.1:8011, chỉ GET các route ảnh /p/{token}; tunnel trỏ vào cổng này.
- Trang QR test có thể mở trực tiếp: `.tools/mobile-qr-demo/mobile-test.html`.
- URL hiện tại và kết quả kiểm tra: `.tools/mobile-qr-demo/status.json`.
- Tài khoản Host demo và mã kiosk: `.tools/mobile-qr-demo/operator.json` (chỉ đọc trên laptop, không chia sẻ file này).

Có thể xem riêng thông tin cần nhập:

```powershell
Get-Content .tools/mobile-qr-demo/operator.json | ConvertFrom-Json | Select-Object username,password,pairing_code
```

Host đang chạy ở cổng 8000 không bị dừng hoặc đổi mật khẩu. Demo dùng storage riêng `.tools/mobile-qr-demo/storage`, MockCamera/MockPrinter có nhãn DEMO và không in giấy thật. Host có thể chọn UVC DEMO trong Camera Settings nếu OpenCV/driver đã được cài và webcam được phép truy cập.

## Quét ngay

1. Mở `mobile-test.html` trên laptop để thấy QR của hai composite mẫu 4/6 ảnh.
2. Tắt Wi-Fi trên điện thoại và bật 4G/5G.
3. Quét QR bằng Camera/Zalo, mở Guest Photo Page rồi bấm **Download Image • Tải ảnh**.

Để thử ảnh của phiên mới: mở Photobooth 8010, nhập pairing_code khi được hỏi, chụp và xem lại, bấm **Xác nhận ảnh & nhận QR**. QR nằm tại giao diện kết quả sau khi composite đã được lưu. Không có token/QR cho phiên chưa xác nhận.

Giữ laptop online, không sleep; giữ supervisor demo, Host 8010, public gateway 8011 và cloudflared đang chạy. Script khởi chạy nền, nên đóng terminal sau khi báo running không dừng demo.

## Dừng và khởi động lại

```powershell
.\scripts\stop_mobile_qr_demo.ps1
.\scripts\start_mobile_qr_demo.ps1
```

Stop chỉ yêu cầu supervisor dừng các Popen process mà nó đã tạo. Không tìm/kill ứng dụng theo port hoặc tên process. Không sửa firewall, task scheduler hay production credentials. Nếu port đang được ứng dụng khác dùng, script báo lỗi và không kill process đó.

Ảnh, SQLite, share key, token và tài khoản demo được giữ. Hai fixture mẫu được tái sử dụng. URL Quick Tunnel có thể đổi khi restart; dùng QR mới trong trang test hoặc reload kết quả / bấm **Xác nhận & Tạo QR** để lấy origin mới. Composite, file QR gốc và bản in đã lưu không bị ghi đè khi origin thay đổi; QR đã nhúng trong bản in cũ vẫn chứa URL cũ. Không dùng bản in cũ để kiểm tra hostname mới.

URL mới chỉ là override cục bộ có hạn trong development/rehearsal. Event/production bỏ qua override; PUBLIC_BASE_URL môi trường không bị sửa. Khi Stop, override bị xóa. Link tunnel ngừng hoạt động khi tunnel tắt. Không coi đây là URL sự kiện lâu dài.

Nếu supervisor gặp lỗi, nó dừng các service thuộc demo và xóa override. Xem `status.json`, `supervisor.log`, `host.log`, `public.log`, `cloudflared.log` trong thư mục demo. Chạy Stop rồi Start; không mở thêm tunnel thủ công vào cổng Host.

## Kiểm tra và bảo mật

Startup tự kiểm tra:

- Trang ảnh/token hợp lệ, hai token khác nhau; token sai không truy cập được.
- PNG image/download khớp; Download có attachment header.
- QR được decode bằng zxingcpp và khớp HTTPS URL thật.
- Các đường dẫn admin, login, camera, print, kiosk, gallery, storage, env, docs và healthz đều không phục vụ qua public gateway.
- SHA256 composite mẫu trước/sau cấu hình URL không đổi.

Các HTTP test không thay thế việc quét trên điện thoại thật.

Regression:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_mobile_qr.py tests/test_sharing.py tests/test_deployment.py -q
cd ../frontend
npm test
npm run build:host
npx playwright test --config playwright.mobile.config.js
```

Playwright mobile suite chạy trên demo đã Start. Nó tạo một phiên Mock có chủ đích, chụp bốn ảnh, xác nhận composite, khôi phục phiên sau reload, kiểm tra QR HTTPS và làm mới metadata mà không upload composite lần nữa. Cổng mặc định là 8010/8011; có thể dùng `-HostPort` và `-PublicPort` khi Start nếu cổng bị chiếm (Playwright config dùng cổng mặc định).

Cloudflare Quick Tunnel chính thức: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
