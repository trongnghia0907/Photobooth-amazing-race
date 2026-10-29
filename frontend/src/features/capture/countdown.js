/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function startOrContinueSequence(app) {
  app.ensureAudio();
  if (app.isCapturingSequence) {
    app.clearTimers();
    app.updateCaptureScreenUI();
    return;
  }

  if (app.photos.every(p => p !== null) && app.singleRetakeIndex === null) {
    app.photos = [null, null, null, null, null, null];
  }

  app.isCapturingSequence = true;
  app.updateCaptureScreenUI();
  app.runNextShotCountdown();
}

export function runNextShotCountdown(app) {
  if (!app.isCapturingSequence) return;

  const targetIndex = app.singleRetakeIndex !== null
    ? app.singleRetakeIndex
    : app.photos.findIndex(p => p === null);

  if (targetIndex === -1) {
    app.isCapturingSequence = false;
    app.updateCaptureScreenUI();
    app.onAllSixShotsCompleted();
    return;
  }

  app.updateCaptureScreenUI();

  let remaining = app.countdownSeconds;
  const overlay = document.getElementById('countdownOverlay');
  const numEl = document.getElementById('countdownNumber');
  const labelEl = document.getElementById('countdownLabel');

  if (overlay) overlay.classList.remove('hidden');
  if (labelEl) {
    labelEl.textContent = app.singleRetakeIndex !== null
      ? `Đang chụp lại tấm #${targetIndex + 1}...`
      : `Chuẩn bị chụp tấm #${targetIndex + 1} / 6...`;
  }

  const tick = () => {
    if (numEl) {
      numEl.textContent = remaining;
      numEl.classList.remove('count-animate');
      void numEl.offsetWidth;
      numEl.classList.add('count-animate');
    }
    app.playBeep(remaining === 1 ? 1200 : 800, 0.12);
  };

  tick();

  app.countdownTimerId = setInterval(() => {
    remaining--;
    if (remaining > 0) {
      tick();
    } else {
      clearInterval(app.countdownTimerId);
      app.countdownTimerId = null;
      if (overlay) overlay.classList.add('hidden');

      // Gửi tín hiệu phần cứng đóng màn trập máy ảnh cho frame này
      app.triggerHardwareCameraShutter();
      app.captureFrameIntoSlot(targetIndex);

      if (app.singleRetakeIndex !== null) {
        app.singleRetakeIndex = null;
        app.isCapturingSequence = false;
        app.updateCaptureScreenUI();
        if (app.photos.every(p => p !== null)) {
          app.onAllSixShotsCompleted();
        }
      } else {
        app.sequenceTimerId = setTimeout(() => {
        app.sequenceTimerId = null;
          app.runNextShotCountdown();
        }, 950);
      }
    }
  }, 1000);
}
