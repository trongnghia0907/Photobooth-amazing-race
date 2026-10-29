/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function getSixSlotCoordinates(app, canvasW, canvasH) {
  if (app.customFrameImg && app.detectedSlots && app.detectedSlots.length === 6) {
    return app.detectedSlots.map(s => ({
      x: Math.max(0, (s.x - 0.005) * canvasW),
      y: Math.max(0, (s.y - 0.005) * canvasH),
      w: Math.min(canvasW, (s.w + 0.01) * canvasW),
      h: Math.min(canvasH, (s.h + 0.01) * canvasH)
    }));
  }

  const isLandscape = canvasW > canvasH;
  const cols = isLandscape ? 3 : 2;
  const rows = isLandscape ? 2 : 3;

  const padX = (app.slotMetrics.padX / 100) * canvasW;
  const padTop = (app.slotMetrics.padTop / 100) * canvasH;
  const padBottom = (app.slotMetrics.padBottom / 100) * canvasH;
  const gapX = (app.slotMetrics.gap / 100) * canvasW;
  const gapY = (app.slotMetrics.gap / 100) * canvasW;

  const availW = canvasW - padX * 2 - gapX * (cols - 1);
  const availH = canvasH - padTop - padBottom - gapY * (rows - 1);

  const slotW = availW / cols;
  const slotH = availH / rows;

  const slots = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      slots.push({
        x: padX + c * (slotW + gapX),
        y: padTop + r * (slotH + gapY),
        w: slotW,
        h: slotH
      });
    }
  }
  return slots;
}

export function renderCompositeCanvas(app) {
  const canvas = document.getElementById('compositeCanvas');
  if (!canvas) return;

  let cw = 1200;
  let ch = 1800;

  if (app.customFrameImg) {
    cw = app.customFrameImg.width;
    ch = app.customFrameImg.height;
    if (cw < 900) {
      const scale = 1200 / cw;
      cw = Math.round(cw * scale);
      ch = Math.round(ch * scale);
    }
  } else if (app.presetLayout === 'grid3x2') {
    cw = 1800;
    ch = 1200;
  }

  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = app.frameBgColor;
  ctx.fillRect(0, 0, cw, ch);

  if (!app.customFrameImg) {
    app.drawBuiltInFrameDecorationsBackground(ctx, cw, ch);
  }

  const slots = app.getSixSlotCoordinates(cw, ch);
  const activeFilterObj = app.filters.find(f => f.id === app.selectedFilter) || app.filters[0];

  slots.forEach((slot, idx) => {
    const photoCanvas = app.photos[idx];
    ctx.save();
    const radius = app.customFrameImg ? Math.min(cw, ch) * 0.008 : Math.min(cw, ch) * 0.018;
    app.roundRectPath(ctx, slot.x, slot.y, slot.w, slot.h, radius);
    ctx.clip();

    if (photoCanvas) {
      ctx.filter = activeFilterObj.css;
      app.drawImageCover(ctx, photoCanvas, slot.x, slot.y, slot.w, slot.h);
      ctx.filter = 'none';
    } else {
      ctx.fillStyle = '#0F172A';
      ctx.fillRect(slot.x, slot.y, slot.w, slot.h);
      ctx.fillStyle = '#94A3B8';
      ctx.font = `bold ${Math.round(cw * 0.025)}px "Plus Jakarta Sans", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`Ảnh #${idx + 1}`, slot.x + slot.w / 2, slot.y + slot.h / 2);
    }
    ctx.restore();
  });

  if (app.customFrameImg) {
    ctx.drawImage(app.customFrameImg, 0, 0, cw, ch);
  } else {
    app.drawBuiltInFrameForegroundTexts(ctx, cw, ch);
  }

  app.placedStickers.forEach(st => {
    ctx.save();
    const px = st.x * cw;
    const py = st.y * ch;
    const pSize = st.size * Math.min(cw, ch);
    if (st.img) {
      ctx.drawImage(st.img, px - pSize / 2, py - pSize / 2, pSize, pSize);
    } else if (st.emoji) {
      ctx.font = `${Math.round(pSize)}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(st.emoji, px, py);
    }
    ctx.restore();
  });

  try {
    const dataUrl = canvas.toDataURL('image/png');
    const printImg = document.getElementById('printImageElement');
    if (printImg) printImg.src = dataUrl;
    const mobileImg = document.getElementById('mobileModalImage');
    if (mobileImg) mobileImg.src = dataUrl;
  } catch (e) {}
}

export function drawBuiltInFrameDecorationsBackground(app, ctx, cw, ch) {
  const grad = ctx.createRadialGradient(cw * 0.5, ch * 0.5, cw * 0.1, cw * 0.5, ch * 0.5, cw * 0.8);
  grad.addColorStop(0, 'rgba(255, 255, 255, 0.12)');
  grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, cw, ch);
}

export function drawBuiltInFrameForegroundTexts(app, ctx, cw, ch) {
  const isLightBg = app.isColorLight(app.frameBgColor);
  const primaryTextColor = isLightBg ? '#0F172A' : '#FFFFFF';
  const secondaryTextColor = isLightBg ? '#2563EB' : '#BAE0FD';

  ctx.save();
  ctx.textAlign = 'center';

  if (app.customTexts.topText) {
    ctx.fillStyle = secondaryTextColor;
    ctx.font = `800 ${Math.round(ch * 0.022)}px "Plus Jakarta Sans", sans-serif`;
    ctx.fillText(app.customTexts.topText.toUpperCase(), cw / 2, ch * 0.042);
  }

  if (app.customTexts.cardTitle) {
    ctx.fillStyle = primaryTextColor;
    ctx.font = `700 ${Math.round(ch * 0.036)}px "Fredoka", "Plus Jakarta Sans", sans-serif`;
    ctx.fillText(app.customTexts.cardTitle, cw / 2, ch * 0.915);
  }

  if (app.customTexts.brandingText) {
    ctx.fillStyle = secondaryTextColor;
    ctx.font = `600 ${Math.round(ch * 0.017)}px "Plus Jakarta Sans", sans-serif`;
    ctx.fillText(app.customTexts.brandingText, cw / 2, ch * 0.955);
  }

  ctx.restore();
}
