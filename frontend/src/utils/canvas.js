/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function isColorLight(app, hex) {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16) || 0;
  const g = parseInt(clean.substring(2, 4), 16) || 0;
  const b = parseInt(clean.substring(4, 6), 16) || 0;
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.62;
}

export function roundRectPath(app, ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

export function drawImageCover(app, ctx, img, x, y, w, h) {
  const iw = img.width;
  const ih = img.height;
  const r = Math.max(w / iw, h / ih);
  const cw = w / r;
  const ch = h / r;
  const cx = (iw - cw) * 0.5;
  const cy = (ih - ch) * 0.5;
  ctx.drawImage(img, cx, cy, cw, ch, x, y, w, h);
}

export function canvasToBlob(app, canvas, mimeType = 'image/jpeg', quality = 0.92) {
  return new Promise((resolve) => {
    if (canvas.toBlob) {
      canvas.toBlob((blob) => resolve(blob), mimeType, quality);
    } else {
      const dataURL = canvas.toDataURL(mimeType, quality);
      const byteString = atob(dataURL.split(',')[1]);
      const ab = new ArrayBuffer(byteString.length);
      const ia = new Uint8Array(ab);
      for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
      resolve(new Blob([ab], { type: mimeType }));
    }
  });
}
