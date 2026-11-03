import { layouts } from '../../config/layouts.js';
/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function handleCustomFrameUpload(app, event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      app.customFrameImg = img;
      app.customFrameName = file.name;

      if (app.slotCount === 4) {
        app.presetLayout = 'landscape_4';
      } else if (img.width > img.height) {
        app.presetLayout = 'grid3x2';
      } else {
        app.presetLayout = 'grid2x3';
      }

      const detected = app.detectSixTransparentRegions(img);
      if (detected && detected.length === app.slotCount) {
        app.detectedSlots = detected;
        app.showToast(`Đã tải Frame "${file.name}" và tự động khớp chính xác ${app.slotCount} ô trống!`, 'success');
      } else {
        app.detectedSlots = null;
        app.showToast(`Đã tải Frame "${file.name}" thành công!`, 'success');
      }

      app.updateFrameSelectionUI();
      if (app.currentScreen === 'result') {
        app.renderCompositeCanvas();
        app.generateQRCodeForCurrentPhoto(true);
      }
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
  event.target.value = '';
}

export function clearCustomFrame(app) {
  app.customFrameImg = null;
  app.customFrameName = '';
  app.detectedSlots = null;
  app.updateFrameSelectionUI();
  if (app.currentScreen === 'result') {
    app.renderCompositeCanvas();
    app.scheduleQRCodeUpdate();
  }
  app.showToast('Đã quay về khung xanh AMAZING RACE 2026 mặc định.', 'info');
}

export function selectPresetLayout(app, layout) {
  const definition = layouts[layout];
  if (!definition) return;
  if(layout!==app.presetLayout&&(app.isCapturingSequence||app.guestStarting||app.persistenceBusy||app.captureBusy||app.hasPendingWork()||app.resumeRecoveryPending)){
    app.showToast('Wait for the current action to finish before changing the layout.', 'info');
    return;
  }
  if(layout!==app.presetLayout&&(app.currentScreen!=='home'||app.photos.some(Boolean)||(app.serverSession&&app.serverSession.status!=='created'))){
    app.showToast('Capture has started. Choose New Session to change the layout.', 'info');
    return;
  }
  if (definition.slotCount !== app.slotCount) {
    if (app.currentScreen !== 'home' || app.photos.some(Boolean) || app.hasPendingWork() || app.persistenceBusy || app.captureBusy) {
      app.showToast('Start a new session on the Home screen before changing the photo count.', 'info');
      return;
    }
    app.slotCount = definition.slotCount;
    app.photos = Array(app.slotCount).fill(null);
    app.pendingPhotos = Array(app.slotCount).fill(null);
    app.updateCaptureScreenUI();
  }
  app.customFrameImg = null;
  app.customFrameName = '';
  app.detectedSlots = null;
  app.presetLayout = layout;
  app.updateFrameSelectionUI();
  if(app.currentScreen==='home')app.saveSetupLayout();
  if (app.currentScreen === 'result') {
    app.renderCompositeCanvas();
    app.scheduleQRCodeUpdate();
  }
}

export function updateFrameSelectionUI(app) {
  app.updateSlotLabels();
  const cardCustom = document.getElementById('frameCardCustom');
  const card2x3 = document.getElementById('frameCardGrid2x3');
  const card3x2 = document.getElementById('frameCardGrid3x2');
  const card4 = document.getElementById('frameCardLandscape4');
  const badge = document.getElementById('customFrameBadge');
  const subtext = document.getElementById('customFrameSubtext');
  const calibrateBtn = document.getElementById('calibrateSlotsBtn');
  const homeFrameName = document.getElementById('homeFrameName');
  const homeFrameDesc = document.getElementById('homeFrameDesc');
  const homeFrameThumb = document.getElementById('homeFrameThumb');

  const baseClass = 'layout-choice-card p-4 rounded-2xl border-2 transition-all cursor-pointer bg-white border-brand-100';
  const selectedClass = 'layout-choice-card p-4 rounded-2xl border-2 transition-all cursor-pointer bg-brand-50/90 border-brand-600 shadow-sm';
  [cardCustom, card2x3, card3x2, card4].forEach(el => {
    if (el) { el.className = baseClass; el.setAttribute('aria-checked', 'false'); }
  });

  if (app.customFrameImg) {
    const selectedLayoutCard = app.presetLayout === 'landscape_4' ? card4 : card2x3;
    if (selectedLayoutCard) { selectedLayoutCard.className = selectedClass; selectedLayoutCard.setAttribute('aria-checked', 'true'); }
    if (cardCustom) cardCustom.className = selectedClass;
    if (badge) badge.classList.remove('hidden');
    if (calibrateBtn) calibrateBtn.classList.add('hidden');
    if (subtext) subtext.textContent = `Frame tùy chỉnh: ${app.customFrameName} (${app.customFrameImg.width}×${app.customFrameImg.height}px)`;
    if (homeFrameName) homeFrameName.textContent = `Frame ${app.customFrameName}`;
    if (homeFrameDesc) homeFrameDesc.textContent = app.detectedSlots ? `Automatically aligned ${app.slotCount} transparent slots` : `Custom ${app.slotCount}-photo layout`;
    if (homeFrameThumb) homeFrameThumb.innerHTML = `<img src="${app.customFrameImg.src}" class="w-full h-full object-contain" />`;
  } else {
    if (badge) badge.classList.add('hidden');
    if (calibrateBtn) calibrateBtn.classList.add('hidden');
    if (subtext) subtext.textContent = 'Nhấn để tải file Frame PNG cá nhân của bạn (Tự động khớp 6 ô trống)';
    if (homeFrameThumb) homeFrameThumb.innerHTML = `<span class="text-xs font-bold text-brand-600">AR</span>`;

    if (app.presetLayout === 'grid2x3') {
      if (card2x3) { card2x3.className = selectedClass; card2x3.setAttribute('aria-checked', 'true'); }
      if (homeFrameName) homeFrameName.textContent = 'AMAZING RACE 2026 • 6 Portrait Photos';
      if (homeFrameDesc) homeFrameDesc.textContent = '6-photo portrait layout (10×15 cm)';
    } else if (app.presetLayout === 'landscape_4') {
      if (card4) { card4.className = selectedClass; card4.setAttribute('aria-checked', 'true'); }
      if (homeFrameName) homeFrameName.textContent = 'AMAZING RACE 2026 • 4 Landscape Photos (2×2)';
      if (homeFrameDesc) homeFrameDesc.textContent = '4-photo landscape layout';
    } else {
      if (card3x2) { card3x2.className = selectedClass; card3x2.setAttribute('aria-checked', 'true'); }
      if (homeFrameName) homeFrameName.textContent = 'AMAZING RACE 2026 • 6 Landscape Photos';
      if (homeFrameDesc) homeFrameDesc.textContent = '6-photo landscape layout';
    }
  }
}

export function updateCustomSlotMetrics(app) {
  app.slotMetrics.padX = parseFloat(document.getElementById('slotPadX').value) || 0;
  app.slotMetrics.padTop = parseFloat(document.getElementById('slotPadTop').value) || 0;
  app.slotMetrics.padBottom = parseFloat(document.getElementById('slotPadBottom').value) || 0;
  app.slotMetrics.gap = parseFloat(document.getElementById('slotGap').value) || 0;
  app.detectedSlots = null;
  if (app.currentScreen === 'result') {
    app.renderCompositeCanvas();
    app.scheduleQRCodeUpdate();
  }
}

export function openSlotCalibrator(app) {
  app.openSettingsModal();
}
