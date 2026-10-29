/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function goToScreen(app, screenName) {
  app.clearTimers();
  app.currentScreen = screenName;
  app.transitionSession(screenName === 'result' ? 'EDIT' : screenName === 'capture' ? 'PREVIEW' : 'RESET');
  app.syncPersistenceUI();

  const homeSec = document.getElementById('screenHome');
  const capSec = document.getElementById('screenCapture');
  const resSec = document.getElementById('screenResult');

  if (homeSec) homeSec.classList.toggle('hidden', screenName !== 'home');
  if (capSec) capSec.classList.toggle('hidden', screenName !== 'capture');
  if (resSec) resSec.classList.toggle('hidden', screenName !== 'result');

  const navMap = {
    home: document.getElementById('stepNavHome'),
    capture: document.getElementById('stepNavCapture'),
    result: document.getElementById('stepNavResult')
  };
  Object.entries(navMap).forEach(([key, btn]) => {
    if (!btn) return;
    btn.className = key === screenName
      ? 'px-4 py-1.5 rounded-full text-xs font-bold transition-all bg-brand-600 text-white shadow-sm'
      : 'px-4 py-1.5 rounded-full text-xs font-bold transition-all text-brand-700 hover:bg-brand-100';
  });

  if (screenName === 'capture') {
    app.updateCaptureScreenUI();
  } else if (screenName === 'result') {
    app.renderCompositeCanvas();
    app.generateQRCodeForCurrentPhoto(false);
  }
}
