# Phase 4 — Printing System & Host Dashboard

Phạm vi: giữ frontend/editor Phase 1–3; thêm print-ready + queue + Host. Không camera SDK, Frame Editor nâng cao, tunnel production, commit/push hoặc Phase 5.

## Mốc Phase 3 trước thay đổi

Đã thực chạy: backend **42 passed**, Playwright **14 passed**, build demo và production PASS. Kiểm tra capture 4/6, retake/delete, pending upload/lost response, composite confirmation, finalize, QR riêng, Guest A/B download và 18 so sánh pixel compositor với legacy. Giữ nguyên HTML gốc và legacy.

## Chức năng và luồng

Confirm composite → lưu original composite → complete → stable share/QR → tạo PNG print-ready cùng transaction → ACK → QR và preview tự xuất hiện → POST print job → FIFO worker → Mock/GDI adapter → persisted status.

Ảnh print-ready thêm một footer trắng nằm hoàn toàn dưới composite, QR giữ quiet zone và phóng theo số nguyên module. Không crop/đè ô ảnh; giữ tỷ lệ. Ảnh nhỏ được upscale đồng tỷ lệ tới tối thiểu 640px; ảnh tỷ lệ cực đoan bị từ chối thay vì cấp phát bộ nhớ quá lớn. Composite gốc giữ nguyên byte/hash. `/p/{token}/image` và `/download` trả **chính file** được gửi tới printer; reprint giữ token/file cũ. Share Phase 3 cũ được tạo derivative một lần khi finalize/guest lookup, không rotate token.

SQLite migration 004 thêm `print_ready`, `print_jobs`, `host_settings`, `admin_credentials`, `admin_sessions`. Queue FIFO, idempotency theo quyền + key + payload, copies 1..MAX_PRINT_COPIES (mặc định 3, cấu hình tối đa 100). Worker OS file lock đảm bảo một worker dispatch trên cùng runtime. Job `processing` bị ngắt thành `failed/uncertain` sau restart; không tự retry. Job queued tiếp tục sau restart. Reprint/retry là job mới có audit `retry_of`; ambiguous retry cần xác nhận. Không thay đổi ảnh khi in lỗi.

`submitted` = adapter đã nhận/spool, không phải giấy đã in xong. Mock ghi bản sao PNG trong runtime/mock_prints và receipt số bản, không gửi OS printer. Windows GDI tạo printer DC, contain-fit cả bản in trên vùng printable, một page/copy, StartDoc/EndDoc; lỗi sau khi bắt đầu được coi là chưa rõ kết quả. Không tự chọn tên máy in thật. CUPS mới có contract `PrinterAdapter`, chưa implementation.

Dashboard `/admin` chỉ public login shell, toàn bộ dữ liệu/ảnh/hành động `/api/admin/*` đều xác thực backend. ENV creds, PBKDF2 SHA256 600000 vòng, session token ngẫu nhiên chỉ lưu hash, cookie HttpOnly/SameSite Strict, Secure ở production, 8h, CSRF cho mutations, giới hạn login 5 lần/phút/IP. Đổi credentials thu hồi session cũ. Không password frontend/localStorage hoặc credentials mặc định. Gallery phân trang, composite/print-ready/download/chi tiết, print queue, chọn printer, retry/cancel, system counts và polling 3s.

Result giữ canvas chỉnh sửa và download composite cũ; thêm preview/download bản có QR, copies, nút In ảnh và trạng thái. `triggerPrint` giữ tên facade nhưng gọi API, không window.print. Sau mất ACK, giữ cùng key/copies để retry không in trùng. In lại sau submitted/lỗi qua Host. Cài đặt auto-print cũ không tự gửi giấy trước confirm; hiện thông báo yêu cầu thao tác rõ ràng.

## File tạo mới

- `backend/app/migrations/004_printing.sql`: schema mới.
- `backend/app/services/print_ready.py`: derivative + footer QR, immutable metadata.
- `backend/app/services/printing.py`: queue, worker, lease, idempotency, status.
- `backend/app/services/printers.py`: protocol + Windows GDI, controlled errors.
- `backend/app/services/admin_auth.py`: credentials, cookie sessions, CSRF, login throttle.
- `backend/app/printing_routes.py`: owner print API + protected Host API.
- `backend/app/admin_page.py`, `backend/app/admin_ui/{index.html,dashboard.js,dashboard.css}`: login/dashboard assets, fixed whitelist.
- `backend/tests/test_printing.py`: Phase 4 automated acceptance.
- `docs/PHASE4_REPORT.md`, screenshots `phase4-host-dashboard.png`, `phase4-print-result.png`.

File sửa Phase 4: backend config/database/main/routers/repository/sharing/mock_printer, requirements và lock, `.env.example`; backend tests sessions/sharing/restart; frontend index, store/events/main/result, photo-repository/print-client, vite proxy; Playwright config/isolated/local QR config, backend-server và E2E/QR assertions; scripts/run_local_backend.py; README/API_CONTRACT/ACCEPTANCE_TESTS/SECURITY_PRIVACY/MIGRATION_LOG. Các sửa QR local có sẵn được giữ nguyên; không reset working tree.

## Kiểm thử

API mới: GET `/api/print-config`; POST `/api/sessions/{sid}/print-jobs`; GET `/api/sessions/{sid}/print-jobs/{job_id}`; `/api/admin/login`, `/me`, `/logout`, `/status`, `/sessions`, `/sessions/{sid}`, `/sessions/{sid}/images/{kind}/{id}`, `/print-jobs`, `/print-jobs/{id}/retry`, `/print-jobs/{id}/cancel`, `/printers`, `/printers/selected`. Method, body, auth và lỗi cụ thể ở [API_CONTRACT](API_CONTRACT.md#phase-4--schema-4-current).

Kết quả cuối: backend **59/59 PASS**, Node **8/8 PASS**, Playwright full **15/15 PASS**, QR localhost **3/3 PASS**, Phase 4 E2E chạy lại sau hardening polling/copies **1/1 PASS**. Build demo và production **PASS**. Có một assertion E2E cũ so download với original composite; đã sửa sang descriptor print-ready đúng yêu cầu Phase 4 rồi chạy lại full suite. Node runner từng bị sandbox chặn spawn EPERM; chạy lại với quyền tạo subprocess đã PASS. Không có test in giấy hoặc phone public.

Lệnh từ backend: `.venv/Scripts/python.exe -m pytest -q --tb=short`.

Lệnh từ frontend (PowerShell):

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run build:production -- --outDir dist-production
$env:CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
npm.cmd run test:e2e -- --config playwright.isolated.config.js
npm.cmd run test:e2e -- --config playwright.qr-confirm.config.js
```

Chạy hai bộ Playwright nối tiếp vì dùng chung port 5183. Config dùng storage fixture `.tools/`, ép Mock; không tác động runtime thật. Screenshots fixture đã xem trực tiếp để xác nhận QR footer và gallery original/print-ready. Node test mới kiểm tra pagehide trong lúc request status chưa trả về không tự khởi động polling lại (`frontend/tests/printing.test.js`).

Các bài backend mới giải mã QR từ ảnh 4 ngang/6 dọc/6 ngang, so crop composite gốc, SHA file Guest=Mock, copies 1/3, key duplicate/conflict, FIFO, cancel, fail/uncertain/retry, lease 2 workers, queued restart, interrupted processing, thiếu file, gallery auth/IDOR, CSRF/logout/password rotation/rate-limit/Secure cookie, Windows GDI fake (không device), backfill share cũ.

E2E thêm: confirm → print preview → 2 copies → mất ACK HTTP → retry cùng key chỉ một job → submitted Mock → Host login/gallery/download/reprint → Guest denied admin → logout. Regression giữ tests pixel parity, filters/stickers/text/timers/retake/manual upload và QR.

## Chạy và kiểm tra thủ công

Từ gốc: `python scripts/run_local_backend.py --admin`, nhập account/password riêng; terminal khác `cd frontend`, `npm.cmd ci`, `npm.cmd run dev`. Script ép Mock và localhost; không đổi biến toàn hệ thống. `.env.example` chỉ tham khảo, không tự nạp `.env`.

Mở localhost:5173 → chụp đủ 4/6 → chỉnh/filter/retake → Xác nhận & Tạo QR. Xem bản in có QR, chọn 1–3 bản, In ảnh. Kiểm tra Mock đã nhận. Mở localhost:8000/admin → đăng nhập → xem phiên/ảnh gốc/ảnh QR → tải ảnh → in lại → xem jobs/copies/status → logout. Không đăng nhập gọi `/api/admin/sessions` phải 401. File runtime không public. Mở Guest link → tải PNG phải đúng bản có QR. Thay editor sau confirm phải xác nhận revision mới mới được in.

## Windows thực tế (chưa kiểm thử giấy)

Chỉ khi chủ động thử một bản: cài driver/máy in, dừng helper Mock, terminal backend đặt APP_ENV=development, PUBLIC_BASE_URL=http://localhost:8000, ADMIN_USERNAME/ADMIN_PASSWORD của bạn, PRINTER_MODE=windows và ENABLE_PHYSICAL_PRINTING=true; chạy `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Mở `/admin`, chọn đúng printer driver, xác nhận giấy/kích thước/hướng từ Windows Printing Preferences; thử **một bản** và kiểm tra QR, lề, màu. Không dùng printer PDF/XPS tương tác cho luồng sự kiện. Helper local luôn Mock, không dùng để bật in thật.

Adapter dùng [Windows GDI print functions](https://learn.microsoft.com/en-us/windows/win32/printdocs/gdi-print-api-functions) và [pywin32 PyCDC](https://timgolden.me.uk/pywin32-docs/PyCDC.html); tự động tests thay GDI bằng fake. Không thử máy in vật lý, không xác nhận driver/paper/cắt ảnh/màu/DPI của thiết bị thật.

## Giới hạn và việc sau Phase 4

- Chưa kiểm chứng in giấy, điện thoại ngoài mạng, public DNS/TLS/Internet. Localhost không dùng trên điện thoại khác. Cần public HTTPS ổn định để QR in cho khách dùng thực tế; không tự triển khai tunnel.
- Footer thay đổi tỷ lệ toàn tờ; Windows contain-fit không crop nhưng cần chọn giấy/hướng/lề và hiệu chuẩn trên thiết bị thật. Không coi event-ready khi chưa thử giấy/điện thoại.
- CUPS, camera SDK/shutter/live preview thật, production deployment, retention/backup worker thuộc bước sau; không triển khai ở đây. Backup nhất quán toàn runtime gồm DB/WAL, originals/composites/QR/print-ready và .share-key.
- Receipt/spool không chứng minh giấy đã ra. Lỗi không rõ phải Host kiểm tra trước retry. Nếu frontend reload giữa request và ACK, dùng Host xem job trước khi chủ động in lại; frontend hiện không resume toàn phiên sau reload.
- Queue/lease dành cho cùng laptop/filesystem local, không phải distributed multi-host. Dashboard không có WebSocket/advanced search; dùng phân trang/polling.
- Có warning deprecation Starlette TestClient/httpx từ dependency; không đổi framework trong Phase 4.

Dừng ở Phase 4; không commit/push.
