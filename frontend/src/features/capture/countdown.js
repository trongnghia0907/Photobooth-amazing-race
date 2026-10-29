/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function startOrContinueSequence(app) {
  app.ensureAudio();
  if (app.isCapturingSequence) {
    app.clearTimers();
    app.updateCaptureScreenUI();
    return;
  }

  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;

  if (app.photos.every(p => p !== null) && app.singleRetakeIndex === null) {
    if (!await app.resetSessionShots()) return;
  }

  const epoch = app.captureEpoch;
  if (!await app.prepareSession() || epoch !== app.captureEpoch) return;

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
      : `Chuẩn bị chụp tấm #${targetIndex + 1} / ${app.slotCount}...`;
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

  app.transitionSession('COUNTDOWN');
  tick();

  app.countdownTimerId = setInterval(async () => {
    remaining--;
    if (remaining > 0) {
      app.transitionSession('COUNTDOWN');
  tick();
    } else {
      clearInterval(app.countdownTimerId);
      app.countdownTimerId = null;
      if (overlay) overlay.classList.add('hidden');

      const epoch = app.captureEpoch;
      app.captureBusy = true;
      app.transitionSession('CAPTURE');
      let accepted = false;
      try { accepted = (await app.capturePhoto(targetIndex)).accepted; }
      catch (error) { app.reportSaveError(error); }
      finally { app.captureBusy = false; app.syncPersistenceUI(); }
      if (epoch !== app.captureEpoch) return;
      if (!accepted) {
        app.isCapturingSequence = false;
        app.updateCaptureScreenUI();
        return;
      }

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
