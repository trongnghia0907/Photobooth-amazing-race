# Restricted event-display exception — current Phase 6

The user authorized an intentional event projection feature, separate from the private Host Gallery and per-photo Guest QR page. Every photo is private-by-default until Host explicitly records a consent/authorization basis and confirmation for that official final. Hide/revoke affects only projection; final composite/QR/printing remain intact.

Display code/session hashes are in existing SQLite. A separate HttpOnly scoped cookie grants only approved display media/feed, never admin/session/camera/print APIs. Host controls retain authentication, mutation CSRF and laptop-only deployment checks. Unlock has custom-header protection and rate limiting. No share tokens or paths/download links enter the display feed. Public app/tunnel do not expose event-display.

Poll responses/media are no-store; connection errors/401 clear displayed photos, retry is automatic. Removal reaches a connected screen on the next poll, not instant recall of previously viewed pixels. Use an independent browser profile for projection and Extend mode for the projector so Host data/cookies are not shared with that window. [Full guide](EVENT_LIVE_GALLERY.md).

---

# Phase 6 current security boundary

Built deployment is a paired private kiosk, authenticated laptop-only Host, and separate token-scoped public photo app. Do not expose the development server or tunnel port 8000. Only photo-only loopback port 8001 may be selected for the public tunnel. Public app has no camera/print/cleanup workers, session/gallery APIs, admin UI or Swagger.

Kiosk requires HttpOnly SameSite Strict station cookie plus session owner token; mutation CSRF, station/session binding and operation rate limits apply. Pairing code is operator-controlled (minimum 16 characters), not a guest password; do not publish it. Secure cookies enabled in production; LAN HTTP is explicit development on a trusted network. No permissive CORS. Host has separate credentials, session cookie, CSRF and login limit, with real client loopback enforcement. Forwarded headers are accepted only by the explicit loopback-proxy launch option. Share links remain bearer access to one photo; preserve .share-key, do not log or post QR tokens.

Kiosk CSP allows legacy inline handlers/styles for compatibility; private static UI inserts camera labels as text, not HTML. Public Guest Page uses a nonce CSP, no-store/no-referrer/noindex. No environment, DB or runtime directories are mounted. Runtime directory and backup require operator-level filesystem protection. No secrets are supplied in source or CLI arguments; launch prompts read passwords/keys hidden. Public tunnel credentials/certificates must stay outside Git. Deployment examples contain only placeholders.

Upgrade migration 7 preserves existing pending/blocked photo cleanup, not deletion. New confirms still verify a durable final hash before deleting only owned temporary assets. Unconfirmed/interrupted sessions remain private and retained; no age-based deletion without an approved retention policy. New Session clears individual previews, custom text, filters, stickers, QR and saved image state. Browser reload of an unfinished session does not restore its canvases automatically: keep browser open for retry. See [event checklist](EVENT_DAY_CHECKLIST.md) and [runbook](WINDOWS_EVENT_GUIDE.md).

---

# Sharing boundary — Phase 3

Current schema 6 storage policy: individual shots/native JPGs are private temporary working assets; owner media access is closed after confirmation and Host photo routes never serve them. One official composite per session is pinned in session_finals; a trigger prevents new duplicate session shares. Cleanup journals only session-owned allowlisted paths and validates the final hash before any deletion. Failed/unconfirmed sessions retain working files for recovery. See PHOTO_STORAGE_LIFECYCLE.md for retry/restart and historical-link compatibility.

## Phase 4 boundary

Phase 5 adds owner-scoped host camera controls and native file delivery; all routes authenticate the session, enforce an exclusive camera lease, validate file membership/containment/hash, and never expose camera-original folders as static. Host adapter/arming/disconnect/fault configuration uses the same backend cookie/CSRF protection. No control via public share token. Camera guest control is opt-in; use a trusted booth network until kiosk enrollment/public routing exists. No physical camera or network/firewall is opened automatically. Preview bytes are separate from captured-file ingestion; legacy upload callers cannot set source=camera_original. Native originals and capture journal are included in runtime backup/retention scope; uncertain commands are not auto-retried.

Guest `/p/token` now serves the immutable print-ready derivative with embedded QR, identical to the printer input. Original composites stay private; tokens remain scoped to one final. Existing link tokens never rotate during reprint/backfill. No runtime/static directory mount.

`/admin` exposes only a login shell. All `/api/admin/*` data/image/action endpoints require backend cookie authentication (login excepted). ENV credentials only, no defaults; password minimum 12, PBKDF2-SHA256 600000 with random salt stored at rest. Cookie token hash only in SQLite, HttpOnly/SameSite Strict, Secure outside development, 8h expiry. Rotation invalidates sessions; logout revokes session server-side. CSRF header required on authenticated mutations; login requires custom header and JSON; no permissive CORS. Login throttled 5 attempts/min/client IP. Host images validate session membership and resolved storage containment. UI inserts data via textContent.

Owner print mutations require session bearer + idempotency key; guest share token cannot list gallery/jobs or reprint. Print paths come only from DB, integrity checked before enqueue/dispatch. Mock default; real Windows requires explicit mode, flag and host-selected printer. Ambiguous failures never automatically reprint. Backup now includes print-ready, queue and admin DB state. See [hardware compatibility](HARDWARE_COMPATIBILITY.md) for hardware limits.

**Cập nhật yêu cầu QR localhost:** APP_ENV mặc định production vẫn giữ HTTPS public policy. Chỉ development + origin localhost/loopback hợp lệ được HTTP local; không arbitrary HTTP/LAN. Metadata local_only và cảnh báo UI bắt buộc, không coi là link điện thoại/public. Không thay auth/token/file isolation hoặc điều kiện complete trước share. Chạy helper local không expose server ra Internet.

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
