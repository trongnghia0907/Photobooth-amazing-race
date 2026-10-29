/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function renderColorSwatches(app) {
  const grid = document.getElementById('colorSwatchesGrid');
  if (!grid) return;
  grid.innerHTML = app.colorSwatches.map(hex => {
    const active = hex.toLowerCase() === app.frameBgColor.toLowerCase();
    return `<button onclick="app.setFrameBackgroundColor('${hex}')" class="h-11 rounded-2xl border-2 transition-transform hover:scale-105 ${active ? 'border-brand-600 ring-2 ring-brand-300 scale-105' : 'border-slate-200'}" style="background-color: ${hex};"></button>`;
  }).join('');
}

export function setFrameBackgroundColor(app, hex) {
  app.frameBgColor = hex;
  const picker = document.getElementById('customColorPicker');
  const hexLabel = document.getElementById('customColorHexLabel');
  if (picker) picker.value = hex;
  if (hexLabel) hexLabel.textContent = hex.toUpperCase();
  app.renderColorSwatches();
  app.renderCompositeCanvas();
  app.scheduleQRCodeUpdate();
}

export function updateCustomTextsUI(app) {
  const top = document.getElementById('inputTopText');
  const card = document.getElementById('inputCardTitle');
  const brand = document.getElementById('inputBrandingText');
  if (top) top.value = app.customTexts.topText;
  if (card) card.value = app.customTexts.cardTitle;
  if (brand) brand.value = app.customTexts.brandingText;
}

export function updateCustomTexts(app) {
  app.customTexts.topText = document.getElementById('inputTopText').value;
  app.customTexts.cardTitle = document.getElementById('inputCardTitle').value;
  app.customTexts.brandingText = document.getElementById('inputBrandingText').value;
  app.renderCompositeCanvas();
  app.scheduleQRCodeUpdate();
}
