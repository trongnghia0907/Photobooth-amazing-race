# P1 — Audit Photobooth và khả năng dùng Vercel Hobby

**22/11/2026 · 120 người · dự kiến 150 ảnh ghép.** Audit chỉ đọc dữ liệu vận hành, đọc mã và chạy test cách ly. Khi kiểm tra cuối không có listener Host 8000 hoặc gateway 8011. Luồng hiện tại có điểm chốt ảnh phù hợp để gắn worker cloud. Chưa đủ bằng chứng để triển khai lên Hobby hoặc thử in trên thiết bị sự kiện.

## 1. Workflow hiện tại

| Bước | Tệp và hàm | Kích hoạt, lưu trữ và lỗi |
|---|---|---|
| Mở phiên, chọn 2×2 hay 2×3 | [capture.js](../frontend/src/features/capture/capture.js) **startAutomaticSession**, [photo-repository.js](../frontend/src/services/photo-repository.js) **ensureSession**, **saveSetupLayout**; [repository.py](../backend/app/services/repository.py) **create**, **update_layout** | Booth gửi preset, số ô, owner token và idempotency key. Host ghi SQLite trước khi chụp. Camera hoặc lưu bố cục lỗi giữ người dùng ở bước chuẩn bị. |
| Live View, đếm ngược, chụp 4/6 | [countdown.js](../frontend/src/features/capture/countdown.js), [host-camera.js](../frontend/src/services/host-camera.js) **prepareHostCamera**, **captureHostPhoto**, **retryHostCapture**; [camera_routes.py](../backend/app/camera_routes.py); [controller.py](../backend/app/services/camera/controller.py) **capture**, **result**; [Sony adapter](../backend/app/services/camera/sony_zve10.py) | Host điều khiển USB/WIA/PTP; preview và tiến độ qua API local. JPEG đi vào staging, ảnh slot vào originals; SQLite ghi camera_captures, photos, slots. Khi kết quả không chắc chắn, phục hồi hoặc đối soát biên nhận trước khi gửi shutter khác. |
| Review | [result.js](../frontend/src/features/result/result.js) **finishCaptureAndGoToResult**; [compositor.js](../frontend/src/features/editor/compositor.js) **renderCompositeCanvas** | Đợi ảnh đủ, ghép canvas trong trình duyệt với frame và thiết lập. Render review chưa xuất bản. |
| Confirm & Display | [photo-repository.js](../frontend/src/services/photo-repository.js) **confirmAndSaveSession**; [routers.py](../backend/app/routers.py); [repository.py](../backend/app/services/repository.py) **upload_composite**, **complete** | Nút gửi PNG và shots_revision rồi chờ /complete. File ở `runtime/composites/<session>/<composite>.png`. Host kiểm tra slot, ảnh chính thức, SHA-256 và capture còn bất định. Cùng giao dịch, ghi session_finals, xếp job Drive/cleanup và tự duyệt local nếu Host bật chính sách **và** snapshot có đồng ý. Mất ACK thì đọc lại phiên, giữ khóa thử lại. Ảnh làm việc có thể được dọn sau commit theo chính sách hiện tại. |
| Drive backup | [drive_storage.py](../backend/app/services/drive_storage.py) **queue**, **_process_one**, **local**, **retry**, **start** | Worker đọc job bền vững trong drive_uploads sau Confirm. Xác minh ACL, ID đã giữ trước, folder, size và MD5 rồi đánh dấu SYNCED. Lỗi có backoff và retry. Restart dùng lại ID Drive. Xác nhận local không đợi Drive. |
| Gallery / Event Display | [photo_gallery.py](../backend/app/photo_gallery.py) **photos**, **published_file**, **preview**; [event_display.py](../backend/app/event_display.py) **approve**, **approved_photo_feed**, **media** | Duyệt tự động hoặc operator. Gallery phân trang 10, loại ảnh ẩn và share thu hồi, độc lập hạn QR. Event Display có quy tắc riêng, feed mặc định 60 mục, JS poll mỗi 2,5 giây và thay ảnh theo ID. Media ưu tiên local. Nếu thiếu, có đường phục hồi Drive đã xác minh rồi ghi cache. |
| QR và tải ảnh | [qr-client.js](../frontend/src/services/qr-client.js) **generateQRCodeForCurrentPhoto**, **refreshPublicQR**; [sharing.py](../backend/app/services/sharing.py) **finalize**, **verify_public**, **lookup**; [guest.py](../backend/app/guest.py) **view_image**, **download**, **qr_image** | Sau ACK Confirm, tạo hoặc dùng lại share đúng composite. Host xác minh origin, isolation và fingerprint trước khi UI báo sẵn sàng. Hạn 24 giờ bắt đầu từ xác minh đầu, retry không gia hạn. Preview/download mặc định là PNG sạch. Route Gallery riêng. Share có expires_at NULL chưa phải bằng chứng đã phát hành, vì lookup vẫn có thể trả ảnh nếu token hợp lệ. P2 cần điều kiện đã phát hành riêng. |
| In / New Session | [print-client.js](../frontend/src/services/print-client.js) **triggerPrint**; [printing.py](../backend/app/services/printing.py) **enqueue**, **process_one**; [capture.js](../frontend/src/features/capture/capture.js) **startNewGuestSession** | Guest gửi final ID và số bản, nhận job rồi poll. Worker in kiểm tra hash, hạn QR và trạng thái thu hồi. New Session dọn UI, final và job còn trong Host. |

**Ranh giới Confirm đã có.** File PNG nháp có thể được viết trước /complete nhưng chỉ ảnh đã chốt, duyệt mới vào danh sách công khai. Điểm gắn cloud outbox là giao dịch complete khi đủ duyệt, hoặc giao dịch phê duyệt sau. Cloud worker hiện chưa có.

## 2. Mức sẵn sàng cloud và xung đột

| Mức | Bằng chứng và hệ quả |
|---|---|
| **Chặn** | **0/76 PNG đã chốt** còn tại đường dẫn local trong DB. **64** job Drive SYNCED và **12** final không có job Drive. SYNCED là trạng thái lịch sử, không chứng minh backup hiện đọc được. Gallery có thể liệt kê từ catalog dù media thiếu. Cần kiểm kê nguồn và quyền backfill trước P2. |
| **Chặn** | [public_main.py](../backend/app/public_main.py) chỉ gắn QR và Gallery. [public_gateway.py](../backend/app/services/public_gateway.py) kiểm tra ranh giới với Admin, Booth, camera, in và Event Display. Gateway hiện đọc SQLite/files của laptop; URL LAN hoặc Quick Tunnel không tồn tại độc lập khi laptop/tunnel tắt. |
| **Cao** | Confirm commit local trước nhưng UI còn đợi lần thử QR đầu khi busy. P2 cần tách ACK local khỏi ACK cloud, báo đã lưu/đang xuất bản và retry nền. Bản in QR hiện phụ thuộc HTTPS hợp lệ. Khi cloud lỗi, vẫn chụp, chốt và backup local; QR và bản in có QR chờ chính sách offline đã chọn. |
| **Cao** | Bỏ ảnh khỏi danh sách chưa đủ nếu dùng Blob public: URL trực tiếp có thể vẫn đọc được. Dùng private Blob và kiểm tra trạng thái duyệt/ẩn hoặc token/hạn ngay ở handler trước khi stream. QR 24 giờ có ích để giới hạn link cá nhân, nhưng khó tải hôm sau; P2 cân nhắc 72 giờ hoặc 7 ngày riêng với chính sách Gallery/thu hồi/lưu trữ. Giữ hạn hiện tại trong P1. |

**Giao diện tái sử dụng:** Gallery và Event Display có HTML/CSS/JS có thể đóng gói tĩnh. Gallery nhận preview_url, photo_url từ feed, nên giữ phân trang/lazy-loading và trả URL cloud cùng contract. Event Display có thể giữ một poll ngắn trả ID, kích thước và URL của các ảnh mới nhất. Nếu cần PIN công khai, triển khai quyền tương đương, không mở API cấp mã của Host. Trang QR hiện do FastAPI dựng, cần Function để tra token và phục vụ trang/ảnh/download. Các API Gallery feed/media, Event Display feed/media, QR status/download và publish/hide cần đọc catalog cloud. Admin, Booth, printer và camera vẫn nằm local. Dùng một bản PNG và một thumbnail cho cả ba mặt công khai.

**QR chọn A.** Cloud tạo token, ghi hash và trả URL HTTPS ổn định sau khi ảnh cùng catalog đã sẵn sàng. Laptop dùng bộ render QR hiện tại cho Booth/in. Retry cùng ID phải lấy lại đúng URL khi mất ACK. Cách B tạo cả SVG/PNG trên cloud cũng làm được nhưng thêm endpoint và phụ thuộc khi in, chưa cần cho 150 ảnh. Link Quick Tunnel đã phát không đổi được bằng cách chuyển catalog.

## 3. Drive và in Windows

- **Drive:** Folder đích cố định qua APPROVED_GOOGLE_DRIVE_FOLDER_ID trong [config.py](../backend/app/config.py). [drive_client.py](../backend/app/services/drive_client.py) và worker dùng backup riêng, kiểm tra quyền Restricted và checksum. Cloud worker dùng PNG local sau Confirm, độc lập với Drive. Trong audit không gọi upload, tái tạo cache hay làm mới OAuth.
- **Máy in:** [printers.py](../backend/app/services/printers.py) **WindowsPrinterAdapter** dùng pywin32, enum queue local, lọc máy ảo, báo offline/blocked. Dashboard chọn máy hoặc dùng mặc định Windows qua [printing_routes.py](../backend/app/printing_routes.py); Booth chọn số bản, mặc định 1–3. Probe chỉ đọc: pywin32 import được, Windows liệt kê 3 queue và adapter trả **0 queue hợp lệ** sau lọc. DB có **7 job mock submitted**. Với Windows, submitted chỉ chứng minh spooler nhận, không xác nhận giấy ra.
- **Khổ, lề và hướng:** Chưa có selector media, khổ, hướng hay preset 2×2/2×3 trong app. GDI dùng Printing Preferences của driver. Đọc HORZRES/VERTRES, căn giữa và scale contain trong vùng in được, không ép tỷ lệ hoặc recompress thành JPEG. Preview là bản in, chưa tính lề thực tế hay borderless. Không có danh sách khổ app hỗ trợ độc lập với driver.
- **Bản in:** [print_ready.py](../backend/app/services/print_ready.py) **ensure** dán composite lên PNG RGB, thêm chân trắng và QR. Nguồn thường 1800×1200 hoặc 1200×1800; mock trên đĩa có 1800×1608, 1200×2130 hoặc 1200×2154. Khoảng trắng trên giấy 3:2 sẽ khác nhau. Có thể retry job lỗi với cùng final, không cần ghép lại; job bất định cần đối soát spooler/giấy và xác nhận. QR hết hạn hoặc thu hồi có thể chặn retry.
- **Trước thử vật lý:** Cần model và queue/driver thật, khổ giấy mm, media/tray, hướng, DPI/vùng in được và borderless. Chọn Printing Preferences, kiểm tra preview cho hai loại ảnh, rồi khi được phép mới thử giấy và đo lề/độ lớn/khả năng quét QR. **Chưa sẵn sàng để thử vật lý trên laptop tại thời điểm audit.**

## 4. Dữ liệu và dung lượng Vercel Hobby

| Số liệu runtime | Kết quả |
|---|---|
| Final và publication | 76 final, 69 bản ghi công bố (68 duyệt, 1 ẩn), 7 chưa có bản ghi. 76 shares: 41 chưa có hạn, 27 hết hạn, 8 còn hạn lúc audit. Catalog không chứng minh tải được media. |
| Kích thước trong SQLite | 1800×1200: 41; 1200×800: 2; 1200×1800: 20; 1181×1772: 13. Định dạng PNG theo pipeline và đường dẫn, chưa đọc được nội dung file. |
| Dung lượng PNG đã chốt | 0/76 file tại đường dẫn đã ghi. **Không đo được trung bình, median, p95, max hay số file vượt 4,5 MB.** Hai mẫu từ lượt HTTPS trước là 3.275.985 và 3.029.387 B, chỉ dùng làm mốc giả định. |
| Thumbnail đã đo | 32 JPEG trong event_previews, cạnh dài 480 px: trung bình **27.811 B**, median **27.851,5 B**, p95 **42.118 B** (nearest rank), max **42.701 B**. Đây là cache Booth, không phải thumbnail Gallery 600 px. |

Mô hình giả định PNG **3,2 MB**, thumbnail **60 KB**, đơn vị thập phân và chưa trừ cache.

| Kịch bản | Kết quả |
|---|---:|
| 150 PNG + 150 thumbnail | **489 MB**. Nếu PNG trung bình 6 MB thì **909 MB**, nếu 7 MB thì **1.059 MB**. Trần 1 GB tương ứng ~6,61 MB/PNG trước overhead và phiên bản thừa. |
| Gallery ngày sự kiện: 120 người × 2 lượt × 50 thumbnail | **720 MB**, 12.000 lượt đọc thumbnail |
| QR: 120 người × (1 preview full + 1 download) | **768 MB** |
| Event Display: 1 màn hình, 4 giờ poll 2,5 giây | **5.760 request**, ~11,5 MB JSON nếu 2 KB/lượt, ~9 MB ảnh nếu tải mỗi thumbnail mới một lần |
| Tổng một ngày | **~1,51 GB**, chưa tính assets/HTTP hoặc click full từ Gallery |
| Sau sự kiện: 120 người × 5 lượt × 150 thumbnail, mỗi người thêm 6 lượt full | **7,70 GB**, cộng ngày sự kiện ~**9,21 GB** |
| Traffic mở rộng: 360 người × 3 lượt × 150 thumbnail, mỗi người thêm 2 lượt full | **12,02 GB** trước assets và lượt ngày sự kiện |

**Phán định quota:** Hobby có **1 GB Blob storage**, **10 GB Blob Transfer**, **10.000 Simple Operations**, **2.000 Advanced Operations**; Fast Data Transfer **100 GB** và Fast Origin Transfer đến **10 GB** là số đo riêng. Private Blob stream qua Function có cả lượt Blob→Function và Function→browser; cache MISS ảnh hưởng Origin Transfer và simple ops. Ngày sự kiện có thể vừa dung lượng nhưng riêng 12.000 lượt thumbnail đã vượt simple quota nếu phần lớn là MISS. Sau sự kiện ít dư địa và kịch bản mở rộng vượt Blob Transfer nếu đa số byte qua Blob. Poll 2,5 giây liên tục 30 ngày tạo ~1,04 triệu request, nên chỉ poll khi màn hình được dùng. Hobby có thể ngừng phục vụ khi chạm giới hạn. [Blob pricing](https://vercel.com/docs/vercel-blob/usage-and-pricing) · [Vercel limits](https://vercel.com/docs/limits) · [Hobby](https://vercel.com/docs/plans/hobby)

**Gói và DB:** Hobby chỉ dành cho mục đích cá nhân, phi thương mại; cần xác nhận sự kiện đủ điều kiện. Vercel xác nhận **10 GB Deployment Storage** là quota giữ artifact, không phải kho ảnh. Chưa xác nhận con số **10 GB Functions Storage** như quota riêng theo tài liệu đã kiểm tra. Neon Marketplace có gói từ $0; bảng giá Neon hiện ghi **1 GB DB/project và 100 CU-giờ/tháng** ở Free. Supabase Free **500 MB DB**, **5 GB egress uncached + 5 GB cached**, có thể pause sau một tuần ít hoạt động. Catalog 150 ảnh phù hợp về dung lượng DB. Cần xác nhận quota của đúng gói Marketplace trước khi tạo. [Deployment Storage](https://vercel.com/changelog/hobby-projects-now-retain-fewer-deployments-to-free-up-storage) · [Neon Marketplace](https://vercel.com/marketplace/neon) · [Neon pricing](https://neon.com/pricing) · [Supabase pricing](https://supabase.com/pricing)

**Ảnh lớn:** Functions mặc định nhận body tối đa **4,5 MB**; beta 20 MiB yêu cầu cấu hình Pro/Enterprise. Worker laptop xin token upload ngắn hạn từ endpoint xác thực, giới hạn key/định dạng/kích thước và gửi byte trực tiếp vào private Blob. Xác minh đối tượng và checksum trước khi ghi trạng thái published. Tải full qua Function theo dạng stream sau kiểm tra quyền. Giữ token Blob/DB/khóa publish phía server, không đưa vào bundle. [Functions limits](https://vercel.com/docs/functions/limitations) · [Client uploads](https://vercel.com/docs/vercel-blob/client-upload) · [Private Blob](https://vercel.com/docs/vercel-blob/private-storage)

## 5. Kiến trúc tối thiểu và thứ tự P2

**Windows** giữ Booth desktop, Sony, SQLite, Dashboard, Drive, in và worker publish. **Một project Vercel** phục vụ ba trang public và API tối thiểu, sử dụng **một private Blob + một Postgres**. Cloud không gọi ngược laptop. Khi publish thành công, Gallery/QR có thể làm việc khi laptop tắt. Khi cloud mất kết nối, tiếp tục chụp/chốt local; QR và in kèm QR đợi phục hồi.

1. Chốt quyền dùng Hobby, domain HTTPS, hạn QR/ảnh, quy tắc duyệt/thu hồi, và chính sách in offline. Kiểm kê hoặc khôi phục nguồn dưới quyền operator. Đo lại PNG p95/max và chỉ lên danh sách backfill được phép.
2. Định nghĩa catalog và API xác thực tối thiểu. Unique theo event/session/composite, lưu hash, trạng thái staged/published/hidden, timestamp, kích thước, key private và hạn/token. Kiểm tra quyền tại từng handler media; không mở route local.
3. Thêm outbox local cùng giao dịch Confirm/phê duyệt. Worker retry có backoff sau restart, upload PNG + một thumbnail, xác minh ACK và ghi SQLite. Dedupe callback/replay; hide/unpublish có version để retry cũ không hiện lại ảnh. Dọn staged mồ côi theo chính sách. Drive là queue riêng.
4. Nối Gallery, Event Display, Guest vào cùng catalog. Giữ lazy-load/phân trang, poll JSON ngắn/ETag, thumbnail trong grid và ảnh full khi xem/tải. Dùng QR A, tạo bản in local sau ACK khi cần QR.
5. Kiểm tra mất mạng, restart, tải >4,5 MB, quyền deny-by-default, revoke/hide qua cache, tắt laptop sau publish, điện thoại thật và băng thông theo số đo. Hiệu chỉnh printer riêng.

## 6. Trạng thái P1

**65/65 ca backend đạt** trong runtime thử riêng: printing, print-ready HTTPS, Drive storage, photo gallery, event display, QR readiness và async photo workflow. Các ca in dùng mock hoặc adapter GDI giả lập, không gửi job vật lý.

| Phân hệ | Kết quả |
|---|---|
| Booth desktop, 4/6 và Confirm | **PASS** theo mã và bằng chứng phần mềm giả lập. Sony/Live View/shutter vật lý **NOT VERIFIED** trong lượt audit. |
| Kho ảnh PNG local | **FAIL** · thiếu file cho 76/76 bản ghi tại đường dẫn catalog. |
| Drive queue và checksum | **PASS** phần mềm; khả năng đọc lại 64 backup và OAuth hiện tại **NOT VERIFIED**. |
| Gallery, Event Display, QR và download | **PASS** phần mềm cách ly; phục vụ ảnh thật từ runtime đang kiểm kê **NOT VERIFIED**. |
| Gateway | **PASS** theo phạm vi router và test cách ly; endpoint công khai live **NOT VERIFIED**. |
| Printer | **PASS** phần mềm mock/GDI giả lập. Model, media, lề và giấy thật **NOT VERIFIED**. |
| Cloud publish, quyền cloud, chạy khi tắt laptop | **NOT VERIFIED** · chưa implement/triển khai. |
