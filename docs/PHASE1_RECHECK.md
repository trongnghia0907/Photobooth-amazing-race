# Kiểm tra lại frontend sau Phase 1 — 30/10/2026

Đã kiểm tra bằng **Node.js v26.13.0 / npm 11.20.0 được cài trên Windows**, không dùng Node portable của lần refactor trước. Git working tree sạch trước khi kiểm tra. Không triển khai Phase 2 và không thay đổi code ứng dụng vì không phát hiện lỗi hồi quy.

## Lệnh và kết quả thực tế

Chạy trong `frontend/`, dùng `npm.cmd` để gọi npm trên PowerShell:

| Lệnh | Kết quả |
|---|---|
| `npm.cmd ci --no-audit --no-fund --offline=false --cache=../.tools/npm-cache` | PASS — cài 85 packages từ package-lock.json, không đổi dependency versions |
| `npm.cmd run build` | PASS — Vite 7.3.7, 38 modules, 944 ms |
| `npm.cmd test` | PASS — 6/6 Node regression tests |
| `npm.cmd run build:production -- --outDir dist-production` | PASS — 38 modules, 807 ms |
| `$env:CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'; npm.cmd run test:e2e` | PASS — cả 6 bài Playwright trong một lượt, 53,6 giây |

Lần `npm ci` đầu bị sandbox chặn tạo process con (`spawn EPERM`). Chạy lại với quyền thực thi process con đã thành công. Đây là giới hạn môi trường thực thi, không phải lỗi import hay dependency của frontend. npm có cảnh báo install-scripts esbuild chưa nằm trong allowScripts; binary hiện được cài và Vite/esbuild build đã pass. Không thay đổi cấu hình npm toàn hệ thống.

## Chức năng được xác nhận hoạt động

- Home/Capture/Result và các modal; lựa chọn camera, fallback mô phỏng khi từ chối quyền, mirror state, timer 3/5/7/10.
- Countdown chụp đủ sáu ảnh mô phỏng, pause/resume, retake riêng ô 2/5, xóa một ô, reset và khách tiếp theo; hủy delayed start khi quay Home.
- Upload sáu ảnh fixture, frame PNG sáu lỗ alpha, phát hiện đúng sáu slots, calibrator với lề 0%, presets 2×3 và 3×2.
- Toàn bộ chín filters, bốn nhóm emoji, sticker ảnh upload, kéo bằng chuột và sự kiện touch tổng hợp, màu khung và text.
- Mobile preview tại thiết bị đang mở, tải file PNG, toast; print handler chỉ được gọi một lần khi chủ động yêu cầu trong test.
- Composite PNG trùng pixel với HTML gốc cho **18 tổ hợp = 9 filters × 2 presets**.
- Artifact demo tại hai viewport 820×1180 và 1180×820: Result không tràn ngang, dynamic handlers chạy.
- Artifact production guard không tự mở camera và từ chối mock/manual/video-frame capture.
- Không có pageerror/console.error, import hỏng, blank screen hoặc asset nội bộ 404 trong test harness. Không ghi nhận external upload, loopback shutter call hoặc auto print ngoài ý muốn.
- Sáu Node tests kiểm tra bản gốc/legacy khớp byte, mapping 80/80 method, state isolation, filters/stickers, tọa độ/drawing calls, DOM IDs/CSS và timer cleanup.

## Những giới hạn còn tồn tại

- Chỉ DEMO: chưa có backend, lưu ảnh bền vững, khôi phục phiên, QR public tải ảnh, print queue hoặc camera shutter/transfer ảnh gốc thật. Reload vẫn mất ảnh chưa tải xuống.
- Capture vẫn sáu ảnh; layout bốn ảnh mới chỉ có config disabled. `window.app` vẫn là facade tạm thời cho inline handlers.
- Camera preview thật, Safari/iPad thật, âm thanh nghe thực tế và giấy in chưa được kiểm chứng. Test dùng camera permission bị từ chối/mock; `window.print()` được stub, không in thật.
- Google Fonts/QRCode CDN và cloud upload legacy không được kiểm chứng online: test chặn/giả lập các resource ngoài. QR mặc định báo chưa sẵn sàng; không có QR/link giả và không upload ảnh khách.
- Home có thể bị tràn card với camera selector dài ở một số độ rộng/font — vấn đề baseline đã ghi trong MIGRATION_LOG; responsive test hiện xác nhận màn hình Result.
- Upload frame/sticker/ảnh legacy chưa bổ sung giới hạn kích thước, magic-byte validation hoặc đầy đủ phục hồi lỗi file hỏng.

Screenshots fixture được tạo lại trong `docs/screenshots/`; không chứa ảnh khách. Không có thay đổi mã ứng dụng hay lockfile. Các server kiểm thử được Playwright dọn khi kết thúc.

## Chạy thử

```powershell
cd frontend
npm run dev
```

Mở http://127.0.0.1:5173. `npm run build` vẫn là artifact **DEMO** để review Phase 1. Không coi production guard là bản event-ready. Dừng ở Phase 1.
