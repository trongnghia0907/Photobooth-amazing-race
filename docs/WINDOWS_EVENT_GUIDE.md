# Cập nhật Event Readiness và cấu hình Windows 11

Windows 11 là nền tảng chính. Xem [cấu hình Event/rehearsal](EVENT_CONFIGURATION.md) trước khi dùng các ví dụ mạng bên dưới. macOS có [hướng dẫn riêng](MACOS_SETUP.md), chưa được kiểm thử trực tiếp.

Giữ các bước cài Python/Node/driver trong tài liệu này. Với vận hành có cấu hình cố định:

```powershell
Copy-Item deployment/event.env.example deployment/event.env
# Sửa file bằng editor: hostname, TLS riêng, credentials, runtime, camera, printer.
& backend/.venv/Scripts/python.exe scripts/run_host.py --env-file deployment/event.env --check --no-prompt
.\scripts\start_event.ps1 --env-file deployment/event.env --build
# Dừng từ terminal khác, vẫn dùng đúng file/runtime:
.\scripts\stop_event.ps1 --env-file deployment/event.env
```

`--check` không chụp/in và không mở tunnel. Ví dụ Event chưa thể nghiệm thu vật lý khi vendor SDK chưa tích hợp. Để diễn tập bằng Mock, dùng `--mode rehearsal --allow-mock-hardware`; webcam video-frame cần thêm `--camera uvc_demo`. Không xóa nhãn DEMO để giả thành camera thật.

Sau cập nhật source, dừng launcher cũ rồi khởi động lại; build frontend riêng không cập nhật được API đang chạy. Log private/public nằm trong `runtime/logs` hoặc `OSA_LOG_DIRECTORY`; kiểm tra Host Dashboard để xem mode, ổ đĩa, camera và máy in. Không tạo Scheduled Task tự động.

# Máy chiếu / LED — bổ sung Phase 6

Sau khi restart server mới, Host mở /admin → Màn hình sự kiện → tạo mã riêng; duyệt từng composite đã chốt với cơ sở đồng ý/ủy quyền. Mở **http://localhost:8000/event-display** ở browser profile riêng, nhập mã và chọn Tường ảnh hoặc Slideshow → Toàn màn hình/F11. Kết nối HDMI/USB-C, dùng Win+P → Extend để giữ Host trên laptop; kéo cửa sổ trình chiếu sang màn hình ngoài. Không cần refresh.

Hướng dẫn đầy đủ cho LAN/HTTPS, duyệt/ẩn ảnh và khôi phục kết nối: [EVENT_LIVE_GALLERY](EVENT_LIVE_GALLERY.md). Gallery mới không được mở trên public photo gateway/tunnel hiện có. Các bước Windows/camera/printer bên dưới vẫn áp dụng.

---

# Windows 11 — vận hành Phase 6

Chỉ camera Mock và máy in Mock được kiểm thử tự động. Chưa xác nhận model DSLR/mirrorless, SDK, iPad, máy in hay mạng sự kiện. Không bật chế độ vendor để kỳ vọng chụp thật: adapter báo chưa hỗ trợ. Không có VPS hoặc dịch vụ lưu ảnh bên thứ ba.

## Cài đặt và chạy thử trên laptop

Mở PowerShell tại repository. Python 3.12 và Node >=22.12 cần có trên PATH.

```powershell
Set-Location '<path-to-repository>'
py -3.12 -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
Set-Location frontend
npm.cmd ci
npm.cmd run build:host
Set-Location ..
& backend/.venv/Scripts/python.exe scripts/run_host.py
```

Launcher hỏi tên Host, mật khẩu Host (ít nhất 12 ký tự) và mã ghép kiosk (ít nhất 16 ký tự). Giữ cùng thông tin cho lần khởi động lại. Mật khẩu/mã được nhập ẩn; không có tài khoản mặc định. `.env.example` là tài liệu, không tự được đọc. Có thể cung cấp biến môi trường từ công cụ quản lý bí mật; không đặt giá trị thật trong Git hoặc tham số dòng lệnh.

Mở **http://localhost:8000/booth**; nhập mã kiosk. Host trên laptop: **http://localhost:8000/admin**. Kiểm tra sức khỏe: `Invoke-RestMethod http://localhost:8000/api/health`. Không cần chạy Vite. `/` cũng mở booth, không còn trả 404.

Chọn frame, 4/6 ảnh, timer → Bắt đầu chụp → xem lại/chụp lại → Result → **Xác nhận & lưu ảnh**. QR tự hiện sau lưu và tạo share thành công. Chọn số bản → In ảnh. Mock chỉ ghi nhận job, không in giấy. QR localhost chỉ mở trên laptop này.

## Local development với Vite (chỉ loopback)

Dừng launcher trước; dùng runtime development riêng. Cửa sổ PowerShell 1, tại repository:

```powershell
$env:OSA_FRONTEND_DIST=$null
$env:OSA_STORAGE_ROOT=Join-Path (Get-Location) '.tools/development-runtime'
& backend/.venv/Scripts/python.exe scripts/run_local_backend.py --admin
```

Cửa sổ PowerShell 2, tại repository:

```powershell
Set-Location frontend
npm.cmd run dev:host
```

Mở **http://127.0.0.1:5173**; Host tại **http://localhost:8000/admin**. `npm.cmd run dev` dùng demo canvas cũ thay host camera, vẫn ghi dữ liệu qua backend. Vite proxy `/api`, `/p`, `/admin` đến 127.0.0.1:8000; có thể đổi bằng OSA_BACKEND_URL khi phát triển. Dừng mỗi cửa sổ bằng Ctrl+C. `stop_host.py` chỉ dừng launcher có manifest, không dừng Uvicorn/Vite chạy thủ công. Development không có lớp ghép kiosk của bản build; không dùng làm public origin hoặc cho mạng không tin cậy.

## Dừng, restart, backup và phục hồi

Giữ cửa sổ launcher mở. Nhấn Ctrl+C, hoặc từ PowerShell khác tại repository:

```powershell
& backend/.venv/Scripts/python.exe scripts/stop_host.py
```

Nếu dùng `--storage-root`, truyền đúng thư mục đó cho stop và backup. Launcher dùng khóa tiến trình, không tự mở nhiều worker trên cùng runtime. Nếu camera/in đang bận, dừng cho phép hoàn tất có giới hạn; job còn không chắc chắn sau lỗi không tự in lại. Kiểm tra giấy thực tế trước khi retry.

Sau khi dừng, sao lưu sang thư mục **mới**, nằm ngoài runtime (thay tên ngày nếu đã tồn tại):

```powershell
& backend/.venv/Scripts/python.exe scripts/backup_runtime.py --output .tools/backup-before-event-20261030
```

Backup từ chối khi ứng dụng còn hoạt động, không ghi đè, không xóa nguồn; sao chép DB và ảnh cùng `.share-key`, kèm SHA256 manifest. Giữ backup riêng tư. Phục hồi bằng cách chạy `--storage-root` trỏ **bản sao** đã kiểm tra manifest; giữ nguyên runtime cũ. Mất `.share-key` sẽ làm hỏng QR cũ. Không xóa DB, WAL hoặc file khóa để chữa lỗi khi server còn chạy. Chỉ chạy một ứng dụng sở hữu camera/máy in, không chạy đồng thời Vite/backend thủ công trên cùng runtime triển khai.

## iPad qua LAN và QR Wi-Fi

Chạy `ipconfig`, lấy IPv4 Wi-Fi của laptop, ví dụ **192.168.1.20**; iPad và điện thoại phải cùng Wi-Fi, không bật client isolation. Dừng bản local trước rồi chạy:

```powershell
& backend/.venv/Scripts/python.exe scripts/run_host.py --profile lan --lan-ip 192.168.1.20
```

Mở **http://192.168.1.20:8000/booth** trên iPad và ghép mã. Cho phép Python qua Windows Firewall **Private network**, giới hạn subnet nội bộ; không bật Public network hoặc chuyển tiếp cổng router. Host Dashboard chỉ mở trên laptop qua localhost. Nút Start dùng camera trên laptop, không xin webcam iPad.

Profile LAN dùng APP_ENV=development, có nhãn LAN/Wi-Fi trên QR, không dùng trên 4G/5G và HTTP không mã hóa. Chỉ dùng trên mạng tin cậy để thử. Đổi IP/public origin không đổi các QR đã phát: URL được ghim theo ảnh, nên phải giữ hostname/IP cũ hoặc tạo phiên mới sau thay cấu hình. Đặt DHCP reservation trước sự kiện. Bản production dùng HTTPS như dưới đây.

## HTTPS riêng cho iPad và HTTPS public cho điện thoại

Hai cổng độc lập: **8000 private kiosk/API/Host**, **8001 photo-only loopback**. Chỉ `/p/{token}` và ảnh/download/QR liên quan được public; không proxy toàn bộ 8000 ra Internet. Cổng public không chạy camera, in hay cleanup.

Nếu có certificate/key hợp lệ cho host nội bộ, chạy HTTPS trực tiếp bằng `--profile https --mode rehearsal --allow-mock-hardware --public-url https://photos.example.com --ssl-certfile <certificate.pem> --ssl-keyfile <private-key.pem> --tls-host 192.168.1.20 --bind 0.0.0.0 --public-gateway`. Bảo vệ file khóa bên ngoài repo. URL iPad phải khớp certificate và được iPad tin cậy. Certificate trực tiếp cần SAN gồm cả IP/hostname iPad sử dụng và DNS:localhost để Host mở https://localhost:8000/admin từ laptop. --tls-host phải khớp tên/IP trong certificate cho kiểm tra health.

Cách khác: chuẩn bị Caddy riêng trên LAN, sao chép `deployment/Caddyfile.example` ra file cấu hình ngoài repo, thay IP rồi chạy Caddy theo [tài liệu TLS chính thức](https://caddyserver.com/docs/caddyfile/directives/tls). `tls internal` cần cài và tin cậy root CA trên iPad một cách chủ động; ví dụ tắt tự cài trust. Không bỏ qua xác minh certificate. Backend phía sau proxy:

```powershell
& backend/.venv/Scripts/python.exe scripts/run_host.py --profile https --mode rehearsal --allow-mock-hardware --behind-proxy --public-url https://photos.example.com --public-gateway
```

Chỉ proxy loopback được tin forwarded headers; Caddy chuyển IP thật, nên `/admin` từ iPad vẫn bị chặn. Với Caddy example, trên laptop mở Host qua https://localhost:8443/admin (đã tin cậy CA); iPad mở https://192.168.1.20:8443/booth. Không mở Host bằng LAN IP vì backend chỉ cho client loopback. Cookie production có Secure; đăng nhập Host/ghép kiosk bằng HTTP trực tiếp 8000 sẽ không hoạt động đúng. Đường kết nối Caddy→backend loopback dùng HTTP; iPad→Caddy dùng HTTPS.

**Không có tunnel nào được tự động tạo hay chạy bởi dự án.** Các lệnh sau là thao tác tùy chọn của người vận hành; tạo tunnel/DNS là tạo tài nguyên ngoài máy. Cần domain và quyền quản lý Cloudflare. Cài cloudflared theo [tài liệu chính thức](https://developers.cloudflare.com/tunnel/get-started/), sau đó cấu hình [tunnel với hostname ổn định](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/):

```powershell
cloudflared tunnel login
cloudflared tunnel create amazing-race-photos
cloudflared tunnel route dns amazing-race-photos photos.example.com
```

Sao chép `deployment/cloudflared.example.yml` vào `$env:USERPROFILE/.cloudflared/config.yml`, thay UUID, đường dẫn credentials và hostname. Giữ credentials trong thư mục người dùng, không trong repo. Origin luôn là **http://127.0.0.1:8001**. Kiểm tra trước khi chủ động mở tunnel:

```powershell
cloudflared tunnel --config "$env:USERPROFILE/.cloudflared/config.yml" ingress validate
cloudflared tunnel --config "$env:USERPROFILE/.cloudflared/config.yml" run amazing-race-photos
```

Quy tắc hostname/path và catch-all 404 theo [tài liệu cấu hình](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/). Public hostname phải trùng `--public-url` từ **trước khi chốt ảnh**. Tunnel tạm `cloudflared tunnel --url http://127.0.0.1:8001` có URL thay đổi; chỉ dùng khi chủ động thử, cập nhật PUBLIC_BASE_URL và khởi động lại trước phiên mới. QR cũ không tự đổi domain. Laptop phải chạy và có Internet khi khách tải ảnh; tắt tunnel/server thì link tạm không truy cập được. Chưa thử mạng ngoài/4G trong phiên kiểm thử này.

## iPad, Host, camera, máy in

Setup landscape: workspace khoảng 75%, sidebar 25%, chỉ ảnh của khách hiện tại. Start vào fullscreen CSS (không phụ thuộc Fullscreen API của Safari), preview giữ tỉ lệ, countdown/progress lớn. Tạm dừng/Thoát nếu cần. Sau retake/edit, xác nhận lưu rồi mới có QR/in. Phiên mới xóa preview/state cá nhân; thao tác bỏ ảnh chưa chốt yêu cầu xác nhận. Zoom vẫn được cho phép. Safari thực tế còn cần kiểm thử thủ công.

Host đăng nhập `/admin`: gallery chỉ composite đã chốt, chi tiết có bản gốc và bản QR in; số bản in lại không tạo token mới. Xem hàng đợi, lỗi, camera và printer. Logout hết phiên Host. Không đưa mật khẩu Host cho khách; mã kiosk cũng chỉ người vận hành ghép thiết bị. Cookie kiosk hết hạn sau 12 giờ, nhập lại cùng mã trên cùng browser để phục hồi quyền; thay mã sẽ thu hồi các station cũ. Phiên làm dở chỉ ở bộ nhớ browser, reload không tự phục hồi canvas; backend giữ working assets để người vận hành kiểm tra, không xóa mù.

Camera Mock mặc định. Xem [giới hạn thiết bị](HARDWARE_COMPATIBILITY.md). `--camera vendor` báo blocked cho đến khi có model/SDK; không thay ảnh gốc bằng Live View. `--camera uvc_demo` cần dependency OpenCV tùy chọn và chỉ cho demo, không phải shutter DSLR. Camera lỗi/mất USB: dừng countdown, reconnect trên Host, retry cùng capture; không bấm shutter thật liên tục khi chưa biết lần trước đã chụp chưa.

Máy in Mock mặc định. Chỉ khi đã cài đúng Windows driver và muốn in thật: `--printer windows --enable-physical-printing`, rồi chọn máy in trong Host. Thử một bản, giấy/margin/tỉ lệ/QR trước khi in hàng loạt. `submitted` chỉ là đã gửi spooler, không xác nhận giấy đã ra. Printer rớt: kiểm tra spooler/giấy rồi retry từ Host sau khi xác minh chưa in, tránh trùng giấy.

Mất Wi-Fi: giữ browser mở, không bấm New Session/reload khi đang lưu; retry sau kết nối lại, idempotency giữ cùng thao tác. Laptop restart: mở lại cùng runtime và bí mật, ảnh đã chốt/QR/job còn trong SQLite; job interrupted được đánh dấu failed/uncertain, không tự in lại. Giữ laptop cắm điện; Settings → System → Power & battery → Screen, sleep & hibernate: tắt Sleep khi cắm điện cho thời gian sự kiện, phục hồi thiết lập sau sự kiện. Tắt auto reboot trong khung vận hành theo chính sách máy.

## Lệnh kiểm thử phần mềm

```powershell
Set-Location backend
& .venv/Scripts/python.exe -m pytest tests -q
Set-Location ../frontend
npm.cmd test
npm.cmd run build
npm.cmd run build:production -- --outDir dist-production
npm.cmd run build:host
$env:CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
npm.cmd run test:e2e -- --config playwright.isolated.config.js
npm.cmd run test:e2e -- --config playwright.deployment.config.js
Set-Location ..
```

Các test dùng DB riêng trong temp hoặc `.tools`, Mock adapters, không xóa runtime ảnh thật.
