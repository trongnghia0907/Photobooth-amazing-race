# Acceptance tests — Phase 0 / Phase 1

Checkpoint hoàn thiện Phase 2: **13/13 backend, 7/7 Node, 10/10 Playwright**, demo/production builds PASS. Bổ sung luồng bốn ảnh ngang, state machine/MockCameraAdapter và MockPrinterAdapter dry-run; kiểm tra sáu ảnh/editor/baseline tiếp tục PASS.

**Cập nhật Phase 2:** backend 12/12 pytest, frontend 6/6 Node, full 9/9 Playwright với FastAPI thật và cả hai build PASS. Xem [PHASE2_REPORT.md](PHASE2_REPORT.md). Các kết quả Phase 1 bên dưới là lịch sử, không thay cho scope Phase 2 mới.

Kiểm tra lại sau khi cài Node/npm Windows: **Node v26.13.0 / npm 11.20.0**, `npm ci`, cả hai build, 6/6 Node tests và 6/6 Playwright tests đều PASS. Xem [PHASE1_RECHECK.md](PHASE1_RECHECK.md) cho kết quả mới nhất; thông tin bên dưới ghi nhận lượt refactor ban đầu.

Ngày chạy: 30/10/2026 (Asia/Saigon). Windows, Node portable 24.22.2, Vite 7.3.7, Tailwind 3.4.17, PostCSS 8.5.32, Playwright 1.64.1 và Chrome headless đã cài. Không chạm camera/máy in thật hoặc upload ảnh khách.

| Kiểm tra | Kết quả | Bằng chứng/phạm vi |
|---|---|---|
| `npm run build` | PASS | 38 modules, HTML/CSS/JS artifact demo trong dist |
| `npm run build:production -- --outDir dist-production` | PASS | Artifact chặn mock/video-frame capture |
| `npm test` | PASS — 6/6 | tests/baseline.test.js; source/legacy byte-identical, mapping 80, state isolation, filters/stickers, tọa độ, drawing calls, IDs/CSS, timer cleanup |
| Home/setup browser | PASS | Camera selector, denied permission fallback, mock select, mirror state/video class, timers 3/5/7/10, modal/calibrator, delayed start bị hủy khi về Home |
| Capture browser | PASS | Sáu shot qua countdown, pause/resume, retake slots 2/5, nút delete động không bubble, immediate snap, reset, grace và auto Result, khách mới |
| Editor browser | PASS | Upload sáu fixture, custom PNG với sáu vùng alpha/detection, calibrator 0%, cả hai presets, 9 filters, bốn sticker categories, emoji/PNG, mouse và synthetic DOM touch drag, màu và text |
| Result/services browser | PASS | Mobile preview, PNG download filename, toast, manual print stub; không in lại khi render tiếp; QR unavailable không link giả |
| Baseline compositor | PASS | Pixel-identical PNG cho 18 tổ hợp 9 filters × 2 presets; fixtures cùng màu/kích thước, fallback fonts giống nhau |
| Built demo responsive | PASS | Preview artifact tại 820×1180 và 1180×820; Result không tràn chiều ngang, dynamic sticker handler chạy |
| Production guard browser | PASS | Không tự mở camera; gọi mock/manual/video-frame capture bị từ chối, photos rỗng |
| Console/imports/assets | PASS trong test harness | Không pageerror/console.error, không 404 CSS/JS/asset nội bộ; không blank screens |
| External upload / auto print | PASS | Test ghi nhận 0 external writes, 0 loopback shutter calls, 0 auto print; 1 manual print call được stub |

Năm bài E2E chính pass trong một lượt (40,1s); bài production guard bổ sung chạy riêng sau build production. File `tests/e2e/photobooth.spec.js` hiện có sáu bài. Lệnh chạy đầy đủ từ frontend:

```powershell
npm test
npm run build
npm run build:production -- --outDir dist-production
npm run test:e2e
```

Các ảnh `screenshots/legacy-{home,capture,result,settings}.png` và `screenshots/modular-{home,capture,result,settings}.png` là fixture screenshots; thêm hai viewport iPad ở `modular-ipad-820.png` / `modular-ipad-1180.png`. Baseline screenshot sử dụng CSS build cùng theme vì CDN Tailwind lỗi 403; QR/shutter/print bị chặn. Ảnh Home/settings có thể chứa toast; không dùng screenshot toàn UI làm pixel assertion. Pixel assertion áp dụng riêng cho composite canvas.

| Chưa verify | Trạng thái | Lý do |
|---|---|---|
| Video stream/camera permission thật, ImageCapture/PTP/SDK/transfer JPEG | BLOCKED_BY_HARDWARE | Chưa chốt thiết bị; browser test chỉ denied/fallback/mock |
| Safari iPad, fullscreen/autoplay/audio nghe thực tế | SKIPPED / manual pending | Viewport Chrome và synthetic touch không thay cho thiết bị thật; audio/flash code được thực thi nhưng chưa nghe/đo trên hardware |
| QRCode CDN, Google Fonts online, legacy cloud upload/QR scanning | SKIPPED | External resources được stub; default QR là TODO, không gửi ảnh tới dịch vụ |
| Hộp thoại in/giấy/QR trên giấy | BLOCKED_BY_HARDWARE | window.print bị stub; chưa có queue hay máy in được chọn |
| Backend/storage/restart/backup/security tokens | TODO Phase 2+ | Không thuộc phạm vi Phase 0/1 |
| Layout capture bốn ảnh | TODO Phase 2 | Chỉ có config disabled, giữ baseline sáu ảnh |

DONE = audit/refactor/tooling và regression demo đã nêu. DEMO = preview/capture canvas, editor và browser print legacy. Không đánh dấu Software MVP hoặc Event Ready.
