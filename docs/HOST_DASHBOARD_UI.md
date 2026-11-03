# Host Dashboard — event operations

Mở `http://localhost:8000/admin` trên laptop Host và đăng nhập bằng tài khoản đã cấu hình.

## Điều hướng

| Mục | Nội dung |
| --- | --- |
| Tổng quan | Tổng phiên, composite hoàn tất, job đang chờ/xử lý, job lỗi; trạng thái và ảnh gần đây |
| Ảnh đã chụp | 20 composite cuối/trang, chi tiết phiên, tải ảnh, bản in có QR, in lại, duyệt/ẩn sự kiện |
| Hàng đợi in | Chọn máy in, 50 job/trang, trạng thái, chi tiết lỗi, retry và hủy job chờ |
| Camera | Adapter, quyền điều khiển, ngắt camera, làm mới trạng thái và chẩn đoán nâng cao |
| Khung ảnh | Danh sách mẫu, PNG custom, preview, cấu hình và căn chỉnh thu gọn |
| Màn hình sự kiện | Bật/thu hồi mã truy cập, số ảnh duyệt, mở màn hình trình chiếu |
| Mạng & QR | Cấu hình URL, backend, Guest Photo Page và phạm vi truy cập |
| Hệ thống | Chế độ hoạt động, OS, dung lượng trống, thông tin kỹ thuật và đăng xuất |

Chuyển mục không tải lại trang, không đổi camera/máy in, không xóa form chưa lưu và không chạy chẩn đoán phần cứng. Thông báo thao tác tự ẩn sau 7 giây; lỗi hiện tại có trong Tổng quan và trang tương ứng.

Kết quả chẩn đoán có thời gian kiểm tra riêng. Khi trạng thái hoặc adapter thay đổi, kết quả trước được đánh dấu đã cũ. Demo không xác minh shutter thật; dashboard không phát shutter trong chẩn đoán. In Submitted chỉ xác nhận đã gửi spooler.

Frame 3×2 ngang sáu ảnh được đánh dấu Legacy và vẫn lưu nguyên cấu hình; Guest hiện chỉ dùng 2×3 dọc và 2×2 ngang. Không sửa ảnh lịch sử.

Mã màn hình chỉ hiện sau thao tác tạo mã, được xóa khỏi giao diện khi rời trang Màn hình sự kiện hoặc đăng xuất. Ảnh chỉ được duyệt sau khi Host xác nhận cơ sở đồng ý/ủy quyền.

## Kiểm thử

```powershell
cd frontend
npm test
npm run build:production -- --outDir dist-production
npx playwright test --config playwright.dashboard.config.js
```

Playwright dùng backend riêng cổng 8027, storage ngẫu nhiên trong `.tools/dashboard-*`, MockPrinter và Chrome local nếu có. Có thể cấu hình `CHROME_PATH` cho trình duyệt khác. Không dùng dữ liệu runtime của người vận hành.

Suite kiểm tra đăng nhập/đăng xuất, 8 mục điều hướng, form chưa lưu, camera/chẩn đoán/stale state, lưu frame, composite 4/6 ảnh, download, duyệt/ẩn, in lại, trạng thái job, mã sự kiện, QR/network, lỗi/timeout, chặn click lặp, phiên hết hạn và layout 1366/1024/600px. Screenshot sau refactor được lưu ở `frontend/test-results/dashboard/`.

Phần mềm không xác nhận phần cứng camera, giấy in thật hoặc kết nối điện thoại tại sự kiện. Trang hệ thống hiển thị dung lượng trống/dự phòng do API hiện có cung cấp; không quét toàn bộ kho ảnh để tính dung lượng sử dụng.
