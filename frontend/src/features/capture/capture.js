/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function startAutomaticSession(app) {
  app.ensureAudio();
  if (app.photos.every(p => p !== null)) {
    app.photos = [null, null, null, null, null, null];
  }
  app.goToScreen('capture');
  app.sessionStartTimerId = setTimeout(() => {
    app.sessionStartTimerId = null;
    if (app.currentScreen !== 'capture') return;
    app.startOrContinueSequence();
  }, 500);
}

export function startNewGuestSession(app) {
  app.clearTimers();
  app.photos = [null, null, null, null, null, null];
  app.placedStickers = [];
  app.singleRetakeIndex = null;
  app.lastUploadedUrl = '';
  app.renderSixSlotsGrid();
  app.renderCaptureDots();
  if (app.fullAutoMode) {
    app.startAutomaticSession();
  } else {
    app.goToScreen('home');
  }
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
  const grid = document.getElementById('sixSlotsGrid');
  if (!grid) return;

  grid.innerHTML = app.photos.map((canvasItem, idx) => {
    if (canvasItem) {
      const dataUrl = canvasItem.toDataURL('image/jpeg', 0.85);
      return `
        <div class="group relative aspect-[4/3] rounded-2xl overflow-hidden border-2 border-brand-400 bg-slate-900 shadow-sm cursor-pointer transition-all hover:scale-[1.02]" onclick="app.triggerSingleRetake(${idx})">
          <img src="${dataUrl}" class="w-full h-full object-cover" alt="Shot ${idx + 1}" />
          <div class="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-brand-600/90 text-white font-extrabold text-[10px]">#${idx + 1}</div>
          <button onclick="event.stopPropagation(); app.deleteSingleSlot(${idx})" class="absolute top-2 right-2 w-6 h-6 rounded-full bg-rose-600/90 hover:bg-rose-700 text-white text-xs font-bold flex items-center justify-center opacity-90 sm:opacity-0 group-hover:opacity-100 transition-opacity" title="Xoá ảnh này">✕</button>
          <div class="absolute inset-0 bg-brand-900/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <span class="px-3 py-1 rounded-full bg-white text-brand-800 font-extrabold text-xs shadow">🔄 Chụp lại ô #${idx + 1}</span>
          </div>
        </div>
      `;
    } else {
      const isTarget = (app.singleRetakeIndex === idx) || (app.singleRetakeIndex === null && app.photos.findIndex(p => p === null) === idx);
      return `
        <div onclick="app.triggerSingleRetake(${idx})" class="aspect-[4/3] rounded-2xl border-2 border-dashed ${isTarget ? 'border-brand-500 bg-brand-50/80' : 'border-brand-200 bg-white/60'} flex flex-col items-center justify-center cursor-pointer hover:border-brand-400 transition-all">
          <span class="text-xs font-extrabold ${isTarget ? 'text-brand-600' : 'text-slate-400'}">Ô ảnh #${idx + 1}</span>
          <span class="text-[10px] text-slate-400 mt-0.5">${isTarget ? 'Đang chờ chụp...' : 'Chạm để chụp'}</span>
        </div>
      `;
    }
  }).join('');

  const takenCount = app.photos.filter(p => p !== null).length;
  const badge = document.getElementById('capturedCountBadge');
  if (badge) badge.textContent = `${takenCount} / 6 hoàn tất`;

  const goBtn = document.getElementById('goToResultBtn');
  if (goBtn) {
    if (takenCount === 6) {
      goBtn.disabled = false;
      goBtn.className = 'w-full py-4 rounded-2xl font-extrabold text-sm sm:text-base transition-all flex items-center justify-center gap-2 btn-primary-blue text-white shadow-glow-blue cursor-pointer';
    } else {
      goBtn.disabled = true;
      goBtn.className = 'w-full py-4 rounded-2xl font-extrabold text-sm sm:text-base transition-all flex items-center justify-center gap-2 bg-slate-200 text-slate-400 cursor-not-allowed';
    }
  }
}

export function updateCaptureScreenUI(app) {
  const nextEmpty = app.photos.findIndex(p => p === null);
  const currentShotIndex = app.singleRetakeIndex !== null
    ? app.singleRetakeIndex
    : (nextEmpty !== -1 ? nextEmpty : 5);

  const titleEl = document.getElementById('captureProgressTitle');
  if (titleEl) {
    titleEl.textContent = nextEmpty === -1 && app.singleRetakeIndex === null
      ? 'Đã hoàn thành 6 / 6 tấm! 🎉'
      : `Tấm ${currentShotIndex + 1} / 6`;
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
      mainBtnText.textContent = '⏸️ Tạm dừng đếm ngược';
    } else if (app.singleRetakeIndex !== null) {
      mainBtnText.textContent = `Chụp Lại Ô #${app.singleRetakeIndex + 1} (${app.countdownSeconds}s)`;
    } else if (nextEmpty === -1) {
      mainBtnText.textContent = 'Chụp Lại Toàn Bộ 6 Tấm';
    } else {
      mainBtnText.textContent = 'Bắt Đầu Chụp Tự Động (6 Tấm)';
    }
  }

  app.renderCaptureDots();
  app.renderSixSlotsGrid();
}

export function captureCurrentFrameImmediately(app) {
  app.clearTimers();
  const targetIndex = app.singleRetakeIndex !== null
    ? app.singleRetakeIndex
    : app.photos.findIndex(p => p === null);

  if (targetIndex === -1) {
    app.showToast('Đã đủ 6 tấm ảnh! Nhấn vào ô bất kỳ nếu bạn muốn chụp lại ô đó.', 'info');
    return;
  }

  app.triggerHardwareCameraShutter();
  app.captureFrameIntoSlot(targetIndex);
  app.singleRetakeIndex = null;
  app.updateCaptureScreenUI();

  if (app.photos.every(p => p !== null)) {
    app.onAllSixShotsCompleted();
  }
}

export function onAllSixShotsCompleted(app) {
  if (!app.fullAutoMode) {
    app.showToast('Đã chụp đủ 6 tấm! Nhấn "Hoàn Tất & Xuất Ảnh In" để tiếp tục.', 'success');
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
  app.showToast('Đã tạm dừng tự động in. Chạm vào ô ảnh bất kỳ để chụp lại!', 'info');
}
