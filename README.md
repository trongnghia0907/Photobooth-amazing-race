# Phase 6 addition — Event Live Gallery

Màn hình máy chiếu/LED riêng tại **http://localhost:8000/event-display**. Host đăng nhập **/admin**, tạo mã màn hình riêng và duyệt từng composite đã chốt sau khi xác nhận đồng ý/ủy quyền. Mặc định mọi ảnh chưa được duyệt; Host có thể ẩn ảnh mà không xóa composite/QR. Màn hình có tường ảnh, slideshow/fullscreen và tự cập nhật/kết nối lại.

[Hướng dẫn màn hình, duyệt ảnh và máy chiếu](docs/EVENT_LIVE_GALLERY.md) · [Kiểm thử và file thay đổi](docs/EVENT_LIVE_GALLERY_VERIFICATION.md). Đây là gallery sự kiện có giới hạn truy cập, không phải Host Gallery hay gallery public. Cổng Cloudflare/public-photo hiện tại không mở route này.

---

# OSA BOOTH — Phase 6 integration

Current instructions: [Windows setup, local/LAN/HTTPS and operator guide](docs/WINDOWS_EVENT_GUIDE.md), [Phase 0–6 audit](docs/PHASE0_6_VERIFICATION.md), [hardware/event acceptance](docs/EVENT_DAY_CHECKLIST.md).

Built kiosk and API now run together without Vite: build `frontend` with `npm.cmd run build:host`, then from repository root run `& backend/.venv/Scripts/python.exe scripts/run_host.py`. Enter Host credentials and a separate kiosk pairing code when prompted. Open **http://localhost:8000/booth**, Host **http://localhost:8000/admin**. Default camera/printer are Mock. Confirm/save composite to get QR automatically. Localhost QR is laptop-only; use the documented explicit LAN or HTTPS profile for phones.

Phase 6 adds 75/25 Setup, fullscreen capture, current-session-only sidebar, complete New Session privacy reset, station pairing/CSRF, Host restricted to laptop, separate public-photo app, migration preserving old files, supervised Windows launch/stop, offline backup and deployment examples. No public tunnel, physical print or real camera operation was enabled. Actual iPad/camera/printer/LAN/public Internet tests remain pending. See the current report before interpreting historical readiness statements below.

---

# OSA BOOTH — Phase 5 Host Camera Integration

## Vòng đời ảnh hiện tại

**Một phiên → một composite cuối → một QR ổn định.** Ảnh chụp riêng chỉ là dữ liệu làm việc để retake/chỉnh ảnh trước khi xác nhận. Sau khi composite được lưu và chốt thành công, backend dọn ảnh tạm an toàn; Dashboard/Guest chỉ xem ảnh cuối và bản in có QR. Lỗi lưu/confirm giữ dữ liệu để phục hồi; lỗi dọn được thử lại. Sau khi chốt, dùng **Khách tiếp theo** để tạo ảnh khác.

Chi tiết và chính sách dữ liệu cũ: [PHOTO_STORAGE_LIFECYCLE](docs/PHOTO_STORAGE_LIFECYCLE.md). Mục này thay thế các mô tả lịch sử về sửa ảnh/tạo token mới trong cùng phiên sau khi xác nhận.

## Chạy thử camera trên laptop host (Mock)

Terminal 1 tại thư mục gốc:

```powershell
python scripts/run_local_backend.py --admin
```

Nhập tài khoản/mật khẩu Host tự chọn. Helper dùng **Host Mock Camera + Mock Printer**, không điều khiển máy ảnh thật/in giấy.

Terminal 2:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev:host
```

Mở http://localhost:5173 → chọn layout 4/6 ảnh và timer → Bắt đầu. Preview/capture đi qua backend trên laptop; không dùng camera iPad hoặc ảnh chụp preview làm file chụp thật. Capture Mode phủ màn hình, có countdown/progress và nút dừng xem ảnh. Retake, editor, QR, download và hàng đợi in giữ nguyên. Dashboard: http://localhost:8000/admin; xem trạng thái/capabilities của camera và bật guest control nếu trước đó Host đã tắt.

**Mock workflow là software test; chưa HARDWARE READY.** Chưa có model/SDK để xác minh shutter DSLR/file gốc/Live View trên thiết bị thật. UVC tùy chọn chỉ là webcam-frame DEMO. Xem [báo cáo Phase 5](docs/PHASE5_REPORT.md), [camera capability matrix](docs/HARDWARE_COMPATIBILITY.md), [Phase 4 audit gate](docs/PHASE4_VERIFICATION.md). Không triển khai Phase 6, không commit/push.

iPad cùng mạng test: dùng `npm.cmd run dev:host -- --host 0.0.0.0`, mở `http://<IP-LAN-của-laptop>:5173`; Vite chuyển API tới backend laptop. Chỉ dùng mạng tin cậy; không tự mở firewall/tunnel. Hướng dẫn và giới hạn mạng/HTTPS trong báo cáo. **QR localhost từ helper vẫn chỉ mở trên laptop**, cần origin public thật ở bước triển khai sau để khách quét bằng điện thoại.

## Chạy thử Phase 4 (Mock, không in giấy)

Từ thư mục gốc, terminal 1:

```powershell
python scripts/run_local_backend.py --admin
```

Nhập tài khoản và mật khẩu Host bạn tự chọn (mật khẩu ít nhất 12 ký tự, nhập không hiện trên màn hình). Script chạy backend localhost:8000, QR localhost và **ép Mock Printer**, không mở tunnel. Nếu đã đặt ADMIN_USERNAME/ADMIN_PASSWORD trong environment, script dùng các giá trị đó. Không có tài khoản/mật khẩu mặc định.

Terminal 2:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

1. Mở http://localhost:5173 → chụp/upload đủ 4 hoặc 6 ảnh → Result → **Xác nhận & Tạo QR**.
2. QR tự xuất hiện. Mở **Xem bản in có QR** để xem/tải phiên bản sẽ in. Chọn số bản → **In ảnh**; trạng thái Mock đã nhận nghĩa là mô phỏng, không có giấy in.
3. Mở http://localhost:8000/admin (hoặc http://localhost:5173/admin), đăng nhập bằng tài khoản vừa nhập. Xem gallery → chi tiết phiên → composite gốc/bản có QR → tải/in lại. Dashboard có hàng đợi, lỗi, chọn máy in và logout.
4. Guest mở QR chỉ xem/tải đúng bản print-ready của mình, không có gallery. **QR localhost chỉ dùng trên laptop này, không mở được từ điện thoại khác.**

Ảnh gốc và bản có QR được lưu riêng; QR nằm ở footer thêm bên dưới, không che ô ảnh. Hàng đợi SQLite chống request trùng. `submitted` chỉ xác nhận gửi hệ thống in; không khẳng định giấy đã in. Job lỗi không tự in lại. Host phải xác nhận khi job có kết quả chưa rõ.

Xem [báo cáo Phase 4](docs/PHASE4_REPORT.md) cho file thay đổi, kiểm thử, API, giới hạn và hướng dẫn in Windows. Chưa triển khai Phase 5/camera SDK/tunnel production. Không commit/push trong lượt này.

Các mục Phase 2–3 bên dưới ghi lại luồng nền; mô tả “chưa có print worker/Host Dashboard/QR embedding” chỉ áp dụng checkpoint cũ. Phase 4 thay thế luồng in trình duyệt bằng backend queue.

## Chạy thử QR trên localhost — không cần domain

Dừng backend cũ bằng Ctrl+C. Tại **thư mục gốc dự án**, chạy:

```powershell
python scripts/run_local_backend.py
```

Terminal thứ hai, cũng từ thư mục gốc:

```powershell
cd frontend
npm.cmd run dev
```

Mở http://localhost:5173, chụp/upload đủ ảnh → Result → bấm **“Xác nhận & Tạo QR”** ngay trong ô QR (hoặc nút xác nhận/lưu ở đầu màn hình). Backend lưu composite, complete và finalize; **QR tự hiện**, không cần nhấn Refresh. Bấm **Mở Web** rồi **Download Image** để thử đúng ảnh đó.

Script chỉ đặt `APP_ENV=development`, `PUBLIC_BASE_URL=http://localhost:8000` cho process con, bind backend 127.0.0.1. Không sửa environment toàn hệ thống, không mở tunnel hoặc gallery. Dùng `--port 8002` nếu cần đổi port; khi đổi port, Vite cần OSA_BACKEND_URL tương ứng.

**QR localhost là QR thật trỏ tới file đã lưu nhưng chỉ mở trên máy này, không dùng được trên điện thoại khác.** UI có cảnh báo rõ. Production vẫn yêu cầu URL HTTPS công khai. Nếu không dùng script, từ backend/ đặt hai biến rồi chạy Uvicorn:

```powershell
$env:APP_ENV = 'development'
$env:PUBLIC_BASE_URL = 'http://localhost:8000'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

`GET /api/health` có phần `sharing` để xem mode/cấu hình/lỗi cụ thể. `.env` không tự được đọc; script giúp tránh thiếu biến. Không tự rotate link đã phát hành: tạo phiên/revision mới sau khi chuyển từ localhost sang domain thật.

Xem [QR_LOCAL_FIX](docs/QR_LOCAL_FIX.md) cho nguyên nhân, file sửa và kết quả kiểm thử. Không commit/push trong lượt sửa này.

Frontend ES Modules + Vite, tái sử dụng HTML/CSS/editor Phase 1. Backend FastAPI + SQLite lưu từng ảnh demo/webcam/manual và composite trên laptop. Luồng: **Home → tạo session → Capture 6 ảnh → Result/editor → Xác nhận & Lưu ảnh trên laptop**.

Hoàn thiện Phase 2 trước checkpoint: Home có thêm **4 ảnh ngang (2×2)**, slotCount 4/6 xuyên suốt capture/retake/composite/backend; state machine và adapter camera mock trả metadata, printer adapter chỉ dry-run (không in). Sáu ảnh và mọi chức năng editor cũ được giữ. Kiểm tra checkpoint: backend **13/13**, Node **7/7**, Playwright **10/10**, cả hai build PASS.

Đã có QR riêng và Guest Photo Page sau khi xác nhận composite: URL localhost trong development hoặc HTTPS public trong production. Chưa có physical shutter/SDK, Host Dashboard, print worker hoặc public deployment. Dừng ở Phase 3; các checkpoint cũ giữ nguyên, lượt sửa QR local không commit/push.

## Phase 3: QR và trang khách

Luồng **Capture → Customize → Confirm → Save Composite → Complete → Finalize share → QR**. QR/ảnh phục vụ từ backend/laptop, không dùng ImgBB/TmpFiles/File.io hoặc QR server ngoài. Thay filter/sticker/render không upload lại composite và không tạo token; xác nhận revision mới mới có link mới. Link cũ vẫn xem đúng file cũ.

`/p/{token}` chỉ có một ảnh và nút Download Image, có loading/error. Image/download/QR đều kiểm tra token; không gallery hoặc runtime listing. Token là bearer link: ai có link đó có thể xem ảnh tương ứng, không phải xác thực danh tính người chụp.

**QR chưa chèn vào ảnh** (`qr_embedded=false`) theo yêu cầu mới: Phase 3 chuẩn bị asset PNG/link, Phase 4 mới dùng cho bản in. Không có print worker/in vật lý.

### Cấu hình và thử trên điện thoại

Trong shell backend, trước khi chạy Uvicorn:

```powershell
$env:PUBLIC_BASE_URL = 'https://<ten-mien-public-thuc-te-cua-ban>'
```

Phần này dành cho điện thoại/public deployment: thay placeholder bằng origin HTTPS thực tế, không path/query/credentials; production không dùng localhost/private IP/example.com. Mặc định production + URL trống: vẫn lưu ảnh nhưng QR báo thiếu cấu hình. Test trên máy dùng script localhost ở đầu README. Đổi biến cần restart backend. Không xóa database.

Điện thoại mạng ngoài cần **domain/DNS ổn định + HTTPS hợp lệ + public proxy/tunnel trỏ /p/* tới backend**. Vite localhost:5173 không phải share origin. Chưa tự cài/deploy Cloudflare hoặc tunnel; deployment thuộc phase sau. Laptop/backend/storage và Internet phải còn chạy để link hoạt động.

Sau khi có origin thực: chụp/upload → chỉnh → Xác nhận → chờ “QR sẵn sàng” → quét điện thoại, thử xem/tải trên Wi-Fi và 4G/5G. Trạng thái QR sẵn sàng xác nhận file/URL/PNG đã tạo, không tự chứng minh DNS/Internet online. **Chưa kiểm chứng điện thoại/Internet thực tế trong lượt này.**

Tests dùng `https://photos.osa.test` và proxy nội bộ chỉ trong Playwright; không dùng origin đó cho điện thoại/sự kiện.

Storage bổ sung: `runtime/qrcodes/<session>/<final>.png`, table shares và **runtime/.share-key**. DB lưu hash token + nonce, ACK cache chỉ giữ composite reference; key 32 byte riêng không gửi frontend/commit/log. Backup nhất quán toàn runtime (DB, ảnh, QR, key); mất key không được tự sinh key thay thế link cũ. Chưa có backup worker.

Xem [PHASE3_REPORT](docs/PHASE3_REPORT.md), [API_CONTRACT](docs/API_CONTRACT.md), [SECURITY_PRIVACY](docs/SECURITY_PRIVACY.md). Checkpoint Phase 2 `dad43d0`, nhánh Phase 3 `feat/phase3-qr-guest-page`.

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

HTML root và legacy giữ nguyên. Upload QR legacy đã ngắt khỏi frontend; handler names/UI vẫn tái sử dụng. Nút in legacy là browser print demo, chưa có QR embedded/print worker hay bằng chứng giấy đã in. Không triển khai Phase 4.
