/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function goToScreen(app, screenName) {
  if(screenName!=='result' && (app.serverSession?.finalized||app.finalOperation?.confirmationStarted)){
    app.showToast('This session is finalized or waiting to be saved. Retry saving if there is an error; start a New Session to take or edit another photo.','info');return;
  }
  app.clearTimers();
  app.currentScreen = screenName;
  // Home and Capture share the same live camera. Result releases the lease;
  // an explicit navigation cancelling an in-flight connect still cleans up.
  if (screenName === 'result' || (screenName === 'home' && app.hostConnectRequest)) app.releaseHostCamera();
  app.transitionSession(screenName === 'result' ? 'EDIT' : screenName === 'capture' ? 'PREVIEW' : 'RESET');
  app.syncPersistenceUI();

  const homeSec = document.getElementById('screenHome');
  const capSec = document.getElementById('screenCapture');
  const resSec = document.getElementById('screenResult');

  if (homeSec) homeSec.classList.toggle('hidden', screenName !== 'home');
  if (capSec) capSec.classList.toggle('hidden', screenName !== 'capture');
  if (resSec) resSec.classList.toggle('hidden', screenName !== 'result');

  if (screenName === 'capture') {
    app.updateCaptureScreenUI();
  } else if (screenName === 'result') {
    app.renderCompositeCanvas();
    app.generateQRCodeForCurrentPhoto(false);
  }
  app.syncSetupLayout();
  if(screenName==='home'&&app.cameraSource==='host'&&!app.hostPreviewHealthy&&!app.hostConnectRequest&&!app.persistenceBusy&&!app.resumeRecoveryPending){
    app.prepareHostCamera().catch(error=>app.showToast(error.message,'error'));
  }
}
