import { requireDemo } from '../config/defaults.js';
/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function startCameraStream(app, deviceId = '', notifyOnSuccess = false) {
  requireDemo();
  app.stopCurrentStreams();
  const constraints = {
    audio: false,
    video: {
      width: { ideal: 1280 },
      height: { ideal: 960 },
      ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: 'user' })
    }
  };

  try {
    app.stream = await navigator.mediaDevices.getUserMedia(constraints);
    await app.attachRealStreamToVideo(notifyOnSuccess);
  } catch (firstErr) {
    try {
      app.stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      await app.attachRealStreamToVideo(notifyOnSuccess);
    } catch (permissionOrHardwareErr) {
      app.startSimulatedCamera(
        notifyOnSuccess
          ? 'Trình duyệt đang chặn quyền Camera. Vui lòng bật quyền Camera trên thanh địa chỉ hoặc dùng chế độ Mô Phỏng.'
          : 'Chưa cấp quyền Webcam — Đã tự động bật Camera Mô Phỏng để bạn trải nghiệm đầy đủ tính năng!'
      );
    }
  }
}

export async function attachRealStreamToVideo(app, notifyOnSuccess) {
  app.isUsingSimulatedCamera = false;
  const fallbackBar = document.getElementById('cameraFallbackBar');
  if (fallbackBar) fallbackBar.classList.add('hidden');

  const simLiveCanvas = document.getElementById('simLiveCanvas');
  if (simLiveCanvas) simLiveCanvas.classList.add('hidden');

  const videoEl = document.getElementById('liveVideo');
  if (videoEl) {
    videoEl.classList.remove('hidden');
    videoEl.srcObject = app.stream;
    await videoEl.play().catch(() => {});
  }

  const track = app.stream.getVideoTracks()[0];
  if (track && track.getSettings && track.getSettings().deviceId) {
    app.selectedDeviceId = track.getSettings().deviceId;
  }

  if (notifyOnSuccess) {
    app.showToast('Đã kết nối video preview (DEMO, chưa tích hợp chụp ảnh gốc)!', 'success');
  }
}

export function stopCurrentStreams(app) {
  if (app.simAnimId) {
    cancelAnimationFrame(app.simAnimId);
    app.simAnimId = null;
  }
  if (app.stream) {
    app.stream.getTracks().forEach(t => t.stop());
    app.stream = null;
  }
}

export function toggleMirror(app) {
  app.mirrorVideo = !app.mirrorVideo;
  const videoEl = document.getElementById('liveVideo');
  if (videoEl) videoEl.classList.toggle('mirror-video', app.mirrorVideo);
  const homeMirrorBtn = document.getElementById('homeMirrorBtn');
  if (homeMirrorBtn) {
    homeMirrorBtn.textContent = `🪞 Lật gương: ${app.mirrorVideo ? 'BẬT' : 'TẮT'}`;
  }
}
