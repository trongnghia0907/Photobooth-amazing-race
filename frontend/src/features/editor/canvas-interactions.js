/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function setupCanvasStickerInteractions(app) {
  const canvas = document.getElementById('compositeCanvas');
  if (!canvas) return;

  const getNormalizedPos = (clientX, clientY) => {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (clientX - rect.left) / rect.width,
      y: (clientY - rect.top) / rect.height
    };
  };

  const onPointerDown = (clientX, clientY) => {
    const pos = getNormalizedPos(clientX, clientY);
    for (let i = app.placedStickers.length - 1; i >= 0; i--) {
      const st = app.placedStickers[i];
      const dist = Math.hypot(pos.x - st.x, pos.y - st.y);
      if (dist <= st.size * 0.75) {
        app.draggingSticker = st;
        app.dragOffsetX = pos.x - st.x;
        app.dragOffsetY = pos.y - st.y;
        return true;
      }
    }
    return false;
  };

  const onPointerMove = (clientX, clientY) => {
    if (!app.draggingSticker) return;
    const pos = getNormalizedPos(clientX, clientY);
    app.draggingSticker.x = Math.max(0.02, Math.min(0.98, pos.x - app.dragOffsetX));
    app.draggingSticker.y = Math.max(0.02, Math.min(0.98, pos.y - app.dragOffsetY));
    app.renderCompositeCanvas();
  };

  const onPointerUp = () => {
    if (app.draggingSticker) {
      app.draggingSticker = null;
      app.scheduleQRCodeUpdate();
    }
  };

  canvas.addEventListener('mousedown', e => onPointerDown(e.clientX, e.clientY));
  window.addEventListener('mousemove', e => onPointerMove(e.clientX, e.clientY));
  window.addEventListener('mouseup', onPointerUp);

  canvas.addEventListener('touchstart', e => {
    if (e.touches.length === 1) {
      const hit = onPointerDown(e.touches[0].clientX, e.touches[0].clientY);
      if (hit) e.preventDefault();
    }
  }, { passive: false });

  window.addEventListener('touchmove', e => {
    if (app.draggingSticker && e.touches.length === 1) {
      e.preventDefault();
      onPointerMove(e.touches[0].clientX, e.touches[0].clientY);
    }
  }, { passive: false });

  window.addEventListener('touchend', onPointerUp);
}
