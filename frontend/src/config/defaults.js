/** Phase 1 is a demonstration, never an event-ready camera/print system. */
export const defaults = Object.freeze({
  demoEnabled: import.meta.env?.DEV || import.meta.env?.MODE === 'demo',
  enableLegacyUpload: import.meta.env?.DEV && import.meta.env?.VITE_ENABLE_LEGACY_UPLOAD === 'true',
  enableLegacyShutter: import.meta.env?.DEV && import.meta.env?.VITE_ENABLE_LEGACY_SHUTTER === 'true',
  autoPrintPopup: false,
});

export function requireDemo() {
  if (!defaults.demoEnabled) throw new Error('DEMO disabled. Real camera integration is not implemented.');
}
