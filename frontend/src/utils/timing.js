/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function clearTimers(app) {
  for (const key of ['sessionStartTimerId', 'sequenceTimerId', 'autoPrintTimerId', 'qrUpdateDebounceTimer']) {
    if (app[key]) clearTimeout(app[key]);
    app[key] = null;
  }
  if (app.countdownTimerId) {
    clearInterval(app.countdownTimerId);
    app.countdownTimerId = null;
  }
  if (app.autoGraceTimerId) {
    clearInterval(app.autoGraceTimerId);
    app.autoGraceTimerId = null;
  }
  app.isCapturingSequence = false;
  const overlay = document.getElementById('countdownOverlay');
  if (overlay) overlay.classList.add('hidden');
  const graceOverlay = document.getElementById('autoGraceOverlay');
  if (graceOverlay) graceOverlay.classList.add('hidden');
}

export function ensureAudio(app) {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    if (!app.audioCtx) app.audioCtx = new AudioContextClass();
    if (app.audioCtx.state === 'suspended') app.audioCtx.resume().catch(() => {});
  } catch (e) {}
}

export function playBeep(app, freq = 800, duration = 0.12) {
  try {
    app.ensureAudio();
    if (!app.audioCtx) return;
    const osc = app.audioCtx.createOscillator();
    const gain = app.audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, app.audioCtx.currentTime);
    gain.gain.setValueAtTime(0.15, app.audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, app.audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(app.audioCtx.destination);
    osc.start();
    osc.stop(app.audioCtx.currentTime + duration);
  } catch (e) {}
}

export function playShutterSound(app) {
  try {
    app.ensureAudio();
    if (!app.audioCtx) return;
    const now = app.audioCtx.currentTime;
    const osc = app.audioCtx.createOscillator();
    const gain = app.audioCtx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(1600, now);
    osc.frequency.exponentialRampToValueAtTime(180, now + 0.09);
    gain.gain.setValueAtTime(0.28, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
    osc.connect(gain);
    gain.connect(app.audioCtx.destination);
    osc.start(now);
    osc.stop(now + 0.09);
  } catch (e) {}
}
