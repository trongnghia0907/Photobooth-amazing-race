import * as client from './session-client.js';
import { newId } from '../utils/ids.js';
import {rememberSession,forgetRememberedSession} from './session-recovery.js';

const key = () => newId();
const pending = app => app.pendingPhotos.some(Boolean) || app.pendingDeletion || app.hostCaptureOperation;

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
  app.syncHostCaptureUI();
  app.syncPrintUI();
  const message = document.getElementById('sessionSaveStatus');
  if (!message) return;
  message.textContent = app.persistenceError || (app.persistenceBusy ? 'Waiting for the backend to save your photo…'
    : app.saveState === 'saved' ? 'Your composite has been saved and the session is complete on the laptop.'
    : app.sessionContext?.id ? `Saved ${app.serverSession?.photos.length || 0}/${app.slotCount} captured photos. The composite is saved only after confirmation.`
    : 'A new session will be created when you start capturing.');
  message.dataset.state = app.saveState;
  if(app.eventConfig?.event_mode)message.textContent=app.persistenceError?'Your photo could not be saved. Please ask an event staff member for help.':app.persistenceBusy?'Saving your photo…':app.saveState==='saved'?'Your photo has been saved.':app.sessionContext?.id?`${app.photos.filter(Boolean).length}/${app.slotCount} photos captured. Review and confirm your photo.`:'Choose a layout and start capturing when you are ready.';
  const retry = document.getElementById('retrySessionSaveBtn');
  retry.classList.toggle('hidden', !app.persistenceError);
  retry.disabled = app.persistenceBusy;
  const confirm = document.getElementById('confirmSessionBtn');
  confirm.classList.toggle('hidden', app.currentScreen !== 'result'||(app.guestWorkflowActive&&!!app.serverSession?.finalized));
  confirm.disabled = app.persistenceBusy || app.captureBusy || (!app.serverSession?.finalized && !app.photos.every(Boolean)) || !!pending(app);
  const locked=!!(app.serverSession?.finalized||app.finalOperation?.confirmationStarted);
  confirm.textContent = app.serverSession?.finalized ? 'Photo Confirmed — Check QR' : 'Confirm & Save Photo on Laptop';
  for(const node of document.querySelectorAll('[id^="tabPanel_"], [id^="tabBtn_"]')){node.inert=locked;if('disabled' in node)node.disabled=locked;}
  const canvas=document.getElementById('compositeCanvas');if(canvas)canvas.inert=locked;
  const notice=document.getElementById('finalPhotoNotice');if(notice)notice.hidden=!locked;
  const qrConfirm=document.getElementById('confirmQRCodeBtn');
  if(qrConfirm) {
    qrConfirm.disabled=app.persistenceBusy || app.captureBusy || app.shareBusy;
    qrConfirm.textContent=app.persistenceBusy ? 'Saving photo & creating QR…' : app.saveState==='saved' ? 'Create / Retry QR' : '✓ Confirm & Create QR';
  }
}

export async function ensureSession(app) {
  if (!app.sessionContext) {
    app.sessionContext = {
      id: null, token: newId().replaceAll('-', '') + newId().replaceAll('-', ''),
      createKey: key(), slotCount: app.slotCount, layout: app.presetLayout, request: null,
    };
  }
  const context = app.sessionContext;
  rememberSession(context);
  if (context.id) return context;
  if (!context.request) {
    context.request = client.createSession(context, context.layout).then(result => {
      context.id = result.session_id;
      if (app.sessionContext === context) {rememberSession(context);app.serverSession = result;}
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
    await app.updateSessionLayout();
    app.persistenceError = '';
    app.saveState = 'capturing';
    app.transitionSession('PREVIEW');
    return true;
  } catch (error) {
    failed(app, error);
    return false;
  } finally { busy(app, false); }
}

export async function updateSessionLayout(app) {
  const context=app.sessionContext;
  if(!context)return;
  if(context.layoutRequest)return context.layoutRequest;
  if(context.layout===app.presetLayout&&context.slotCount===app.slotCount)return;
  const operation={layout:app.presetLayout,slotCount:app.slotCount,key:key()};
  context.layoutRequest=(async()=>{
    await app.ensureSession();
    const result=await client.updateLayout(context,operation);
    if(app.sessionContext!==context)return;
    context.layout=operation.layout;context.slotCount=operation.slotCount;
    app.serverSession=result;rememberSession(context);
  })();
  try{await context.layoutRequest;}finally{context.layoutRequest=null;}
}

export async function saveSetupLayout(app) {
  if(!app.sessionContext)return;
  busy(app,true);
  try{await app.updateSessionLayout();app.persistenceError='';}
  catch(error){failed(app,error);}
  finally{busy(app,false);}
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
    app.showToast('Retry saving the pending photo before deleting or resetting it.', 'info');
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
  if(app.resumeRecoveryPending)return app.restoreSavedSession();
  if (app.hostCaptureOperation) return app.retryHostCapture();
  if (app.finalOperation && !pending(app)) return app.confirmAndSaveSession();
  busy(app, true);
  try {
    await app.ensureSession();
    await app.updateSessionLayout();
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

export async function confirmAndSaveSession(app,publishToEvent=false) {
  if (app.persistenceBusy || app.captureBusy || pending(app)) return;
  if (app.serverSession?.finalized) return app.generateQRCodeForCurrentPhoto(true);
  if (!app.photos.every(Boolean)) return;
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
    // Only the disclosed "confirm, project & QR" action opts into display.
    // Recovery of an already-confirmed private snapshot must stay private.
    const previousConsent=app.finalOperation?.editor?.event_display_consent===true;
    const eventConsent=app.finalOperation?.confirmationStarted?previousConsent:publishToEvent===true||previousConsent;
    if (!app.finalOperation || app.finalOperation.dataUrl !== dataUrl || app.finalOperation.shotsRevision !== app.serverSession.shots_revision || (!app.finalOperation.confirmationStarted&&app.finalOperation.editor?.event_display_consent!==eventConsent)) {
      app.finalOperation = {
        dataUrl, blob: await app.canvasToBlob(canvas, 'image/png'),
        shotsRevision: app.serverSession.shots_revision,
        uploadKey: key(), completeKey: key(), compositeId: null,
        editor: { event_display_consent:eventConsent, layout: app.presetLayout, filter: app.selectedFilter, frame: app.customFrameName,
          event_display_consent_source:publishToEvent===true?'confirmation_projection_qr_v1':app.finalOperation?.editor?.event_display_consent_source||null,
          background: app.frameBgColor, texts: { ...app.customTexts },
          stickers: app.placedStickers.map(({ x, y, size, emoji, img }) => ({ x, y, size, emoji, uploaded: !!img })) },
      };
    }
    const operation = app.finalOperation;
    if (!operation.compositeId) {
      const uploaded = await client.uploadComposite(app.sessionContext, operation);
      operation.compositeId = uploaded.composite.id;
    }
    operation.confirmationStarted=true;
    const completed = await client.completeSession(app.sessionContext, operation);
    if (completed.status !== 'completed' || completed.session_id !== app.sessionContext.id || completed.composite?.id !== operation.compositeId) {
      throw new Error('The backend did not confirm that the correct composite was finalized. Please retry saving.');
    }
    app.serverSession = completed;
    app.releaseHostCamera();
    app.lastSavedImage = dataUrl;
    app.saveState = 'saved';
    // Only the confirmed composite remains in the kiosk after a durable ACK.
    // On a lost/failed confirmation response these working canvases are kept
    // until the same confirmation request can be resolved safely.
    app.photos = Array(app.slotCount).fill(null);
    app.singleRetakeIndex = null;
    app.renderSixSlotsGrid();
    app.renderCaptureDots();
    app.transitionSession('SAVED');
    app.persistenceError = '';
    await app.generateQRCodeForCurrentPhoto(true);
    app.showToast('The composite has been saved and the session is complete on the laptop.', 'success');
  } catch (error) {
    // A known failed confirmation is still an editable working session. If
    // the response was merely lost (or status cannot be read), keep the chosen
    // snapshot locked and retry its key instead of inventing another final.
    const operation=app.finalOperation;
    if(operation?.confirmationStarted && app.sessionContext){
      try{
        const stored=await client.getSession(app.sessionContext);
        if(!stored.finalized){
          app.serverSession=stored;operation.confirmationStarted=false;
          if(stored.status==='failed'){
            operation.compositeId=null;operation.uploadKey=key();operation.completeKey=key();
          }
        }
      }catch{/* Outcome unknown: retain working canvases and the original key. */}
    }
    failed(app, error);
  }
  finally { resultScreen.inert = false; busy(app, false); }
}

export function forgetSession(app) {
  if (app.persistenceBusy || app.captureBusy || app.shareBusy || pending(app) || app.persistenceError) {
    app.showToast('This session still has unsaved data. Retry saving before starting a new guest session.', 'info');
    return false;
  }
  app.stopPrintPolling();
  forgetRememberedSession();
  app.releaseHostCamera();
  app.printOperation = null;
  app.printError = '';
  app.sessionContext = null;
  app.activeShare = null;
  app.shareError = '';
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
