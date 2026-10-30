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
  app.showToast('Đã quay về Khung Xanh OSA BOOTH mặc định.', 'info');
}

export function selectPresetLayout(app, layout) {
  const definition = layouts[layout];
  if (!definition) return;
  if (app.cameraSource === 'host' && app.currentScreen === 'home' && !app.photos.some(Boolean)
      && app.sessionContext?.id && app.sessionContext.layout !== layout) {
    if (!app.forgetSession()) return;
  }
  if (definition.slotCount !== app.slotCount) {
    if (app.currentScreen !== 'home' || app.photos.some(Boolean) || app.hasPendingWork() || app.persistenceBusy || app.captureBusy) {
      app.showToast('Hãy bắt đầu khách mới ở Home trước khi đổi số ảnh.', 'info');
      return;
    }
    if (!app.forgetSession()) return;
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

  [cardCustom, card2x3, card3x2, card4].forEach(el => {
    if (el) el.className = 'p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center justify-between bg-white border-brand-100 hover:border-brand-300';
  });

  if (app.customFrameImg) {
    if (cardCustom) cardCustom.className = 'p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center justify-between bg-brand-50/90 border-brand-600 shadow-sm';
    if (badge) badge.classList.remove('hidden');
    if (calibrateBtn) calibrateBtn.classList.remove('hidden');
    if (subtext) subtext.textContent = `Frame Osa first meeting: ${app.customFrameName} (${app.customFrameImg.width}×${app.customFrameImg.height}px)`;
    if (homeFrameName) homeFrameName.textContent = `Osa first meeting (${app.customFrameName})`;
    if (homeFrameDesc) homeFrameDesc.textContent = app.detectedSlots ? `Đã tự động khớp ${app.slotCount} ô trong suốt` : `Bố cục ${app.slotCount} ô tuỳ chỉnh`;
    if (homeFrameThumb) homeFrameThumb.innerHTML = `<img src="${app.customFrameImg.src}" class="w-full h-full object-contain" />`;
  } else {
    if (badge) badge.classList.add('hidden');
    if (calibrateBtn) calibrateBtn.classList.add('hidden');
    if (subtext) subtext.textContent = 'Nhấn để tải file Frame PNG cá nhân của bạn (Tự động khớp 6 ô trống)';
    if (homeFrameThumb) homeFrameThumb.innerHTML = `<span class="text-xs font-bold text-brand-600">OSA</span>`;

    if (app.presetLayout === 'grid2x3') {
      if (card2x3) card2x3.className = 'p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center justify-between bg-brand-50/90 border-brand-600 shadow-sm';
      if (homeFrameName) homeFrameName.textContent = 'Frame: Osa first meeting (2×3)';
      if (homeFrameDesc) homeFrameDesc.textContent = 'OSA BOOTH • 6 ảnh dọc (10×15cm)';
    } else if (app.presetLayout === 'landscape_4') {
      if (card4) card4.className = 'p-4 rounded-2xl border-2 bg-brand-50/90 border-brand-600 shadow-sm cursor-pointer';
      if (homeFrameName) homeFrameName.textContent = 'Frame: 4 ảnh ngang (2×2)';
      if (homeFrameDesc) homeFrameDesc.textContent = 'OSA BOOTH • 4 ảnh ngang';
    } else {
      if (card3x2) card3x2.className = 'p-4 rounded-2xl border-2 transition-all cursor-pointer flex items-center justify-between bg-brand-50/90 border-brand-600 shadow-sm';
      if (homeFrameName) homeFrameName.textContent = 'Frame: Osa first meeting (3×2)';
      if (homeFrameDesc) homeFrameDesc.textContent = 'OSA BOOTH • 6 ảnh ngang';
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
