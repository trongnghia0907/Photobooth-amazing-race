/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function init(app) {
  app.renderCaptureDots();
  app.renderSixSlotsGrid();
  app.renderFilterButtons();
  app.renderStickerCategories();
  app.renderStickerItems();
  app.renderColorSwatches();
  app.setupCanvasStickerInteractions();
  app.updateCustomTextsUI();
  await app.initCameraDevices();
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
  if (hint) hint.textContent = `${sec} giây / tấm`;
}

export function toggleFullAutoMode(app) {
  app.fullAutoMode = !app.fullAutoMode;
  const chk = document.getElementById('chkFullAuto');
  if (chk) chk.checked = app.fullAutoMode;
  app.updateAutoModeUI();
  app.showToast(app.fullAutoMode ? 'Đã BẬT Chế độ Tự động hoàn toàn (Chụp 6 tấm → QR → Tự động In)!' : 'Đã chuyển sang Chế độ Thủ công.', 'info');
}

export function updateAutoModeUI(app) {
  const dot = document.getElementById('autoModeDot');
  const text = document.getElementById('autoModeStatusText');
  if (dot && text) {
    if (app.fullAutoMode) {
      dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse';
      text.textContent = 'BẬT';
    } else {
      dot.className = 'w-2.5 h-2.5 rounded-full bg-slate-400';
      text.textContent = 'TẮT';
    }
  }
}
