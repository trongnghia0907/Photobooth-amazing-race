import { requireDemo } from '../config/defaults.js';
/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function startSimulatedCamera(app, toastMsg = '') {
  requireDemo();
  app.stopCurrentStreams();
  app.isUsingSimulatedCamera = true;

  const fallbackBar = document.getElementById('cameraFallbackBar');
  if (fallbackBar) fallbackBar.classList.remove('hidden');

  const videoEl = document.getElementById('liveVideo');
  if (videoEl) videoEl.classList.add('hidden');

  const simLiveCanvas = document.getElementById('simLiveCanvas');
  if (simLiveCanvas) {
    simLiveCanvas.classList.remove('hidden');
    app.simCanvas = simLiveCanvas;
  } else if (!app.simCanvas) {
    app.simCanvas = document.createElement('canvas');
    app.simCanvas.width = 960;
    app.simCanvas.height = 720;
  }

  const ctx = app.simCanvas.getContext('2d');
  const poses = [
    { icon: '✌️', title: 'Tạo dáng Peace tươi tắn!' },
    { icon: '🫶', title: 'Thả tim đôi thật xinh!' },
    { icon: '😎', title: 'Phong cách cực ngầu!' },
    { icon: '🥳', title: 'Nụ cười rạng rỡ nhất!' },
    { icon: '👑', title: 'Thần thái ngôi sao sự kiện!' },
    { icon: '💙', title: 'Kỷ niệm đáng nhớ cùng nhau!' }
  ];

  const renderSimFrame = (time) => {
    const t = (time || 0) * 0.001;
    const w = app.simCanvas.width;
    const h = app.simCanvas.height;

    const grad = ctx.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, '#1E3A8A');
    grad.addColorStop(0.5, '#2563EB');
    grad.addColorStop(1, '#0EA5E9');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    for (let i = 0; i < 8; i++) {
      const bx = (w * (0.12 + i * 0.11)) + Math.sin(t * 1.2 + i) * 45;
      const by = (h * (0.2 + (i % 3) * 0.28)) + Math.cos(t * 0.9 + i) * 35;
      const radius = 45 + (i % 4) * 22;
      ctx.beginPath();
      ctx.arc(bx, by, radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
      ctx.fill();
    }

    const emptyIdx = app.photos.findIndex(p => p === null);
    const nextIdx = app.singleRetakeIndex !== null
      ? app.singleRetakeIndex
      : (emptyIdx !== -1 ? emptyIdx : 0);
    const currentPose = poses[nextIdx % poses.length];

    const bounceY = Math.sin(t * 3) * 10;
    ctx.beginPath();
    ctx.arc(w / 2, h * 0.42 + bounceY, 115, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.18)';
    ctx.fill();
    ctx.lineWidth = 4;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.65)';
    ctx.stroke();

    ctx.font = '92px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(currentPose.icon, w / 2, h * 0.42 + bounceY);

    ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
    app.roundRectPath(ctx, w / 2 - 240, h * 0.67, 480, 56, 28);
    ctx.fill();

    ctx.fillStyle = '#1E40AF';
    ctx.font = 'bold 23px "Plus Jakarta Sans", sans-serif';
    ctx.fillText(`TẤM #${nextIdx + 1}: ${currentPose.title}`, w / 2, h * 0.67 + 29);

    ctx.fillStyle = 'rgba(224, 242, 254, 0.95)';
    ctx.font = '600 17px "Plus Jakarta Sans", sans-serif';
    ctx.fillText(`✨ OSA BOOTH DEMO • Sẵn sàng chụp ${app.slotCount} tấm ✨`, w / 2, h * 0.80);

    app.simAnimId = requestAnimationFrame(renderSimFrame);
  };

  app.simAnimId = requestAnimationFrame(renderSimFrame);
  if (toastMsg) app.showToast(toastMsg, 'info');
}

export function handleManualPhotoFilesUpload(app, event) {
  requireDemo();
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;
  const files = Array.from(event.target.files || []);
  if (!files.length) return;

  app.clearTimers();
  event.target.value = '';
  app.captureBusy = true;
  return (async () => {
    const epoch = app.captureEpoch;
    try {
      const canvases = [];
      for (const [idx, file] of files.slice(0, app.slotCount).entries()) {
        if (epoch !== app.captureEpoch) return;
        const img = await new Promise((resolve, reject) => {
          const image = new Image();
          const url = URL.createObjectURL(file);
          image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
          image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Không thể đọc file ảnh. Hãy chọn PNG/JPEG/WebP hợp lệ.')); };
          image.src = url;
        });
        const snapCanvas = document.createElement('canvas');
        snapCanvas.width = 960;
        snapCanvas.height = 720;
        const ctx = snapCanvas.getContext('2d');
        app.drawImageCover(ctx, img, 0, 0, snapCanvas.width, snapCanvas.height);

        canvases.push(snapCanvas);
      }
      if (epoch !== app.captureEpoch || !await app.acceptPhotoBatch(canvases)) return;
      app.showToast(`Backend đã lưu ${Math.min(app.slotCount, files.length)} ảnh chụp.`, 'success');
      if (app.photos.every(Boolean)) app.onAllSixShotsCompleted();
    } catch (error) { app.reportSaveError(error); }
    finally { app.captureBusy = false; app.syncPersistenceUI(); }
  })();
}

export function captureFrameIntoSlot(app, slotIndex) {
  requireDemo();
  const videoEl = document.getElementById('liveVideo');
  const snapCanvas = document.createElement('canvas');
  snapCanvas.width = 960;
  snapCanvas.height = 720;
  const ctx = snapCanvas.getContext('2d');

  if (app.isUsingSimulatedCamera && app.simCanvas) {
    ctx.drawImage(app.simCanvas, 0, 0, snapCanvas.width, snapCanvas.height);
  } else if (videoEl && videoEl.readyState >= 2) {
    const vw = videoEl.videoWidth || 1280;
    const vh = videoEl.videoHeight || 960;
    const targetAspect = 4 / 3;
    let sx = 0, sy = 0, sw = vw, sh = vh;
    const videoAspect = vw / vh;

    if (videoAspect > targetAspect) {
      sw = vh * targetAspect;
      sx = (vw - sw) / 2;
    } else {
      sh = vw / targetAspect;
      sy = (vh - sh) / 2;
    }

    if (app.mirrorVideo) {
      ctx.translate(snapCanvas.width, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(videoEl, sx, sy, sw, sh, 0, 0, snapCanvas.width, snapCanvas.height);
  } else {
    const grad = ctx.createLinearGradient(0, 0, snapCanvas.width, snapCanvas.height);
    grad.addColorStop(0, '#2563EB');
    grad.addColorStop(1, '#38BDF8');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, snapCanvas.width, snapCanvas.height);
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 48px "Plus Jakarta Sans", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`POSE #${slotIndex + 1} ✨`, snapCanvas.width / 2, snapCanvas.height / 2);
  }

  app.playShutterSound();
  app.triggerFlashEffect();
  const source = app.isUsingSimulatedCamera || !videoEl || videoEl.readyState < 2 ? 'demo' : 'webcam_frame';
  return app.acceptPhoto(slotIndex, snapCanvas, source);
}
