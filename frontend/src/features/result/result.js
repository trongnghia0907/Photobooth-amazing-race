/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function finishCaptureAndGoToResult(app, isAutoTriggered = false) {
  if (!app.photos.every(Boolean) || app.persistenceBusy || app.hasPendingWork()) {
    app.showToast(`Cần lưu đủ ${app.slotCount} ảnh chụp trước khi sang Result.`, 'info');
    return;
  }
  app.clearTimers();
  app.currentScreen = 'result';
  app.releaseHostCamera();
  app.transitionSession('EDIT');
  app.syncPersistenceUI();

  document.getElementById('screenHome').classList.add('hidden');
  document.getElementById('screenCapture').classList.add('hidden');
  document.getElementById('screenResult').classList.remove('hidden');

  const navMap = {
    home: document.getElementById('stepNavHome'),
    capture: document.getElementById('stepNavCapture'),
    result: document.getElementById('stepNavResult')
  };
  Object.entries(navMap).forEach(([key, btn]) => {
    if (!btn) return;
    btn.className = key === 'result'
      ? 'px-4 py-1.5 rounded-full text-xs font-bold transition-all bg-brand-600 text-white shadow-sm'
      : 'px-4 py-1.5 rounded-full text-xs font-bold transition-all text-brand-700 hover:bg-brand-100';
  });

  app.renderCompositeCanvas();
  await app.generateQRCodeForCurrentPhoto(false);

  if (isAutoTriggered && app.fullAutoMode && app.autoPrintPopup) {
    app.showToast('Hãy xác nhận & tạo QR, rồi bấm In ảnh để gửi yêu cầu tới host.', 'info');
  }
}

export function switchCustomTab(app, tabId) {
  app.activeCustomTab = tabId;
  ['filters', 'stickers', 'color', 'text'].forEach(t => {
    const btn = document.getElementById(`tabBtn_${t}`);
    const panel = document.getElementById(`tabPanel_${t}`);
    if (btn && panel) {
      if (t === tabId) {
        btn.className = 'py-3 px-3 rounded-full font-extrabold text-xs sm:text-sm flex items-center justify-center gap-1.5 transition-all btn-primary-blue text-white';
        panel.classList.remove('hidden');
      } else {
        btn.className = 'py-3 px-3 rounded-full font-extrabold text-xs sm:text-sm flex items-center justify-center gap-1.5 transition-all bg-white border border-brand-200 text-brand-800 hover:bg-brand-50';
        panel.classList.add('hidden');
      }
    }
  });
}

export function openMobilePreviewModal(app) {
  app.renderCompositeCanvas();
  document.getElementById('mobilePreviewModal').classList.remove('hidden');
}

export function downloadCompositeImage(app) {
  app.renderCompositeCanvas();
  const canvas = document.getElementById('compositeCanvas');
  const link = document.createElement('a');
  const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  link.download = `osa-booth-${timestamp}.png`;
  link.href = canvas.toDataURL('image/png', 1.0);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  app.showToast('Đã tải ảnh OSA BOOTH về thiết bị!', 'success');
}
