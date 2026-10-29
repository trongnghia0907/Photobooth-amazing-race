/** Pure event-driven phase model; busy flags retain their separate timer/network ownership. */
const targets = Object.freeze({ RESET: 'IDLE', PREVIEW: 'PREVIEW', COUNTDOWN: 'COUNTDOWN',
  CAPTURE: 'CAPTURING', REVIEW: 'REVIEW', EDIT: 'EDITING', BUSY: 'SAVING', SAVED: 'READY', FAIL: 'ERROR' });

export function nextPhase(current, event) {
  if (!Object.values(targets).includes(current) || !targets[event]) throw new Error('Invalid session transition');
  return targets[event];
}

export function transitionSession(app, event) {
  app.sessionPhase = nextPhase(app.sessionPhase, event);
  const panel = typeof document === 'undefined' ? null : document.getElementById('sessionPersistencePanel');
  if (panel?.dataset) panel.dataset.phase = app.sessionPhase;
}
