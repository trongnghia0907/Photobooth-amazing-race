/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function triggerSingleRetake(app, slotIndex) {
  app.clearTimers();
  app.singleRetakeIndex = slotIndex;
  app.updateCaptureScreenUI();
  app.startOrContinueSequence();
}

export function deleteSingleSlot(app, slotIndex) {
  app.clearTimers();
  app.photos[slotIndex] = null;
  app.singleRetakeIndex = slotIndex;
  app.updateCaptureScreenUI();
  app.showToast(`Đã xoá ô #${slotIndex + 1}. Nhấn Bắt đầu để chụp lại ô này!`, 'info');
}

export function cancelSingleRetake(app) {
  app.clearTimers();
  app.singleRetakeIndex = null;
  app.updateCaptureScreenUI();
}

export function resetSessionShots(app) {
  app.clearTimers();
  app.photos = [null, null, null, null, null, null];
  app.singleRetakeIndex = null;
  app.updateCaptureScreenUI();
  app.showToast('Đã làm mới toàn bộ 6 ô ảnh.', 'info');
}
