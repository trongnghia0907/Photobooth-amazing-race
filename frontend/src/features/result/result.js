/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function finishCaptureAndGoToResult(app, isAutoTriggered = false) {
  if (!app.photos.every(Boolean) || app.persistenceBusy || app.hasPendingWork()) {
    app.showToast(`Capture all ${app.slotCount} photos before continuing to your results.`, 'info');
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

  app.renderCompositeCanvas();
  await app.generateQRCodeForCurrentPhoto(false);
  app.syncSetupLayout();

  if (isAutoTriggered && app.fullAutoMode && app.autoPrintPopup) {
    app.showToast('Confirm your photo and create a QR code, then select Print Photo to send the request to the host.', 'info');
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
  if(app.serverSession?.finalized&&app.activeShare){
    if(!app.activeShare.print_ready||!app.activeShare.public_ready){app.showToast(app.activeShare.print_ready_error||'Waiting for a verified HTTPS print image with a QR code.','info');return;}
    const download=document.createElement('a');download.href=app.activeShare.download_url;download.download='amazing-race-2026-print-ready.png';
    document.body.appendChild(download);download.click();download.remove();return;
  }
  app.renderCompositeCanvas();
  const canvas = document.getElementById('compositeCanvas');
  const link = document.createElement('a');
  const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  link.download = `amazing-race-2026-${timestamp}.png`;
  link.href = canvas.toDataURL('image/png', 1.0);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  app.showToast('AMAZING RACE 2026 photo downloaded to your device!', 'success');
}
