"""Refresh source-to-module documentation without modifying application code."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
functions=json.loads((root/'docs/function-map.json').read_text(encoding='utf-8'))
descriptions='''
init|Khởi tạo grids, editor, drag listeners và preview
initCameraDevices|Kiểm tra media API, khởi tạo preview và camera selectors
refreshCameraList|Liệt kê video inputs và thêm lựa chọn camera mô phỏng
selectCameraDevice|Chuyển nguồn preview thật hoặc mô phỏng
requestRealCameraPermission|Xin quyền video preview và cập nhật selectors
startCameraStream|Mở getUserMedia với constraints/fallback demo
attachRealStreamToVideo|Gắn stream vào video, play và lấy deviceId
stopCurrentStreams|Dừng tracks và animation loop của preview
startSimulatedCamera|Vẽ canvas preview mô phỏng với poses và animation
handleManualPhotoFilesUpload|Đọc tối đa 6 file, crop vào canvas shot và cập nhật slots
toggleMirror|Đổi mirrorVideo, class video và label Home
handleCustomFrameUpload|Đọc frame, chọn hướng, dò lỗ alpha và render lại
scheduleQRCodeUpdate|Debounce yêu cầu QR sau chỉnh sửa editor
detectSixTransparentRegions|Flood fill alpha trên ảnh thu nhỏ, lọc/sắp xếp 6 bounding boxes
autoDetectTransparentHolesFromFrame|Chạy slot detection, thông báo và fallback metrics
clearCustomFrame|Xóa custom frame/detectedSlots, phục hồi preset
selectPresetLayout|Chọn preset 2×3 hoặc 3×2
updateFrameSelectionUI|Đồng bộ highlight, tên, thumbnail và badge frame
updateCustomSlotMetrics|Đọc phần trăm lề/gap cho layout custom
setCountdownSeconds|Chọn 3/5/7/10 giây và đồng bộ nút timer
toggleFullAutoMode|Bật/tắt auto workflow, đồng bộ checkbox
updateAutoModeUI|Hiển thị trạng thái auto ở header
goToScreen|Chuyển Home/Capture/Result, cleanup timers, cập nhật nav
startAutomaticSession|Đi Capture và khởi động chuỗi sau 500ms
startNewGuestSession|Reset photos, stickers, retake, QR và điều hướng theo auto mode
clearTimers|Hủy countdown/grace và ẩn overlays
renderCaptureDots|Tạo dots tương ứng từng slot đã/chưa chụp
renderSixSlotsGrid|Render thumbnail và dynamic retake/delete handlers, enable Result
updateCaptureScreenUI|Đồng bộ progress, retake banner, main button, dots/grid
startOrContinueSequence|Pause/resume chuỗi hoặc bắt đầu chụp lại cả bộ
runNextShotCountdown|Tick/beep/overlay, chụp slot và lập lịch shot tiếp
captureCurrentFrameImmediately|Chụp ngay slot trống/retake sau cleanup countdown
triggerHardwareCameraShutter|Legacy signal ImageCapture/localhost bridge, không xác nhận ảnh gốc
testHardwareShutterSignal|Test hiệu ứng âm thanh/flash và legacy signal nếu được bật
captureFrameIntoSlot|Snapshot canvas mô phỏng/video với crop/mirror, lưu shot trong RAM
triggerSingleRetake|Chọn slot retake và bắt đầu countdown
deleteSingleSlot|Xóa một slot, chọn slot đó để chụp lại
cancelSingleRetake|Hủy retake/countdown, đồng bộ UI
resetSessionShots|Xóa cả 6 ảnh và retake state
onAllSixShotsCompleted|Thông báo manual hoặc grace countdown tự đi Result
pauseAutoGraceForReview|Dừng grace để khách xem lại/retake
finishCaptureAndGoToResult|Đi Result, render composite, QR service và auto print nếu đã bật
getSixSlotCoordinates|Tọa độ slot từ detected alpha boxes hoặc công thức lề/gap
renderCompositeCanvas|Ghép shots, filter, frame, chữ, stickers, cập nhật preview/print image
drawBuiltInFrameDecorationsBackground|Vẽ gradient trang trí nền preset
drawBuiltInFrameForegroundTexts|Vẽ top/title/footer theo màu nền và kích thước canvas
isColorLight|Tính luminance để chọn màu chữ tương phản
roundRectPath|Tạo path chữ nhật bo góc cho clipping
drawImageCover|Crop giữa theo tỷ lệ cover rồi drawImage
switchCustomTab|Chuyển panel filters/stickers/color/text
renderFilterButtons|Tạo 9 nút filter và dynamic handlers
selectFilter|Chọn filter, render composite, báo QR dirty
renderStickerCategories|Tạo các nút category từ stickerLibrary
selectStickerCategory|Chọn category và render lại danh sách
renderStickerItems|Tạo nút emoji với dynamic add handlers
addEmojiSticker|Thêm sticker emoji tại vị trí ngẫu nhiên chuẩn hóa
handleCustomStickerUpload|Đọc ảnh sticker, thêm object vị trí/kích thước và render
clearAllStickers|Xóa stickers và render lại composite
setupCanvasStickerInteractions|Hit test, kéo mouse/touch, clamp normalized coordinates
renderColorSwatches|Tạo swatches với trạng thái selected
setFrameBackgroundColor|Đổi nền/viền, picker/label và render composite
updateCustomTextsUI|Điền form text từ state
updateCustomTexts|Đọc top/title/footer và render composite
setQRProvider|Chọn provider legacy và yêu cầu regenerate
copyQRLink|Copy URL đang có vào clipboard
renderQRCodeVisual|Vẽ QRCode.js hoặc fallback QR image endpoint
canvasToBlob|Xuất Blob qua canvas.toBlob hoặc dataURL fallback
generateQRCodeForCurrentPhoto|Upload legacy ImgBB/TmpFiles/File.io, cập nhật QR UI
openMobilePreviewModal|Render và mở modal preview ảnh trên thiết bị hiện tại
triggerPrint|Chuẩn bị PNG rồi mở window.print thủ công
downloadCompositeImage|Xuất PNG qua anchor download với timestamp
openSettingsModal|Mở settings modal
closeSettingsModal|Đồng bộ settings và đóng modal
openSlotCalibrator|Mở settings để chỉnh lề/gap và detect frame
syncSettingsFromModal|Đọc auto/print/key từ modal vào state
showToast|Tạo toast và nút đóng, tự xóa sau timeout
ensureAudio|Khởi tạo/resume AudioContext khi có thể
playBeep|Phát oscillator beep cho countdown
playShutterSound|Phát oscillator mô phỏng tiếng shutter
triggerFlashEffect|Khởi động lại CSS flash animation
'''
behavior=dict(line.split('|',1) for line in descriptions.strip().splitlines())
notes={
 'generateQRCodeForCurrentPhoto':'Wrapper mặc định không upload; implementation gốc ở services/legacy-qr.js, opt-in dev. Bỏ QR fragment giả, failure báo unavailable.',
 'triggerHardwareCameraShutter':'Tắt mặc định; opt-in dev ở config/defaults.js. Không có real camera SDK.',
 'testHardwareShutterSignal':'Mặc định chỉ hiệu ứng demo; không báo thành công phần cứng.',
 'clearTimers':'Thêm cleanup sessionStartTimerId, sequenceTimerId, autoPrintTimerId và qrUpdateDebounceTimer.',
 'triggerPrint':'Đăng ký onload trước src và xóa handler sau khi in, tránh render sau đó kích hoạt in lại.',
 'selectPresetLayout':'Xóa custom frame/detection khi chọn preset; render lại ở Result.',
 'updateCustomSlotMetrics':'Bổ sung DOM inputs bị thiếu; cho phép giá trị 0%.',
 'refreshCameraList':'Vẫn có lựa chọn mô phỏng khi mediaDevices không khả dụng.',
 'startCameraStream':'Await attach để giữ lifecycle đúng; chỉ preview trong DEMO.',
 'captureFrameIntoSlot':'requireDemo guard: production không chấp nhận screenshot/video frame.',
 'startSimulatedCamera':'requireDemo guard; badge demo luôn hiện.',
 'handleManualPhotoFilesUpload':'requireDemo guard; chỉ trong RAM, không lưu bền vững.',
}
out=['# FUNCTION_INVENTORY — Phase 0 / Phase 1','','80/80 methods của `app` được mapping. Source locations tính từ HTML gốc 2.493 dòng. Mỗi function mới nhận `app` làm đối số đầu: context truy cập state do `core/store.js` sở hữu và các dependencies được wiring tại `core/bootstrap.js`. Không còn method-binding `this`.','','| old_function | old_source_location | behavior | new_module | new_symbol | reuse/refactor/replace-later | status | notes |','|---|---|---|---|---|---|---|---|']
for f in functions:
 name=f['name']; assert name in behavior
 f['behavior']=behavior[name]
 f['newSymbol']=name
 later=name in ['generateQRCodeForCurrentPhoto','triggerHardwareCameraShutter','testHardwareShutterSignal','triggerPrint']
 detail=notes.get(name,'Di chuyển thuật toán/DOM/classes/callbacks, truyền context tường minh.')
 detail+=' Call sites: '+', '.join(map(str,f['callers']))+'. State/dependencies: '+', '.join(f['dependencies'])+'.'
 out.append(f"| `{name}` | `osa_booth_photobooth.html:{f['line']}` | {behavior[name]} | `frontend/src/{f['module']}.js` | `{name}(app, …)` | {'replace-later' if later else 'refactor'} | {'DEMO / TODO integration' if later else 'DONE'} | {detail} |")
out+=['','## Callback và DOM coverage','','`SOURCE_AUDIT.json` liệt kê 68 inline handlers (cả static markup và template string động), DOM IDs/classes, state properties, CDN paths, callback registrations kèm dòng nguồn. `function-map.json` chứa call sites và toàn bộ `this.*` dependencies của từng method. Callback closures di chuyển cùng method, không tạo logic thứ hai.','','- `DOMContentLoaded → app.init()`: thay bằng module bootstrap sau khi DOM parse xong.','- `window.app`: facade tạm thời được đăng ký trong `core/events.js`; giữ các inline `onclick/onchange/oninput` và dynamic templates. Chưa chuyển hết sang event delegation.','- `renderSimFrame`, `tick`, FileReader/Image onload, Promise/array callbacks: nằm trong module của method cha.','- `getNormalizedPos`, `onPointerDown/Move/Up`, mouse/touch listeners: `features/editor/canvas-interactions.js`.','- Timers countdown/grace/start/next/auto-print/QR: IDs trong store, cleanup ở utils/timing.js.','- Toast timeout chỉ gỡ DOM toast; giữ nguyên. `pagehide` dọn timers/streams.','','## Screen / media / controls','','Home `screenHome`: camera selector/mirror, frame presets/upload, timer 3/5/7/10. Capture `screenCapture`: `liveVideo`, `simLiveCanvas`, countdown/grace overlays, dynamic 6 slots, retake/delete/reset. Result `screenResult`: `compositeCanvas`, filters/stickers/color/text, QR status, print/download. Settings và mobile preview giữ nguyên IDs; calibrator inputs được bổ sung. `printArea/printImageElement`, flash và toast vẫn dùng CSS/DOM gốc.','','State đầy đủ nằm trong SOURCE_AUDIT; filters được chuyển config/filters.js, các field khác ở store.js. layouts.js chuẩn bị metadata 4/6 ảnh; UI/thuật toán legacy vẫn 6 ảnh. State machine và API lưu trữ thuộc Phase 2, chưa tạo file rỗng.']
(root/'docs/FUNCTION_INVENTORY.md').write_text('\n'.join(out)+'\n',encoding='utf-8')
(root/'docs/function-map.json').write_text(json.dumps(functions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Inventory refreshed: 80/80 methods')
