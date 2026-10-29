# OSA BOOTH — Phase 2 Backend Foundation

Frontend ES Modules + Vite, tái sử dụng HTML/CSS/editor Phase 1. Backend FastAPI + SQLite lưu từng ảnh demo/webcam/manual và composite trên laptop. Luồng: **Home → tạo session → Capture 6 ảnh → Result/editor → Xác nhận & Lưu ảnh trên laptop**.

Hoàn thiện Phase 2 trước checkpoint: Home có thêm **4 ảnh ngang (2×2)**, slotCount 4/6 xuyên suốt capture/retake/composite/backend; state machine và adapter camera mock trả metadata, printer adapter chỉ dry-run (không in). Sáu ảnh và mọi chức năng editor cũ được giữ. Kiểm tra checkpoint: backend **13/13**, Node **7/7**, Playwright **10/10**, cả hai build PASS.

Chưa có physical shutter/SDK, QR public, Guest Photo Page, Host Dashboard, print worker hoặc deployment. Dừng ở Phase 2; không commit/push tự động.

## Windows 11: chạy backend

Cần Python 3.11+, Node.js 22.12+, npm. Đã test Python 3.12.10, Node 26.13.0 và npm 11.20.0. Không cần Docker. PowerShell tại thư mục gốc:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

`requirements.lock.txt` khóa phiên bản đã test; `requirements.txt` ghi dependencies trực tiếp. Không cần activate venv hoặc đổi Execution Policy.

Health: http://127.0.0.1:8000/api/health. OpenAPI: http://127.0.0.1:8000/docs.

## Chạy frontend

PowerShell thứ hai tại thư mục gốc:

```powershell
cd frontend
npm ci
npm run dev
```

Mở **http://127.0.0.1:5173**. Nếu npm.ps1 bị chặn, dùng `npm.cmd` thay npm. Vite proxy `/api` đến backend. Biến shell `OSA_BACKEND_URL` đổi target; mặc định `http://127.0.0.1:8000`. Không hardcode URL backend trong logic frontend.

Chọn mock hoặc webcam preview, chụp sáu ảnh hoặc upload file thử nghiệm. Từng slot chỉ được thay sau ACK lưu của backend. Retake thất bại giữ ảnh cũ và canvas mới đang chờ. **Thử lưu lại** giữ nguyên payload/idempotency key; mất phản hồi sau khi đã ghi không tạo file trùng. Lỗi batch upload giữ cả những canvas chưa upload xong.

Đi Result/chỉnh filter, frame, sticker hoặc text chưa upload composite. Chỉ nút **Xác nhận & Lưu ảnh trên laptop** render snapshot, lưu composite và complete; editor tạm khóa khi lưu. UI chỉ báo thành công sau ACK đúng session/composite. Chỉnh sửa sau khi lưu làm snapshot chưa xác nhận; xác nhận lại tạo composite revision mới. Retake/xóa/reset cập nhật active slots và vô hiệu composite cũ; files revision cũ vẫn private.

**Không reload trình duyệt khi còn dữ liệu chưa lưu:** canvas/credential/pending retry chỉ ở RAM; chưa có resume UI. Backend restart không mất file/metadata đã commit. Bấm khách mới tạo session mới; không xóa file cũ.

## Storage

Mặc định dưới thư mục gốc repository, không phụ thuộc working directory:

```text
runtime/photobooth.sqlite3
runtime/originals/<session_id>/<photo_id>.png
runtime/composites/<session_id>/<composite_id>.png
```

Mở bằng Explorer để xem ảnh trên laptop. SQLite chỉ giữ metadata/path tương đối, không chứa binary. SQLite WAL có thể tạo thêm `-wal`/`-shm`. `originals` ở Phase 2 là ảnh canvas/manual normalize PNG, **chưa phải file shutter DSLR**. Source ghi đúng `demo`, `webcam_frame`, `manual_upload`.

Không public runtime/gallery. API xem ảnh yêu cầu credential đúng session; metadata không lộ filesystem paths. Các thư mục runtime, venv, ảnh khách, DB, .env và logs được ignore.

Tùy chọn set biến môi trường trong shell backend:

```powershell
$env:OSA_STORAGE_ROOT = 'D:\OSA_Runtime'
$env:OSA_MAX_UPLOAD_BYTES = '10485760'
$env:OSA_MAX_IMAGE_PIXELS = '24000000'
```

`backend/.env.example` là mẫu tham chiếu, không tự được đọc. Đường dẫn cấu hình tương đối resolve theo working directory. macOS có thể dùng `.venv/bin/python`; code core dùng pathlib/sqlite3, chưa test macOS thực tế.

## Build và test

Từ backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Từ frontend:

```powershell
npm test
npm run build
npm run build:production -- --outDir dist-production
$env:CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:e2e
```

Hoặc bỏ CHROME_PATH và `npx playwright install chromium`. E2E tự mở/dọn các port **8001, 5173, 5174, 4173, 4273**; cần port trống, backend venv/dependencies và hai frontend builds. Storage test riêng `.tools/e2e-backend/`, không dùng runtime của người vận hành.

`npm run build` là **DEMO** để review; `npm run preview` mở http://127.0.0.1:4173 với API proxy. `build:production` chỉ chặn mock/video capture, chưa phải event-ready deployment. Tests dùng fixture, stub window.print và tài nguyên CDN, không upload ra ngoài/in giấy. Google Fonts/QRCode CDN chưa được kiểm chứng online; Tailwind build local giữ theme gốc.

## Cấu trúc và tài liệu

- `backend/app/`: app factory, config/pathlib, sqlite3 database/migration, schemas, routers và services file/metadata.
- `frontend/src/services/{api-client,session-client,photo-repository}.js`: HTTP/session/pending/retry/confirm.
- Giữ nguyên editor/layout algorithms; compositor chỉ thêm hook báo dirty. Giữ facade window.app cho handlers cũ.
- SQLite schema nằm trong `migrations/001_initial.sql`; không tạo ORM models/folder rỗng. Browser camera/mock tiếp tục dùng service Phase 1; backend không giả lập shutter thật.
- [API_CONTRACT](docs/API_CONTRACT.md), [PHASE2_REPORT](docs/PHASE2_REPORT.md), [FUNCTION_INVENTORY](docs/FUNCTION_INVENTORY.md), [MIGRATION_LOG](docs/MIGRATION_LOG.md), [ACCEPTANCE_TESTS](docs/ACCEPTANCE_TESTS.md).

HTML root và legacy giữ nguyên. QR/shutter legacy opt-in DEV mặc định tắt. Nút in legacy vẫn là browser print, không có print worker hoặc bằng chứng giấy đã in. Chưa làm Phase 3.
