/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function init(app) {
  if(app.useHostCameraByDefault())app.cameraSource='host';
  app.updateSlotLabels();
  app.renderCaptureDots();
  app.renderSixSlotsGrid();
  app.renderFilterButtons();
  app.renderColorSwatches();
  app.updateCustomTextsUI();
  if(!app.serverSession?.finalized&&!app.resumeRecoveryPending&&app.currentScreen!=='result')await app.initCameraDevices();
}

export function updateSlotLabels(app) {
  for (const element of document.querySelectorAll('[data-shot-template]')) {
    element.textContent = element.dataset.shotTemplate.replaceAll('{count}', app.slotCount);
  }
}

export function setCountdownSeconds(app, sec) {
  app.countdownSeconds = sec;
  [3, 5, 7, 10].forEach(s => {
    const btn = document.getElementById(`timerBtn${s}`);
    if (btn) {
      btn.className = s === sec
        ? 'py-3 rounded-2xl font-extrabold text-sm border transition-all btn-primary-blue text-white border-transparent'
        : 'py-3 rounded-2xl font-extrabold text-sm border transition-all bg-brand-50 border-brand-200 text-brand-800 hover:bg-brand-100';
    }
  });
  const hint = document.getElementById('timerHintText');
  if (hint) hint.textContent = `${sec} seconds per photo`;
}

export function toggleFullAutoMode(app) {
  app.fullAutoMode = !app.fullAutoMode;
  const chk = document.getElementById('chkFullAuto');
  if (chk) chk.checked = app.fullAutoMode;
  app.updateAutoModeUI();
  app.showToast(app.fullAutoMode ? `Automatic capture enabled for ${app.slotCount} photos.` : 'Manual capture enabled.', 'info');
}

export function updateAutoModeUI(app) {
  const dot = document.getElementById('autoModeDot');
  const text = document.getElementById('autoModeStatusText');
  if (dot && text) {
    if (app.fullAutoMode) {
      dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse';
      text.textContent = 'ON';
    } else {
      dot.className = 'w-2.5 h-2.5 rounded-full bg-slate-400';
      text.textContent = 'OFF';
    }
  }
}
