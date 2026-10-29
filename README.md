# OSA BOOTH — Phase 0 + Phase 1

Frontend Vanilla JavaScript ES Modules + Vite, tách trực tiếp từ HTML gốc. Giữ Home → Capture → Result, CSS/theme, mock preview, 6 shots, countdown/retake, frame detection, 9 filters, stickers, text, download và in trình duyệt legacy. **Chỉ DEMO; chưa có backend, camera shutter thật, lưu ảnh tự động, QR public hay print queue.** Dừng trước Phase 2.

## Chạy trên Windows 11

Cần Node.js 22.12+ (đã kiểm tra bằng Node 24.22.2), npm và trình duyệt hiện đại. PowerShell:

```powershell
cd frontend
npm ci
npm run dev
```

Mở http://127.0.0.1:5173. Khi trình duyệt từ chối camera, ứng dụng chuyển sang camera mô phỏng có nhãn DEMO. Selector cho phép chọn video preview hoặc mô phỏng. Ảnh chỉ ở RAM đến khi tải PNG; reload sẽ mất phiên. Webcam là nguồn preview/video frame, chưa phải ảnh gốc DSLR/mirrorless.

```powershell
npm run build
npm run preview
```

Mở http://127.0.0.1:4173 để kiểm tra bản build. **`build` chủ động dùng Vite mode `demo`**, artifact hiện badge DEMO và vẫn cho mock/video capture để review Phase 1. Không triển khai artifact này cho sự kiện. `npm run build:production` dùng mode production và chặn mock/video capture; chưa phải ứng dụng production hoàn chỉnh.

## Kiểm thử

```powershell
cd frontend
npm test
npm run build
npm run build:production -- --outDir dist-production
npx playwright install chromium
npm run test:e2e
```

Nếu dùng Chrome đã cài thay Chromium của Playwright:

```powershell
$env:CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:e2e
```

E2E tự mở/dọn servers ở 5173, 5174 (baseline), 4173 (demo artifact), 4273 (production guard artifact); cần các port này trống. Phải build hai artifact trước E2E. Tests chỉ dùng ảnh canvas fixture, chặn dịch vụ ngoài, stub `window.print()`, mô phỏng từ chối camera. Google Fonts/QRCode CDN không được kiểm chứng online trong tests. Screenshot fixture nằm ở `docs/screenshots/`; không chứa ảnh khách.

Môi trường lần refactor chưa có Node trên PATH. Helper tùy chọn từ thư mục gốc, không cài phần mềm toàn hệ thống:

```powershell
python scripts/setup_test_tools.py
python scripts/frontend_command.py ci --offline=false --cache=../.tools/npm-cache
python scripts/frontend_command.py test
python scripts/frontend_command.py run build
python scripts/frontend_command.py run build:production -- --outDir dist-production
python scripts/frontend_command.py run test:e2e
```

Helper ưu tiên Node portable tại `.tools/`, dùng Chrome ở đường dẫn trên. Máy có Node/npm bình thường nên dùng các lệnh npm chuẩn. `.tools/`, dependencies, build output và test traces được ignore.

## Cấu trúc và tài liệu

- `frontend/index.html`: markup gốc, giữ nguyên IDs và classes; thêm nhãn demo và inputs calibrator bị thiếu.
- `frontend/src/`: `config`, `core`, `services`, `features`, `components`, `styles`, `utils`. State ở `core/store.js`; wiring ở `core/bootstrap.js`; startup ở `main.js`.
- Tailwind 3.4.17 build cục bộ, giữ nguyên theme. Google Fonts và QRCode.js CDN tạm giữ; cần local assets trước sự kiện.
- `legacy/osa_booth_photobooth.original.html`: bản sao byte-for-byte; HTML gốc ở root không sửa.
- [FUNCTION_INVENTORY](docs/FUNCTION_INVENTORY.md): mapping 80/80 method, behavior, call sites, dependencies và module mới.
- [MIGRATION_LOG](docs/MIGRATION_LOG.md): baseline, ngoại lệ refactor, bug cũ và giới hạn.
- [ACCEPTANCE_TESTS](docs/ACCEPTANCE_TESTS.md): kết quả và những phần chưa verify.
- [FILES_CREATED](docs/FILES_CREATED.md): danh sách file bàn giao.

`window.app` là facade tương thích **tạm thời** cho inline handlers tĩnh/động; không có bản logic thứ hai. Khi chuyển sang delegation, phải sửa cả HTML và template strings trong modules cùng tests.

## QR / in / camera legacy

QR mặc định hiển thị unavailable, không upload và không tạo link fragment giả. Nút tải PNG và mobile preview vẫn dùng được. In chỉ mở hộp thoại trình duyệt khi bấm hoặc khi người vận hành chủ động bật checkbox auto print; mặc định checkbox **tắt**. Không có bằng chứng giấy đã in.

Chỉ để đối chiếu legacy trong development, copy `frontend/.env.example` thành `.env.local`, bật flag tương ứng rồi restart dev server:

- `VITE_ENABLE_LEGACY_UPLOAD=true`: cho phép lại ImgBB/TmpFiles/File.io; có thể gửi ảnh tới dịch vụ ngoài. Mã nằm trong `services/legacy-qr.js`; không dùng cho sự kiện.
- `VITE_ENABLE_LEGACY_SHUTTER=true`: cho phép signal ImageCapture/loopback 5513 cũ; không xác nhận physical shutter hoặc file camera gốc.

Hai flags chỉ hiệu lực khi Vite DEV; không bật trong tests. Backend/QR/print/camera SDK sẽ làm theo từng phase sau khi người dùng review Phase 1. Session machine/API/admin/share/storage chưa được triển khai. Repository ban đầu không có `.git`, nên không có branch/commit baseline hoặc refactor; không khởi tạo Git thay người dùng.
