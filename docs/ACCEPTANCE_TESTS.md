# Event Live Gallery acceptance — Phase 6 extension

Verify private defaults, Host consent/basis requirement, only official final PNGs, 4/6 aspect ratios, one item/session, latest prominence, approval/hide polling without reload, slideshow/fullscreen, isolated display credentials, revoked/expired access, migration preserving old photos, and actual backend restart. Browser test: playwright.event-display.config.js; backend: tests/test_event_display.py. Existing Phase 1–6 regressions must remain green.

Results: [Gallery acceptance tests](../backend/tests/test_event_display.py). Physical projector/LED and venue LAN checks are separate NOT TESTED items; see [operator guide](EVENT_LIVE_GALLERY.md).

---

# Phase 6 acceptance additions

Current acceptance and results: [event checklist](EVENT_DAY_CHECKLIST.md), [Windows commands](WINDOWS_EVENT_GUIDE.md), [physical-device/event checklist](EVENT_DAY_CHECKLIST.md). Browser production scenario uses built assets without Vite and tests six shots plus retake, one final, automatic QR, Guest/download, two-copy Mock printing, Host, a second four-shot guest, actual process restart and offline backup hashes. Backend deployment tests cover paired station/owner isolation, CSRF/logout/rates, remote Host denial, public route boundaries, migration preservation and LAN QR decoding; real loopback TLS verifies Secure cookies and launcher leases. Physical camera/printer/iPad/network assertions remain NOT TESTED.

---

# Acceptance tests — Phase 0 / Phase 1

## Current photo storage lifecycle — schema 6

Final localhost QR smoke **3/3 PASS** after the lifecycle changes; QR still generates/retries/downloads correctly after working originals have been removed.

Backend **79/79 PASS**, Node **9/9 PASS**, full Phase 1–5 browser suite **21/21 PASS**, demo/production/host builds **PASS**. Tests now require one official composite/token per session, retake before confirmation, working assets retained after failed upload/commit, retry after locked deletion/restart, protected cleanup paths/final hash, final-only Host media/counts, released working files/canvases after ACK and stable QR without originals. The delete/retake E2E explicitly waits for the deletion ACK before shooting again. New lifecycle tests: backend/tests/test_storage_lifecycle.py; updated backend camera/share/restart tests and frontend E2E. See [PHOTO_STORAGE_LIFECYCLE](PHOTO_STORAGE_LIFECYCLE.md) for policy and legacy compatibility. Earlier phase counts below are checkpoints.

## Phase 5 (current software verification)

Backend **73 PASS**, Node **9 PASS**, full Phase 1–5 E2E **20 PASS**, build demo/production/host **PASS**, QR localhost **3 PASS**. Details and hardware limitations are recorded in [hardware compatibility](HARDWARE_COMPATIBILITY.md). Tests use forced Mock camera/printer and isolated storage. Host tests cover 4/6 countdown, landscape iPad-sized viewport, retake, preview-to-shot substitution guard, timeout/transfer/lost ACK recovery, stale frames, cancelling a delayed connection and camera/session release. Vendor SDK, real shutter/native transfer, physical webcam/printer/phone/iPad device remain **NOT TESTED / BLOCKED BY HARDWARE**; no HARDWARE READY claim.

## Phase 4 checkpoint

Trước thay đổi: backend 42 PASS, E2E 14 PASS, hai build PASS. Sau Phase 4: backend 59 PASS; Node 8 PASS; E2E đầy đủ 15 PASS (bao gồm Host/Mock/lost print ACK), chạy lại riêng Phase 4 sau hardening copies lock/polling 1 PASS; QR localhost 3 PASS; demo và production builds PASS. Chi tiết ở [printing API contract](API_CONTRACT.md). Không có lệnh in vật lý trong tests. Các assertion download được nâng từ checksum composite gốc sang print-ready vì Guest phải tải đúng bản in có QR; vẫn có kiểm tra checksum/crop nguyên bản riêng.

**Lượt sửa QR localhost:** backend **42/42**, Node **7/7**, localhost E2E **3/3**, full Phase 1–3 E2E **14/14** và hai build PASS. Local test dùng HTTP localhost thật, mở Guest Page và download so checksum. Chi tiết/các file sửa ở [QR_LOCAL_FIX](QR_LOCAL_FIX.md). Không test QR trên điện thoại khác vì localhost chỉ cùng máy.

**Phase 3 mới nhất:** backend **31/31**, Node **7/7**, toàn bộ Playwright **14/14**, build demo/production guard PASS. QR PNG được decode; mobile guest A/B/download/error và token/retry/restart được kiểm chứng tự động. **Chưa test điện thoại/Internet/QR giấy thật**. Xem [Mobile QR guide](MOBILE_QR_DEMO.md); các mốc bên dưới là lịch sử.

Checkpoint hoàn thiện Phase 2: **13/13 backend, 7/7 Node, 10/10 Playwright**, demo/production builds PASS. Bổ sung luồng bốn ảnh ngang, state machine/MockCameraAdapter và MockPrinterAdapter dry-run; kiểm tra sáu ảnh/editor/baseline tiếp tục PASS.

**Cập nhật Phase 2:** backend 12/12 pytest, frontend 6/6 Node, full 9/9 Playwright với FastAPI thật và cả hai build PASS. Xem [API contract](API_CONTRACT.md). Các kết quả Phase 1 bên dưới là lịch sử, không thay cho scope Phase 2 mới.

Kiểm tra lại sau khi cài Node/npm Windows: **Node v26.13.0 / npm 11.20.0**, `npm ci`, cả hai build, 6/6 Node tests và 6/6 Playwright tests đều PASS. Xem [Windows test commands](WINDOWS_EVENT_GUIDE.md) cho kết quả mới nhất; thông tin bên dưới ghi nhận lượt refactor ban đầu.

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
