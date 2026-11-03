# AMAZING RACE 2026 — Event-day operator checklist

Record operator, date/time, host OS/version/CPU, camera model/firmware/SDK, printer/driver/paper, iPad/browser, network and evidence. Physical acceptance is **NOT TESTED** until an operator records actual results. Windows is primary; macOS/Linux need their own acceptance run.

## Before opening

- [ ] Host on mains power; charger/cables secured; sleep/screensaver/update policy prepared; sufficient disk space above reserve and a realistic event storage budget.
- [ ] Correct config file and runtime selected; backup verified; credentials and private certificates protected. Never reset/delete runtime to fix a startup problem.
- [ ] Validate configuration with `run_host.py --env-file ... --check --no-prompt`; start the built host app with the appropriate platform script. Check only one server/camera controller/print worker owns this runtime.
- [ ] Confirm Event vs rehearsal mode in Host Dashboard. Rehearsal is visibly marked. Event cannot use Mock/UVC frames as real shutter capture, and cannot use MockPrinter as physical output.
- [ ] Router/Wi-Fi and Internet ready; host DHCP reservation/IP and firewall correct; real iPad can reach the printed private HTTPS URL and trusts its certificate. Admin stays local to the host.
- [ ] Actual supported camera connected; verify model, SDK/OS/architecture and permissions. Check fresh Live Preview, one physical shutter per command and original JPG transfer, resolution/orientation/hash and correct slot.
- [ ] Perform both a four-photo and six-photo session, retake one slot, review filters/stickers/frame and confirm exactly one final composite. Do not auto-finalize a guest's unconfirmed image.
- [ ] Selected physical printer/driver/paper/copy limit correct; operator authorizes one controlled test print. Check all photos, margins, orientation and QR. `submitted` alone does not prove paper printed.
- [ ] Public photo gateway and intentionally configured stable HTTPS tunnel reachable. Test printed/screen QR over 4G/5G and event Wi-Fi, direct navigation, refresh and image download. Verify it opens only that session's final photo.
- [ ] Verify public origin returns 404 for booth/admin/API/storage/event-display routes; no database, log, credentials or private Host Gallery are exposed.
- [ ] Pair kiosk; open Host Dashboard; issue separate projector code. Approve an image only with recorded consent/authorization. Verify sidebar/projector update, newest composite order and hide without deleting the original.
- [ ] Hide any previously approved rehearsal images from event display; do not delete completed guest photos as part of mode switching.
- [ ] Projector/LED physically connected as extended display; verify 16:9 wall/slideshow/fullscreen, brightness, orientation and readable title; keep Host controls on laptop.
- [ ] Reload an unconfirmed kiosk session and verify saved captures return for review; reload a final session and verify the same composite/QR. New Session clears guest state while approved event photos remain.
- [ ] Test safe camera/printer/Wi-Fi recovery with the real devices and inspect uncertain jobs before any retry. Complete all mandatory hardware/network acceptance below before marking physical event GO.

## During the event

- [ ] Monitor Host camera status, free disk space, print queue and private rotating logs. Keep camera/software permissions and the intended USB connection stable.
- [ ] Check public QR download and projector/sidebar updates regularly. Do not claim Internet downloads work while connectivity is unavailable.
- [ ] Keep the guest flow continuous; let guests confirm the composite. Do not discard unconfirmed work for idle timeout, cleanup, printer failure or a new guest.
- [ ] If transfer/save fails, retain the original request key and use explicit retry. Never send a second shutter command or print merely because an ACK was lost.
- [ ] If print status is uncertain, check spooler/CUPS and paper before authorizing a retry. Capture, review and final photo storage should continue when printing is unavailable.
- [ ] Restart only through the configured runtime's safe stop/start procedure, after checking active capture/transfer/print work. Keep runtime, public hostname and secrets stable.
- [ ] Hide a photo promptly if display consent is withdrawn; restrict Host access and keep approval decisions with authorized staff.

## After the event

- [ ] Stop accepting new sessions; resolve active image transfers and confirm final photo saves.
- [ ] Finish/check pending print jobs; record uncertain/failed jobs and actual paper before shutdown. Do not auto-reprint.
- [ ] Close projector display and revoke its code. Stop the authorized public tunnel deliberately.
- [ ] Stop the supervised app using the matching config/runtime; verify processes have exited.
- [ ] Create a new offline backup containing SQLite, completed composites, QR/print-ready files and `.share-key`; verify every manifest hash and protect backup/configuration secrets.
- [ ] Record final session/composite/job counts, disk usage, failures and operator actions. Retain/delete photos and unfinished sources only under the event organization's approved retention policy.
- [ ] On another laptop, restore to a new runtime directory and repeat startup/camera/printing/network acceptance; preserve old data and stable public QR hostname.

## Projector and hardware evidence

# Event Live Gallery — additional venue checks

Software has automated 16:9 wall/slideshow/fullscreen, consent/isolation/hide/reconnect/restart coverage. The following physical checks remain NOT TESTED:

- Real projector/LED: resolution 16:9, brightness, photo orientation/letterboxing, readable title, HDMI/USB-C and Windows Extend mode.
- Host stays on laptop; display uses a separate browser profile and independent display code.
- Approve only with actual consent/authorization; test one 4-photo and one 6-photo final, then hide one without losing QR.
- Leave display open and prove new approved image appears automatically; unplug network briefly and verify photos clear/recover.
- Test code rotation/revocation on every real screen; close projection and revoke access at event end.

[Operator instructions](EVENT_LIVE_GALLERY.md). Existing hardware/event checks below remain required.

---

# Event-Day / Hardware Acceptance — chưa đánh dấu PASS

Ghi ngày, người thử, thiết bị/model/firmware/SDK, browser/OS, mạng, printer/driver/khổ giấy và bằng chứng cho mỗi mục. Tất cả mục vật lý dưới đây hiện **NOT TESTED**.

| Kiểm tra tại sự kiện | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|
| iPad thật landscape/portrait + Safari | 75/25, zoom/touch, fullscreen CSS, browser chrome không che nút | NOT TESTED |
| Live View camera thật | Độ trễ đo được, không giãn hình, ngắt USB không hiển thị frame cũ | NOT TESTED |
| Shutter + original JPG | SDK hỗ trợ model, một lệnh một ảnh, JPG gốc đủ độ phân giải, đúng slot/hash | NOT TESTED |
| Chuỗi 6 và 4 ảnh + retake | Chờ file xong mới bước tiếp; retake đúng slot | NOT TESTED |
| Máy in Windows thật | Chọn đúng driver, số bản, giấy, margin, hướng, không cắt slot/QR | NOT TESTED |
| QR trên giấy | Camera điện thoại quét được, tải đúng composite | NOT TESTED |
| LAN Wi-Fi | iPad chụp; điện thoại cùng Wi-Fi mở QR; admin trên iPad bị chặn | NOT TESTED |
| Public HTTPS + điện thoại 4G/5G | Certificate hợp lệ, direct/refresh/download; admin/API/booth public đều 404 | NOT TESTED |
| Rớt Wi-Fi/camera/printer | Hiện lỗi rõ, retry không chụp/in trùng; không mất ảnh đã chốt | NOT TESTED |
| Restart laptop | Cùng runtime và secrets, cả hai QR cũ tải đúng ảnh, gallery/queue còn | NOT TESTED |

Trước mở cửa: backup offline có `.share-key`, đủ dung lượng, nguồn điện/sleep, DHCP reservation, firewall Private, đúng hostname trước chốt ảnh; ghép kiosk; Host password riêng; thử 6+retake và 4; đối chiếu một composite/một token; nguồn tạm chỉ dọn sau final ACK. Kiểm tra không lộ ảnh khách trước qua Phiên mới.

Sau đóng cửa: chờ capture/transfer/print, xác minh job uncertain trên giấy, dừng tunnel chủ động, dừng host, backup offline mới, kiểm tra manifest. Không xóa originals của phiên gián đoạn tự động: chưa có chính sách retention được duyệt. Giữ backup/photo theo chính sách tổ chức.

**NO-GO cho sự kiện vật lý** cho đến khi tất cả mục thiết bị/mạng bắt buộc được kiểm chứng. Camera model/SDK hiện còn chưa xác nhận; Mock PASS không thay cho hardware PASS.
