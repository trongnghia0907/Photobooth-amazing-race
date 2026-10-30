# Fix QR Not Ready — Phase 3, 30/10/2026

## Nguyên nhân thực sự

1. Lần kiểm tra runtime trước: các session gần nhất có đủ 6 active slots nhưng status editing, composite_id chưa có và shares=0. Upload sáu ảnh **khác** với xác nhận ảnh ghép. Guard yêu cầu finalOperation.compositeId + session completed + canvas khớp lastSavedImage đang chặn đúng bước chưa xác nhận.
2. Backend `public_origin()` trước chỉ nhận HTTPS public, từ chối mọi localhost. `PUBLIC_BASE_URL` mặc định rỗng, chỉ đọc os.environ, không tự load `.env`. Chỉ chạy Uvicorn không đủ để tạo share.
3. Frontend còn guard `protocol === https:` nên dù backend hỗ trợ local, HTTP localhost vẫn bị frontend từ chối. Đã sửa đồng bộ cả hai phía.
4. UI gộp chưa xác nhận, thiếu cấu hình và lỗi tải QR vào “QR chưa sẵn sàng / Chờ xác nhận & cấu hình URL”. Render/schedule có thể thay thông báo lỗi cụ thể bằng lời nhắc chưa xác nhận, gây nhầm.
5. UI trước báo ready ngay khi gán src, chưa chờ PNG load. Đã đổi: chỉ báo ready sau image.onload/naturalWidth hợp lệ; lỗi PNG báo chính xác và retry không lưu trùng ảnh.

Trong lần đọc health cuối, port 8000 không phản hồi và không có listener 8000/5173; cần khởi động lại bằng lệnh local mới để áp dụng cấu hình. Không tự giết/dừng process operator; tests dùng cổng và storage riêng.

## Luồng đã sửa

**Xác nhận & Tạo QR → PUT composite → POST complete → kiểm tra ACK → đọc health.sharing → POST finalize → nhận token/link/PNG → image.onload → QR sẵn sàng.** Nút xác nhận ở đầu Result cũng tự chạy toàn bộ luồng, không cần Refresh QR. Khi đã lưu, nút trong QR chỉ retry share/PNG; không upload composite lần nữa.

Chưa xác nhận: UI nói rõ bấm nút nào. Thiếu/sai cấu hình: hiện message PUBLIC_BASE_URL/APP_ENV và cách chạy script local. Ảnh đã lưu nhưng QR lỗi: giữ saved state và thông báo riêng. Chỉnh filter/sticker vẫn chỉ dirty, không tự lưu/finalize.

## Chính sách URL

- Mặc định `APP_ENV=production`, HTTPS public policy cũ giữ nguyên.
- Chỉ `APP_ENV=development` cho phép HTTP/HTTPS hostname localhost hoặc địa chỉ loopback chuẩn (127.x.x.x/::1); vẫn từ chối private LAN, 0.0.0.0, credentials/path/query/malformed origin.
- Không có fallback token/fragment hoặc URL giả. Share chỉ tạo sau complete và file tồn tại. Không thay schema/rotate token, không mount storage/gallery.
- Descriptor thêm `local_only`. Frontend chỉ nhận HTTP loopback nếu backend gắn flag này, đồng thời cảnh báo rõ **không dùng trên điện thoại khác**.
- `GET /api/health` thêm `sharing: {configured, app_env, base_url, local_only, message}`; không có secrets/token/path filesystem.
- Script run_local_backend.py chỉ cấu hình process con và bind loopback; không deploy/public tunnel.

## File sửa / mới

- Backend: `app/config.py`, `app/services/sharing.py`, `app/routers.py`, `.env.example`, `tests/test_sharing.py`.
- Frontend: `src/services/qr-client.js`, `components/qr-status.js`, `components/qr-view.js`, `core/store.js`, `main.js`, `services/photo-repository.js`, `index.html`.
- Helper mới: `scripts/run_local_backend.py`.
- Tests: `playwright.qr-confirm.config.js`, `tests/qr-confirm/qr-confirm.spec.js`; test server helper giữ OSA_TEST_PORT override.
- Full-suite isolation: `playwright.isolated.config.js`, port-offset URLs trong tests/e2e và baseline server. Không đổi default ports/scope của suite gốc.
- Docs: README, API_CONTRACT, SECURITY_PRIVACY, MIGRATION_LOG, ACCEPTANCE_TESTS và báo cáo này; fixture screenshots do regression tạo lại.

Không sửa Frame Editor/compositor/layout/filter/sticker algorithms, không thay file HTML gốc hoặc legacy original. Không triển khai Phase 4. Không commit/push.

## Kết quả chạy thật

| Kiểm tra | Kết quả |
|---|---|
| Backend pytest toàn bộ | **42/42 PASS**, gồm 31 bài cũ và development/local/prod guards mới |
| Node regression | **7/7 PASS** |
| Build demo | **PASS**, 42 modules |
| Build production guard | **PASS**, 42 modules |
| Localhost E2E | **3/3 PASS**, HTTP localhost thực, không proxy fake HTTPS |
| Full Phase 1–3 Playwright | **14/14 PASS**, cổng offset riêng |

Local E2E gọi chính script run_local_backend.py trên 8002/storage test. Tạo session → chụp 6 ảnh → xác nhận → real QR localhost → Guest Page → tải PNG, checksum trùng backend. Kiểm tra auto QR bằng nút lưu (không refresh), cảnh báo local, missing config thông báo cụ thể, lỗi PNG không false-ready, retry không thêm composite/token.

Full regression giữ 4/6 ảnh, retake/delete/reset, custom frame, 9 filters, stickers/drag/text/download, guest A/B/token/retry. 18 composite PNG vẫn trùng pixel legacy. Có warning test-only Starlette/httpx như trước, không test failure. Không test điện thoại/Internet/print thật; QR localhost không dành cho điện thoại.

## Tự thử đơn giản

1. Ctrl+C backend cũ. Terminal ở thư mục gốc: `python scripts/run_local_backend.py`.
2. Terminal mới ở gốc: `cd frontend`, `npm.cmd run dev`.
3. Mở http://localhost:5173. Chụp/upload → Result → **Xác nhận & Tạo QR**.
4. Chờ “QR sẵn sàng • Chỉ trên máy này” và cảnh báo localhost. Bấm **Mở Web**, rồi **Download Image**.

Nếu GUI đã reload trong lúc sửa, bắt đầu phiên thử mới; các file/metadata đã ghi trên laptop không bị xóa. Browser resume vẫn chưa có như giới hạn Phase 2–3 trước đây.

Kiểm tra config ở http://localhost:8000/api/health: phải thấy sharing.configured=true, app_env=development, local_only=true và base_url=http://localhost:8000. Không cần URL public/tunnel cho bài thử này.

Chạy tests khi đang dùng server operator:

```powershell
cd frontend
$env:CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm.cmd run test:e2e -- --config playwright.qr-confirm.config.js
npm.cmd run test:e2e -- --config playwright.isolated.config.js
```

Các cổng test riêng không chiếm/dừng 8000/5173. Dữ liệu test dưới .tools/, operator data dưới runtime/ hoặc OSA_STORAGE_ROOT đã chọn.
