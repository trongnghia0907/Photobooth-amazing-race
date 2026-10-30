# Phase 6 Event Live Gallery — schema 8 (2026-10-30)

Migration 008 adds event_display_config, event_display_sessions and event_display_photos to the same SQLite database. No source/final photo file is removed or rewritten, no existing session is approved automatically, no QR token is regenerated. Consent/approval, hide state and display access hashes persist across restart/backup. Existing schema-7 data is verified private and unchanged after migration.

Added restricted display route/UI and authenticated Host approval/access controls. Fixed Host detail selection/loading races so a stale consent form cannot remain active while selecting another session. No new dependency or public deployment. [Verification](EVENT_LIVE_GALLERY_VERIFICATION.md).

---

# Phase 6 — migration 7 and integration (2026-10-30)

Migration 007 adds booth station/session bindings and marks all pre-upgrade pending/blocked final cleanup retained_legacy. No photo file is deleted during migration. Migration 006 backfill still identifies official finals; 007 runs before cleanup workers, preserving existing completed data. Newly confirmed sessions retain normal post-commit cleanup.

Reused existing UI controls in 75/25 Setup and fullscreen flow; added station CSRF/pairing, private/public app boundary, LAN URL opt-in, secure deployment profiles, OS leases/supervised shutdown and offline backup. Fixed prior guest custom-text retention and supervisor stop-marker race. Existing uncommitted Phase 3–5 work retained; legacy HTML untouched; no commit/push/public deployment. See [verification](PHASE0_6_VERIFICATION.md).

---

# Migration log — 30/10/2026, Asia/Saigon

## Photo storage clarification — schema 6

Added session_finals and temporary_file_cleanup migration, sealed confirmation boundary, one-share insertion guard and safe post-commit cleanup/retry worker. All working photo/native/spool revisions and unpublished draft files become temporary; final/QR/print-ready stay. Retake/edit moves strictly before confirmation, kiosk frees working canvases after ACK, Host only serves official finals, and post-confirmation original endpoints close. Updated recovery/security/lifecycle tests and documentation. Legacy published links remain compatible; ambiguous historical edited drafts are retained for review. Physical camera original-file requirement unchanged. No commit/push or Phase 6.

## Phase 5 — host camera software

Phase 4 gate re-run and audit fixes documented in PHASE4_VERIFICATION.md. Migration 005 preserves photo/slot IDs while allowing camera_original source and adds capture journal; FK check before commit. Host camera protocol/controller + Mock/optional UVC DEMO/blocked vendor adapter, exclusive lease, native files and transfer retry are isolated from frontend. Same-origin preview and capture API integrate via existing facade/timers/retake/editor; CSS fullscreen overlay covers setup during capture. Added Host diagnostics, host dev/build mode, hardware matrix and software/hardware readiness report. No Phase 6 or commit/push. Previous uncommitted Phase 3–4 changes retained.

## Phase 4 — Printing System & Host Dashboard

Đã chốt Phase 3 bằng 42 backend + 14 E2E PASS trước thay đổi. Migration 004 thêm bảng derivative, print jobs, printer selection, admin credentials/sessions; không sửa/xóa composite gốc. Share cũ backfill print-ready khi finalize/lookup, giữ token. Guest image/download chuyển sang file print-ready có QR footer; compositor/editor giữ nguyên. `triggerPrint` giữ facade, thay window.print bằng API owner + idempotency + polling. Auto-print trước confirm đổi thành nhắc thao tác thủ công. Mock mặc định, Windows GDI opt-in; lease OS + SQLite FIFO, interrupted job không tự in lại. Dashboard riêng `/admin`, API cookie auth/CSRF, gallery/queue/reprint/printer/system. Chi tiết file/tests/giới hạn ở PHASE4_REPORT.md. Không Phase 5, commit hoặc push; giữ sửa QR local có sẵn.

## Fix QR Not Ready và test localhost

Yêu cầu mới cho phép localhost trong development, supersede HTTPS-only restriction của Phase 3 cũ cho local testing. Đã sửa backend APP_ENV/URL validation, frontend HTTP-loopback validation, health diagnostics, stage-specific UI và PNG-load readiness. QR tự tạo sau confirm ACK, không refresh; không tạo trước khi lưu. Thêm run_local_backend.py một lệnh. Test backend42/42, Node7/7, localE2E3/3, fullE2E14/14 và hai builds PASS. Không đổi Frame Editor, không Phase4, không commit/push. Xem QR_LOCAL_FIX.md.

## Sửa nút QR dễ gây nhầm

Kiểm tra phiên operator thấy đủ sáu slots nhưng status editing, composite chưa lưu. Nút QR “Cập nhật lại Link QR” trước đây không xác nhận composite nên không thể tạo link. Đổi ngay nút trong QR card thành “Xác nhận & Tạo QR”, thêm handler riêng: xác nhận/lưu nếu ảnh còn dirty, nếu đã lưu thì chỉ retry QR, không upload composite trùng. Không gọi handler này từ filter/frame/sticker changes. Không bypass PUBLIC_BASE_URL hoặc tạo QR localhost giả. Build PASS; smoke Playwright riêng trên ports 8002/5183 PASS, bao gồm missing-public-URL và retry sau cấu hình, không đụng server/storage operator. Không commit thay đổi sửa nút này.

## Phase 3 — QR & Guest Photo Page

Phase 2 hoàn thiện/checkpoint dad43d0, sau đó nhánh feat/phase3-qr-guest-page. Schema 002 thêm shares, 003 redacts bearer URL khỏi ACK cache; token hash/nonce + private .share-key giữ link qua restart. Owner finalize chỉ sau complete; guest routes check token, chỉ immutable composite. QR UI reuse, module upload ngoài archive dưới legacy, không active. QR overlay defer Phase 4 theo yêu cầu mới. Backend31/31, Node7/7, Playwright14/14 và builds PASS. Không deploy/push/merge; chi tiết tại PHASE3_REPORT/API_CONTRACT/SECURITY_PRIVACY.

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
