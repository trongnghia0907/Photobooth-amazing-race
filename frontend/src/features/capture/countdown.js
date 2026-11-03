/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function startOrContinueSequence(app) {
  app.ensureAudio();
  if(app.persistenceBusy||app.captureBusy||app.sequenceStarting)return;
  if (app.isCapturingSequence) {
    app.sequencePaused=!app.sequencePaused;
    const state=app.countdownState;
    if(state){
      if(app.sequencePaused){
        state.remainingMs=Math.max(0,state.deadline-performance.now());
        clearTimeout(app.countdownTimerId);clearTimeout(app.sequenceTimerId);
        app.countdownTimerId=null;app.sequenceTimerId=null;
        document.getElementById('countdownOverlay')?.classList.add('hidden');
      }else{
        if(state.kind==='countdown')document.getElementById('countdownOverlay')?.classList.remove('hidden');
        state.resume();
      }
    }
    app.updateCaptureScreenUI();
    return;
  }

  if (app.persistenceBusy || app.captureBusy || app.hasPendingWork()) return;

  if (app.photos.every(p => p !== null) && app.singleRetakeIndex === null) {
    if (!await app.confirmResetShots()) return;
  }

  const epoch = app.captureEpoch;
  app.sequenceStarting=true;app.updateCaptureScreenUI();
  try{
  if (!await app.prepareSession() || epoch !== app.captureEpoch) return;
  if (app.cameraSource === 'host' && !app.hostPreviewHealthy) {
    try { await app.prepareHostCamera(); }
    catch(error) { app.reportSaveError(error);return; }
    if (epoch !== app.captureEpoch) return;
  }

  app.isCapturingSequence = true;
  app.sequencePaused=false;
  app.updateCaptureScreenUI();
  app.runNextShotCountdown();
  }finally{if(epoch===app.captureEpoch){app.sequenceStarting=false;app.updateCaptureScreenUI();}}
}

function schedule(app,kind,ms,callback,tick=()=>{}){
  const epoch=app.captureEpoch,key=kind==='countdown'?'countdownTimerId':'sequenceTimerId';
  const state={kind,remainingMs:ms,deadline:0,resume(){
    if(epoch!==app.captureEpoch||!app.isCapturingSequence||app.sequencePaused)return;
    state.deadline=performance.now()+state.remainingMs;
    const step=()=>{
      app[key]=null;
      if(epoch!==app.captureEpoch||app.sequencePaused||app.countdownState!==state)return;
      state.remainingMs=Math.max(0,state.deadline-performance.now());
      if(state.remainingMs<=0){app.countdownState=null;callback();return;}
      tick(Math.ceil(state.remainingMs/1000));
      app[key]=setTimeout(step,kind==='countdown'?(state.remainingMs%1000||1000):state.remainingMs);
    };step();
  }};
  app.countdownState=state;state.resume();
}

export function runNextShotCountdown(app) {
  if (!app.isCapturingSequence||app.sequencePaused||app.captureBusy||app.countdownState) return;

  const targetIndex = app.singleRetakeIndex !== null
    ? app.singleRetakeIndex
    : app.photos.findIndex(p => p === null);

  if (targetIndex === -1) {
    app.isCapturingSequence = false;
    app.updateCaptureScreenUI();
    app.onAllSixShotsCompleted();
    return;
  }

  app.updateCaptureScreenUI();

  const overlay = document.getElementById('countdownOverlay');
  const numEl = document.getElementById('countdownNumber');
  const labelEl = document.getElementById('countdownLabel');

  if (overlay) overlay.classList.remove('hidden');
  if (labelEl) {
    labelEl.textContent = app.singleRetakeIndex !== null
      ? `Retaking photo #${targetIndex + 1}...`
      : `Get ready for photo #${targetIndex + 1} of ${app.slotCount}...`;
  }

  const tick = remaining => {
    if (numEl) {
      numEl.textContent = remaining;
      numEl.classList.remove('count-animate');
      void numEl.offsetWidth;
      numEl.classList.add('count-animate');
    }
    app.playBeep(remaining === 1 ? 1200 : 800, 0.12);
  };

  app.transitionSession('COUNTDOWN');
  schedule(app,'countdown',app.countdownSeconds*1000,async () => {
      if (overlay) overlay.classList.add('hidden');

      const epoch = app.captureEpoch;
      app.captureBusy = true;
      app.transitionSession('CAPTURE');
      app.updateCaptureScreenUI();
      let accepted = false;
      try { accepted = (await app.capturePhoto(targetIndex)).accepted; }
      catch (error) { app.reportSaveError(error); }
      finally { app.captureBusy = false; app.syncPersistenceUI();app.updateCaptureScreenUI(); }
      if (epoch !== app.captureEpoch) return;
      if (!accepted) {
        app.isCapturingSequence = false;
        app.updateCaptureScreenUI();
        return;
      }

      if (app.singleRetakeIndex !== null) {
        app.singleRetakeIndex = null;
        app.retakeReturnToReview=false;
        app.isCapturingSequence = false;
        app.updateCaptureScreenUI();
        if (app.photos.every(p => p !== null)) {
          app.onAllSixShotsCompleted();
        }
      } else {
        if(app.guestWorkflowActive&&app.photos.every(Boolean)){
          app.isCapturingSequence=false;
          app.updateCaptureScreenUI();
          app.onAllSixShotsCompleted();
          return;
        }
        schedule(app,'gap',950,()=>app.runNextShotCountdown());
      }
  },tick);
}
