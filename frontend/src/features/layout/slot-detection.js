/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function detectSixTransparentRegions(app, img) {
  try {
    const width = img.naturalWidth || img.width;
    const height = img.naturalHeight || img.height;
    const scale = Math.min(1, 900 / Math.max(width, height));
    const scanW = Math.round(width * scale);
    const scanH = Math.round(height * scale);
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = scanW;
    tempCanvas.height = scanH;
    const ctx = tempCanvas.getContext('2d');
    ctx.drawImage(img, 0, 0, scanW, scanH);
    const imgData = ctx.getImageData(0, 0, scanW, scanH).data;

    const visited = new Uint8Array(scanW * scanH);
    const boxes = [];
    const isTransparent = (x, y) => imgData[(y * scanW + x) * 4 + 3] < 50;

    for (let y = 0; y < scanH; y++) {
      for (let x = 0; x < scanW; x++) {
        const pos = y * scanW + x;
        if (!visited[pos] && isTransparent(x, y)) {
          let minX = x, maxX = x, minY = y, maxY = y, count = 0;
          const queue = [pos];
          visited[pos] = 1;

          while (queue.length > 0) {
            const curr = queue.pop();
            const cx = curr % scanW;
            const cy = Math.floor(curr / scanW);
            count++;
            if (cx < minX) minX = cx;
            if (cx > maxX) maxX = cx;
            if (cy < minY) minY = cy;
            if (cy > maxY) maxY = cy;

            const neighbors = [
              cy > 0 ? curr - scanW : -1,
              cy < scanH - 1 ? curr + scanW : -1,
              cx > 0 ? curr - 1 : -1,
              cx < scanW - 1 ? curr + 1 : -1
            ];
            for (const n of neighbors) {
              if (n >= 0 && !visited[n]) {
                const nx = n % scanW;
                const ny = Math.floor(n / scanW);
                if (isTransparent(nx, ny)) {
                  visited[n] = 1;
                  queue.push(n);
                }
              }
            }
          }

          const bw = maxX - minX + 1;
          const bh = maxY - minY + 1;
          if (minX > 0 && minY > 0 && maxX < scanW - 1 && maxY < scanH - 1 &&
              count > (scanW * scanH * 0.03) && bw > scanW * 0.15 && bh > scanH * 0.12 && bw < scanW * 0.95) {
            boxes.push({ x: minX / scanW, y: minY / scanH, w: bw / scanW, h: bh / scanH });
          }
        }
      }
    }

    if (boxes.length === app.slotCount) {
      boxes.sort((a, b) => (Math.abs(a.y - b.y) > 0.08 ? a.y - b.y : a.x - b.x));
      return boxes;
    }
    return null;
  } catch (e) {
    return null;
  }
}

export function autoDetectTransparentHolesFromFrame(app) {
  const statusEl = document.getElementById('slotDetectStatus');
  if (!app.customFrameImg) {
    statusEl.textContent = 'Upload a PNG frame first.';
    statusEl.className = 'text-xs font-semibold text-amber-600';
    return;
  }
  const detected = app.detectSixTransparentRegions(app.customFrameImg);
  if (detected && detected.length === app.slotCount) {
    app.detectedSlots = detected;
    statusEl.textContent = `✅ Detected ${app.slotCount} transparent slots.`;
    statusEl.className = 'text-xs font-semibold text-emerald-600';
    if (app.currentScreen === 'result') app.renderCompositeCanvas();
  } else {
    app.detectedSlots = null;
    statusEl.textContent = `Using default margins. Could not detect ${app.slotCount} separate slots.`;
    statusEl.className = 'text-xs font-semibold text-brand-600';
  }
}
