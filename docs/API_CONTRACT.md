# Phase 6 Event Live Gallery API (schema 8)

Private app only. Public-photo app never registers these routes.

| Method / route | Permission / behavior |
|---|---|
| GET /event-display | Static login/presentation shell, no photo data |
| POST /event-display/unlock | JSON {code}, X-OSA-Display: 1, 5 attempts/min/IP, independent 12h HttpOnly cookie |
| POST /event-display/lock | Display cookie + custom header; revoke this display session |
| GET /event-display/api/photos?limit=60 | Display cookie; 1..100 limit; approved official finals only |
| GET /event-display/media/{display_id} | Display cookie + current approval; original final PNG only, no download route |
| GET /api/admin/event-display/status | Existing authenticated Host; enabled + approved_count |
| POST /api/admin/event-display/access | Host + CSRF; rotate code and revoke every display cookie, return new code once |
| POST /api/admin/event-display/access/revoke | Host + CSRF; disable display access without deleting photos/approvals |
| PUT /api/admin/event-display/photos/{sid} | Host + CSRF; JSON approved:true requires approval_basis guest_consent/event_authorization and consent_confirmed:true; approved:false hides only |

Display feed item fields: id (independent UUID), image_url (protected display media), width, height, approved_at. No session ID, share token, storage path, owner credentials or download URL. Host session list adds display_approved; detail adds event_display approval state. Responses are no-store; production cookie Secure, Path=/event-display, SameSite Strict. Bad/expired display access 401, hidden/missing media 404, invalid final 409, missing consent 422. No permissive CORS. See [privacy/lifecycle and operator guide](EVENT_LIVE_GALLERY.md).

---

# Phase 6 deployment additions (current)

When OSA_FRONTEND_DIST is set, `/` and `/booth` serve built files, `/assets` serves only the built assets directory, and Swagger/OpenAPI are disabled. No wildcard SPA fallback. GET `/api/booth/me` returns pairing requirement and station CSRF after authentication. POST `/api/booth/pair` takes `{key}` and `X-OSA-Pair: 1`; successful pairing sets `osa_booth` HttpOnly/SameSite=Strict cookie (Secure in production), valid 12h. POST `/api/booth/logout` requires `X-Booth-CSRF` and expires station access.

All session and print-config endpoints in built deployment require the station cookie; session creation binds the existing owner token's session to that station. Every mutation also requires X-Booth-CSRF. Session routes additionally retain Authorization Bearer owner and operation Idempotency-Key requirements. Another station cannot access a session even with its owner token. Pairing/session/capture/print creation have bounded per-process rate limits. Production rejects the development photo-upload path; host adapters save original files internally.

Host routes additionally require an actual loopback client and existing Host authentication/CSRF. Default admin gallery includes only official completed sessions; `include_working=true` exposes private recovery metadata to authenticated Host, never temporary images. Public `app.public_main:app` only serves `/p/{token}` subresources and minimal `/healthz`; no admin, API, booth, static storage or hardware workers. The tunnel config restricts even health from public routing.

Sharing metadata adds `lan_only`. RFC1918 HTTP origins require APP_ENV=development and ALLOW_LAN_HTTP=true, independent from explicit localhost sharing; UI/print footer clearly label LAN. Production requires HTTPS. Previously issued URLs are pinned. Migration 7 retains pre-upgrade pending cleanup as retained_legacy; only newly confirmed sessions clean temporary files automatically. See [Windows guide](WINDOWS_EVENT_GUIDE.md) and [audit](PHASE0_6_VERIFICATION.md). Earlier API notes below remain applicable except where superseded here.

---

# API contract — Phase 2

## Current storage clarification — schema 6

`complete` is the irreversible application confirmation boundary for a session's one official composite. It commits `session_finals` plus a durable temporary-file cleanup queue only after final file/hash/current-shot checks. Snapshots add finalized boolean and cleanup_status (working/pending/complete/blocked/retained_legacy). Successful confirmation can return even when deletion is blocked; saved final and QR remain usable. Retry complete/finalize never creates a different official composite/share. Post-confirmation photo upload/delete/new composite/camera connect/new shutter return 409; start another session for another photo. Published legacy links remain read-only for compatibility.

Owner photos and camera original endpoints return 410 after confirmation. Host photo routes return 404; gallery/detail/image endpoints only expose the official composite and print-ready version (no working shots/drafts). Host photos/composites counts represent official finals. Working files are private and retained for recovery until confirmation commits; then checked-path deletion is journaled and retried after restart. Full lifecycle and legacy retention policy: [PHOTO_STORAGE_LIFECYCLE](PHOTO_STORAGE_LIFECYCLE.md). Earlier per-revision sharing/edit-after-complete notes below are historical.

## Phase 5 — host camera (schema 5)

All session camera endpoints require the existing Authorization Bearer owner credential. No query-string tokens, arbitrary device path, file name or preview-image upload is accepted. Guest share tokens cannot control the camera. Public creation of a session is not a trusted kiosk enrollment mechanism; guest camera control defaults disabled and must only be armed on the trusted booth deployment.

| Method | Path | Contract |
|---|---|---|
| GET | `/api/sessions/{sid}/camera/status` | Owner; state/connection/capabilities/freshness/errors, no other session ID |
| POST | `/api/sessions/{sid}/camera/connect` | Owner; claim session lease and explicitly connect host adapter |
| POST | `/api/sessions/{sid}/camera/disconnect` | Owner; stop Live View/disconnect/release; busy capture → 409 |
| POST | `/api/sessions/{sid}/camera/live-view/start` or `/stop` | Owner + session lease; enable/disable preview |
| GET | `/api/sessions/{sid}/camera/frame` | Owner + lease; JPEG, no-store, X-Frame-Sequence/X-Frame-Time; stale/missing → error |
| POST | `/api/sessions/{sid}/camera/captures` | Owner + Idempotency-Key; JSON slot_index strict integer ONLY; no image/screenshots |
| GET | `/api/sessions/{sid}/camera/captures/{capture_id}` | Owner; capture metadata + saved ACK snapshot when captured |
| GET | `/api/sessions/{sid}/camera/captures/{capture_id}/original` | Owner; exact native transferred JPEG/PNG/WebP; private, validates path/hash/membership |
| GET | `/api/admin/camera` | Host cookie; adapters/current state/capabilities/error/guest arming |
| PUT | `/api/admin/camera/config` | Host cookie+CSRF; optional adapter mock/uvc_demo/vendor and guest_enabled bool; active session must disconnect first |
| POST | `/api/admin/camera/disconnect` | Host cookie+CSRF; controlled release (refuses during capture) |
| POST | `/api/admin/camera/mock-failure` | Host cookie+CSRF; development + CAMERA_ALLOW_FAULTS + Mock only; failure timeout/capture/transfer/disconnect/stale_preview or null |

Capture response `{capture,session}`. capture metadata includes id/session_id/slot_index/adapter_mode/status/photo_id/native_sha256/mime/error_code/error_message/uncertain/timestamps, never filesystem paths. session is the saved snapshot from the corresponding photo operation. Replay returns the same capture/photo even after disconnect/restart. Wrong slot for same key → 409. Native original and normalized PNG are separate; existing photos endpoint provides normalized PNG for editor. A camera-original provenance cannot be supplied through the legacy upload API.

Journal states: capturing → transferring → captured; safe capture failure → failed; transfer/storage failure → transfer_failed (same key resumes transfer/reference/file, no shutter). Interrupted capturing becomes failed/uncertain; no automatic new shutter. Revision mismatch keeps the native file but does not overwrite a changed slot. Capture/provenance/capability errors preserve old photos and counter.

CameraError JSON: error.code/message/stage/uncertain/capture_id. Busy/disabled/lease mismatch → 409; unsupported/disconnected/stale/transfer → 503; timeout → 504. Authentication remains 401/404; malformed payload/extra preview image → 422. Missing/expired stream frames are not successful live-view receipts. Camera health is distinct from backend health; `/api/health` phase=5 is not hardware verification.

Camera implementation requires a single Uvicorn worker; an OS lease prevents separate processes from issuing overlapping device commands. Lease expiry disconnects an abandoned session; captures hold exclusive ownership until completion. Preview is short same-origin authenticated JPEG polling (~5fps nominal), not a public device stream. Native SDK adapters must respect deadlines and retain durable capture references; existing vendor placeholder is blocked, not a fake real-camera implementation.

## Phase 4 — schema 4 (retained endpoints)

Existing routes retained. Finalize now atomically creates a separate print-ready PNG after QR; response `share.qr_embedded=true`, `share.print_ready={sha256,width,height,source_height,qr_x,qr_y,qr_size}`. Public image/download paths unchanged, now return that PNG (original composite remains owner/admin-only). Reprint keeps share/token unchanged. Existing Phase 3 shares backfill derivative once on finalize/guest lookup. A print-ready render failure rolls back finalize, retaining previously completed original.

| Method | Path | Authorization / input |
|---|---|---|
| GET | `/api/print-config` | Public mode/max_copies/available/message, no gallery/device paths |
| POST | `/api/sessions/{sid}/print-jobs` | Session bearer + Idempotency-Key; JSON final_id UUID, copies integer 1..MAX_PRINT_COPIES |
| GET | `/api/sessions/{sid}/print-jobs/{job_id}` | Same session bearer; other session/owner → 404 |
| POST | `/api/admin/login` | X-OSA-Login: 1 + JSON username/password; ENV account, returns csrf_token, sets HttpOnly cookie |
| GET | `/api/admin/me` | Host cookie; username/csrf_token |
| POST | `/api/admin/logout` | Host cookie + X-CSRF-Token; revoke/delete cookie |
| GET | `/api/admin/status` | Host cookie; backend/counts/printer config |
| GET | `/api/admin/sessions?limit=20&offset=0` | Host cookie; paged records, total; max limit 100 |
| GET | `/api/admin/sessions/{sid}` | Host cookie; metadata/all composite revisions, protected preview/download paths |
| GET | `/api/admin/sessions/{sid}/images/{kind}/{id}?download=true` | Host cookie; kind photos/composites/print_ready; membership + path containment validation |
| GET | `/api/admin/print-jobs?limit=50&offset=0` | Host cookie; newest first, max limit 100 |
| POST | `/api/admin/print-jobs` | Host cookie + CSRF + Idempotency-Key; JSON session_id,final_id,copies; explicit reprint |
| POST | `/api/admin/print-jobs/{id}/retry` | Host cookie + CSRF + Idempotency-Key; JSON acknowledge_uncertain bool; failed only, creates new job with retry_of |
| POST | `/api/admin/print-jobs/{id}/cancel` | Host cookie + CSRF; queued only, other state → 409 |
| GET | `/api/admin/printers` | Host cookie; driver list/selection/mode |
| PUT | `/api/admin/printers/selected` | Host cookie + CSRF; JSON printer_id from adapter list |

Job JSON: id,session_id,final_id,copies,status,mode,printer_id,retry_of,error_message,uncertain,created_at,updated_at,physical_print_confirmed=false, optional receipt. Never returns filesystem paths/passwords/owner hashes. `queued → processing → submitted/failed`, queued can cancel. `submitted` is spool/mock receipt, **not proof of paper output**. Retry old processing after process death never automatic; failed/uncertain needs explicit Host acknowledgement. Jobs and idempotency persist in SQLite across restart. HTTP retry same key/payload returns same job; changed payload → 409. Missing/corrupt/unconfirmed print-ready → 409; printer unavailable → 503; invalid copies → 422.

Admin API missing/expired cookie → 401, CSRF missing on mutations → 403, login unset/short ENV password → 503 with configuration message, failed credentials → 401, repeated login → 429. Login shell `/admin` has no sensitive data and no gallery before authentication; assets fixed whitelist. Cookie Path=/api/admin, 8h, SameSite Strict, Secure in production; no permissive CORS.

## Sửa QR local development

Settings mới `APP_ENV` mặc định production. Production giữ HTTPS public-only. Development cho phép origin HTTP/HTTPS localhost/loopback chuẩn để test cùng máy; không cho phép arbitrary HTTP/private LAN. Vẫn phải complete/file lưu thành công trước finalize.

Health thêm `sharing` gồm configured/app_env/base_url/local_only/message; dùng để chẩn đoán PUBLIC_BASE_URL thiếu/sai và mode đang chạy. Share descriptor thêm `local_only` từ origin đã pin. Frontend chỉ nhận HTTP loopback có flag local_only, hiển thị cảnh báo không dùng trên điện thoại khác; QR ready sau PNG onload.

Chạy `python scripts/run_local_backend.py` từ root để đặt APP_ENV=development, PUBLIC_BASE_URL=http://localhost:8000 cho process con. Không tự load .env, không mở gallery/tunnel, không rotate share cũ. Những ghi chú “localhost luôn bị từ chối” ở phần lịch sử bên dưới nay chỉ áp dụng production.

## Bổ sung Phase 3 — schema 3

`POST /api/sessions/{session_id}/finalize`: JSON `{"composite_id":"UUID"}`, cùng owner Authorization/Idempotency-Key. Chỉ nhận current composite đã complete (chưa xác nhận → 409). PUBLIC_BASE_URL phải origin HTTPS public hợp lệ; trống/local/private/placeholder/path/query/credentials → 503, ảnh đã lưu vẫn giữ.

Response là owner snapshot kèm `share`: final_id, composite_id, share_url, qr_image_url, image_url, download_url, qr_embedded=false. Unique composite_id đảm bảo key mới cũng không tạo token/PNG trùng. Không upload composite ở finalize. URL/QR pin theo final; đổi cấu hình không tự đổi link đã cấp.

| Method | Public path | Kết quả |
|---|---|---|
| GET | `/p/{token}` | Mobile HTML một ảnh + Download; invalid/missing file → HTML 404 |
| GET | `/p/{token}/image` | Đúng confirmed composite PNG |
| GET | `/p/{token}/download` | Cùng PNG, attachment filename server-generated |
| GET | `/p/{token}/qr.png` | PNG QR chứa chính share_url |

Tất cả verify token hash/revocation/expiry; không nhận ID ảnh khác từ query/listing. Headers no-store/noindex/no-referrer/nosniff; page CSP nonce. Chỉ phục vụ immutable composite, không raw. Chưa overlay QR, theo yêu cầu mới defer Phase 4.

Migration 002 tạo shares; 003 loại bearer URL khỏi ACK cache, giữ composite reference và tái dựng metadata cho owner khi replay. Token derive HMAC(secret 32 byte runtime/.share-key, random nonce + composite UUID); DB chỉ lưu hash/nonce. Link giữ qua restart, không rotate. Key mất/sai → 503 cho owner reconstruction, không tự sinh key thay thế. Backup key, không commit.

Endpoints Phase 2 bên dưới vẫn giữ contract; health hiện phase=3, snapshots có thể thêm share. Các ghi chú “chưa có share” bên dưới ghi nhận baseline Phase 2.

Prefix `/api` theo yêu cầu mới, thay `/api/v1` dự kiến trong technical spec. JSON thành công trả HTTP **200**, kể cả replay. Không có public gallery/share/admin/printer/camera SDK API.

## Auth và idempotency

Frontend dùng Web Crypto tạo token ngẫu nhiên 256-bit, giữ trong RAM. Backend chỉ lưu SHA-256. Mọi session endpoint kể cả create yêu cầu:

```http
Authorization: Bearer <32-128 ký tự an toàn A-Z a-z 0-9 _ ->
Idempotency-Key: <16-128 ký tự an toàn A-Z a-z 0-9 _ ->
```

GET không cần Idempotency-Key. Frontend thực tế dùng token hex 64 ký tự và key UUID. Create key scoped theo token, cùng key/body trả cùng session ID. Mutations scoped theo session, fingerprint gồm action, slot/source, hash byte ảnh đầu vào/JSON. Cùng key/payload trả ACK cũ, không tạo file/revision mới; khác payload trả 409. Retake có chủ đích dùng key mới. GET session để lấy trạng thái mới nhất thay vì đọc ACK replay cũ.

Đây là credential theo possession, chưa có admin/kiosk enrollment/rate limit. Backend bind loopback trong Phase 2. Thiếu/sai cú pháp token trả 401; sai token với session hoặc ID lạ trả 404, không lộ sự tồn tại.

## Endpoints

| Method | Path | Request / chức năng |
|---|---|---|
| GET | `/api/health` | Không auth; liveness DB, phase/modes |
| POST | `/api/sessions` | JSON layout/slot_count + auth/key; create/replay |
| GET | `/api/sessions/{session_id}` | Auth; snapshot session |
| POST | `/api/sessions/{session_id}/photos` | Multipart + auth/key; upload/retake slot |
| DELETE | `/api/sessions/{session_id}/photos/{slot_index}` | Auth/key; xóa active slot |
| DELETE | `/api/sessions/{session_id}/photos` | Auth/key; reset active slots |
| PUT | `/api/sessions/{session_id}/composite` | Multipart + auth/key; lưu composite |
| POST | `/api/sessions/{session_id}/complete` | JSON composite_id + auth/key; complete |
| GET | `/api/sessions/{session_id}/photos/{photo_id}/image` | Auth; private PNG |
| GET | `/api/sessions/{session_id}/composites/{composite_id}/image` | Auth; private composite |

IDs phải UUID; không nhận filesystem path. Metadata không chứa owner hashes, token, đường dẫn file hoặc dữ liệu session khác. File cũ không bị xóa khi retake/reset; active pointers được cập nhật.

### Create

```json
{"layout":"grid2x3","slot_count":6}
```

`grid2x3`/`grid3x2` dùng 6; `landscape_4` dùng 4. Backend hỗ trợ 4/6, frontend vẫn giữ UI sáu ảnh, không sửa Frame Editor.

### Photo multipart

- `slot_index`: 0-based, trong [0, slot_count-1], tối đa 5.
- `source`: `demo`, `webcam_frame`, `manual_upload`; từ chối physical shutter/real.
- `file`: PNG/JPEG/WebP; kiểm tra MIME lẫn decode bằng Pillow.

Upload tạo revision/file mới, tăng `shots_revision` và vô hiệu active composite. Xóa/reset cũng tăng shots_revision. Status → capturing hoặc editing khi đủ ảnh.

### Composite multipart

- `file`: ảnh composite hợp lệ.
- `shots_revision`: revision frontend nhận sau lưu slots, phải khớp backend.
- `editor_json`: object JSON tối đa 32.000 ký tự, mặc định `{}`. Không chứa binary.

Thiếu ảnh hoặc revision stale trả 409. Frontend chỉ gọi khi xác nhận; thay filter/frame/sticker không gọi endpoint này.

### Complete

```json
{"composite_id":"UUID của composite hiện tại"}
```

Kiểm tra composite đúng session/current shots và tất cả files tồn tại rồi mới chuyển completed. File đã commit bị mất → 409 và status failed. Lỗi upload tạm thời không xóa slot cũ. Chưa có QR/share/print-ready.

Phase 2 cho phép chỉnh lại session completed: shots mới → capturing/editing; composite mới → editing rồi complete. File revisions bất biến, session có thể đổi active revision. Phase 3 sẽ chốt final-photo/share immutability riêng.

## Snapshot

```json
{
  "session_id":"UUID","status":"editing","layout":"grid2x3","slot_count":6,
  "shots_revision":6,"created_at":"UTC ISO8601","updated_at":"UTC ISO8601",
  "photos":[{"id":"UUID","slot_index":0,"revision":1,"source":"demo",
    "sha256":"PNG checksum","width":960,"height":720,"created_at":"UTC ISO8601"}],
  "composite":null
}
```

Photos chỉ active slots, sort theo slot_index. Composite metadata có id/revision/shots_revision/sha256/width/height/created_at. Image response gửi no-store, noindex/nofollow, nosniff.

## Storage và errors

Mặc định 10 MiB/file, 24 triệu pixel, tổng request giới hạn file limit + 64 KiB multipart overhead kể cả chunked. Từ chối corrupt/unsupported/image bomb. Normalize PNG, áp EXIF orientation rồi bỏ metadata. Tên file khách không dùng tạo path; server sinh UUID dưới storage root pathlib.

SQLite WAL/foreign keys/busy timeout, schema `PRAGMA user_version=1`. Write transaction BEGIN IMMEDIATE; ghi temp → flush/fsync → atomic replace → DB commit. File/DB lỗi rollback, dọn file mới và giữ active pointer cũ. Process chết giữa rename và commit có thể để orphan file private; chưa có reconcile/retention/backup worker.

```json
{"error":{"code":"503","message":"Không thể lưu dữ liệu. Hãy kiểm tra ổ đĩa và thử lại."}}
```

| HTTP | Ý nghĩa |
|---|---|
| 401 / 404 | Credential thiếu/sai; session/ảnh không có quyền hoặc không tồn tại |
| 409 | Key dùng với payload khác; thiếu/stale shots/composite; mất file đã lưu |
| 413 | Vượt file/pixel/request limit |
| 415 / 422 | MIME không hỗ trợ; UUID/slot/source/JSON/file không hợp lệ |
| 503 | File system/SQLite lỗi; không trả success |

Errors không echo body/token/stack trace/absolute path. Không mount runtime hay bật CORS rộng; frontend dùng Vite same-origin proxy.

## Smoke API PowerShell

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
$token = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
$headers = @{ Authorization = "Bearer $token"; 'Idempotency-Key' = [guid]::NewGuid().ToString() }
$session = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/sessions -Headers $headers -ContentType 'application/json' -Body '{"layout":"grid2x3","slot_count":6}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/sessions/$($session.session_id)" -Headers @{Authorization="Bearer $token"}
```

OpenAPI `/docs` mô tả multipart/header fields. Các tests backend/frontend kiểm tra upload/retake/complete/retry. Reload browser mất credential; chưa có resume/enrollment/rotation UI.
