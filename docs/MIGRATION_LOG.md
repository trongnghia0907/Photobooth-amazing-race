# Migration log — 30/10/2026, Asia/Saigon

## Phase 2 — Backend Foundation (bổ sung sau Phase 1)

Đã triển khai theo yêu cầu Phase 2 mới: FastAPI/sqlite3/Pillow, migration SQL version 1, local file revisions, owner token hash, idempotency, APIs /api và frontend persistence/retry/confirm. Giữ nguyên editor và source/legacy. Không commit/push. Chi tiết file/behavior/test ở [PHASE2_REPORT](PHASE2_REPORT.md); API ở [API_CONTRACT](API_CONTRACT.md). Backend 12/12, Node 6/6, full Playwright 9/9 và builds PASS. Những dòng “dừng trước Phase 2” bên dưới ghi nhận mốc lịch sử Phase 1, đã được yêu cầu Phase 2 hiện tại thay thế.

## Phase 0 — DONE

Đọc technical spec, refactor prompt và toàn bộ HTML 2.493 dòng. Thư mục ban đầu chỉ có ba file đầu vào, không có assets/config/tests/AGENTS.md hoặc Git repository. `git status --short` trả “not a git repository”; không có thay đổi tracked để ghi đè, không tạo branch/commit. Node/npm chưa có PATH: dùng runtime portable trong `.tools/` (ignored).

Giữ nguyên HTML root và sao lưu `legacy/osa_booth_photobooth.original.html`. SHA-256 của cả hai:

```text
fe582825c2f08c78c865c5799bf6da57c3031afdffe7d6164540ee454ca21b67
```

Kiểm kê 80 methods, 68 inline handler occurrences (cả templates), state, IDs/classes, external assets và callback registrations ở `SOURCE_AUDIT.json`. Call sites/dependencies theo method ở `function-map.json` và `FUNCTION_INVENTORY.md`. Screenshots Home/Capture/Result/Settings trước và sau ở `screenshots/`. Baseline screenshot được tạo bằng cùng Tailwind theme build cục bộ, fonts fallback, cloud/shutter/print bị chặn để không gửi ảnh/in thật.

Baseline: HTML có đủ UI và thuật toán demo, không có backend. Camera preview dùng getUserMedia, fallback sang canvas animation; shot thực tế là canvas 960×720 crop từ video/mock, mirror video shots theo setting. Photos nằm trong RAM. Presets 2×3 và 3×2 đều sáu ảnh. Composite mặc định 1200×1800 hoặc 1800×1200; custom frame giữ tỷ lệ/kích thước với upscaling cũ. Editor có 9 filters, emoji categories, PNG sticker upload, mouse/touch drag, màu/chữ, preview/download PNG. QR gọi dịch vụ thứ ba; in gọi window.print.

## Phase 1 — DONE (demo refactor)

Tách markup, CSS và 80 function sang ES Modules theo trách nhiệm của specification. Mỗi function nhận context tường minh; store giữ state, bootstrap cung cấp state accessors và function dependencies, không có circular imports hoặc hai app cùng chạy. `window.app` facade tạm thời giữ inline handlers ở markup và nội dung innerHTML động. `core/events.js` đăng ký facade và cleanup pagehide. Module main chạy sau DOM parse, không đăng ký init lần hai.

Các thuật toán compositor/crop/roundRect/slot detection/filter/sticker giữ nguyên. Test browser xác nhận PNG composite **trùng pixel với HTML gốc trên 18 tổ hợp** (9 filters × 2 presets, fixture xác định). Toàn bộ DOM IDs và CSS gốc được kiểm tra bảo toàn tự động. `layouts.js` chuẩn bị slotCount 4/6, kích thước và rows/columns; layout 4 ảnh chưa enable. Không thêm state machine rỗng: workflow bất đồng bộ/backend là Phase 2.

Tailwind CDN trả 403 khi tải trong môi trường này. Chuyển sang Tailwind 3.4.17 + PostCSS cục bộ với theme và classes gốc; không redesign. Google Fonts/QRCode CDN tạm giữ, test chặn/giả lập các resource này. CSS gốc được chia base/components/print; Tailwind directives bổ sung trong base. Dependency versions khóa trong package-lock.json.

## Các thay đổi hành vi có chủ đích

1. **DEMO rõ ràng:** dev và build mode demo cho phép mock/video frame; production guard từ chối mock, upload ảnh manual và video-frame capture. Không claim real shutter. `npm run build` tạo artifact demo để review; production build chưa event-ready.
2. **QR:** wrapper mặc định không upload, không có QR/link tải giả. UI báo TODO; local download/mobile preview giữ nguyên. Legacy HTTP implementation giữ ở `services/legacy-qr.js`, opt-in bằng flag DEV. Failure không dùng `#osabooth-*`. Không triển khai QR backend thay thế.
3. **Shutter signal:** giữ ImageCapture/localhost behavior trong `services/legacy-camera.js`, tắt mặc định, opt-in DEV. Test shutter mặc định chỉ hiệu ứng và thông báo đúng demo. `ImageCapture.takePhoto()` cũ vẫn bỏ kết quả khi opt-in; loopback là thiết bị đang mở trang, không phải host từ xa.
4. **Print:** autoPrintPopup và checkbox mặc định false. Thủ công vẫn dùng window.print legacy; handler onload đặt trước src và tự gỡ sau khi chạy, tránh editor render tiếp làm bật print lại. E2E dùng stub, không mở hộp thoại/in giấy.
5. **Timers:** theo dõi/cleanup start-delay, next-shot delay, delayed print và QR debounce cùng countdown/grace khi chuyển screen/pause/reset/pagehide. Tránh start trễ sau khi rời Capture; tránh grace interval trùng.
6. **Calibrator:** thêm inputs/status mà JS cũ tham chiếu nhưng DOM thiếu; cho phép lề/gap 0%. Chọn preset xóa custom frame/detection và render lại khi đang ở Result.
7. **Preview:** await attachRealStreamToVideo; selector vẫn có camera mô phỏng khi mediaDevices thiếu. Thông báo kết nối video không gọi đó là ảnh chụp camera thật.

## Bug/giới hạn baseline còn lại

- Chưa persist/recover session; reload mất ảnh chưa download. Không có API, database, backup, guest token hoặc printer queue.
- UI/thuật toán legacy vẫn sáu slot; cấu hình bốn slot là chuẩn bị Phase 2, không claim chạy capture bốn ảnh.
- Upload ảnh/frame/sticker cũ chưa có giới hạn kích thước, kiểm tra magic bytes hoặc đầy đủ onerror/recovery. Chưa mở rộng phạm vi sang hardening pipeline.
- Google Fonts/QRCode CDN cần nội địa hóa trước event; bài test dùng fallback fonts và không xác minh CDN live. Legacy upload opt-in chưa kiểm tra với dịch vụ thật.
- Source Home có camera select dài có thể tràn card ở một số độ rộng/font. Không redesign layout trong phase này. Responsive Result được test tại 820×1180 và 1180×820; chưa chứng minh Safari/iPad thiết bị thật.
- Thư viện sticker chỉ có drag vị trí/kích thước mặc định của source, chưa thêm UI scale/rotate mới.
- Production guard không phải production workflow. Không triển khai ứng dụng sự kiện từ Phase 1.

## Kiểm chứng và điểm dừng

Build demo, build production guard, 6 Node tests và các bài Chrome Playwright được ghi trong `ACCEPTANCE_TESTS.md`. Lỗi test canvas ban đầu do so sánh reference gradient mock, đã chuẩn hóa test log. Lỗi countdown test ban đầu do Playwright fastForward chỉ kích một tick interval, đã dùng runFor cho từng tick; không đổi thuật toán countdown vì lỗi test. Phát hiện handler print tồn tại qua nhiều render được sửa và test chỉ có một print call sau render tiếp.

**Dừng ở Phase 1.** Backend mock, storage, async camera contract, state machine và bật layout 4 ảnh là Phase 2; chỉ làm tiếp sau khi người dùng kiểm tra.
