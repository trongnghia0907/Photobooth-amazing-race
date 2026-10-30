# PHASE 6 ADDENDUM — RESTRICTED EVENT LIVE GALLERY

Yêu cầu được bổ sung theo xác nhận mới của người dùng cho AMAZING RACE 2026. Không thay đổi phạm vi refactor ban đầu hoặc quy tắc QR riêng.

- Trang riêng /event-display cho máy chiếu/LED 16:9, tối, tiêu đề lớn căn giữa, wall và slideshow/fullscreen, tự cập nhật, empty state và tự phục hồi mạng.
- Một session có đúng một composite chính thức. Chỉ composite đã lưu/chốt thành công VÀ đã được Host duyệt mới đủ điều kiện; nguồn/retake/draft không được hiển thị.
- Mọi ảnh mặc định chưa được duyệt, bao gồm dữ liệu có trước migration. Host chọn cơ sở guest consent hoặc event authorization và xác nhận chủ động cho từng ảnh. Host ẩn ảnh chỉ thu hồi quyền trình chiếu, không xóa gốc/QR.
- Quyền màn hình tách Host/kiosk/Guest QR; mã do Host tạo, cookie riêng, revoke/rotate, không chứa token QR trong URL hay feed. API chỉ metadata tối thiểu và media được bảo vệ; không có link tải, storage path hoặc private gallery.
- Ngoại lệ gallery này chỉ dành cho trình chiếu sự kiện có kiểm soát quyền. Quy tắc không public gallery và QR truy cập đúng một ảnh vẫn áp dụng; public photo gateway không đăng ký /event-display.
- Tái sử dụng FastAPI/SQLite/session_finals/composite hiện có, không dịch vụ upload/database thứ hai. Polling có giới hạn là đủ. Giữ camera, in, QR, Host và frontend cũ.
- Kiểm thử duyệt/không duyệt, layout 4/6, một item/session, ẩn/reapprove, restart, phân quyền, 16:9, fullscreen/slideshow, offline recovery và toàn bộ regression Phase 1–6.

Thiết kế, thao tác và giới hạn hiện tại: [EVENT_LIVE_GALLERY](docs/EVENT_LIVE_GALLERY.md). Kết quả: [EVENT_LIVE_GALLERY_VERIFICATION](docs/EVENT_LIVE_GALLERY_VERIFICATION.md).

---

# OSA BOOTH — TECHNICAL REQUIREMENTS & IMPLEMENTATION SPECIFICATION

> **Phiên bản:** 1.0 · 29/10/2026  
> **Trạng thái:** Specification để Codex đọc và triển khai theo phase; **không phải** tuyên bố rằng các tính năng đã hoàn thành.  
> **Nguồn code cần tái sử dụng:** `osa_booth_photobooth.html` hoặc `osa_booth_photobooth(1).html` (HTML single-file hiện tại, khoảng 2.493 dòng).  
> **Mục tiêu:** Photobooth cho sự kiện với camera ngoài chụp **ảnh thật**, Guest UI trên iPad, laptop host backend/storage/print, QR riêng được in trên từng ảnh, Guest Photo Page riêng tư, Host Dashboard quản lý tất cả phiên.

## 0. Quy tắc bắt buộc khi Codex thực hiện

1. **Đọc toàn bộ file này và HTML gốc trước khi code.** Ghi nhận tên hàm, DOM IDs, hành vi đã có và hành vi cần đổi; tuyệt đối không xây một giao diện khác từ đầu rồi bỏ chức năng cũ.
2. **Refactor an toàn trước, tích hợp sau.** Phase đầu tiên chỉ tách HTML/CSS/JS thành module, giữ giao diện, thuật toán ghép, filters, stickers, retake, layout, auto mode (nếu bật), preview giả lập và event handlers đang chạy. Không gộp refactor với thay đổi backend/hardware trong một commit lớn.
3. **Không giả vờ hardware đã hoạt động.** `getUserMedia()` hoặc video HDMI/UVC dùng cho preview **không tự chứng minh** camera đã chụp bằng màn trập vật lý. `ImageCapture.takePhoto()` cũng không đảm bảo tương đương với ảnh gốc DSLR/mirrorless. Chế độ sự kiện (production) không được im lặng fallback sang screenshot/mô phỏng khi camera lỗi.
4. **Hệ thống có thể đổi Camera Adapter.** Chưa chốt model camera, iPad, cách cắm USB/HDMI/Wi-Fi. Không hardcode SDK của Canon/Sony/Nikon ở tầng UI hoặc business logic.
5. **QR riêng = truy cập đúng một ảnh.** Link `/p/{share_token}` chỉ cho xem/tải đúng ảnh final tương ứng. Không để public gallery, file list, ảnh nguyên bản, ảnh khác hoặc đường dẫn thư mục storage.
6. **Một ảnh hoàn chỉnh chỉ được finalize một lần cho một revision.** Tạo token → chèn QR → lưu phiên bản in → in; không upload/tạo token mới mỗi lần thay filter hoặc nhấn in lại. Các bản in thêm của cùng final sử dụng cùng QR.
7. **Không làm mất dữ liệu vì lỗi mạng/in.** Ảnh gốc camera, ảnh ghép và thông tin in có trạng thái bền vững, retry có kiểm soát, thông báo rõ khi lỗi.
8. **Không xóa HTML gốc.** Giữ bản `legacy/osa_booth_photobooth.original.html`; commit refactor và tính năng thành các phase riêng; không commit secrets, ảnh khách hoặc database.
9. **Khi chưa thể xác minh phần cứng**, tạo adapter giả lập rõ ràng `DEMO/MOCK` để test và ghi tính năng real hardware là pending; không báo hoàn thành.
10. **Định nghĩa hoàn thành (DoD)** nằm ở mục 17. Không đánh dấu hoàn tất nếu chưa có bài kiểm thử và hướng dẫn chạy.

---

## 1. Bối cảnh và những gì đã thống nhất

### 1.1. Bố trí trạm

- **Tripod:** camera ở phía trên, iPad ở giữa; khách nhìn Live Preview và bấm thao tác trên iPad.
- **Camera:** máy ảnh ngoài là nguồn chụp **ảnh gốc thật**. UI hiển thị đúng những gì camera đang nhìn thấy (Live Preview). Khi bấm Chụp trên iPad, camera phải nhận lệnh chụp; hệ thống nhận lại file ảnh do camera tạo ra.
- **Laptop host:** máy Windows 11 hoặc macOS, chạy web frontend, API/backend, lưu ảnh/database, camera service khi cần, hàng đợi in. Windows 11 là môi trường phát triển ban đầu, **MacBook không bắt buộc**.
- **Máy in:** kết nối trực tiếp với laptop host qua USB hoặc Wi-Fi; không dùng `window.print()` trên iPad cho quy trình sự kiện.
- **Điện thoại khách:** quét QR in trên ảnh giấy, mở đúng Guest Photo Page, xem và tải đúng ảnh đó. Không truy cập kho tổng.
- **Mạng:** iPad truy cập web/API do laptop host phục vụ qua HTTPS; điện thoại khách có thể dùng 4G/5G để mở ảnh nếu có endpoint public hoạt động. Có thể dùng Cloudflare Tunnel; domain và phương thức public URL cần kiểm chứng trước sự kiện.

### 1.2. Các yêu cầu chức năng đã chốt

| Mã | Yêu cầu | Phân loại |
|---|---|---|
| FR-01 | Guest UI tối ưu cảm ứng iPad, Home/Setup → Capture → Result | Bắt buộc |
| FR-02 | Bắt đầu chụp: giao diện Capture chiếm tối đa màn hình, ưu tiên Live Preview lớn | Bắt buộc |
| FR-03 | Camera ngoài gửi Live Preview đến iPad; nhận lệnh chụp từ giao diện | Bắt buộc |
| FR-04 | Mỗi shot phải lấy **file ảnh camera chụp thật**, không dùng frame video trong production | Bắt buộc |
| FR-05 | Countdown có thể chọn 3/5/7/10 giây, chụp chuỗi, pause/resume, retake/xóa/reset | Bắt buộc |
| FR-06 | Hỗ trợ preset 6 ảnh dọc; thêm cấu hình 4 ảnh ngang (theo note team), không hardcode số slot | Bắt buộc; hình học khung phải xác nhận |
| FR-07 | Frame preset/custom PNG, detect slot; filter, sticker, màu khung, text/logo | Bắt buộc |
| FR-08 | Ghép ảnh chất lượng đủ in; preview trước khi xác nhận final | Bắt buộc |
| FR-09 | Backend laptop tự lưu ảnh và metadata; có chế độ backup thực sự | Bắt buộc |
| FR-10 | **Một final photo có một QR token riêng**, QR được chèn trên ảnh gửi tới máy in | Bắt buộc |
| FR-11 | Guest Photo Page: chỉ xem/tải một ảnh được in, không có album tổng | Bắt buộc |
| FR-12 | Host Dashboard: đăng nhập, quản lý tất cả ảnh/phiên/print jobs, in lại, thiết bị và cài đặt | Bắt buộc |
| FR-13 | Khách chọn số bản in; backend in qua Windows Print Spooler hoặc CUPS (nếu macOS) | Bắt buộc |
| FR-14 | QR/print chỉ sẵn sàng khi file final đã lưu thành công, token hợp lệ | Bắt buộc |
| FR-15 | Hệ thống miễn phí VPS/storage bên thứ ba: ưu tiên self-host + local disk | Mục tiêu triển khai; domain/Internet có thể phát sinh chi phí |
| FR-16 | Có mock camera để phát triển sớm; sau đó thay adapter cho camera thật | Bắt buộc |
| FR-17 | Guest UI, Host Dashboard và Guest Photo Page phải tách vai trò | Bắt buộc |
| FR-18 | Lỗi mạng/camera/printer không tạo “thành công giả”, có retry và log | Bắt buộc |

**Ghi chú về `4 ngang / 6 dọc`:** ghi nhận theo note họp 29/10/2026; đặc tả kỹ thuật tạm hiểu **4 shot cho bố cục ngang** và **6 shot cho bố cục dọc**. Thiết kế phải dựa trên cấu hình `slotCount + aspectRatio + slotCoordinates` để dễ thay đổi, vì tên và kích thước frame in thực tế chưa được xác nhận. Layout cũ `grid3x2` gồm 6 ảnh **không đồng nghĩa** với layout mới 4 ảnh ngang.

### 1.3. Những điểm vẫn CHƯA chốt

- Model máy ảnh (Canon/Sony/Nikon/...); cổng và protocol điều khiển, SDK, hỗ trợ Live View + shutter + download, đồng thời hay không.
- iPad model/cổng USB-C/Lightning/iPadOS; sơ đồ nối dây cuối cùng; có dùng HDMI capture hay không.
- Dạng truyền preview: USB/SDK → laptop → WebRTC → iPad (**phương án mặc định đề xuất**) hoặc HDMI → UVC → iPad + đường control riêng hoặc Wi-Fi camera API.
- Máy in/model, khổ giấy, dpi, borderless, yêu cầu color management, số bản in tối đa.
- Frame in chính thức cho 4 ngang và 6 dọc; vùng đặt QR; thời gian lưu file và thời hạn QR.
- Domain ổn định cho QR và Internet ở địa điểm sự kiện; lựa chọn backup drive.

**Quy tắc:** Không “đoán thay” các phần chưa chốt; đưa vào config/adapter và ghi `BLOCKED_BY_HARDWARE` khi cần kiểm thử.

---

## 2. Kiến trúc tổng thể (modular, đổi camera được)

```text
                   ┌──────────────────────────────────┐
                   │ CAMERA (trên tripod)             │
                   │ Live View + Physical Capture      │
                   └───────────────┬──────────────────┘
                                   │ USB / Wi-Fi / HDMI+control (TBD)
                  ┌────────────────▼─────────────────┐
                  │ Camera Integration Adapter       │
                  │ preview / capture / transfer     │
                  └────────────────┬─────────────────┘
                                   │
             ┌─────────────────────▼────────────────────┐
             │ LAPTOP HOST (Windows 11 / macOS)          │
             │ FastAPI + SQLite + local files            │
             │ Camera Service / Print Worker / Backup    │
             │ Private Host Dashboard                    │
             └─────────┬─────────────┬──────────┬────────┘
                       │             │          │
                   HTTPS API     print job  PUBLIC HTTPS
                       │             │          │
                ┌──────▼─────┐ ┌─────▼────┐ ┌───▼────────────────┐
                │ iPad Guest │ │ Printer  │ │ Guest Phone        │
                │ UI + Live  │ │ USB/WiFi │ │ /p/{share_token}   │
                │ Preview    │ └──────────┘ │ 1 ảnh + Download   │
                └────────────┘              └────────────────────┘
```

**Lưu ý:** Trong phương án camera nối iPad trực tiếp, Live Preview có thể đi thẳng Camera → iPad; sơ đồ trên mô tả **dịch vụ logic**, không bắt mọi tín hiệu phải qua laptop. Dù phương án vật lý nào, API Capture phải trả về tham chiếu **file ảnh thật** được lưu/đăng ký bền vững; UI không dùng một video frame như chứng cứ thành công.

### 2.1. Phương án reference để Codex triển khai phần mềm

- **Frontend:** HTML + CSS + JavaScript ES Modules, Vite cho build/dev; **không tự chuyển sang React/Vue** trong giai đoạn refactor.
- **Backend:** Python 3.11+ FastAPI, Pydantic, SQLAlchemy + SQLite, migration (Alembic), Pillow, QR generator, worker in; tương thích Windows 11 đầu tiên, thiết kế adapter cho macOS.
- **Camera:** `MockCameraAdapter` để dev; `RealCameraAdapter` theo SDK chính thức khi biết thiết bị; `PreviewProvider` riêng có thể triển khai WebRTC cho camera nối laptop.
- **Printing:** `MockPrinterAdapter`, `WindowsPrinterAdapter` (driver/spooler), `CupsPrinterAdapter` (macOS nếu cần). Queue bền vững.
- **Storage:** thư mục riêng do config chỉ định, metadata trong SQLite; file gốc/ghép/bản in và thumbnails tách nhau; ảnh không nằm trong static/public assets.
- **Deployment:** laptop serve frontend `dist/` + FastAPI trên một origin; public HTTPS qua tunnel hoặc domain đã chốt; iPad chạy Safari/PWA nếu phù hợp.
- **Secrets/config:** backend `.env` (không commit); frontend chỉ chứa giá trị public; không đẩy API key bên thứ ba vào HTML/JS.

### 2.2. Contract Camera Adapter (thiết kế, không phải code đã chạy)

```python
from typing import Protocol

class CameraAdapter(Protocol):
    async def connect(self) -> None: ...
    async def status(self) -> dict: ...
    async def start_preview(self) -> dict: ...  # preview source/session descriptor
    async def stop_preview(self) -> None: ...
    async def capture(self, session_id: str, shot_index: int,
                      request_id: str) -> dict: ...
    # capture() chỉ success khi file ảnh do camera tạo đã được nhận/lưu;
    # trả {shot_id, storage_ref, width, height, mime_type, captured_at}.
    async def disconnect(self) -> None: ...
```

- Preview stream và captured photo là **hai đường dữ liệu độc lập**. `capture()` không bao giờ âm thầm chụp từ `<video>` trong `REAL` mode.
- Nếu SDK thiếu cách lấy ảnh gốc: adapter báo `UNSUPPORTED_FEATURE`; không dùng frame giả để “lách” yêu cầu.
- Mock adapter sử dụng ảnh fixture/file upload **chỉ trong development**, phải hiển thị nhãn `DEMO`, server sản xuất không cho bật tùy tiện.
- Một camera có thể phục vụ một lượt chụp tại một thời điểm; dùng khóa/queue và trạng thái device, timeout, cancellation.
- Phân tách `CameraAdapter` (shutter+file transfer) và `PreviewProvider` (preview qua WebRTC/HTTPS hoặc browser UVC). Đổi transport không buộc viết lại Canvas/editor.

### 2.3. QR URL phải ổn định

- URL in trên giấy sẽ tiếp tục tồn tại sau khi khách rời trạm. **Không dùng URL Quick Tunnel thay đổi khi restart** để in ảnh thật. Quick Tunnel `trycloudflare.com` chỉ dành cho dev/demo; cần domain/hostname ổn định với named tunnel hoặc một giải pháp public URL tương đương.
- Nếu chỉ sử dụng laptop local, **laptop + backend + kết nối Internet/tunnel phải còn chạy** để khách ngoài mạng tải ảnh. Không có VPS/storage cloud không đồng nghĩa ảnh truy cập được khi tắt laptop.
- Cấu hình `PUBLIC_BASE_URL` phải chốt và được kiểm tra từ điện thoại dùng mạng di động **trước khi tạo QR in**.
- Khi public URL, storage hoặc tunnel gặp lỗi, **không tạo QR giả từ `#fragment`**; disable finalize/print tự phục vụ hoặc cảnh báo rõ để host xử lý.

---

## 3. Cấu trúc thư mục đề xuất (đích refactor)

```text
osa-booth/
├── README.md
├── TECHNICAL_SPEC.md                 # copy của tài liệu này trong repo
├── CODEX_REFACTOR_PROMPT.md
├── .gitignore
├── .env.example
├── legacy/
│   └── osa_booth_photobooth.original.html
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   │   ├── frames/                   # ảnh frame preset/demo không chứa PII
│   │   ├── logos/
│   │   └── audio/
│   └── src/
│       ├── main.js                   # bootstrap + wiring
│       ├── styles/
│       │   ├── base.css
│       │   ├── components.css
│       │   └── print.css
│       ├── config/
│       │   ├── defaults.js
│       │   ├── layouts.js
│       │   └── filters.js
│       ├── core/
│       │   ├── store.js              # state tập trung, không DOM
│       │   ├── router.js             # guest/admin/public routes
│       │   ├── events.js             # bind event listeners
│       │   └── session-machine.js    # trạng thái chụp
│       ├── services/
│       │   ├── api-client.js
│       │   ├── camera-client.js       # CameraClient interface
│       │   ├── mock-camera.js
│       │   ├── preview-provider.js
│       │   ├── photo-repository.js    # giao tiếp lưu ảnh API
│       │   ├── qr-client.js
│       │   └── print-client.js
│       ├── features/
│       │   ├── home/home.js
│       │   ├── capture/capture.js
│       │   ├── capture/countdown.js
│       │   ├── capture/retake.js
│       │   ├── layout/frame.js
│       │   ├── layout/slot-detection.js
│       │   ├── editor/compositor.js
│       │   ├── editor/filters.js
│       │   ├── editor/stickers.js
│       │   ├── editor/text.js
│       │   ├── editor/canvas-interactions.js
│       │   ├── result/result.js
│       │   ├── guest/guest-app.js
│       │   ├── share/photo-page.js    # 1 ảnh qua token
│       │   └── admin/dashboard.js
│       ├── components/
│       │   ├── toast.js
│       │   ├── modal.js
│       │   ├── qr-view.js
│       │   └── loading-state.js
│       └── utils/
│           ├── canvas.js
│           ├── image.js
│           ├── timing.js
│           └── validators.js
├── backend/
│   ├── pyproject.toml                 # hoặc requirements.txt, chọn 1 cách
│   ├── alembic/
│   ├── app/
│   │   ├── main.py                    # FastAPI entrypoint, static SPA
│   │   ├── core/config.py
│   │   ├── core/security.py
│   │   ├── db/database.py
│   │   ├── db/models.py
│   │   ├── db/schemas.py
│   │   ├── api/health.py
│   │   ├── api/camera.py
│   │   ├── api/sessions.py
│   │   ├── api/photos.py
│   │   ├── api/public_share.py
│   │   ├── api/printing.py
│   │   ├── api/admin.py
│   │   ├── services/camera/base.py
│   │   ├── services/camera/mock.py
│   │   ├── services/camera/real_placeholder.py
│   │   ├── services/camera/preview.py
│   │   ├── services/photos/storage.py
│   │   ├── services/photos/compositor.py
│   │   ├── services/photos/qr_overlay.py
│   │   ├── services/photos/thumbnails.py
│   │   ├── services/printing/base.py
│   │   ├── services/printing/mock.py
│   │   ├── services/printing/windows.py
│   │   ├── services/printing/cups.py
│   │   ├── services/printing/worker.py
│   │   ├── services/backups.py
│   │   └── services/retention.py
│   └── tests/
│       ├── test_camera_mock.py
│       ├── test_sessions.py
│       ├── test_share_security.py
│       ├── test_print_queue.py
│       └── test_finalize.py
├── tests/
│   ├── frontend/
│   └── e2e/
├── scripts/
│   ├── dev_windows.ps1
│   ├── run_windows.ps1
│   ├── dev_macos.sh
│   ├── run_macos.sh
│   └── check_event_readiness.py
├── docs/
│   ├── FUNCTION_INVENTORY.md
│   ├── MIGRATION_LOG.md
│   ├── API_CONTRACT.md
│   ├── HARDWARE_COMPATIBILITY.md
│   ├── EVENT_RUNBOOK.md
│   ├── SECURITY_PRIVACY.md
│   └── ACCEPTANCE_TESTS.md
└── runtime/                          # .gitignore (tạo khi chạy)
    ├── photobooth.sqlite3
    ├── originals/<session_id>/
    ├── composites/<session_id>/
    ├── print_ready/<photo_id>/
    ├── thumbnails/
    ├── backups/                    # không gọi đây là backup thật nếu cùng ổ
    └── logs/
```

- `frontend/src` là code ứng dụng; `backend/app` phục vụ API/storage/print; `legacy` giữ HTML cũ bất biến.
- Cấu trúc trên là **đích hướng tới**. Phase refactor chỉ tạo những file cần thiết cho logic HTML đang có; các file API/SDK có thể là skeleton được đánh dấu rõ `TODO`, không giả làm tính năng đã chạy.
- Không cố ép mỗi hàm thành một file; gom theo trách nhiệm và hạn chế circular imports.

---

## 4. Kiểm kê HTML cũ và hướng tái sử dụng (QUAN TRỌNG)

**Nguồn thực tế:** `osa_booth_photobooth.html` có `const app = { ... }` và DOM sections `screenHome`, `screenCapture`, `screenResult`. Source hiện **chưa tách module**. Bảng này là mapping ban đầu; Codex phải xác nhận lại sau khi đọc file trong repo.

| Nhóm file mới | Hàm/state đã có trong HTML | Hành động |
|---|---|---|
| `core/store.js`, `core/router.js` | `currentScreen`, `photos`, `goToScreen()`, `startNewGuestSession()`, `clearTimers()` | **Reuse + refactor**; tách state khỏi DOM; số slot có thể cấu hình |
| `services/camera-client.js`, `services/preview-provider.js` | `initCameraDevices()`, `refreshCameraList()`, `selectCameraDevice()`, `startCameraStream()`, `attachRealStreamToVideo()`, `stopCurrentStreams()`, `toggleMirror()` | **Reuse preview**; tách preview khỏi nguồn ảnh chụp thật |
| `services/mock-camera.js` | `startSimulatedCamera()`, `handleManualPhotoFilesUpload()`, `captureFrameIntoSlot()` | **Chỉ demo/dev**; cho ảnh fixture/upload có gắn nhãn MOCK |
| `features/capture/*` | `startAutomaticSession()`, `startOrContinueSequence()`, `runNextShotCountdown()`, `captureCurrentFrameImmediately()`, `triggerSingleRetake()`, `deleteSingleSlot()`, `resetSessionShots()`, `onAllSixShotsCompleted()`, `pauseAutoGraceForReview()` | **Reuse logic countdown/retake** nhưng đổi shot sang async/await thật, state machine và `slotCount` |
| `services/camera-client.js` | `triggerHardwareCameraShutter()`, `testHardwareShutterSignal()` | **PHẢI THAY**: hiện gọi `ImageCapture.takePhoto()` không dùng ảnh trả về và `127.0.0.1:5513` chỉ là loopback ở thiết bị mở trang; không phải integration production |
| `features/layout/*` | `handleCustomFrameUpload()`, `detectSixTransparentRegions()`, `autoDetectTransparentHolesFromFrame()`, `clearCustomFrame()`, `selectPresetLayout()`, `getSixSlotCoordinates()`, slot metrics | **Reuse**; tổng quát hóa 4/6 slots; sửa calibrator DOM thiếu |
| `features/editor/compositor.js` | `renderCompositeCanvas()`, `drawBuiltInFrameDecorationsBackground()`, `drawBuiltInFrameForegroundTexts()`, `drawImageCover()`, `roundRectPath()` | **Reuse cốt lõi**; từ 6 Canvas cố định → cấu hình số slot, nguồn là ảnh camera thực; xuất composite **chưa có QR** cho backend finalize |
| `features/editor/filters.js` | `filters`, `renderFilterButtons()`, `selectFilter()` | **Reuse** 9 filters và giao diện |
| `features/editor/stickers.js` | `stickerLibrary`, `renderStickerCategories()`, `renderStickerItems()`, `addEmojiSticker()`, `handleCustomStickerUpload()`, `clearAllStickers()`, `setupCanvasStickerInteractions()` | **Reuse**; bảo toàn kéo/thả/căn tỉ lệ |
| `features/editor/text.js` | `customTexts`, `updateCustomTextsUI()`, `updateCustomTexts()`, `colorSwatches`, `setFrameBackgroundColor()` | **Reuse** |
| `features/result/result.js` | `finishCaptureAndGoToResult()`, `downloadCompositeImage()`, `openMobilePreviewModal()` | **Sửa workflow**: sau chụp về Result để chỉnh, chỉ finalize sau xác nhận; download theo chính sách |
| `services/qr-client.js`, `components/qr-view.js` | `renderQRCodeVisual()`, `canvasToBlob()`, `generateQRCodeForCurrentPhoto()`, `copyQRLink()`, `scheduleQRCodeUpdate()` | **Reuse UI QR + blob util**, **THAY upload** ImgBB/TmpFiles/File.io bằng API backend; tuyệt đối không tạo token/upload mới khi chỉnh filter |
| `services/print-client.js` | `triggerPrint()` → `window.print()` và `autoPrintPopup` | **THAY** thành backend print job/queue; chỉ có print-ready artifact chứa QR |
| `components/toast.js`, `utils/timing.js` | `showToast()`, `playBeep()`, `playShutterSound()`, `triggerFlashEffect()`, `clearTimers()` | **Reuse** (kiểm tra autoplay AudioContext trên iPad) |
| `features/guest/guest-app.js` | markup `screenHome`, `screenCapture`, `screenResult`; các modal | **Giữ giao diện/thương hiệu**, tách template/style/event; bỏ inline `onclick="app..."` dần dần |
| `features/share/photo-page.js` | Chưa có | **New**: `/p/:token`, một ảnh + download |
| `features/admin/dashboard.js` | Chưa có | **New**: /admin, auth, gallery, trạng thái in, settings, camera |

**Các lỗi hiện hữu cần giải quyết sau khi có baseline refactor:**

1. `runNextShotCountdown()` hiện gọi `triggerHardwareCameraShutter()` **không await**, ngay sau đó `captureFrameIntoSlot()` lấy frame video; đây **không phải** pipeline chụp thật.
2. `triggerHardwareCameraShutter()` gọi `ImageCapture.takePhoto()` nhưng bỏ kết quả; URL `http://127.0.0.1:5513` chạy trên **iPad** nếu web đang mở ở iPad, không phải laptop từ xa.
3. `generateQRCodeForCurrentPhoto()` gọi ImgBB/TmpFiles/File.io; fallback `#osabooth-...` **không chứa ảnh**, điện thoại khác không thể lấy ảnh qua URL đó.
4. `scheduleQRCodeUpdate()` có thể tạo nhiều lần upload khi khách đổi filter/sticker; phải đổi thành **QR cố định sau Finalize**.
5. `triggerPrint()` hiện gọi `window.print()`; không bảo đảm silent print trên iPad và không có queue.
6. `finishCaptureAndGoToResult()` hiện có nhánh auto QR và auto print quá sớm; cần chờ khách xác nhận bản cuối.
7. `photos` hiện cố định 6 ô `960×720`; cần `slotCount` và metadata ảnh thật; mock có thể dùng Canvas nhưng production cần ảnh/tệp trả từ camera.
8. CSS/JS đang inline, CDN Tailwind/QRCode/Google Fonts cần chiến lược build/local assets để chạy ổn định khi sự kiện.
9. Frame calibrator có tham chiếu một số DOM input chưa hiện diện; sau refactor kiểm tra và bổ sung test thực tế.
10. Dùng HTML hiện tại làm **baseline**: không xóa bộ lọc, frame upload, mirror, retake, sticker drag, preset, audio/toast chỉ để code trông gọn hơn.

---

## 5. Luồng Guest UI và quản lý session

### 5.1. Màn hình

- `/booth` hoặc `/`: **Guest UI** trên iPad; không có menu admin công khai.
- **Home/Setup:** frame/layout; nếu host cho phép thì guest chọn preset, timer; nút bắt đầu phiên.
- **Capture:** Live Preview lớn, chế độ kiosk gần fullscreen. Trên iPad Safari không mặc định giả định `requestFullscreen()` hoạt động; ưu tiên layout viewport, hướng dẫn Add to Home Screen/PWA khi tương thích, có thể dùng Guided Access của iPad để cố định trạm. Nút dừng/sửa rõ ràng.
- **Review:** thấy danh sách shot đầy đủ, xóa/chụp lại từng shot, không tự in.
- **Result/Customize:** ghép ảnh, filter, sticker, frame/color/text, QR placeholder; hiện nút **Xác nhận & Tạo ảnh in**, sau đó mới tạo token/QR.
- **Ready:** xem bản ảnh in có QR, chọn số bản trong giới hạn, bấm In, hiện trạng thái; hiển thị QR để khách chủ động quét nếu muốn.
- **Reset/New Guest:** tạo session mới, không để ảnh/token phiên cũ lưu lại trên UI mới; hoàn thành workflow không xóa file server.

### 5.2. State machine bắt buộc

```text
IDLE → PREVIEW → COUNTDOWN → CAPTURING → REVIEW
                      ↑             │        │
                      └──── RETAKE ─┘        ↓
                                      EDITING → FINALIZING
                                                 ↓
                                              READY
                                           ↙          ↘
                                      PRINT_QUEUED   DOWNLOAD
                                           ↓
                                      PRINT_SENT / PRINT_ERROR
```

- Khi `CAPTURING`: khóa nút shutter trùng, không cho finalize, chờ adapter trả kết quả ảnh gốc.
- Shot lỗi/timeout: hiển thị lỗi, giữ slot chưa thành công, cho Retry; không tăng số shot.
- Retake: giữ file cũ cho audit/khôi phục nếu cần, update slot active chỉ sau ảnh mới nhận thành công; không tạo ảnh final khi chưa confirm.
- Sau `FINALIZING`: ảnh **immutable**. Muốn đổi filter sau finalize phải tạo revision/final mới, token mới; không sửa file đã in và khiến QR trỏ tới ảnh khác bất ngờ.
- Trạng thái từ backend là nguồn sự thật cho đã lưu/đã in; frontend timer không thể tự suy ra thành công.

### 5.3. Camera và preview

- Hỗ trợ mirror **chỉ là cách hiển thị**; ảnh gốc và ảnh xuất phải có chính sách mirror rõ ràng/config, không vô tình đảo chữ trên áo.
- Preview phải có loading, disconnected, reconnect, camera busy, permission denied, image transfer pending.
- Tất cả ảnh camera thật được nhận và lưu qua backend; ảnh raw chỉ trả cho phiên đang chụp qua endpoint được xác thực/ủy quyền, không public.
- Tối ưu hiển thị JPEG gốc: tạo thumbnail/preview theo đúng tỷ lệ, không làm giảm chất lượng file gốc lưu trữ.

### 5.4. Image editor và bố cục

- Duy trì 9 filter và thư viện sticker hiện tại, upload sticker PNG, frame PNG custom, text/logo/màu, drag & scale/position sticker (khi source hỗ trợ); frame slot detection phải có fallback calibrator khi không nhận đúng số vùng.
- `LayoutDefinition` chứa `id`, `slotCount`, `canvasWidth`, `canvasHeight`, `aspectRatio`, `slotCoordinates`, `qrSafeArea`, `bleed`, `dpiTarget` (host config).
- Preset mục tiêu `portrait_6` và `landscape_4`; có thể giữ `grid3x2` 6 ô cũ như preset bổ sung.
- Frontend render một bản `composite_without_qr`, để backend chèn QR nhất quán cho bản in; tránh QR bị che bởi sticker/filter.
- Khi xuất in: ảnh đủ độ phân giải theo giấy/dpi đã chọn; không coi kích thước mặc định Canvas `1200×1800` là bảo đảm đủ dpi cho mọi máy in.

---

## 6. Pipeline từ camera thật đến bản in có QR

```text
1. Client tạo session với layout (4 hoặc 6) và cấu hình chụp.
2. Camera/PreviewProvider sẵn sàng; iPad thấy Live Preview.
3. User nhấn bắt đầu → countdown → POST capture(slot).
4. CameraAdapter thực sự yêu cầu máy ảnh chụp + tải file về laptop.
5. Backend lưu raw/original và metadata → trả shot_id + URL preview được phép.
6. UI cập nhật đúng slot sau khi đã có file thật; tiếp tục shot còn lại.
7. User retake nếu muốn, rồi vào editor; tạo composite chưa có QR.
8. User nhấn XÁC NHẬN FINAL → upload composite + cấu hình editor.
9. Backend xác thực phiên, file hợp lệ, persist composite, tạo photo_id và share_token bí mật.
10. Backend tạo https://<PUBLIC_BASE_URL>/p/<share_token> và QR bitmap/vector.
11. Backend chèn QR vào qrSafeArea, render và lưu `print_ready` bất biến.
12. Backend commit metadata READY; API trả photo_id, share_url, print-preview URL.
13. iPad hiển thị preview + chọn số bản; POST print job.
14. PrintWorker lấy CHÍNH file print_ready đã lưu → printer trên laptop.
15. Điện thoại quét QR in trên giấy → GET /p/<token> → xem/tải đúng file print_ready.
```

**Bất biến:** `print_ready` và nội dung hiển thị/tải trên Guest Photo Page phải cùng version/ảnh đã được in; QR nằm trên ảnh bản giấy và trong file cho tải, trừ khi host chọn thêm một phiên bản download không QR như **tùy chọn riêng** được ghi rõ. Không cho trang guest truy cập `originals` hoặc các ảnh của người khác.

**QR uniqueness:** Mỗi **final-photo/revision** có token riêng. In 3 bản giống nhau từ cùng final photo → 3 bản giấy dùng **cùng token**, không phát sinh 3 ảnh khác nhau. In hai ảnh final khác nhau → token khác nhau.

**Thời điểm chốt QR:** khi finalize, KHÔNG phải mỗi lần người dùng thay filter. QR phải được server xác nhận `READY` trước khi tự in; không tạo QR để giả lập success khi upload lỗi.

---

## 7. Host Dashboard, Guest Photo Page và phân quyền

### 7.1. Guest Photo Page — `/p/{share_token}`

- Trình duyệt điện thoại truy cập URL từ QR; trang responsive chứa **một ảnh duy nhất** + nút `Xem ảnh` / `Tải ảnh`.
- Public endpoints chỉ lấy dữ liệu của token này; không trả file paths, session list, gallery index hoặc ID ảnh khác.
- Không có link `/gallery`, `/admin`, tìm kiếm hoặc điều hướng sang ảnh người khác trên trang guest.
- Download sử dụng response `Content-Disposition: attachment`; xem ảnh dùng loại MIME thích hợp.
- Token phải ngẫu nhiên đủ mạnh (ví dụ >= 128 bit entropy), lưu **hash token** trong DB nếu phù hợp, so khớp an toàn; không dùng `photo_id`, số thứ tự phiên, timestamp làm token.
- Invalid/revoked/expired token → `404` hoặc `410` có trang giải thích; không lộ thông tin ảnh khác; rate-limit, chống đoán token, không index (`noindex`), hạn chế cache và referrer.
- Ai sở hữu QR cũng có thể chia sẻ link này; **không tuyên bố** đây là cơ chế xác thực danh tính người chụp. Nếu sự kiện cần riêng tư hơn, thêm PIN/hết hạn là nâng cấp có thể cấu hình.

### 7.2. Host Dashboard — `/admin`

- Bắt buộc đăng nhập; không dùng một API key hardcode trong JS; session cookie `HttpOnly`, `Secure`, `SameSite` và CSRF protection cho thao tác state-changing (hoặc cơ chế tương đương).
- Xem toàn bộ sessions/photos, trạng thái raw/final/print, thumbnails, tìm theo thời gian, filter/layout, print job, retry.
- Xem/tải ảnh hoàn chỉnh, in lại; nếu quyền cho phép xem ảnh camera gốc thì chỉ qua admin authenticated endpoint.
- Quản lý camera online/offline, mode demo/real, camera active, preview diagnostics, lỗi driver/SDK.
- Quản lý máy in (printer selection, số bản max, queue, lỗi, cancel/reprint), cấu hình khổ giấy, frame/layout, countdown, branding, QR safe area, thời gian retention.
- Hiển thị tình trạng public URL/tunnel, dung lượng disk, backup gần nhất; lịch sử lỗi và audit event (không log secrets/token/raw customer content).
- Cho phép export data có kiểm soát và xóa phiên theo chính sách; không public all-photos gallery.

### 7.3. Guest Booth UI khác Guest Photo Page

| Giao diện | Đường dẫn dự kiến | Khả năng |
|---|---|---|
| Booth Kiosk (iPad) | `/booth` | Tạo phiên, live preview, shutter, editor, finalize, request print theo giới hạn; cần thiết lập/ủy quyền thiết bị kiosk |
| Guest Phone Page | `/p/{token}` | Chỉ xem/tải 1 ảnh, không điều khiển booth |
| Host Dashboard | `/admin` | Toàn quyền vận hành sau khi đăng nhập |

**Quan trọng:** Không chỉ ẩn nút admin bằng CSS/JavaScript; backend phải **kiểm tra phân quyền** trên mỗi endpoint.

---
## 8. Backend API contract (dự kiến v1)

**API prefix:** `/api/v1`; JSON có `request_id`, `status`, `error.code`, `error.message` khi phù hợp; UTC ISO8601; auth & scope theo endpoint. Các chi tiết payload có thể được điều chỉnh trong `docs/API_CONTRACT.md`, nhưng phải đồng bộ frontend/backend/test.

### 8.1. Camera / trạng thái

| Method | Path | Quyền | Mục đích |
|---|---|---|---|
| GET | `/api/v1/health` | Public / redacted | Kiểm tra ứng dụng sống, không lộ PII/config/secrets |
| GET | `/api/v1/camera/status` | Kiosk/Host | `online`, `mode`, `previewReady`, `captureReady`, lỗi |
| POST | `/api/v1/camera/preview/start` | Kiosk/Host | Khởi động preview session nếu camera/service hỗ trợ |
| POST | `/api/v1/camera/preview/stop` | Kiosk/Host | Dừng preview khi phù hợp |
| POST | `/api/v1/camera/preview/offer` | Kiosk/Host | WebRTC signaling nếu chọn WebRTC; không bắt buộc cho mọi adapter |

### 8.2. Phiên chụp và ảnh

| Method | Path | Quyền | Mục đích |
|---|---|---|---|
| POST | `/api/v1/sessions` | Kiosk | Tạo session, layout, số slot, settings snapshot |
| GET | `/api/v1/sessions/{id}` | Owner kiosk/Host | Trạng thái session/shot (không public) |
| POST | `/api/v1/sessions/{id}/shots/{index}/capture` | Owner kiosk | Yêu cầu chụp thật, tạo shot record |
| GET | `/api/v1/sessions/{id}/shots/{index}/preview` | Owner kiosk/Host | Thumbnail của đúng shot, kiểm tra quyền |
| POST | `/api/v1/sessions/{id}/shots/{index}/retake` | Owner kiosk | Capture mới thay slot active có kiểm soát |
| POST | `/api/v1/sessions/{id}/finalize` | Owner kiosk | Nhận composite blob + editor snapshot, tạo QR, print_ready |
| GET | `/api/v1/photos/{id}/status` | Owner kiosk/Host | Trạng thái finalize và các URL được phép |
| GET | `/api/v1/photos/{id}/print-preview` | Owner kiosk/Host | Ảnh final có QR cho preview |

- `index` là **0-based**, trong `[0, slotCount-1]`; giới hạn số slot phải lấy từ layout.
- Các lệnh có tác dụng tạo dữ liệu cần header `Idempotency-Key` hoặc `request_id`, đặc biệt là `capture`, `retake`, `finalize`, `print`.
- Nếu capture/finalize lâu: trả `202 + operation_id` và polling/WebSocket/SSE phù hợp; hoặc đợi trả `201` khi hoàn thành. Không trả `200 success` chỉ vì đã gửi lệnh shutter.
- `finalize` chỉ được khi đủ shot thành công, ảnh composite hợp lệ, host storage đủ dung lượng và cấu hình `PUBLIC_BASE_URL` hợp lệ. Tránh SSRF/path traversal, kiểm tra magic bytes và giới hạn kích thước ảnh.
- Kiosk session token có hạn và chỉ điều khiển session đang hoạt động; không dùng QR share token cho hành động chụp/in.

### 8.3. In ảnh

| Method | Path | Quyền | Mục đích |
|---|---|---|---|
| POST | `/api/v1/photos/{id}/print-jobs` | Owner kiosk/Host | Tạo job cho file `print_ready` đã READY, `copies` có giới hạn |
| GET | `/api/v1/print-jobs/{job_id}` | Owner kiosk/Host | Trạng thái `queued/sending/sent/error/canceled` |
| POST | `/api/v1/print-jobs/{job_id}/retry` | Host | Retry job lỗi, không nhân bản vô ý |
| POST | `/api/v1/print-jobs/{job_id}/cancel` | Host | Cancel job chưa được spooler nhận (nếu hỗ trợ) |

**Ví dụ print request:**

```http
POST /api/v1/photos/PHO_UUID/print-jobs
Idempotency-Key: a-unique-random-request-id
Content-Type: application/json

{"copies": 2, "printer_id": "default"}
```

- Không tạo print job trước khi `photo.status == READY` và file `print_ready` tồn tại.
- Không dùng `window.print()` làm hành vi production. Adapter Windows sử dụng Windows driver/spooler thực; macOS sử dụng CUPS `lp` hoặc API tương ứng; unit test sử dụng `MockPrinterAdapter`.
- `sent` chỉ có nghĩa spooler đã nhận, **không khẳng định giấy đã in xong** nếu driver không báo. Status UI phải trung thực.
- Khi frontend retry do mạng, cùng `Idempotency-Key` trả lại cùng job/result, không in thêm bản ngoài ý muốn.
- Bảo vệ tài nguyên: giới hạn số bản mỗi job/session/ngày theo config và admin override có audit.

### 8.4. Guest public và Host

| Method | Path | Quyền | Mục đích |
|---|---|---|---|
| GET | `/p/{share_token}` | Public possession link | HTML Guest Photo Page, không chứa gallery |
| GET | `/p/{share_token}/image` | Public possession link | Trả đúng final print-ready image |
| GET | `/p/{share_token}/download` | Public possession link | Download đúng file; không truy cập raw |
| POST | `/api/v1/admin/login` | Admin credentials | Đăng nhập secure session |
| POST | `/api/v1/admin/logout` | Admin | Đăng xuất |
| GET | `/api/v1/admin/sessions` | Admin | Session gallery có phân trang, lọc, tìm kiếm |
| GET | `/api/v1/admin/photos/{id}` | Admin | Chi tiết ảnh/print jobs và file có quyền |
| GET | `/api/v1/admin/print-jobs` | Admin | Print queue và lỗi |
| GET/PUT | `/api/v1/admin/settings` | Admin | Cấu hình booth, camera/printer/retention/branding |
| POST | `/api/v1/admin/photos/{id}/revoke` | Admin | Thu hồi chia sẻ ảnh có audit |

**Không triển khai** `GET /api/v1/photos` public, `GET /gallery` public, public directory listing, API query ảnh theo số thứ tự, hoặc serve nguyên thư mục `runtime/` bằng `StaticFiles`.

### 8.5. Ví dụ dữ liệu không nhạy cảm trả về sau finalize

```json
{
  "photo_id": "d682e84f-5ff6-44ba-b77d-0f458f610017",
  "session_id": "39ff014d-dcf4-4523-b37c-2c34590c32d8",
  "status": "READY",
  "share_url": "https://booth.example.com/p/EXAMPLE_RANDOM_OPAQUE_TOKEN",
  "print_preview_url": "/api/v1/photos/d682e84f-5ff6-44ba-b77d-0f458f610017/print-preview",
  "qr_embedded": true,
  "layout_id": "portrait_6"
}
```

`example.com` và IDs trong ví dụ **không phải URL/credentials thực tế**.

---

## 9. Database và file storage

### 9.1. Schema tối thiểu

| Entity | Trường cốt lõi | Ghi chú |
|---|---|---|
| `sessions` | id, kiosk_id, layout_id, slot_count, status, started_at, completed_at, settings_json | Một lượt khách/nhóm |
| `shots` | id, session_id, slot_index, revision, original_path, preview_path, mime, width, height, camera_mode, captured_at, status | Có lịch sử retake, slot active rõ ràng |
| `final_photos` | id, session_id, revision, composite_path, print_ready_path, sha256, layout_id, width, height, status, finalized_at | Một final photo/version immutable |
| `share_links` | id, final_photo_id, token_hash, issued_at, expires_at, revoked_at | Một token cho từng final; unique constraint |
| `print_jobs` | id, final_photo_id, idempotency_key, printer_id, copies, status, attempts, last_error, created_at, updated_at | Tách trạng thái in với trạng thái ảnh |
| `kiosks` | id, name, credential_hash/status, last_seen_at | Nếu có nhiều trạm |
| `admins` | id, username, password_hash, role, enabled | Password hash chuẩn, không plaintext |
| `settings` | key, value_json, updated_at | Cài đặt host quản lý |
| `audit_events` | id, actor, action, resource_type, resource_id, created_at, details_json | Không log share token/password |

- DB dùng migration; SQLite nên bật WAL khi phù hợp, busy timeout, DB access có transaction; không cho worker và web ghi theo kiểu racy.
- Filename do server tạo, không lấy filename user upload làm path. Ví dụ `runtime/originals/{session_uuid}/{shot_uuid}.jpg`.
- Tách bản `original` (ảnh camera), `composite` (ghép chưa QR), `print_ready` (ảnh QR), `thumbnail`.
- Lưu file tạm rồi atomic rename và commit DB sau khi thành công; thao tác lỗi có khả năng reconcile/cleanup để không mất ảnh hoặc record dangling.
- Không lưu file ảnh khách trong Git, frontend/public, CDN hay các dịch vụ thứ ba mặc định.

### 9.2. Backup, retention và phục hồi

- **Tự lưu** nghĩa là backend lưu file và database vào ổ cứng laptop. **Backup** nghĩa là có **bản sao trên thiết bị/địa điểm khác**; một thư mục khác trên cùng ổ **không** được xem là backup an toàn.
- Có backup theo lịch / nút backup từ Host Dashboard; backup DB nhất quán + originals/composites/print_ready; log trạng thái và lần chạy gần nhất.
- Test restore ít nhất một lần trước sự kiện; kiểm tra disk free threshold và quyền ghi lúc startup.
- Chính sách retention (số ngày giữ raw/final, QR expiry, deletion) do Host cấu hình, **không tự đặt cứng một thời hạn thay team**. QR in giấy mất hiệu lực sau thời hạn thì Guest Page giải thích rõ.
- Khi xóa ảnh: xóa có kiểm soát metadata/share/print, audit record tối thiểu phù hợp, không lộ link cũ.
- Không xóa raw originals tự động ngay sau khi render nếu retention đang yêu cầu giữ.

---

## 10. In ảnh: khổ giấy, QR và độ ổn định

1. Mỗi layout phải có một **QR safe area** không đè lên mặt người, chữ hoặc sticker; QR có nền tương phản và vùng yên tĩnh (quiet zone).
2. In thử với **máy in, driver, giấy và DPI thực tế**: kiểm tra ảnh không bị crop/scale, màu và barcode scan được từ bản in.
3. Template in được lưu theo version; cùng một `final_photo_id` dùng một bản `print_ready` bất biến. Không render mới theo cài đặt frame sau khi đã in.
4. Khách chọn số bản trước khi gửi print; mặc định/config giới hạn `min_copies`, `max_copies`, chống spam và double tap.
5. `PrintWorker` đọc job chưa xong từ DB khi restart, nhưng **không tự in lại** job có trạng thái không rõ đã gửi spooler hay chưa; Host phải xác nhận để tránh in trùng.
6. Nếu máy in lỗi/hết giấy/mất kết nối: giữ ảnh và QR, ghi trạng thái lỗi, cho Host retry; không đánh dấu `printed` khi chưa xác minh.
7. Có dry-run mock printer lưu bản print-preview thành file (không gửi in thật) để kiểm tra e2e trên máy phát triển.

---

## 11. Bảo mật, riêng tư và an toàn vận hành

- `PUBLIC_BASE_URL` chỉ dẫn đến domain/path được Host cho phép; tuyệt đối không để URL chứa `localhost`, `127.0.0.1`, `192.168.x.x` trên QR public dành cho khách ngoài mạng.
- Input ảnh: size cap, MIME + magic bytes, pixel count cap để tránh decompression bombs, sanitize hình ảnh cần thiết; giới hạn upload/concurrency/rate.
- Cấu hình CORS đúng origin; không dùng `allow_origins=["*"]` cùng cookies; không mở Camera SDK bridge/print worker ra Internet.
- Cookie admin bảo mật, chống CSRF; kiosk có credential scoped; password hash chuẩn; route public không cần full authentication nhưng phải kiểm token mạnh.
- Public photo endpoints gửi `X-Robots-Tag: noindex, nofollow` và chính sách cache riêng tư phù hợp; không tạo sitemap ảnh khách.
- Admin exports và logs không chứa plaintext tokens, secret keys, raw stack traces hoặc filesystem paths gửi tới guest.
- Có nút host `Pause Booth`/`Stop Capture` khi camera/printer lỗi; không cho tiếp tục capture nếu ổ cứng đầy hoặc backend mất kết nối.
- Lưu ý quyền riêng tư của người được chụp, thông báo thời gian lưu và quyền xóa ảnh theo quy định sự kiện; không mặc định public tất cả ảnh.
- Chặn session fixation / IDOR bằng kiểm tra owner session và chính sách role trên backend, không tin `session_id`/`photo_id` phía client.

---

## 12. Quản lý cấu hình và platform

### 12.1. `.env.example` (không chứa secret thật)

```dotenv
APP_ENV=development
HOST=127.0.0.1
PORT=8000
DATABASE_URL=sqlite:///./runtime/photobooth.sqlite3
STORAGE_ROOT=./runtime
PUBLIC_BASE_URL=https://booth.example.com
CAMERA_MODE=mock
CAMERA_ADAPTER=mock
PREVIEW_TRANSPORT=mock
PRINTER_MODE=mock
DEFAULT_PRINTER=default
MAX_PRINT_COPIES=3
ENABLE_PUBLIC_SHARE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CHANGE_ME_IN_REAL_ENV
# ADMIN_SESSION_SECRET=GENERATE_SECURE_RANDOM_VALUE
# KIOSK_ENROLLMENT_SECRET=GENERATE_SECURE_RANDOM_VALUE
# BACKUP_DESTINATION=EXTERNAL_DRIVE_PATH
# QR_RETENTION_DAYS=CHOOSE_BY_EVENT_POLICY
```

- `PUBLIC_BASE_URL` trong file mẫu chỉ là placeholder. Startup production phải fail nếu chưa cấu hình URL thật và host auth/secrets an toàn.
- `CAMERA_MODE=real` trong production không được chạy khi adapter chưa hỗ trợ hoặc chưa kết nối.
- Dùng `pathlib` cho đường dẫn, không hardcode `C:\\` hay `/Users/...`.
- Frontend không tự đọc backend secrets; config được cung cấp qua endpoint phù hợp hoặc build variables public.

### 12.2. Phát triển trên Windows 11, triển khai Windows/macOS

- Cài Python, Node.js LTS, driver máy in và SDK camera khi đã chốt model; tạo `venv` theo OS.
- Dev frontend Vite trên một port và backend FastAPI một port; proxy `/api` để giảm CORS. Prod backend phục vụ frontend build cùng origin.
- `WindowsPrinterAdapter` thực hiện spool qua API/driver Windows; `CupsPrinterAdapter` dùng `lp`/CUPS nếu host chuyển sang macOS.
- Camera SDK adapter phải có `supports_os()`/capability check; không hứa Windows và macOS đều hỗ trợ một model cụ thể.
- Cloudflare Tunnel có thể expose FastAPI origin; **không expose cổng camera bridge hoặc admin dev tools trực tiếp**.

### 12.3. Lưu ý Cloudflare Quick Tunnel

- Quick Tunnel miễn phí có URL `trycloudflare.com` **tạm thời và thay đổi khi khởi động lại**, chỉ phù hợp để test. QR in từ URL này có thể ngừng hoạt động sau khi dừng tunnel.
- Sự kiện thực tế cần public hostname ổn định (thường dùng named tunnel + domain hoặc giải pháp tương đương). Không tự hứa “miễn phí tuyệt đối” nếu muốn domain riêng và uptime.
- Backend/local disk phải chạy liên tục nếu khách còn cần tải ảnh; phải giải thích chính sách hết hạn cho tổ chức và khách.

---

## 13. Migration strategy — từ single-file HTML sang repo modular

### Phase 0 — Audit & Baseline

- Giữ HTML nguyên trạng trong `legacy/`; tạo screenshot/recording/behavior checklist baseline của Home, Capture, Result và modal.
- Lập `docs/FUNCTION_INVENTORY.md` liệt kê **tất cả** methods của `const app`, nơi gọi, state, dependencies và đích module; phân loại `reuse/refactor/replace/new`.
- Test HTML cũ mở được, chọn camera, mock, countdown, 6 shots, retake, filter, sticker, frame, in/download legacy (nhận diện hành vi legacy); log bug cũ riêng không mặc định sửa tất cả trong một commit.
- Tạo Git branch và commit `chore: preserve legacy photobooth baseline`.

### Phase 1 — **Refactor-only (bắt buộc làm trước)**

- Di chuyển markup sang `frontend/index.html` (hoặc `frontend/src/views` nếu cần), CSS sang `styles/`, JS sang các module như mục 3 và bảng mapping mục 4.
- Vite build chạy. Thay dần `onclick="app.xxx()"` bằng `addEventListener()`/event delegation từ `core/events.js`; không bỏ sót event trong markup động.
- Bảo toàn class Tailwind, CSS design tokens, DOM IDs quan trọng, 3 screens, modals, filter/stickers/frame/editor và hành vi mock hiện có.
- **Chưa thay HTTP upload, chưa thêm camera SDK, chưa thêm database trong commit refactor**, trừ khi phải tách service interface để chạy.
- Khi cần tương thích, tạo `window.app` facade **tạm thời** để không làm vỡ inline handlers, sau đó gỡ dần cùng test.
- Chuẩn hóa imports/export, state owner, timers cleanup; không tạo nhiều duplicate `app` hoặc global state tản mạn.
- Thêm unit tests smoke và Playwright e2e nếu có thể. Đối chiếu before/after screenshots.
- Sau phase này `npm run dev`, `npm run build`, `npm run test` chạy; code tách module nhưng hành vi **legacy tương đương**. Commit riêng `refactor(frontend): split legacy photobooth into ES modules`.

### Phase 2 — Backend foundation & Mock E2E

- Dựng FastAPI + SQLite migrations + local storage, API health/sessions, `MockCameraAdapter`, `MockPrinterAdapter`.
- Thay local-only session bằng session backend, mock ảnh mẫu có DEMO badge, dùng `capture()` async trả shot metadata.
- Đổi Guest UI sang state machine, hỗ trợ `slotCount` 4/6; tuyệt đối không gọi chụp video frame trong real mode.
- Test create session → mock capture → retake → composite → persist.

### Phase 3 — Finalize, QR, Guest Photo Page

- Tạo API finalize, QR token ngẫu nhiên, backend QR overlay vào print-ready, file immutable.
- Thay `generateQRCodeForCurrentPhoto` upload dịch vụ bên ngoài bằng API nội bộ.
- Guest Photo Page `/p/{token}` chỉ xem/tải một ảnh; viết tests security/negative token.
- Tắt mọi QR offline giả; finalize chỉ một lần, in cùng ảnh, không tái tạo token khi filter thay đổi.

### Phase 4 — Print Worker + Host Dashboard

- Queue DB bền vững, mock in, Windows printer integration có kiểm soát; chọn số bản in, retry/error, idempotency.
- `/admin` auth, gallery tất cả ảnh, print queue, camera/device status, layout/settings, retention, backup status.
- Test job duplicate/restart và quyền truy cập; in thử ảnh có QR bằng driver/máy in thật khi có thiết bị.

### Phase 5 — Real Camera Integration

- Chốt model camera, SDK và route vật lý. Trước khi tích hợp xác minh bằng proof-of-concept: (1) preview, (2) shutter thật, (3) nhận JPEG thật, (4) 10 lần chụp liên tiếp không mất ảnh, (5) lỗi và recovery.
- Triển khai `RealCameraAdapter`, `PreviewProvider`, config mode/OS; giữ `MockCameraAdapter` cho CI/dev.
- Thêm test hardware thực (gắn nhãn optional), logging và test tương thích iPad + laptop host.
- Không ghi “DONE” nếu chưa có kết quả chụp vật lý và file camera thực.

### Phase 6 — Event deployment, reliability, acceptance

- Khóa domain public ổn định, HTTPS hoạt động trên điện thoại mạng di động, test QR in trên giấy sau restart service/tunnel.
- Calibrate máy in, print copies, in lại, backup/restore, disk full, camera disconnect, hết giấy, Wi-Fi outage.
- Viết `docs/EVENT_RUNBOOK.md`: startup/shutdown, recovery, thay giấy, chuyển mock/real, xử lý QR lỗi, dọn dữ liệu sau sự kiện.
- Hướng dẫn `npm run build`, backend run prod và các lệnh Windows/macOS rõ ràng.

**Quy tắc Codex:** mỗi phase có branch/commit, changelog, checklist và test. Sau phase 1 **không** làm các phase 2–6 trong cùng refactor commit. Chạy test trước khi bắt đầu phase kế tiếp.

---

## 14. Test plan (bắt buộc)

### 14.1. Frontend/regression

- Home/Setup giữ giao diện gốc; chọn camera/mock, mirror preview, timer 3/5/7/10, chuyển Home→Capture→Result.
- Chụp 6 slot mock; retake riêng slot 2/5; delete/reset; auto/manual mode; không bỏ sót timer sau chuyển screen.
- Thêm layout 4 ảnh, layout 6 ảnh, custom frame, 9 filters, sticker emoji/PNG drag/drop, text, background, download.
- Capture fullscreen responsive trên iPad dọc/ngang (browser limits được ghi rõ); loading/error không che nút cần thiết.
- Verify preview vs real capture semantics: frontend `CAMERA_MODE=real` không được gọi `drawImage(video)` để tạo accepted shot.

### 14.2. Backend/storage/QR

- Session 4 và 6 shots, capture duplicate idempotency, retake revision; không finalize khi thiếu shot.
- Upload ảnh hợp lệ/bị lỗi/oversized/corrupt; disk full; rollback; retry; server restart vẫn còn data.
- Hai ảnh final khác nhau → hai token khác nhau. Tạo nhiều bản in cùng final → **một token**.
- Guest link mở đúng ảnh `print_ready`, ảnh trên điện thoại và file in cùng checksum/version.
- GET `/p/{token}` không có ảnh khác. GET `/api/v1/admin/sessions` anonymous → 401/403. Không cho đoán ID xem ảnh/raw.
- Invalid/expired/revoked token: không lộ ảnh. Không có public gallery/file listing.
- QR scan từ **ảnh giấy thật** qua camera điện thoại; kiểm tra URL từ **4G/5G**, không chỉ Wi-Fi nội bộ.

### 14.3. Print/operations

- Quantity 1..N theo config; double-click in chỉ tạo một job với cùng idempotency key.
- Printer offline/không có driver/hết giấy/worker restart: log và trạng thái trung thực; không in trùng sau restart.
- Kiểm tra QR scan được sau in borderless hoặc có lề, tỷ lệ không crop.
- Host có thể xem tất cả ảnh/in lại, guest không thấy Host Dashboard.
- Test backup + restore; QR vẫn trỏ đến đúng final photo khi host restart và domain không đổi.
- Uptime / storage / print monitoring hiển thị trên admin.

### 14.4. Hardware acceptance (khi có camera)

- Ảnh gốc lưu ở `runtime/originals` có thông số/kích thước do camera thực sự tạo; không phải canvas video `960×720` mặc định.
- iPad hiển thị Live Preview, nhấn shutter → camera phát sinh ảnh thật; adapter trả shot_id khi transfer đã xong; preview không bị giật/ngắt quá mức cho phép theo test thực tế.
- 10 lần chụp liên tiếp, thử retake, mất cáp/Wi-Fi, camera busy, camera full card, SDK restart.
- Test adapter trên host OS được chọn; không suy diễn tương thích từ SDK khác/OS khác.

---

## 15. Phi chức năng và vận hành sự kiện

- **Reliability:** chức năng cần thiết không phụ thuộc upload ảnh lên ImgBB/TmpFiles/File.io; file chính nằm ở laptop. Không chạy chế độ production từ demo QR không truy cập được.
- **Performance:** thiết kế async/non-blocking cho shutter, file transfer, QR render và print; preview ưu tiên mượt, editor không block UI lâu; đo latency trên thiết bị thật rồi ghi threshold thực tế trong `HARDWARE_COMPATIBILITY.md`.
- **Maintainability:** file/module có trách nhiệm rõ, lint/format, type hints Python, JS JSDoc hoặc TypeScript tùy phase được phê duyệt; không thêm framework lớn không cần thiết.
- **Observability:** structured logs, request IDs, camera adapter errors, print job logs, free space; dashboard hiển thị health, không log PII/tokens.
- **Recovery:** khi iPad reload/reconnect, khôi phục session đang làm nếu chưa timeout; khi host restart, ảnh/print jobs vẫn còn, các job chưa rõ status cần kiểm soát.
- **Safety/privacy:** giữ ảnh khách theo chính sách minh bạch; không công khai tổng ảnh; admin mới được liệt kê album.

---

## 16. Tiêu chí bàn giao, README và tài liệu phải có

Repo phải cung cấp:

1. `README.md`: project overview, phần mềm và thiết bị cần, setup Windows 11, dev frontend/backend, build, run production, test, vấn đề thường gặp.
2. `docs/FUNCTION_INVENTORY.md`: mapping **đầy đủ** function cũ → function/module mới, reuse/refactor/replace; không bỏ sót interactive handlers.
3. `docs/MIGRATION_LOG.md`: thay đổi phase/commit, bug cũ so với regression mới, mức test.
4. `docs/API_CONTRACT.md`: request/response/error/status/auth của mọi API.
5. `docs/HARDWARE_COMPATIBILITY.md`: chưa chốt thiết bị, adapters supported, POC checklist và kết quả kiểm thử thực.
6. `docs/SECURITY_PRIVACY.md`: token, auth, retention, permissions, delete policy.
7. `docs/EVENT_RUNBOOK.md`: hướng dẫn setup tripod/iPad/laptop/printer, start/stop tunnel, health, test QR LTE, print calibration, xử lý sự cố.
8. `docs/ACCEPTANCE_TESTS.md`: test matrix với PASS/FAIL/SKIPPED và bằng chứng khi test thiết bị thật.
9. `.env.example`, `.gitignore`, scripts chạy Windows/macOS (nếu hỗ trợ).
10. Có `MockCameraAdapter` và `MockPrinterAdapter` để CI chạy độc lập phần cứng; mock **không được** coi là hoàn thành tích hợp thực tế.

## 17. Definition of Done (DoD)

**Refactor Done** nếu:
- HTML gốc vẫn nằm trong `legacy`; code chạy theo folder modules; màn hình/tương tác cũ tương đương; `npm run build` và smoke test pass.
- `FUNCTION_INVENTORY.md` mapping đầy đủ, không bỏ function, không chuyển behavior mà không thông báo.

**Software MVP Done** nếu:
- Mock E2E tạo một phiên 4/6 shots, retake, ghép ảnh, finalize backend, lưu ảnh, QR embedded, guest xem/tải đúng một ảnh, admin thấy album tổng, chọn bản in, print worker mock/Windows test có log; security tests pass.
- Không dùng third-party temporary upload và QR fragment fallback; secrets không nằm frontend; ảnh không nằm static public.

**Event Ready** chỉ khi:
- Model camera thực tế đã test **Live Preview + physical shutter + transfer file ảnh gốc** trên host/iPad thật.
- Máy in thật đã test QR scan trên giấy; điện thoại LTE mở được link sau restart, domain còn nguyên.
- Host đã test tình huống camera disconnect, printer lỗi, upload fail, backup/restore, disk space và quyền riêng tư.
- Cấu hình retention, print quota, stable URL và admin credentials đã được thống nhất/chốt.

---

## 18. Thứ tự ưu tiên thực thi cho Codex

**Hãy làm trước:** `Phase 0 → Phase 1 (refactor-only)` theo `CODEX_REFACTOR_PROMPT.md`. Hoàn tất bằng code, test, báo cáo mapping và commit độc lập.

**Sau đó thực hiện tuần tự:** Backend Mock → Finalize/QR/Guest Page → Print/Host → Real Camera → Event tests.

**Điều tuyệt đối không được nhầm:**

- *Video Preview* không phải *Physical Shutter Photo*.
- *Ảnh hiện ở trên iPad* không có nghĩa *laptop đã lưu*.
- *Một URL QR* không có nghĩa *guest truy cập được khi host/tunnel tắt*.
- *Print job submitted* không có nghĩa *bản giấy đã in xong*.
- *Gallery Host* không được trở thành *Gallery Guest*.
- *Một loạt ảnh chụp 4/6 shot* khác với *một final photo có QR riêng*.

### Nguồn tra cứu kỹ thuật (để Codex kiểm chứng, không thay cho thử nghiệm phần cứng)

- WebKit iPadOS 17 USB cameras: https://webkit.org/blog/14445/webkit-features-in-safari-17-0/
- FastAPI upload: https://fastapi.tiangolo.com/tutorial/request-files/
- Cloudflare Quick Tunnels (tạm thời): https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- Cloudflare Tunnel production: https://developers.cloudflare.com/tunnel/get-started/

**LƯU Ý CUỐI:** File này là **đặc tả yêu cầu và bản thiết kế đề xuất**, không phải mã nguồn. Khi Codex báo tiến độ, phải phân biệt `implemented/tested/mock-only/hardware-blocked` và đối chiếu với các tiêu chí ở trên.

---

## 19. Phụ lục — danh mục TẤT CẢ method được phát hiện trong HTML gốc

Bảng này được trích trực tiếp từ `const app` trong `osa_booth_photobooth.html` (line numbers là vị trí trong **bản HTML đang kiểm kê**). Codex cần rà soát cả các callback/event handlers, vì một số hàm có thể thay đổi signature trong lúc refactor. Tên file bên dưới là **gợi ý trách nhiệm**, không bắt buộc một file cho mỗi method.

| Line gốc | Hàm HTML gốc | Module đích đề xuất |
|---:|---|---|
| 833 | `init()` | `core/bootstrap` |
| 845 | `initCameraDevices()` | `services/camera-client` |
| 854 | `refreshCameraList()` | `services/camera-client` |
| 876 | `selectCameraDevice()` | `services/camera-client` |
| 887 | `requestRealCameraPermission()` | `services/camera-client` |
| 892 | `startCameraStream()` | `services/camera-client` |
| 920 | `attachRealStreamToVideo()` | `services/camera-client` |
| 945 | `stopCurrentStreams()` | `services/camera-client` |
| 956 | `startSimulatedCamera()` | `services/camera-client` |
| 1047 | `handleManualPhotoFilesUpload()` | `services/mock-camera` |
| 1080 | `toggleMirror()` | `services/camera-client` |
| 1090 | `handleCustomFrameUpload()` | `features/layout/frame` |
| 1128 | `scheduleQRCodeUpdate()` | `services/qr-client` |
| 1139 | `detectSixTransparentRegions()` | `features/layout/frame` |
| 1209 | `autoDetectTransparentHolesFromFrame()` | `features/layout/frame` |
| 1229 | `clearCustomFrame()` | `features/layout/frame` |
| 1241 | `selectPresetLayout()` | `features/layout/frame` |
| 1246 | `updateFrameSelectionUI()` | `features/layout/frame` |
| 1287 | `updateCustomSlotMetrics()` | `features/layout/frame` |
| 1299 | `setCountdownSeconds()` | `config/defaults + capture UI` |
| 1313 | `toggleFullAutoMode()` | `features/capture/capture` |
| 1321 | `updateAutoModeUI()` | `features/capture/capture` |
| 1335 | `goToScreen()` | `core/router` |
| 1367 | `startAutomaticSession()` | `features/capture/capture` |
| 1378 | `startNewGuestSession()` | `core/store` |
| 1393 | `clearTimers()` | `utils/timing` |
| 1409 | `renderCaptureDots()` | `features/capture/capture` |
| 1418 | `renderSixSlotsGrid()` | `features/capture/capture` |
| 1462 | `updateCaptureScreenUI()` | `features/capture/capture` |
| 1502 | `startOrContinueSequence()` | `features/capture/capture` |
| 1519 | `runNextShotCountdown()` | `features/capture/capture` |
| 1588 | `captureCurrentFrameImmediately()` | `features/capture/capture` |
| 1609 | `triggerHardwareCameraShutter()` | `services/camera-client (replace later)` |
| 1626 | `testHardwareShutterSignal()` | `services/camera-client (replace later)` |
| 1633 | `captureFrameIntoSlot()` | `services/mock-camera (dev-only)` |
| 1681 | `triggerSingleRetake()` | `features/capture/capture` |
| 1688 | `deleteSingleSlot()` | `features/capture/capture` |
| 1696 | `cancelSingleRetake()` | `features/capture/capture` |
| 1702 | `resetSessionShots()` | `features/capture/capture` |
| 1710 | `onAllSixShotsCompleted()` | `features/capture/capture` |
| 1735 | `pauseAutoGraceForReview()` | `features/capture/capture` |
| 1745 | `finishCaptureAndGoToResult()` | `features/result/result` |
| 1776 | `getSixSlotCoordinates()` | `features/editor/compositor` |
| 1816 | `renderCompositeCanvas()` | `features/editor/compositor` |
| 1904 | `drawBuiltInFrameDecorationsBackground()` | `features/editor/compositor` |
| 1912 | `drawBuiltInFrameForegroundTexts()` | `features/editor/compositor` |
| 1941 | `isColorLight()` | `utils/canvas` |
| 1950 | `roundRectPath()` | `utils/canvas` |
| 1964 | `drawImageCover()` | `utils/canvas` |
| 1975 | `switchCustomTab()` | `features/result/result` |
| 1992 | `renderFilterButtons()` | `features/editor/filters` |
| 2006 | `selectFilter()` | `features/editor/filters` |
| 2013 | `renderStickerCategories()` | `features/editor/stickers` |
| 2024 | `selectStickerCategory()` | `features/editor/stickers` |
| 2030 | `renderStickerItems()` | `features/editor/stickers` |
| 2039 | `addEmojiSticker()` | `features/editor/stickers` |
| 2052 | `handleCustomStickerUpload()` | `features/editor/stickers` |
| 2077 | `clearAllStickers()` | `features/editor/stickers` |
| 2083 | `setupCanvasStickerInteractions()` | `features/editor/canvas-interactions` |
| 2146 | `renderColorSwatches()` | `features/editor/text` |
| 2155 | `setFrameBackgroundColor()` | `features/editor/text` |
| 2166 | `updateCustomTextsUI()` | `features/editor/text` |
| 2175 | `updateCustomTexts()` | `features/editor/text` |
| 2183 | `setQRProvider()` | `services/qr-client (legacy)` |
| 2188 | `copyQRLink()` | `components/qr-view` |
| 2200 | `renderQRCodeVisual()` | `components/qr-view` |
| 2233 | `canvasToBlob()` | `utils/canvas` |
| 2248 | `generateQRCodeForCurrentPhoto()` | `services/qr-client (replace later)` |
| 2363 | `openMobilePreviewModal()` | `features/result/result` |
| 2368 | `triggerPrint()` | `services/print-client (replace later)` |
| 2378 | `downloadCompositeImage()` | `features/result/result` |
| 2391 | `openSettingsModal()` | `components/modal` |
| 2395 | `closeSettingsModal()` | `components/modal` |
| 2400 | `openSlotCalibrator()` | `features/layout/frame` |
| 2404 | `syncSettingsFromModal()` | `core/store` |
| 2411 | `showToast()` | `components/toast` |
| 2432 | `ensureAudio()` | `utils/timing` |
| 2441 | `playBeep()` | `utils/timing` |
| 2458 | `playShutterSound()` | `utils/timing` |
| 2477 | `triggerFlashEffect()` | `components/toast` |

**Tổng cộng:** 80 method trong object `app` theo mẫu khai báo hiện tại; danh sách trên là inventory tự động từ file HTML đọc được. Không tính các arrow callbacks/nested handlers: Codex cần tiếp tục tìm `onclick=`, `onchange=`, `addEventListener`, `setTimeout`, `setInterval` để kiểm kê toàn bộ behavior.
