# CODEX PROMPT — REFACTOR HTML GỐC THÀNH KIẾN TRÚC MODULAR (PHASE 0 & 1)

> **Cách dùng:** Đặt file này và `OSA_BOOTH_TECHNICAL_SPEC.md` trong thư mục gốc repo cùng file `osa_booth_photobooth.html` (hoặc `osa_booth_photobooth(1).html`). Mở repo bằng Codex, dán toàn bộ phần **PROMPT CHÍNH** bên dưới.  
> **Mục đích lượt đầu:** **Tách file HTML cũ thành modules có thể chạy được, giữ nguyên UI và các chức năng đang có**. Chưa yêu cầu hoàn thành camera thật, backend, QR riêng hay in thật trong commit refactor. Những phần đó sẽ làm tiếp theo các phase trong specification.

---

## PROMPT CHÍNH — COPY VÀ DÁN VÀO CODEX

```text
Bạn là senior full-stack engineer và đang nhận nhiệm vụ refactor AMAZING RACE 2026 Photobooth. Hãy trực tiếp kiểm tra repository, đọc đầy đủ file:

1. OSA_BOOTH_TECHNICAL_SPEC.md  (tài liệu yêu cầu kỹ thuật chuẩn)
2. osa_booth_photobooth.html hoặc osa_booth_photobooth(1).html (single-file HTML gốc)
3. Các assets, config, test, README hiện có nếu có.

NHIỆM VỤ CỦA LƯỢT NÀY: THỰC HIỆN PHASE 0 + PHASE 1 (AUDIT + REFACTOR-ONLY). Dùng tối đa code, function, CSS, DOM và UI hiện có. KHÔNG VIẾT LẠI GIAO DIỆN TỪ ĐẦU. KHÔNG TỰ Ý ĐỔI FRAMEWORK SANG REACT/VUE. KHÔNG LÀM BACKEND/CAMERA THẬT/PRINT SERVER/SHARE WEB TRONG COMMIT REFACTOR.

A. AUDIT TRƯỚC KHI SỬA

- Xác định đúng file HTML gốc và kiểm tra toàn bộ khoảng 2.493 dòng (đừng chỉ đọc một vài đoạn).
- Tìm tất cả methods trong object `app`, object state, event handlers inline, các ID/class trên DOM, CSS, CDN dependencies, asset paths, các lời gọi `app.xxx()`.
- Tạo `docs/FUNCTION_INVENTORY.md` theo bảng: old_function / old_source_location / behavior / new_module / new_symbol / reuse|refactor|replace-later / status / notes.
- Kiểm kê 3 màn hình `screenHome`, `screenCapture`, `screenResult`, modal settings/preview, media/video/canvas, camera selector, countdown, image slots, custom frame, sticker, filter, QR, print.
- Phân biệt hiện trạng và yêu cầu tương lai. Không giả định HTML cũ đã chụp ảnh bằng màn trập vật lý hoặc tự lưu vào laptop.

B. BẢO TOÀN BASELINE

- Copy nguyên file nguồn vào `legacy/osa_booth_photobooth.original.html` (giữ byte-for-byte nếu có thể). Không xóa/ghi đè HTML gốc của người dùng.
- Ghi `docs/MIGRATION_LOG.md` liệt kê hành vi baseline và các vấn đề nguồn đã biết.
- Kiểm tra git status, không ghi đè thay đổi chưa commit của người dùng; nếu branch dirty thì báo rõ và tránh phá thay đổi. Không force reset, không xóa file khác.
- Ghi một commit baseline riêng nếu có quyền commit và repo đã có git: `chore: preserve legacy photobooth baseline`.

C. TÁCH CODE THEO KIẾN TRÚC Ở MỤC 3 TRONG SPEC

Tạo tối thiểu:

frontend/index.html
frontend/package.json
frontend/vite.config.js
frontend/src/main.js
frontend/src/styles/base.css
frontend/src/styles/components.css
frontend/src/styles/print.css
frontend/src/config/defaults.js
frontend/src/config/layouts.js
frontend/src/config/filters.js
frontend/src/core/store.js
frontend/src/core/router.js
frontend/src/core/events.js
frontend/src/core/session-machine.js (có thể là skeleton, chỉ nếu cần)
frontend/src/services/camera-client.js
frontend/src/services/mock-camera.js
frontend/src/services/preview-provider.js
frontend/src/services/qr-client.js
frontend/src/services/print-client.js
frontend/src/features/home/home.js
frontend/src/features/capture/capture.js
frontend/src/features/capture/countdown.js
frontend/src/features/capture/retake.js
frontend/src/features/layout/frame.js
frontend/src/features/layout/slot-detection.js
frontend/src/features/editor/compositor.js
frontend/src/features/editor/filters.js
frontend/src/features/editor/stickers.js
frontend/src/features/editor/text.js
frontend/src/features/editor/canvas-interactions.js
frontend/src/features/result/result.js
frontend/src/components/toast.js
frontend/src/utils/canvas.js

Các file được phép gộp hợp lý nếu thực sự cùng trách nhiệm; phải cập nhật FUNCTION_INVENTORY và không tạo file rỗng chỉ để giống cây thư mục. Các file backend/admin/public share chỉ cần triển khai ở phase sau, KHÔNG làm giả là đã xong.

D. QUY TẮC TÁI SỬ DỤNG CODE CŨ

- Giữ nguyên Tailwind classes, component appearance, màu, fonts, CSS keyframes, DOM IDs quan trọng và các thao tác UI; CSS chỉ di chuyển, không redesign.
- Dời logic từ `const app = { ... }` thành module functions/services có import/export rõ, state tập trung. Không copy/paste thành hai bộ logic cùng chạy.
- Quan trọng nhất: giữ lại thuật toán renderCompositeCanvas(), drawImageCover(), getSixSlotCoordinates(), detectSixTransparentRegions(), filters, stickers, text, countdown, retake, frame upload, camera preview, mock camera, export/download.
- Cẩn thận với `this` đang trỏ tới `app`; khi biến method thành module function, truyền state/dependencies hợp lý, đừng để undefined state hoặc mất binding.
- Cẩn thận với HTML inline `onclick="app.xxx()"` và các button được tạo động bằng innerHTML. Ưu tiên chuyển sang addEventListener()/event delegation trong core/events.js. Nếu chưa thể chuyển hết một lượt, sử dụng `window.app` facade TẠM THỜI tương thích, nêu rõ trong MIGRATION_LOG.
- Cẩn thận khi thay đổi lifecycle: DOMContentLoaded, this.init(), video.srcObject, canvas, document.getElementById, async timing, setTimeout, setInterval, clearTimers, overlay, modal, sticker pointer events.
- Giữ video preview, `mirrorVideo` và mock capture cho việc test chức năng cũ; chỉ dùng mock/video frame trong DEVELOPMENT, có nhãn demo khi hiển thị.
- CHƯA claim đã có real shutter: `triggerHardwareCameraShutter()` hiện gọi ImageCapture.takePhoto() mà không sử dụng ảnh trả về, rồi dùng captureFrameIntoSlot(); bridge localhost:5513 là địa chỉ loopback của thiết bị mở web. Hãy đóng gói legacy behavior này thành adapter/mock riêng và ghi rõ chưa phải real camera integration. Không lén dùng trong production.
- Giữ QR/print legacy functionality để có thể đối chiếu regression ở phase 1 nhưng đặt chúng sau interface/service boundary, ghi deprecation/TODO. Không vô tình upload ảnh thật lên bên thứ ba khi chạy test; sử dụng mock backend hoặc disable external upload trong default dev mode. Không trình bày link QR giả là tải được ảnh.
- Không tự bật auto print khi đang test. Để cấu hình tách biệt, không gọi window.print() không mong muốn trong smoke test.
- Không hardcode cố định 6 slots ở interface mới: giữ layout cũ hoạt động, đồng thời chuẩn bị cấu trúc layout config cho 4/6 slot ở phase sau. Không đổi logic 6 slots phức tạp giữa chừng nếu làm hỏng baseline.

E. TOOLING VÀ DEPENDENCIES

- Dùng Vanilla JavaScript ES Modules + Vite; không cần TypeScript/React ở giai đoạn này.
- Chọn dependency tối thiểu. Để UI ổn định trước, có thể giữ Tailwind CDN/QRCode CDN tạm thời, nhưng ghi rõ cần migrate sang build/local assets trước khi triển khai sự kiện thực.
- Cung cấp npm scripts: dev, build, preview, test (nếu test runner khả dụng). Không dùng versions bịa đặt; chọn versions thực tế cài được trong môi trường repo.
- Tạo .gitignore cho node_modules, dist, .env, runtime/, ảnh khách, database, logs.
- Tạo README.md để người phát triển Windows 11 có thể cd frontend, npm install, npm run dev và truy cập trang.

F. KIỂM THỬ REGRESSION (BẮT BUỘC)

Trước khi kết thúc, chạy các test khả thi và đối chiếu HTML gốc với phiên bản modular cho:

1. Màn hình Home / Setup, camera select, mirror, timer 3/5/7/10 giây.
2. Bắt đầu phiên, Live Preview mock, đếm ngược, chụp 6 tấm, pause/resume.
3. Retake/xóa 1 slot, reset phiên, đi đến Result, quay Home.
4. Các frame preset 2x3, 3x2 và custom PNG, detect slot.
5. Toàn bộ 9 filters; sticker category/emoji, PNG upload, drag interactions.
6. Màu khung, custom text, renderCompositeCanvas(), preview/download ảnh.
7. Modal Settings, mobile preview, toast, beep/shutter/flash.
8. Các handlers của button được render động phải hoạt động (không còn `app is not defined`).
9. No console errors, no broken import, no 404 CSS/JS asset, no blank screen.
10. `npm run build` pass; nếu có Playwright thì chạy screenshot/e2e. Nếu không có browser automation, nêu rõ manual tests chưa verify thay vì tự nhận PASS.

G. DELIVERABLES PHẢI CÓ

- Folder frontend chạy được, đúng cơ cấu module theo TECHNICAL_SPEC.
- legacy copy vẫn còn nguyên.
- docs/FUNCTION_INVENTORY.md (đủ 100% methods source), docs/MIGRATION_LOG.md.
- README, .gitignore, các script dev/build/test và baseline smoke checks.
- Báo cáo cuối gồm: (1) danh sách file thay đổi, (2) mapping chức năng old→new, (3) những phần đã chạy/test, (4) những phần chưa test, (5) known issues, (6) lệnh chạy trên Windows, (7) đề xuất bước tiếp theo.
- Phân biệt DONE/DEMO/TODO/BLOCKED_BY_HARDWARE.

H. STOP CONDITION

Sau khi hoàn tất PHASE 0 và PHASE 1, DỪNG LẠI. Không tự động triển khai FastAPI, SQLite, public guest gallery, Host Dashboard, real camera SDK, Cloudflare hoặc in thật trong cùng commit. Những yêu cầu này đã nằm trong SPEC và sẽ được triển khai tuần tự ở các lệnh sau.

Mục tiêu cao nhất: BẢO TỒN và TẬN DỤNG lại toàn bộ logic có giá trị của HTML cũ, trong khi chuẩn bị được các service boundary để phát triển kiến trúc Photobooth production về sau.

Hãy bắt đầu bằng audit repository và FUNCTION_INVENTORY, sau đó sửa code và chạy test — không chỉ đưa ra kế hoạch suông.
```

---

## PROMPT TIẾP THEO — SAU KHI PHASE 1 PASS (KHÔNG DÁN CÙNG LÚC)

```text
Hãy đọc lại `OSA_BOOTH_TECHNICAL_SPEC.md`, `docs/FUNCTION_INVENTORY.md`,
`docs/MIGRATION_LOG.md` và trạng thái repo sau refactor.

Bây giờ chỉ triển khai PHASE 2 của specification:
- FastAPI backend, SQLite, storage trên laptop, session API,
  MockCameraAdapter và MockPrinterAdapter.
- Kết nối frontend bằng API client, thay vì giữ ảnh chỉ trong RAM.
- Countdown/retake dùng async capture contract, không xem screenshot
  video là thành công của camera thật.
- Layout config hỗ trợ 4-shot ngang và 6-shot dọc,
  giữ thêm preset 6-slot cũ nếu được.
- Duy trì UI và tất cả chức năng editor đã refactor.

Tạo migration, test, docs/API_CONTRACT.md, README setup cho Windows.
Chỉ làm PHASE 2, kiểm thử end-to-end mock rồi DỪNG; chưa làm
QR production, printing thật, Host Dashboard, real camera SDK.
Liệt kê những gì DONE/MOCK/TODO/BLOCKED_BY_HARDWARE.
```

## Cách triển khai các phase sau

Khi Phase 2 pass, mỗi lần yêu cầu Codex **chỉ một phase**:

- **Phase 3:** finalize có QR riêng, in QR vào bản `print_ready`, trang `/p/{token}` chỉ xem/tải đúng một ảnh, không public album tổng.
- **Phase 4:** print queue Windows, số bản in, Host Dashboard private + auth, backup, settings.
- **Phase 5:** tích hợp `RealCameraAdapter` sau khi biết model camera; Live Preview + shutter thật + chuyển ảnh gốc, kiểm chứng trên phần cứng.
- **Phase 6:** test thiết bị thật, domain HTTPS ổn định, QR từ bản giấy, điều kiện mạng, restore và hướng dẫn vận hành.

**Không yêu cầu Codex giả lập rằng các phase chưa triển khai đã hoàn thành.**
