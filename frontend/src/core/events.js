/** Temporary compatibility boundary for original static/dynamic inline handlers.
 * Remove only when both markup and innerHTML templates use delegated listeners.
 */
export function bindEvents(app) {
  window.app = app;
  const cleanup = () => {
    app.clearTimers();
    app.stopPrintPolling();
    app.releaseHostCamera();
    app.stopCurrentStreams();
  };
  window.addEventListener('pagehide', cleanup);
  return () => {
    window.removeEventListener('pagehide', cleanup);
    cleanup();
    delete window.app;
  };
}
