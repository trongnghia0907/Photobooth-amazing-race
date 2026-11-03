/** Extracted from legacy; explicit app context supplied by bootstrap. */
import {createStore} from '../../core/store.js';
import {showQRUnavailable} from '../../components/qr-status.js';

export async function startAutomaticSession(app) {
  if(!app.eventConfigurationReady||app.resumeRecoveryPending){app.showToast('Session setup or recovery is not ready. Please ask event staff to check the host.','error');return;}
  if (app.guestStarting || app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;
  app.ensureAudio();
  app.clearTimers();
  app.guestWorkflowActive=true;app.guestStarting=true;app.syncPersistenceUI();
  try {
    if (app.photos.every(Boolean) && !await app.confirmResetShots()) return;
    const epoch=app.captureEpoch;
    if (!await app.prepareSession() || epoch!==app.captureEpoch) return;
    if(app.cameraSource==='host') await app.prepareHostCamera();
    else if(!app.isUsingSimulatedCamera){
      const video=document.getElementById('liveVideo');
      if(!app.stream?.getVideoTracks().some(track=>track.readyState==='live') || !video?.videoWidth || video.readyState<2)
        throw new Error('The camera is not ready. Check the connection and camera permissions, then try again.');
    } else if(!app.simCanvas?.width) throw new Error('The demo preview is not ready. Reconnect the camera.');
    if(epoch!==app.captureEpoch)return;
    app.goToScreen('capture');
    await app.startOrContinueSequence();
  } catch(error){app.reportSaveError(error);}
  finally{app.guestStarting=false;app.syncPersistenceUI();}
}

export function startNewGuestSession(app) {
  if (!app.forgetSession()) return;
  app.guestWorkflowActive=false;app.guestStarting=false;
  app.clearTimers();
  app.photos = Array(app.slotCount).fill(null);
  app.placedStickers = [];
  app.draggingSticker = null;
  app.customTexts = {...createStore().customTexts};
  app.selectedFilter = 'normal';
  app.updateCustomTextsUI();
  app.renderFilterButtons();
  app.switchCustomTab('filters');
  app.singleRetakeIndex = null;
  app.lastUploadedUrl = '';
  app.renderSixSlotsGrid();
  app.renderCaptureDots();
  app.renderCompositeCanvas();
  showQRUnavailable(app,'Start a new session, take your photos, and confirm them to create a QR code.');
  app.goToScreen('home');
}

export function renderCaptureDots(app) {
  const container = document.getElementById('captureDotsContainer');
  if (!container) return;
  container.innerHTML = app.photos.map((p) => {
    const activeClass = p ? 'bg-brand-600 border-brand-600 scale-110' : 'bg-brand-100 border-brand-300';
    return `<span class="w-3 h-3 rounded-full border transition-all ${activeClass}"></span>`;
  }).join('');
}

export function renderSixSlotsGrid(app) {
  app.renderRecentPhotos?.();
  const grid = document.getElementById('sixSlotsGrid');
  if (!grid) return;

  grid.innerHTML = app.photos.map((canvasItem, idx) => {
    if (canvasItem) {
      const dataUrl = canvasItem.toDataURL('image/jpeg', 0.85);
      return `
        <div class="group relative aspect-[4/3] rounded-2xl overflow-hidden border-2 border-brand-400 bg-slate-900 shadow-sm cursor-pointer transition-all hover:scale-[1.02]" onclick="app.triggerSingleRetake(${idx})">
          <img src="${dataUrl}" class="w-full h-full object-cover" alt="Shot ${idx + 1}" />
          <div class="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-brand-600/90 text-white font-extrabold text-[10px]">#${idx + 1}</div>
          <button onclick="event.stopPropagation(); app.deleteSingleSlot(${idx})" class="absolute top-2 right-2 w-6 h-6 rounded-full bg-rose-600/90 hover:bg-rose-700 text-white text-xs font-bold flex items-center justify-center opacity-90 sm:opacity-0 group-hover:opacity-100 transition-opacity" title="Delete this photo">✕</button>
          <div class="absolute inset-0 bg-brand-900/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <span class="px-3 py-1 rounded-full bg-white text-brand-800 font-extrabold text-xs shadow">🔄 Retake slot #${idx + 1}</span>
          </div>
        </div>
      `;
    } else {
      const isTarget = (app.singleRetakeIndex === idx) || (app.singleRetakeIndex === null && app.photos.findIndex(p => p === null) === idx);
      return `
        <div onclick="app.triggerSingleRetake(${idx})" class="aspect-[4/3] rounded-2xl border-2 border-dashed ${isTarget ? 'border-brand-500 bg-brand-50/80' : 'border-brand-200 bg-white/60'} flex flex-col items-center justify-center cursor-pointer hover:border-brand-400 transition-all">
          <span class="text-xs font-extrabold ${isTarget ? 'text-brand-600' : 'text-slate-400'}">Photo slot #${idx + 1}</span>
          <span class="text-[10px] text-slate-400 mt-0.5">${isTarget ? 'Ready to capture…' : 'Tap to capture'}</span>
        </div>
      `;
    }
  }).join('');

  const takenCount = app.photos.filter(p => p !== null).length;
  const badge = document.getElementById('capturedCountBadge');
  if (badge) badge.textContent = `${takenCount} / ${app.slotCount} complete`;

  const goBtn = document.getElementById('goToResultBtn');
  if (goBtn) {
    if (takenCount === app.slotCount) {
      goBtn.disabled = false;
      goBtn.className = 'w-full py-4 rounded-2xl font-extrabold text-sm sm:text-base transition-all flex items-center justify-center gap-2 btn-primary-blue text-white shadow-glow-blue cursor-pointer';
    } else {
      goBtn.disabled = true;
      goBtn.className = 'w-full py-4 rounded-2xl font-extrabold text-sm sm:text-base transition-all flex items-center justify-center gap-2 bg-slate-200 text-slate-400 cursor-not-allowed';
    }
  }
}

function canCompleteCapture(app) {
  return app.currentScreen==='capture'&&(!app.isCapturingSequence||app.sequencePaused)&&app.singleRetakeIndex===null
    &&app.photos.length===app.slotCount&&app.photos.every(Boolean)
    &&!app.serverSession?.finalized&&!app.finalOperation?.confirmationStarted;
}

export function updateCaptureScreenUI(app) {
  app.syncHostCaptureUI();
  const nextEmpty = app.photos.findIndex(p => p === null);
  const currentShotIndex = app.singleRetakeIndex !== null
    ? app.singleRetakeIndex
    : (nextEmpty !== -1 ? nextEmpty : app.slotCount - 1);

  const titleEl = document.getElementById('captureProgressTitle');
  if (titleEl) {
    titleEl.textContent = nextEmpty === -1 && app.singleRetakeIndex === null
      ? `All ${app.slotCount} photos captured! 🎉`
      : `Tấm ${currentShotIndex + 1} / ${app.slotCount}`;
  }

  const retakeBanner = document.getElementById('retakeBanner');
  if (retakeBanner) {
    if (app.singleRetakeIndex !== null) {
      retakeBanner.classList.remove('hidden');
      document.getElementById('retakeSlotNumber').textContent = app.singleRetakeIndex + 1;
    } else {
      retakeBanner.classList.add('hidden');
    }
  }

  const mainBtnText = document.getElementById('mainCaptureBtnText');
  if (mainBtnText) {
    if (app.isCapturingSequence) {
      mainBtnText.textContent = app.sequencePaused?'Tiếp tục chụp':'Tạm dừng';
    } else if (app.singleRetakeIndex !== null) {
      mainBtnText.textContent = `Retake Slot #${app.singleRetakeIndex + 1} (${app.countdownSeconds}s)`;
    } else if (nextEmpty === -1) {
      mainBtnText.textContent = `Retake All ${app.slotCount} Photos`;
    } else if(app.photos.some(Boolean)){
      mainBtnText.textContent='Tiếp tục chụp';
    } else {
      mainBtnText.textContent = `Start Automatic Capture (${app.slotCount} Photos)`;
    }
  }

  const control=document.getElementById('mainCaptureBtn');
  if(control){control.disabled=!!(app.captureBusy||app.persistenceBusy||app.sequenceStarting);control.setAttribute('aria-pressed',String(!!app.sequencePaused));}
  for(const id of ['manualInstantSnapBtn','resetAllShotsBtn','cancelRetakeBtn']){
    const button=document.getElementById(id);if(button)button.disabled=!!(app.captureBusy||app.persistenceBusy);
  }
  const complete=document.getElementById('completeCaptureBtn');
  if(complete){
    const available=canCompleteCapture(app);
    complete.classList.toggle('hidden',!available);
    complete.disabled=!available||!!(app.captureBusy||app.persistenceBusy||app.sequenceStarting||app.hasPendingWork());
  }

  app.renderCaptureDots();
  app.renderSixSlotsGrid();
}

export async function captureCurrentFrameImmediately(app) {
  if (app.persistenceBusy || app.captureBusy || app.sequenceStarting || app.hasPendingWork()) return;
  const paused=app.sequencePaused;
  app.clearTimers();
  // A manual shot cancels the obsolete countdown, but keeps paused controls.
  app.sequencePaused=!!paused;
  const epoch = app.captureEpoch;
  const retake=app.singleRetakeIndex!==null;
  const targetIndex = app.singleRetakeIndex !== null
    ? app.singleRetakeIndex
    : app.photos.findIndex(p => p === null);

  if (targetIndex === -1) {
    app.showToast(`All ${app.slotCount} photos are ready! Tap any slot to retake that photo.`, 'info');
    return;
  }

  app.captureBusy = true;
  app.updateCaptureScreenUI();
  app.transitionSession('CAPTURE');
  try {
    if(app.cameraSource==='host'&&!await app.prepareSession())return;
    if(epoch!==app.captureEpoch)return;
    if (!(await app.capturePhoto(targetIndex)).accepted || epoch !== app.captureEpoch) return;
    app.singleRetakeIndex = null;
    app.retakeReturnToReview=false;
    app.updateCaptureScreenUI();
    if (retake&&app.photos.every(Boolean)) app.onAllSixShotsCompleted();
  } catch (error) { app.reportSaveError(error); }
  finally { app.captureBusy = false; app.syncPersistenceUI();app.updateCaptureScreenUI(); }
}

export function completePausedCapture(app) {
  if(!canCompleteCapture(app)||app.captureBusy||app.persistenceBusy||app.sequenceStarting||app.hasPendingWork())return;
  const button=document.getElementById('completeCaptureBtn');if(button)button.disabled=true;
  // The existing transition switches screens synchronously before its first
  // await, so a second click cannot enter Review twice. Confirmation stays separate.
  return app.finishCaptureAndGoToResult();
}

export function onAllSixShotsCompleted(app) {
  app.transitionSession('REVIEW');
  if(app.guestWorkflowActive){
    app.finishCaptureAndGoToResult(true);
    return;
  }
  if (!app.fullAutoMode) {
    app.showToast(`All ${app.slotCount} photos are captured! Select “Finish & Create Print” to continue.`, 'success');
    return;
  }

  if (app.autoGraceTimerId) clearInterval(app.autoGraceTimerId);
  app.graceRemaining = 4;
  const graceOverlay = document.getElementById('autoGraceOverlay');
  const graceText = document.getElementById('graceSecondsText');
  if (graceOverlay) graceOverlay.classList.remove('hidden');
  if (graceText) graceText.textContent = app.graceRemaining;

  app.autoGraceTimerId = setInterval(() => {
    app.graceRemaining--;
    if (app.graceRemaining > 0) {
      if (graceText) graceText.textContent = app.graceRemaining;
    } else {
      clearInterval(app.autoGraceTimerId);
      app.autoGraceTimerId = null;
      if (graceOverlay) graceOverlay.classList.add('hidden');
      app.finishCaptureAndGoToResult(true);
    }
  }, 1000);
}

export function pauseAutoGraceForReview(app) {
  if (app.autoGraceTimerId) {
    clearInterval(app.autoGraceTimerId);
    app.autoGraceTimerId = null;
  }
  const graceOverlay = document.getElementById('autoGraceOverlay');
  if (graceOverlay) graceOverlay.classList.add('hidden');
  app.showToast('Automatic printing is paused. Tap any photo slot to retake it!', 'info');
}
