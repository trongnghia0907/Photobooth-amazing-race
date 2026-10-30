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
