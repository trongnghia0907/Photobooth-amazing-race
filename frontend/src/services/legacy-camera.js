import { defaults } from '../config/defaults.js';
/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function triggerHardwareCameraShutter(app) {
  if (!defaults.enableLegacyShutter) return;
  // Gửi xung lệnh phần cứng đóng màn trập máy ảnh (WebUSB PTP / UVC / Serial / Local Bridge)
  try {
    if (app.stream && window.ImageCapture) {
      const track = app.stream.getVideoTracks()[0];
      if (track) {
        const imageCapture = new window.ImageCapture(track);
        if (imageCapture.takePhoto) {
          imageCapture.takePhoto().catch(() => {});
        }
      }
    }
    // Gọi Local digiCamControl / gPhoto2 HTTP bridge nếu có tại cổng sự kiện
    fetch('http://127.0.0.1:5513/?SLC=Capture', { mode: 'no-cors' }).catch(() => {});
  } catch (e) {}
}

export function testHardwareShutterSignal(app) {
  app.triggerHardwareCameraShutter();
  app.playShutterSound();
  app.triggerFlashEffect();
  app.showToast(defaults.enableLegacyShutter ? 'Legacy: chỉ gửi tín hiệu; chưa xác nhận ảnh máy ảnh.' : 'DEMO: hiệu ứng màn trập, không gửi lệnh phần cứng.', 'info');
}
