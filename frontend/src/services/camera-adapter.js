/** DEVELOPMENT adapter: delegates to the preserved mock/webcam canvas path.
 * A future RealCameraAdapter must return a transferred camera file, never this adapter.
 */
class MockCameraAdapter {
  constructor(app) { this.app = app; }
  async capture_photo(index) {
    const accepted = await this.app.captureFrameIntoSlot(index);
    return { accepted, photo: accepted ? this.get_captured_photo(index) : null };
  }
  get_captured_photo(index) { return this.app.serverSession?.photos.find(p => p.slot_index === index) || null; }
  start_live_view() { return this.app.startSimulatedCamera(); }
  stop_live_view() { return this.app.stopCurrentStreams(); }
}

export function capturePhoto(app, index) {
  app.cameraAdapter ||= new MockCameraAdapter(app);
  return app.cameraAdapter.capture_photo(index);
}
