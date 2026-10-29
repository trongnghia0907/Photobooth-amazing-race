/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function openSettingsModal(app) {
  document.getElementById('settingsModal').classList.remove('hidden');
}

export function closeSettingsModal(app) {
  app.syncSettingsFromModal();
  document.getElementById('settingsModal').classList.add('hidden');
}

export function syncSettingsFromModal(app) {
  app.fullAutoMode = document.getElementById('chkFullAuto').checked;
  app.autoPrintPopup = document.getElementById('chkAutoPrintPopup').checked;
  app.imgbbApiKey = document.getElementById('imgbbApiKeyInput').value || '';
  app.updateAutoModeUI();
}
