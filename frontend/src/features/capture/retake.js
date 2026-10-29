/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function triggerSingleRetake(app, slotIndex) {
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;
  app.clearTimers();
  app.singleRetakeIndex = slotIndex;
  app.updateCaptureScreenUI();
  app.startOrContinueSequence();
}

export async function deleteSingleSlot(app, slotIndex) {
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;
  app.clearTimers();
  if (await app.removeStoredPhotos(slotIndex)) {
    app.showToast(`Đã xoá ô #${slotIndex + 1}. Nhấn Bắt đầu để chụp lại ô này!`, 'info');
  }
}

export function cancelSingleRetake(app) {
  app.clearTimers();
  app.singleRetakeIndex = null;
  app.updateCaptureScreenUI();
}

export async function resetSessionShots(app) {
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return false;
  app.clearTimers();
  if (!await app.removeStoredPhotos()) return false;
  app.showToast(`Đã làm mới toàn bộ ${app.slotCount} ô ảnh.`, 'info');
  return true;
}
