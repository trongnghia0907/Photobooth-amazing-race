/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function triggerSingleRetake(app, slotIndex) {
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;
  if(app.serverSession?.finalized||app.finalOperation?.confirmationStarted)return;
  if(!Number.isInteger(slotIndex)||slotIndex<0||slotIndex>=app.slotCount)return;
  app.retakeReturnToReview=app.currentScreen==='result'||app.photos.every(Boolean);
  if(app.guestWorkflowActive&&app.currentScreen==='result')app.goToScreen('capture');
  app.clearTimers();
  app.singleRetakeIndex = slotIndex;
  app.updateCaptureScreenUI();
  // Selecting a slot only opens management/preview. Capture needs an explicit
  // countdown or instant action, even when the camera connection completes.
  const epoch=app.captureEpoch;
  if(app.cameraSource==='host'&&!app.hostPreviewHealthy)app.prepareHostCamera().catch(error=>{
    if(epoch===app.captureEpoch&&app.singleRetakeIndex===slotIndex)app.reportSaveError(error);
  });
}

export async function deleteSingleSlot(app, slotIndex) {
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;
  app.clearTimers();
  if (await app.removeStoredPhotos(slotIndex)) {
    app.showToast(`Slot #${slotIndex + 1} deleted. Select Start to capture it again.`, 'info');
  }
}

export function cancelSingleRetake(app) {
  if(app.captureBusy||app.persistenceBusy)return;
  const review=app.retakeReturnToReview;
  app.clearTimers();
  app.singleRetakeIndex = null;
  app.retakeReturnToReview=false;
  if(review&&app.photos.every(Boolean)){app.goToScreen('result');return;}
  app.updateCaptureScreenUI();
}

export async function resetSessionShots(app) {
  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return false;
  app.clearTimers();
  app.retakeReturnToReview=false;
  if (!await app.removeStoredPhotos()) return false;
  app.showToast(`All ${app.slotCount} photo slots have been reset.`, 'info');
  return true;
}
