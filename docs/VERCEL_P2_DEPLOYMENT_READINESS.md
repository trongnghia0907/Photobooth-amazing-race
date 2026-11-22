# P2 — Chuẩn bị triển khai Amazing Race 2026 trên Vercel Hobby

**22/11/2026 · 120 người · dự kiến tối đa 150 composite.** Phần mềm được chuẩn bị và chạy kiểm thử cục bộ. Chưa tạo tài nguyên Vercel/Neon, chưa deploy và chưa gửi ảnh lên cloud. Máy ảnh, nguồn ảnh lịch sử và SQLite vận hành giữ tại laptop.

## Thay đổi

| Phần | Tệp và hành vi |
|---|---|
| Host Windows | `backend/app/services/cloud_publish.py`, `repository.py`, `drive_storage.py`, `event_display.py`, `main.py`, `routers.py`, `database.py` và migration `010_cloud_and_print_options.sql`. Confirm lưu PNG gốc và tạo bản ghi cloud trong SQLite cùng giao dịch với final. Worker Drive riêng. Chỉ final mới, đã được duyệt, mới đủ điều kiện gửi lên cloud. Duyệt lại ảnh cũ không tạo job. |
| Public Vercel | `cloud/` có Node app riêng, cấu hình Vercel, schema Neon và SDK đã khóa phiên bản. Build dùng lại Gallery, Event Display và artwork hiện có. Chỉ phục vụ trang công khai, media và API nhận metadata có khóa xác thực. |
| QR | `frontend/src/services/qr-client.js`, `components/qr-view.js`, `components/qr-status.js`. Booth đọc trạng thái cục bộ để hiển thị QR Vercel sau ACK. Nếu cloud đang chờ, Booth có thể dùng QR local đã xác minh hoặc hiện trạng thái đang xuất bản. |
| In local | `printers.py`, `printing.py`, `printing_routes.py` và các tệp Host Dashboard. Chọn máy in, khổ và hướng do driver báo. Preview dùng vùng in từ GDI. Queue chốt tùy chọn theo job, giữ copy count và bản in QR hiện có. |

## Xuất bản và quyền truy cập

1. Host lưu composite đã Confirm và xếp Drive độc lập. Khi ảnh được duyệt, SQLite lưu phiên bản cần xuất bản. Bản local của ảnh đã vào hàng đợi cloud được giữ kể cả sau khi gỡ công khai. Tắt credential chỉ dừng worker cloud. Không import hoặc khôi phục 76 composite thử cũ.
2. Worker kiểm tra bản final, trạng thái duyệt và SHA-256. Laptop dùng SDK `@vercel/blob` ghi trực tiếp vào **private Blob**, gồm PNG nguyên byte và JPEG thumbnail cạnh dài tối đa 600 px. Khóa đối tượng cố định theo ID ảnh và checksum. SDK dùng multipart khi PNG vượt 5 MB. API Vercel chỉ nhận metadata nhỏ, nên file trên 4,5 MB không đi qua request body của Function. Catalog kiểm tra lại kích thước, MIME và SHA-256 của Blob trước khi đăng. [Vercel Blob SDK](https://vercel.com/docs/vercel-blob/using-blob-sdk) · [Giới hạn Functions và streaming](https://vercel.com/kb/guide/how-can-i-bypass-vercel-body-size-limit-serverless-functions)
3. Retry tiếp tục sau restart, với backoff tối đa 5 phút. Phiên bản trong Neon chống đăng lại từ yêu cầu cũ sau lệnh ẩn. Nếu Host mất mạng, lệnh gỡ chờ gửi và bản công khai cuối cùng vẫn còn đến khi cloud nhận ACK. Dashboard hiển thị trạng thái đăng/gỡ và kích thước PNG.
4. Gallery phân trang 10 ảnh, lazy-load thumbnail và tải PNG. Event Display giữ hiệu ứng, poll 12 giây khi hiển thị và chậm hơn khi tab ẩn. QR cá nhân dùng token ký ở cloud, có hạn 24 giờ từ lần phát hành đầu và retry không gia hạn. Gallery vẫn phục vụ ảnh đang được duyệt sau khi QR hết hạn. Tất cả đường media kiểm tra quyền ở catalog. Thumbnail và ảnh Event Display dùng `ETag` kèm kiểm tra lại quyền. Preview/download qua QR trả PNG sạch, còn QR footer chỉ thuộc bản in local.

## Năm kiểm tra P2

| Kiểm tra | Bằng chứng |
|---|---|
| 1. Booth local | **PASS.** Hai lượt Chromium mở frontend đã build trên Host loopback, dùng camera mock và tắt cloud. Confirm lưu PNG đúng SHA-256 cho 2×2 (**1.800 × 1.200, 88.064 byte**) và 2×3 (**1.200 × 1.800, 120.362 byte**). Gallery, Event Display và QR local mở được. Chỉ bước bắt tay HTTPS công khai được mô phỏng. |
| 2. Cloud và Drive | **PASS mô phỏng.** Drive nhận đúng PNG độc lập. PNG đã ghi khi upload thumbnail bị ngắt. Sau restart, worker dùng lại khóa PNG, gửi thumbnail rồi đăng một ảnh. Gỡ ảnh và giữ PNG local, reapproval ảnh lịch sử không tạo job. |
| 3. Trang public | **PASS mô phỏng.** HTTP loopback qua handler public trả chính xác cùng byte PNG ở Gallery, Event Display và QR. QR không có footer. Token giả/hết hạn và ảnh bị ẩn bị từ chối. Gallery vẫn tải được PNG còn được duyệt sau khi token hết hạn. |
| 4. In | **PASS mô phỏng.** Bản in QR và queue 2 bản chạy qua Mock Printer ở cả hai bố cục. Kiểm tra khổ giấy, hướng, preview và tùy chọn lưu theo job bằng adapter mô phỏng. Driver Microsoft Print to PDF trả 54 khổ và cả hai hướng khi đọc vùng in. Máy in sự kiện **chưa xác minh**. |
| 5. Build và phạm vi public | **PASS cục bộ.** Build Host và `cloud/` thành công. Bản public chỉ gồm tài sản của ba trang. HTTP mock trả 404 ở route camera, printer, admin và sessions. Routing và streaming trên Vercel thật **chưa xác minh**. |

Bài Playwright kiểm tra bố cục rộng có một sai lệch riêng ở cả hai preset. Mép cuối của preview in vượt viewport 1.920 × 1.080 khoảng 0,8 px. Hai lượt P2 xác nhận luồng Confirm, tải ảnh và queue in hoạt động. CSS bố cục Booth không được chỉnh trong P2.

## Dung lượng và hạn mức

- Mốc P1 dùng 3,2 MB/PNG và 60 KB/thumbnail, tương đương **489 MB** cho 150 ảnh. Ngưỡng 1 GB tương đương trung bình khoảng **6,67 MB cho mỗi cặp PNG + thumbnail** trong một bộ 150 ảnh. Dung lượng PNG thực tế được đo khi Confirm và cập nhật kích thước thumbnail sau upload. Fixture phần mềm không đại diện ảnh Sony của khách.
- Ước tính P1 khoảng **1,51 GB** trong kịch bản thường, **7,7 GB** trong kịch bản tải nhiều và **12,02 GB** trong kịch bản 360 lượt, vượt mức 10 GB. Với private Blob, cần theo dõi cả lượt xác minh upload, cache miss và transfer từ Function tới trình duyệt. Blob Hobby có 1 GB lưu trữ, 10 GB Blob Data Transfer, 10.000 thao tác đơn giản và 2.000 thao tác nâng cao trong hạn mức. Neon Free hiện công bố 1 GB và 100 CU-giờ mỗi project/tháng. [Vercel Blob Pricing](https://vercel.com/docs/vercel-blob/usage-and-pricing) · [Neon Free Plan](https://neon.com/blog/neon-free-plan-1-gb-per-project)

## Các bước khi được phép triển khai

1. Xác nhận việc sử dụng của sự kiện phù hợp quy định Hobby về mục đích cá nhân/phi thương mại. Nếu điều kiện hoặc định mức không phù hợp, báo lại trước khi tạo tài nguyên. [Vercel Hobby](https://vercel.com/docs/plans/hobby)
2. Trong **một Vercel project Hobby**, đặt **Root Directory** thành `cloud`, **Node.js** 22.x và bật **Include source files outside of the Root Directory in the Build Step** để lấy UI/theme của repo. Dùng `npm ci`, `npm run build`, output `public` theo `cloud/vercel.json`. Chọn một HTTPS production origin cố định. [Vercel Monorepos](https://vercel.com/docs/monorepos/monorepo-faq)
3. Tạo một **private Vercel Blob store** dành riêng cho sự kiện và một **Neon Free database**. Chạy `cloud/schema.sql` trong Neon SQL Editor. Đặt các biến server bên dưới. Dùng hai secret ngẫu nhiên độc lập, mỗi secret ít nhất 32 ký tự. Giữ nguyên secret QR cho tới khi các link đang dùng hết hạn. Tránh cấu hình Vercel Deployment Protection yêu cầu khách đăng nhập trên production URL.

| Nơi cấu hình | Biến |
|---|---|
| Vercel server | `DATABASE_URL` (Neon), `BLOB_READ_WRITE_TOKEN` (private event store), `PHOTO_CLOUD_PUBLISH_SECRET` (đối chiếu Host), `PHOTO_CLOUD_QR_SECRET` (chỉ Vercel). |
| Host Windows | Trong file env cục bộ đang dùng với `scripts/run_host.py`, thêm `PHOTO_CLOUD_ORIGIN=https://<production-domain>` với origin thuần, `PHOTO_CLOUD_PUBLISH_SECRET` giống Vercel và `PHOTO_CLOUD_BLOB_TOKEN` là token của cùng private store. Chạy `npm.cmd --prefix cloud ci` từ thư mục repo để worker tìm được SDK. Khởi động Host bằng cấu hình đang dùng. Giữ `PUBLIC_BASE_URL`/gateway cũ cho QR local và bản in QR, giữ cấu hình Drive độc lập. |

4. Sau khi có quyền deploy, kiểm tra bằng composite fixture được duyệt trên chương trình riêng trước khi bật trên runtime sự kiện. Xác minh trên Vercel thật việc trả đủ một PNG trên 4,5 MB, QR trên điện thoại, ID không trùng sau retry, lệnh ẩn có ACK và các đường admin/camera/in trả 404. Kiểm tra thống kê Blob theo kích thước composite thực tế. Dùng máy in sự kiện để đối chiếu khổ, hướng, vùng in và chất lượng vật lý sau khi được phép in.

**Chưa xác minh:** Vercel/Neon/Blob thật, Drive OAuth thật ở lượt P2, Sony thật, điện thoại ngoài LAN và máy in vật lý. Cấu hình local tiếp tục dùng riêng khi chưa điền biến cloud.
