# Phase 3 — QR & Guest Photo Page, 30/10/2026

## Phase 2 — hoàn tất và checkpoint riêng

Checkpoint **dad43d0** trên `checkpoint/phase2-foundation`; main không bị merge/thay lịch sử. Trước checkpoint: backend **13/13**, Node **7/7**, Playwright **10/10**, build demo/production guard PASS. Bổ sung layout 4 ảnh ngang end-to-end bên cạnh sáu ảnh cũ, state machine, camera mock adapter trả shot metadata, printer mock dry-run (không queue/in thật). Đã kiểm tra upload/retake/composite/retry và restart Uvicorn process thật.

Phase 3 làm trên **feat/phase3-qr-guest-page** từ checkpoint trên. Không push GitHub, không merge main. Các file runtime/.env/DB/key/ảnh khách/venv/build/test data được ignore, chỉ source/docs và fixture screenshots vào checkpoint.

## Phase 3 — chức năng đã hoàn thành

- Owner xác nhận → lưu composite → complete → POST finalize. Chỉ current confirmed composite mới được share. Không phát hành link cho ảnh chưa xác nhận.
- Một composite revision có một share/token/QR PNG; same/different idempotency key không tạo share trùng. Chỉnh filter/sticker/render không upload/finalize. Xác nhận revision mới có link mới; link cũ vẫn trả file cũ.
- QR PNG tạo tại backend bằng qrcode/Pillow, không gọi dịch vụ QR/upload ngoài. Đã giải mã PNG bằng ZXing và so đúng share URL.
- `/p/{token}` mobile page chỉ một ảnh và Download Image, có loading/error; endpoint image/download/qr đều kiểm tra token. Download bytes/checksum đúng composite.
- Không public gallery/listing/storage mount; share token không truy cập session API/ảnh người khác qua ID/query. Invalid/expired/revoked token hoặc missing file bị từ chối.
- PUBLIC_BASE_URL bắt buộc HTTPS origin công khai hợp lệ cho share mới; localhost/private/credentials/path/query/placeholders bị chặn. Không hardcode localhost hoặc invent URL fallback.
- DB schema 3, migration không xóa metadata/files cũ. Token HMAC 256-bit từ random nonce và secret riêng; DB lưu hash/nonce. ACK cache được redacted, chỉ lưu composite reference. Owner URL tái dựng khi trả response; không plaintext bearer token trong generated cache rows.
- Secret runtime/.share-key giữ identity qua restart; mất key không tự rotate. Public token hash vẫn kiểm chứng được, owner reconstruction báo cần restore key.
- Privacy headers/CSP nonce/noindex/no-referrer/no-store; Uvicorn access log redacts token.
- QR UI/DOM/handler names cũ được tái sử dụng; không rewrite frontend. Legacy external upload module chuyển vào `legacy/qr-upload.phase1.js`, không còn trong frontend dependency graph; flag DEV không bật lại upload ngoài.

## Quyết định scope theo yêu cầu mới

Technical spec ban đầu mô tả QR overlay trong Phase 3. Yêu cầu mới nói **chuẩn bị QR để Phase 4 chèn vào ảnh**, nên Phase 3 này lưu QR asset/link, trả `qr_embedded=false` và phục vụ immutable composite chưa overlay. Không print-ready artifact, printer worker hoặc in vật lý. Không claim Event Ready/Software MVP toàn bộ các phase.

Hai public-test origin/HTTPS trong automated tests là fixture proxy nội bộ; không phải domain đang deploy. Không có thông tin public URL thực của sự kiện, nên mặc định PUBLIC_BASE_URL trống và UI sẽ báo ảnh đã lưu nhưng QR chưa cấu hình. Đây là fail-closed behavior có chủ đích, không tạo link giả.

## File mới / sửa

Mới:

- `backend/app/services/sharing.py` — share finalization, token/hash/nonce/key, QR asset và lookup.
- `backend/app/guest.py` — mobile HTML, private-by-token view/download/QR routes.
- `backend/app/logging_filters.py` — redact bearer paths trong access log.
- `backend/app/migrations/002_sharing.sql`, `003_share_ack_redaction.sql`.
- `backend/tests/test_sharing.py` — sharing/security/idempotency/migration/restart/QR decode.
- `docs/PHASE3_REPORT.md`, `SECURITY_PRIVACY.md`, `screenshots/phase3-guest-mobile.png`.
- `legacy/qr-upload.phase1.js` — archive module cũ, không chạy/không import từ frontend.

Sửa:

- Backend config/database/main/routers/repository, requirements/lock và .env.example.
- Backend restart/session tests để xác nhận schema mới và share sau restart process.
- Frontend QR client/view/status, store/main/photo-repository, index, Vite proxy /p và .env.example (legacy upload retired).
- Playwright config/test suite, README, API contract, inventory/migration/acceptance docs; fixture screenshots được tạo lại.

HTML gốc, legacy original HTML, compositor/filter/sticker/layout algorithms không bị sửa trong Phase 3. Frontend dependency lock không đổi. Core Phase 2 checkpoint được giữ riêng.

## Kết quả test thực tế

Windows/Python 3.12.10, Node 26.13.0, npm 11.20.0. Dependencies khóa trong requirements.lock.txt; QR library 8.2, test decoder zxing-cpp 2.3.0.

| Kiểm tra | Kết quả |
|---|---|
| Backend toàn bộ | **31/31 PASS**, 20,12s lượt cuối |
| Node frontend | **7/7 PASS** |
| Playwright toàn bộ | **14/14 PASS**, 1,7 phút lượt cuối |
| Build demo / production guard | **PASS**, 42 modules |
| 9 filters × 2 preset cũ | **PASS**, 18 PNG pixel-identical với legacy |
| PNG QR decode | **PASS**, giải mã đúng share URL |
| Restart Uvicorn thật | **PASS**, metadata/file/share URL/view/download vẫn hoạt động |
| Hai guest A/B + download | **PASS**, mỗi ảnh/checksum đúng; không có gallery/IDOR/listing |
| Retry/render | **PASS**, không duplicate token/QR/composite, không rotate khi render |
| Fault injection | **PASS**, lost photo/composite/complete/finalize ACK; loading/error/reload recovery |
| Origin/token/security | **PASS**, invalid/local/private base, invalid/expired/revoked tokens, cache redaction và missing key |

Có một deprecation warning test-only của Starlette TestClient/httpx, không phải test failure. Ban đầu test lost-finalize chưa inject lỗi do thứ tự Playwright routes; đã sửa route registration và chạy lại toàn bộ 14 bài PASS. Rà soát phát hiện raw share URL có thể vào ACK JSON cache: đã thay bằng composite reference, migration 003 redacts row cũ và có test chống regression.

Các HTTP 401/404/503 cố ý trong negative/failure tests là expected; normal UI không có import/page/asset errors. Tests không dùng camera/máy in thật, không external upload hoặc Internet deployment.

## Chưa test / giới hạn còn lại

- **Chưa test điện thoại thật, DNS/cert/public HTTPS, QR qua Wi-Fi hoặc 4G/5G, QR giấy**. Không claim Internet/Event Ready.
- **Chưa deploy tunnel/reverse proxy**, không chọn domain thay người dùng. Cần operator cấu hình origin thực và giữ laptop/backend/storage/Internet chạy.
- QR chưa overlay/in giấy; no print worker/admin/dashboard/camera SDK/Frame Editor nâng cao. Dừng trước Phase 4.
- Bearer link có thể được người nhận chia sẻ. Rate limits, deployment hardening, admin/kiosk auth và retention UI thuộc phase sau.
- Browser reload vẫn mất credential/canvas pending; backend data đã commit giữ qua restart. Chưa có resume UI/backup worker/orphan reconciliation.
- Schema có revoke/expiry checks, chưa có UI policy; không tự đặt hạn lưu. Backup DB/files/QR và .share-key nhất quán; không regenerate key cho link cũ.
- Safari/iPad, macOS, nghe audio trên hardware chưa test thực tế. Responsive Chrome/mobile viewport và synthetic touch không thay hardware test.

## Chạy và kiểm tra ngày mai

README có Windows venv/pip/Vite commands, PUBLIC_BASE_URL và quy trình điện thoại. Backend default 127.0.0.1:8000, frontend 127.0.0.1:5173; API `/api`, guest `/p/token`. Test backend port 8001/storage `.tools/e2e-backend`, không dùng dữ liệu operator.

Operator storage: runtime/photobooth.sqlite3, originals/, composites/, qrcodes/ và .share-key. Không public toàn bộ runtime. Main giữ commit ban đầu; checkpoint Phase 3 nằm HEAD của `feat/phase3-qr-guest-page` (xem `git log --oneline -3`).

**Hoàn tất Phase 3, không push/merge và không triển khai Phase 4.**
