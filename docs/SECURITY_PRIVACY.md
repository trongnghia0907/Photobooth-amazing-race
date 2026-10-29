# Sharing boundary — Phase 3

- Session API dùng credential scoped session. Public share token không thay thế session credential.
- Mỗi confirmed composite có một share row. Random nonce 256-bit + HMAC-SHA256(secret riêng, nonce/composite UUID) tạo token 256-bit URL-safe. DB lưu hash/nonce, không raw bearer token; ACK cache chỉ giữ tham chiếu. Secret 32 byte nằm runtime/.share-key, cần backup cùng DB.
- Owner snapshot/replay tái dựng URL; public lookup dùng hash. Retry/render không rotate token; unique composite_id ngăn share trùng kể cả key mới.
- Page/image/download/QR đều kiểm tra token; invalid/expired/revoked/missing file trả 404. Không lookup ID ảnh khác từ query, không directory listing. Guest HTML không chứa session IDs, gallery/admin links hoặc booth controls.
- File composite là immutable revision. Chỉnh/retake tạo revision mới, link cũ vẫn trả ảnh cũ. QR chưa overlay/print-ready, theo yêu cầu defer sang Phase 4.
- Chỉ issue link mới khi PUBLIC_BASE_URL là origin HTTPS public hợp lệ. Không dùng Host header để tạo URL. Empty/local/private/credentials/path/query URL bị từ chối; cú pháp hợp lệ không chứng minh domain online.
- Page dùng CSP nonce, no-store, noindex/nofollow, no-referrer. Ảnh/download cùng privacy headers. Uvicorn access log redacts /p/token. Proxy/tunnel tương lai cũng cần redact bearer URL trong access logs.
- Ai có link có thể chia sẻ link đó; không cam kết xác thực danh tính. Rate limits, admin auth, kiosk enrollment/retention UI chưa thuộc Phase 3.
- Schema hỗ trợ revoked_at/expires_at và server kiểm tra; mặc định không đặt policy thời hạn thay tổ chức. Chưa có UI quản lý thu hồi/expiry.
- Không mount runtime thành static. Không commit .env, DB, .share-key, ảnh khách/uploads. Screenshots/tests chỉ dùng fixture.
- Backup thủ công cần bản nhất quán (dừng backend trước khi copy nếu chưa có SQLite backup tool). Không xóa .share-key để sửa lỗi; phải khôi phục key gốc. Chưa có backup/cleanup worker.
