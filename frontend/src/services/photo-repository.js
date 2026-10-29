import * as client from './session-client.js';

const key = () => crypto.randomUUID();
const pending = app => app.pendingPhotos.some(Boolean) || app.pendingDeletion;

function busy(app, value) {
  app.persistenceBusy = value;
  if (value) app.transitionSession('BUSY');
  app.syncPersistenceUI();
}

function failed(app, error) {
  app.persistenceError = error.message;
  app.saveState = 'error';
  app.transitionSession('FAIL');
  app.syncPersistenceUI();
  app.showToast(error.message, 'error');
}

export function reportSaveError(app, error) { failed(app, error); }

export function hasPendingWork(app) { return !!pending(app); }

export function syncPersistenceUI(app) {
  const message = document.getElementById('sessionSaveStatus');
  if (!message) return;
  message.textContent = app.persistenceError || (app.persistenceBusy ? 'Đang chờ backend lưu dữ liệu…'
    : app.saveState === 'saved' ? 'Đã lưu ảnh ghép và hoàn tất phiên trên laptop.'
    : app.sessionContext?.id ? `Đã lưu ${app.serverSession?.photos.length || 0}/${app.slotCount} ảnh chụp. Ảnh ghép chỉ lưu khi bấm xác nhận.`
    : 'Backend: phiên mới sẽ được tạo khi bắt đầu chụp.');
  message.dataset.state = app.saveState;
  const retry = document.getElementById('retrySessionSaveBtn');
  retry.classList.toggle('hidden', !app.persistenceError);
  retry.disabled = app.persistenceBusy;
  const confirm = document.getElementById('confirmSessionBtn');
  confirm.classList.toggle('hidden', app.currentScreen !== 'result');
  confirm.disabled = app.persistenceBusy || app.captureBusy || !app.photos.every(Boolean) || !!pending(app);
  confirm.textContent = app.saveState === 'saved' ? 'Đã lưu — Xác nhận lại' : 'Xác nhận & Lưu ảnh trên laptop';
}

export async function ensureSession(app) {
  if (!app.sessionContext) {
    app.sessionContext = {
      id: null, token: crypto.randomUUID().replaceAll('-', '') + crypto.randomUUID().replaceAll('-', ''),
      createKey: key(), slotCount: app.slotCount, layout: app.presetLayout, request: null,
    };
  }
  const context = app.sessionContext;
  if (context.id) return context;
  if (!context.request) {
    context.request = client.createSession(context, context.layout).then(result => {
      context.id = result.session_id;
      app.serverSession = result;
      return context;
    }).finally(() => { context.request = null; });
  }
  return context.request;
}

export async function prepareSession(app) {
  if (app.persistenceBusy) return false;
  busy(app, true);
  try {
    await app.ensureSession();
    app.persistenceError = '';
    app.saveState = 'capturing';
    app.transitionSession('PREVIEW');
    return true;
  } catch (error) {
    failed(app, error);
    return false;
  } finally { busy(app, false); }
}

async function savePhoto(app, operation) {
  const context = await app.ensureSession();
  // Cache the exact Blob so every retry uses the same payload/key.
  operation.blob ||= await app.canvasToBlob(operation.canvas, 'image/png');
  const result = await client.uploadPhoto(context, operation, operation.blob);
  if (app.sessionContext !== context) return false;
  app.serverSession = result;
  app.photos[operation.slot] = operation.canvas;
  app.pendingPhotos[operation.slot] = null;
  app.finalOperation = null;
  app.lastSavedImage = '';
  app.saveState = 'capturing';
    app.transitionSession('PREVIEW');
  app.persistenceError = '';
  app.updateCaptureScreenUI();
  return true;
}

export async function acceptPhoto(app, slot, canvas, source) {
  if (app.persistenceBusy) return false;
  const operation = { slot, canvas, source, key: key(), blob: null };
  app.pendingPhotos[slot] = operation;
  busy(app, true);
  try { return await savePhoto(app, operation); }
  catch (error) { failed(app, error); return false; }
  finally { busy(app, false); }
}

export async function acceptPhotoBatch(app, canvases) {
  if (app.persistenceBusy || pending(app)) return false;
  for (const [slot, canvas] of canvases.entries()) {
    app.pendingPhotos[slot] = { slot, canvas, source: 'manual_upload', key: key(), blob: null };
  }
  busy(app, true);
  try {
    for (const operation of app.pendingPhotos.filter(Boolean)) await savePhoto(app, operation);
    return true;
  } catch (error) { failed(app, error); return false; }
  finally { busy(app, false); }
}

async function saveDeletion(app, operation) {
  const context = await app.ensureSession();
  const result = await client.deletePhotos(context, operation);
  app.serverSession = result;
  if (operation.slot === null) {
    app.photos = Array(app.slotCount).fill(null);
    app.singleRetakeIndex = null;
  } else {
    app.photos[operation.slot] = null;
    app.singleRetakeIndex = operation.slot;
  }
  app.pendingDeletion = null;
  app.finalOperation = null;
  app.lastSavedImage = '';
  app.saveState = 'capturing';
    app.transitionSession('PREVIEW');
  app.persistenceError = '';
  app.updateCaptureScreenUI();
}

export async function removeStoredPhotos(app, slot = null) {
  if (app.persistenceBusy || app.captureBusy || pending(app)) {
    app.showToast('Hãy thử lưu lại ảnh đang chờ trước khi xóa/reset.', 'info');
    return false;
  }
  app.pendingDeletion = { slot, key: key() };
  busy(app, true);
  try { await saveDeletion(app, app.pendingDeletion); return true; }
  catch (error) { failed(app, error); return false; }
  finally { busy(app, false); }
}

export async function retrySessionSave(app) {
  if (app.persistenceBusy || app.captureBusy) return;
  if (app.finalOperation && !pending(app)) return app.confirmAndSaveSession();
  busy(app, true);
  try {
    await app.ensureSession();
    if (app.pendingDeletion) await saveDeletion(app, app.pendingDeletion);
    for (const operation of app.pendingPhotos.filter(Boolean)) await savePhoto(app, operation);
    app.persistenceError = '';
    app.saveState = 'capturing';
    app.transitionSession('PREVIEW');
    app.singleRetakeIndex = null;
    app.updateCaptureScreenUI();
    if (app.photos.every(Boolean)) app.onAllSixShotsCompleted();
  } catch (error) { failed(app, error); }
  finally { busy(app, false); }
}

export function onCompositeRendered(app, dataUrl) {
  if (!app.persistenceBusy) {
    app.saveState = dataUrl === app.lastSavedImage ? 'saved' : 'editing';
    app.transitionSession(app.saveState === 'saved' ? 'SAVED' : 'EDIT');
    app.syncPersistenceUI();
  }
}

export async function confirmAndSaveSession(app) {
  if (app.persistenceBusy || app.captureBusy || pending(app) || !app.photos.every(Boolean)) return;
  app.clearTimers();
  busy(app, true);
  // Freeze the editor only while its chosen snapshot is being persisted.
  const resultScreen = document.getElementById('screenResult');
  resultScreen.inert = true;
  try {
    await app.ensureSession();
    app.renderCompositeCanvas();
    const canvas = document.getElementById('compositeCanvas');
    const dataUrl = canvas.toDataURL('image/png');
    if (!app.finalOperation || app.finalOperation.dataUrl !== dataUrl || app.finalOperation.shotsRevision !== app.serverSession.shots_revision) {
      app.finalOperation = {
        dataUrl, blob: await app.canvasToBlob(canvas, 'image/png'),
        shotsRevision: app.serverSession.shots_revision,
        uploadKey: key(), completeKey: key(), compositeId: null,
        editor: { layout: app.presetLayout, filter: app.selectedFilter, frame: app.customFrameName,
          background: app.frameBgColor, texts: { ...app.customTexts },
          stickers: app.placedStickers.map(({ x, y, size, emoji, img }) => ({ x, y, size, emoji, uploaded: !!img })) },
      };
    }
    const operation = app.finalOperation;
    if (!operation.compositeId) {
      const uploaded = await client.uploadComposite(app.sessionContext, operation);
      operation.compositeId = uploaded.composite.id;
    }
    const completed = await client.completeSession(app.sessionContext, operation);
    if (completed.status !== 'completed' || completed.session_id !== app.sessionContext.id || completed.composite?.id !== operation.compositeId) {
      throw new Error('Backend chưa xác nhận hoàn tất đúng ảnh ghép. Hãy thử lưu lại.');
    }
    app.serverSession = completed;
    app.lastSavedImage = dataUrl;
    app.saveState = 'saved';
    app.transitionSession('SAVED');
    app.persistenceError = '';
    app.showToast('Backend đã lưu ảnh ghép và hoàn tất phiên trên laptop.', 'success');
  } catch (error) { failed(app, error); }
  finally { resultScreen.inert = false; busy(app, false); }
}

export function forgetSession(app) {
  if (app.persistenceBusy || app.captureBusy || pending(app) || app.persistenceError) {
    app.showToast('Phiên còn dữ liệu chưa lưu. Hãy thử lưu lại trước khi đổi khách.', 'info');
    return false;
  }
  app.sessionContext = null;
  app.serverSession = null;
  app.pendingPhotos = Array(app.slotCount).fill(null);
  app.pendingDeletion = null;
  app.finalOperation = null;
  app.lastSavedImage = '';
  app.saveState = 'idle';
  app.transitionSession('RESET');
  app.syncPersistenceUI();
  return true;
}
