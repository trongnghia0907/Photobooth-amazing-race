# Phase 2 — Backend Foundation, 30/10/2026

**Checkpoint theo yêu cầu tiếp tục mới:** đã tạo local commit **dad43d0** trên `checkpoint/phase2-foundation`, sau khi 13/13 backend, 7/7 Node, 10/10 Playwright và hai builds PASS. Nhánh `feat/phase3-qr-guest-page` tạo từ checkpoint đó. Không push/merge main. Ghi chú “không commit” trong báo cáo ban đầu bên dưới phản ánh lệnh Phase 2 trước, đã được lệnh checkpoint mới thay thế. Kết quả Phase 3 nằm riêng tại PHASE3_REPORT.md.

## Hoàn thiện trước checkpoint (yêu cầu tiếp tục Phase 3)

Đã bật layout 4 ảnh ngang ở Home và tổng quát slotCount, capture/retake/composite/detection/persistence 4/6. Tọa độ sáu ảnh và editor cũ giữ nguyên. Bổ sung state machine event-driven (`core/session-machine.js`), MockCameraAdapter browser trả accepted shot metadata, MockPrinterAdapter dry-run không in vật lý/không worker. Kiểm thử mới: backend 13/13, Node 7/7; Playwright có thêm luồng 4 ảnh (10 bài tổng), được chạy trước checkpoint. Mục “UI vẫn sáu ảnh” trong báo cáo cũ bên dưới là lịch sử, đã được hoàn thiện.

**DONE:** FastAPI chạy được, SQLite/file storage thực, frontend tích hợp, session ownership, idempotency, shot/retake/delete/reset, explicit composite confirmation và retry. **DEMO:** nguồn camera browser/mock/manual. Dừng tại Phase 2, không commit/push.

## File mới

- `backend/requirements.txt`, `requirements.lock.txt`, `.env.example`.
- `backend/app/__init__.py`, `main.py`, `config.py`, `database.py`, `schemas.py`, `routers.py`.
- `backend/app/migrations/001_initial.sql` — schema version 1.
- `backend/app/services/images.py`, `repository.py` — Pillow validation/normalization, atomic write, SQLite transactions, revisions/auth/idempotency.
- `backend/tests/test_sessions.py`, `test_restart.py` — 12 backend tests, bao gồm restart Uvicorn process thật.
- `frontend/src/services/api-client.js`, `session-client.js`, `photo-repository.js`.
- `frontend/tests/backend-server.js` — test backend riêng 8001, storage riêng.
- `docs/API_CONTRACT.md`, `docs/PHASE2_REPORT.md`, `docs/screenshots/phase2-saved-result.png`.

## File sửa

- `.gitignore`: ignore venv/pytest cache.
- `frontend/vite.config.js`: dev/preview proxy /api, configurable target.
- `frontend/src/core/{store,bootstrap,router}.js`: persistence state/wiring/status UI.
- `frontend/src/features/capture/{capture,countdown,retake}.js`: await backend shot ACK, khóa capture trùng, cleanup epoch, retake/delete/reset.
- `frontend/src/services/mock-camera.js`: giữ drawing/crop/mirror, chuyển shot qua async persistence; manual batch giữ canvases chưa lưu để retry.
- `frontend/src/features/editor/compositor.js`: **một callback** trạng thái dirty sau render; không đổi thuật toán ghép/filter/layout/sticker.
- `frontend/src/features/result/result.js`: đồng bộ panel và chặn finish khi chưa đủ ảnh đã lưu.
- `frontend/src/utils/timing.js`: tăng capture epoch khi hủy timers để tránh continuation cũ.
- `frontend/src/main.js`, `frontend/index.html`: badge/panel lưu, nút retry/confirm; không redesign editor.
- `frontend/playwright.config.js`, `frontend/tests/e2e/photobooth.spec.js`: backend thật + thêm ba integration/failure tests, await các thao tác capture nay bất đồng bộ.
- `README.md`, `docs/{FUNCTION_INVENTORY,MIGRATION_LOG,ACCEPTANCE_TESTS,FILES_CREATED}.md`: hướng dẫn/mapping/trạng thái mới. Screenshots fixture được tạo lại khi kiểm thử.

Các tài liệu/screenshots/PHASE1_RECHECK chưa commit từ lượt trước được giữ. Không sửa HTML nguồn, legacy, technical spec hoặc package-lock frontend. Không thêm framework.

## Quyết định theo repository thực tế

Yêu cầu Phase 2 mới dùng `/api` và giới hạn sáu ảnh; backend triển khai đúng các route tối thiểu đó, thêm delete/reset và GET ảnh có auth. Backend hỗ trợ slot_count 4/6 nhưng UI vẫn sáu ảnh để giữ Frame Editor. API được ghi trong API_CONTRACT.

Chọn stdlib sqlite3 thay ORM để giữ backend nhỏ: models thể hiện bằng SQL migration và Pydantic schemas.py. Routers/schemas dùng file đơn thay folder rỗng. Không thêm CameraAdapter backend giả: nguồn capture vẫn browser mock/webcam/manual hiện có, gắn provenance đúng khi upload. Chưa có state machine hardware/API camera vì không tích hợp shutter; backend quản lý statuses created/capturing/editing/completed/failed.

Quyền sở hữu bằng random bearer token scoped session, DB chỉ giữ hash; không public gallery hoặc storage mount. Photos là file revisions, slots là active pointers. Composite chỉ được ghi khi xác nhận, đủ shots và đúng shots_revision. Phase 2 cho phép sửa lại active session completed; Phase 3 chưa có immutable public final/share token.

## Kết quả kiểm thử thực tế

Môi trường Windows, Python 3.12.10, Node 26.13.0, npm 11.20.0. FastAPI 0.162.0, Uvicorn 0.54.0, Pydantic 2.14.2, Pillow 12.3.0; dependencies đầy đủ khóa trong requirements.lock.txt.

| Kiểm tra | Kết quả |
|---|---|
| Backend pytest | **12/12 PASS**, 6,24s ở lượt cuối |
| Native frontend tests | **6/6 PASS**, byte equality legacy, mapping 80, state/algorithms/IDs/CSS/timer cleanup |
| Build demo | **PASS**, 41 modules, 740 ms ở lượt cuối |
| Build production guard | **PASS**, 41 modules, 632 ms ở lượt cuối |
| Full Playwright với FastAPI thật | **9/9 PASS**, 1,3 phút ở lượt cuối |
| Composite baseline parity | **PASS**, 18 tổ hợp: 9 filters × 2 presets, PNG pixel-identical |
| Uvicorn stop/start process thật | **PASS**, session completed + metadata, 7 files và replay complete còn sau restart |

Backend: tạo session/retry đồng thời không trùng; upload sáu ảnh; retake đúng slot/revision/source; composite/complete; metadata SQLite, file tồn tại; missing/wrong auth, cross-session access, UUID/slot/source sai; invalid/corrupt/oversized/pixel-limit file; path traversal filename; request cap cả chunked; simulated disk/SQLite lỗi rollback; complete phát hiện file mất và status failed.

Frontend: toàn bộ sáu bài Phase 1 tiếp tục pass với backend thật; thêm explicit confirm không upload sớm, repeat confirm không duplicate, retake metadata, private image API và file count; batch lỗi giữ sáu canvases rồi retry; mất phản hồi sau composite/complete không lưu trùng/không báo saved trước ACK; retake/delete lỗi giữ slot cũ đến khi backend nhận.

Không console/page errors hoặc 404 asset nội bộ trong normal regression. Test cố ý tạo 401/503 có thể sinh browser console HTTP error tương ứng, được xét là expected failure injection, không coi là lỗi import. Không external upload, loopback shutter hoặc auto print ngoài ý muốn. Window.print stub; không in giấy.

Lỗi phát hiện/sửa khi triển khai: retry finalOperation cũ phải nhường pending shot/deletion; manual batch phải giữ cả các canvases chưa tới lượt upload; chunked body overflow cần HTTPException 413 để multipart parser không đổi thành 400; nhận payload complete không đúng session/composite phải từ chối success. Các lỗi đã được xử lý trước lượt test cuối.

Môi trường sandbox ban đầu chặn thư mục temp của pytest; test được chạy lại với quyền tạo process/file test cần thiết. Có **một deprecation warning test-only** từ Starlette TestClient dùng httpx thay httpx2; tests vẫn pass, không phải lỗi backend runtime. Không tự đổi dependency chỉ để tắt warning.

## Chưa chạy / giới hạn

- Camera shutter/SDK/file gốc, iPad Safari/âm thanh thực tế, printer/QR giấy: **BLOCKED_BY_HARDWARE / ngoài Phase 2**.
- macOS, CDN Google Fonts/QRCode live, legacy third-party upload: **chưa test**. Browser tests stub CDN và dùng fixture.
- QR private link, Guest Photo Page, Host Dashboard, print queue, auth enrollment, public HTTPS/tunnel, backup/retention: **TODO phase sau**, không triển khai.
- Browser reload mất session credential/canvas retry chưa lưu; không có resume UI. Backend restart giữ dữ liệu đã commit.
- Files revision cũ còn private; chưa tự cleanup, retention, disk monitoring hoặc crash orphan reconciliation. Process chết giữa rename và SQLite commit có thể để orphan file; không có committed success giả từ đường lỗi thông thường đã test.
- Session credential chỉ scoped possession, không thay admin authentication. Backend local-only, chưa mở ra Internet.
- Home camera selector dài có thể tràn card ở một số font/viewport, là vấn đề baseline; không redesign. Result responsive được test ở 820×1180 và 1180×820.

## Chạy và vị trí dữ liệu

Xem README cho venv/pip/Vite. Backend default `127.0.0.1:8000`, frontend `127.0.0.1:5173`, Vite proxy /api. Health /api/health, Swagger /docs.

Operator data: `runtime/photobooth.sqlite3`, `runtime/originals/<session>/<photo>.png`, `runtime/composites/<session>/<composite>.png`. Tests dùng tmp dirs hoặc `.tools/e2e-backend/`; không dùng ảnh khách. Storage thực được tạo khi backend khởi động/session upload, không lưu binary trong DB.

**Hoàn thành Phase 2 và dừng; không bắt đầu Phase 3.**
