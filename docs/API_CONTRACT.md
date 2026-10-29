# API contract — Phase 2

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
