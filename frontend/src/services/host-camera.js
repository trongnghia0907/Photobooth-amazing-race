import { defaults } from '../config/defaults.js';
import { newId } from '../utils/ids.js';
import { boothFetch } from './booth-access.js';
import { setCapturePaused } from '../features/capture/countdown.js';
import { rememberSession } from './session-recovery.js';

const FRAME_TIMEOUT_MS=4000, DECODE_TIMEOUT_MS=1000, POLL_MS=200;
const FRAME_PERIOD_MS=100;
// One complete HTTP/body + decode + poll budget, rather than expiring before HTTP.
const PREVIEW_STALE_MS=FRAME_TIMEOUT_MS+DECODE_TIMEOUT_MS+POLL_MS;
const TERMINAL=['unsupported','disabled','event_hardware_required','dependency_missing','worker_stalled','wia_device_unavailable'];
const REOPEN=['disconnected','disconnect','not_connected','preview_stopped','adapter_changed','camera_read_failed','transport_failed'];
const CAPTURE_STAGES={preparing:'Capture request received…',waiting_io:'Waiting for the current camera operation…',
  reconciling:'Checking previous camera captures…',preflight:'Checking camera readiness…',
  shutter:'Preparing the shutter request…',shutter_press:'Preparing to send the full shutter command…',
  shutter_dispatch:'Sending the shutter command and waiting for acknowledgment…',
  shutter_acknowledged:'Camera acknowledged the shutter command…',shutter_release:'Releasing the shutter controls…',
  recovering:'Checking the same capture request…',receiving_original:'Waiting for the original JPEG from the camera…',
  waiting_buffer:'Waiting for the original JPEG from the camera…',object_info:'Checking the captured image…',
  jpeg_transfer:'Receiving the original JPEG…',jpeg_validation:'JPEG received. Checking the image…',
  durable_cache:'JPEG validated. Saving the original…',buffer_drain:'Checking camera readiness…',
  normalizing:'Preparing the captured photo for editing…',saving_original:'Saving the original photo…',saving_slot:'Saving the photo slot…'};

async function cameraRequest(app,path,{method='GET',body,key,signal,scope}={}){
  const context=scope||await app.ensureSession();
  if(path==='/connect')metrics(app).connectRequests=(metrics(app).connectRequests||0)+1;
  const response=await boothFetch(`/api/sessions/${context.id}/camera${path}`,{
    method,headers:{Authorization: `Bearer ${context.token}`,...(body?{'Content-Type':'application/json'}:{}),...(key?{'Idempotency-Key':key}:{})},
    body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(130000),
  });
  if(!response.ok){const data=await response.json();const error=new Error(data.error?.message||'The host camera did not respond.');Object.assign(error,data.error);throw error;}
  return response;
}

function metrics(app){return app.hostPreviewDiagnostics??={frames:0,consecutiveFailures:0,reconnectAttempts:0,lastFailure:null};}

export function hostPreviewPerformance(app){
  const stat=metrics(app),samples=stat.samples||[];
  const result={samples:samples.length,displayedFrames:stat.frames,failedRequests:stat.failedRequests||0,
    discardedStaleFrames:stat.discardedStaleFrames||0,
    pendingRequest:app.hostFrameRequest?1:0,pendingRender:stat.pendingPaint?1:0,
    lastSequence:samples.at(-1)?.sequence,
    pendingResponses:stat.pendingResponses||0,reconnects:stat.reconnects||0,connectRequests:stat.connectRequests||0,
    displayedFPS:samples.length>1?Math.round((samples.length-1)*100000/(samples.at(-1).at-samples[0].at))/100:null};
  if(samples.length>1){
    const seconds=(samples.at(-1).at-samples[0].at)/1000;
    result.previewKiBPerSecond=seconds>0?Math.round(samples.slice(1).reduce((sum,s)=>sum+(s.bytes||0),0)/seconds/1024*100)/100:null;
  }
  for(const key of ['httpMs','responseMs','backendMs','bodyMs','decodeMs','intervalMs','ageUpperBoundMs','bytes',
    'ptpMs','workerMs','ipcMs','timerLateMs','paintMs','paintAgeUpperBoundMs']){
    const values=samples.map(sample=>sample[key]).filter(Number.isFinite).sort((a,b)=>a-b);
    if(values.length)result[key]={average:values.reduce((sum,value)=>sum+value,0)/values.length,p50:values[Math.floor((values.length-1)/2)],p95:values[Math.min(values.length-1,Math.floor(values.length*.95))],max:values.at(-1)};
  }
  return result;
}

const cameraStatusDetails=new WeakMap();
const shutterTransitions=new WeakMap();
const SHUTTER_HOLD_MS=4000;

function slideShutter(overlay,closed){
  // Commit the starting position before changing the class (also on a fast mock capture).
  getComputedStyle(overlay,'::before').transform;
  overlay.classList.toggle('is-closed',closed);
  const duration=parseFloat(getComputedStyle(overlay,'::before').transitionDuration)*1000;
  if(!duration)return Promise.resolve();
  return new Promise(resolve=>{
    const end=event=>{
      if(event&&(event.propertyName!=='transform'||event.pseudoElement==='::after'))return;
      clearTimeout(fallback);
      overlay.removeEventListener('transitionend',end);
      resolve();
    };
    const fallback=setTimeout(end,duration+50);
    overlay.addEventListener('transitionend',end);
  });
}

function closeShutter(transition){
  transition.closing??=slideShutter(transition.overlay,true).then(()=>performance.now());
}

function finishShutterTransition(app,transition){
  if(!transition||shutterTransitions.get(app)!==transition)return;
  shutterTransitions.delete(app);
  transition.overlay.classList.remove('is-closed');
}

function displayStatus(app,text,state='error',presentation=state){
  app.hostCameraState=state;
  cameraStatusDetails.set(app,text);
  const label=({
    connecting:'Connecting camera...', recovering:'Reconnecting...',
    connected:'Waiting for camera...', waiting:'Waiting for camera...', busy:'Camera is busy…',
    busy_stopped:app.currentScreen==='home'?'Camera is busy. Select Start Capturing to retry.':'Camera is busy. Select Reconnect Camera.',
    disconnected:'Camera disconnected', error:'Camera unavailable',
    capturing:'Sending capture request...', transferring:'Saving photo...',
    capture_stage:text, capture_blocked:text, usb_action:text,
  })[presentation]||'';
  const status=document.getElementById('hostCameraStatus');
  const waitingWithFreshFrame=app.hostPreviewHealthy&&!app.captureBusy&&(presentation==='waiting'||presentation==='busy');
  const hidden=app.cameraSource!=='host'||!label||waitingWithFreshFrame;
  if(status.hidden!==hidden)status.hidden=hidden;
  if(status.textContent!==label)status.textContent=label;
  if(status.dataset.state!==state)status.dataset.state=state;
  if(status.dataset.presentation!==presentation)status.dataset.presentation=presentation;
  app.syncKioskStatus?.();
}

function updatePreviewStats(app,force=false){
  const output=app.hostPreviewStats;
  if(!output)return;
  if(app.cameraSource!=='host'){output.hidden=true;return;}
  if(output.hidden)output.hidden=false;
  const stat=metrics(app),now=performance.now();
  if(!force&&now<(stat.nextStatsAt||0))return;
  stat.nextStatsAt=now+1000;
  if(!app.hostPreviewHealthy){
    output.textContent='Preview metrics · Waiting for a fresh frame';
    return;
  }
  const data=hostPreviewPerformance(app);
  const latest=stat.samples.at(-1);
  const ms=value=>Number.isFinite(value)?Math.round(value):'—';
  output.textContent=`Preview #${latest.sequence} · ${data.displayedFPS?.toFixed(1)??'—'} FPS · request p95 ${ms(data.responseMs.p95)} ms · frame age p95 ≤ ${ms((data.paintAgeUpperBoundMs||data.ageUpperBoundMs).p95)} ms\nPTP ${ms(latest.ptpMs)} · backend ${ms(latest.backendMs)} · body ${ms(latest.bodyMs)} · decode ${ms(latest.decodeMs)} · next paint ${ms(latest.paintMs)} · timer late ${ms(latest.timerLateMs)} ms`;
}

function hidePreview(app){
  app.hostPreviewHealthy=false;
  const image=document.getElementById('hostCameraPreview');image.hidden=true;image.removeAttribute('src');
  if(app.hostFrameUrl)URL.revokeObjectURL(app.hostFrameUrl);app.hostFrameUrl=null;
  updatePreviewStats(app,true);
}

function previewUnavailable(app,message,presentation='error'){
  hidePreview(app);
  if(app.captureBusy){displayStatus(app,'Receiving the photo file; preview is paused.','transferring');return;}
  // Preserve the countdown's remaining time and all saved slots. Never auto-resume.
  if(app.isCapturingSequence&&!app.sequencePaused)setCapturePaused(app,true);
  displayStatus(app,message,'error',presentation);
}

function armWatchdog(app,epoch){
  clearTimeout(app.hostPreviewWatchdog);
  app.hostPreviewWatchdog=setTimeout(()=>{
    if(epoch!==app.hostPreviewEpoch)return;
    previewUnavailable(app,'No fresh live preview. Capture is paused; waiting for a new frame.','waiting');
  },Math.max(0,PREVIEW_STALE_MS-(performance.now()-app.hostLastFrameAt)));
}

export function stopHostPreview(app){
  const stat=app.hostPreviewDiagnostics;
  if(stat?.pendingPaint){cancelAnimationFrame(stat.pendingPaint);stat.pendingPaint=null;}
  app.hostPreviewEpoch++;clearTimeout(app.hostPreviewTimer);app.hostPreviewTimer=null;
  clearTimeout(app.hostPreviewWatchdog);app.hostPreviewWatchdog=null;
  app.hostPreviewAbort?.abort();app.hostPreviewAbort=null;hidePreview(app);
  app.hostPreviewContext=null;
}

function scheduleRecovery(app,epoch,context,frameOnly=false,delay){
  if(!context||app.cameraSource!=='host'||epoch!==app.hostPreviewEpoch||app.sessionContext!==context||!['home','capture'].includes(app.currentScreen))return;
  const stat=metrics(app);
  if(!frameOnly&&stat.reconnectAttempts>=3){
    const busy=app.hostCameraState==='busy';
    displayStatus(app,'Stopped reconnecting after three attempts. '+(app.hostCameraLastConnectError||'')+' Check the camera and select Reconnect.',busy?'busy':'disconnected',busy?'busy_stopped':'disconnected');
    return;
  }
  clearTimeout(app.hostPreviewTimer);
  const wait=delay??(frameOnly?Math.min(2000,POLL_MS*2**Math.min(stat.consecutiveFailures,3)):2000*2**stat.reconnectAttempts);
  const due=performance.now()+wait;
  app.hostPreviewTimer=setTimeout(()=>{
    app.hostPreviewTimer=null;
    if(epoch!==app.hostPreviewEpoch||app.sessionContext!==context||app.cameraSource!=='host')return;
    // While the curtain holds a completed photo, the camera is already free
    // to continue its existing frame loop underneath the presentation.
    const showingSavedPhoto=shutterTransitions.get(app)?.imageReady;
    if(app.captureBusy&&!(frameOnly&&(app.hostCaptureRequestActive||showingSavedPhoto))){scheduleRecovery(app,epoch,context,frameOnly,POLL_MS);return;}
    if(frameOnly){stat.timerLateMs=Math.max(0,performance.now()-due);nextFrame(app,epoch);}
    else{stat.reconnectAttempts++;stat.reconnects=(stat.reconnects||0)+1;prepareHostCamera(app,{automatic:true}).catch(()=>{});}
  },wait);
}

function nextFrame(app,epoch){
  if(app.hostFrameRequest){
    if(app.hostFrameRequestEpoch===epoch)return app.hostFrameRequest;
    return app.hostFrameRequest.then(()=>{if(epoch===app.hostPreviewEpoch)return nextFrame(app,epoch);});
  }
  const pending=readFrame(app,epoch).finally(()=>{if(app.hostFrameRequest===pending)app.hostFrameRequest=null;});
  app.hostFrameRequest=pending;app.hostFrameRequestEpoch=epoch;
  return pending;
}

async function readFrame(app,epoch){
  if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host')return;
  const context=app.hostPreviewContext;
  if(app.captureBusy&&app.hostCaptureRequestActive){
    const transition=shutterTransitions.get(app);
    try{
      const status=await (await cameraRequest(app,'/status',{scope:context,key:app.hostCaptureOperation?.key,signal:AbortSignal.timeout(2000)})).json();
      if(epoch===app.hostPreviewEpoch&&app.sessionContext===context&&app.hostCaptureRequestActive){
        const progress=status.capture_progress;
        if(transition&&shutterTransitions.get(app)===transition&&transition.context===context&&
          app.currentScreen==='capture'&&progress?.shutter_acknowledged&&
          ['receiving_original','normalizing','saving_original','saving_slot','complete'].includes(progress.stage)&&!transition.closing){
          closeShutter(transition);
        }
        const stage=['shutter','recovering','receiving_original'].includes(progress?.stage)&&status.camera_progress?.capture_id===progress.capture_id
          ?status.camera_progress.stage:progress?.stage;
        if(CAPTURE_STAGES[stage])displayStatus(app,CAPTURE_STAGES[stage],'transferring','capture_stage');
      }
    }catch{/* The capture request owns errors; a status poll must never reconnect or retry a shutter. */}
    // Reuse the capture-status poll, only checking sooner until the shutter is confirmed.
    if(epoch===app.hostPreviewEpoch)scheduleRecovery(app,epoch,context,true,
      transition&&!transition.closing&&shutterTransitions.get(app)===transition?150:1000);
    return;
  }
  const abort=new AbortController();app.hostPreviewAbort=abort;
  let phase='http',timeout=setTimeout(()=>{
    const waitingFor=phase==='body'?'the JPEG body':'response headers';
    abort.abort(new DOMException(`Live preview timed out waiting for ${waitingFor}. Retrying preview. Saved photos are safe.`,'TimeoutError'));
  },FRAME_TIMEOUT_MS);
  const started=performance.now(),stat=metrics(app);
  const timerLateMs=stat.timerLateMs;stat.timerLateMs=undefined;
  try{
    const response=await cameraRequest(app,'/frame',{signal:abort.signal,scope:context});
    stat.httpMs=performance.now()-started;
    stat.backendMs=Number(response.headers.get('X-Preview-Processing-Ms'))||0;
    const backendAgeMs=Math.max(0,Number(response.headers.get('X-Frame-Age-Ms'))||0);
    const sequence=Number(response.headers.get('X-Frame-Sequence')??NaN);
    const stamp=Number(response.headers.get('X-Frame-Time'));
    if(!Number.isFinite(stamp)||stamp<=0||!Number.isFinite(sequence)||sequence<=app.hostFrameSequence){
      stat.discardedStaleFrames=(stat.discardedStaleFrames||0)+1;
      const error=new Error('Waiting for a newer live-view frame.');error.code='preview_pending';throw error;
    }
    phase='body';
    const blob=await response.blob();if(epoch!==app.hostPreviewEpoch)return;
    stat.responseMs=performance.now()-started;
    clearTimeout(timeout);phase='decode';
    timeout=setTimeout(()=>abort.abort(new DOMException('Preview image decoding timed out in this browser.','TimeoutError')),DECODE_TIMEOUT_MS);
    const url=URL.createObjectURL(blob),image=document.getElementById('hostCameraPreview'),decoded=new Image();
    const decodeStarted=performance.now();
    try{await new Promise((resolve,reject)=>{
      const cancelled=()=>finish(()=>reject(abort.signal.reason||new Error('Preview stopped.')));
      const finish=callback=>{abort.signal.removeEventListener('abort',cancelled);decoded.onload=null;decoded.onerror=null;callback();};
      decoded.onload=()=>finish(resolve);decoded.onerror=()=>finish(()=>reject(new Error('Could not decode the host preview image.')));
      abort.signal.addEventListener('abort',cancelled,{once:true});
      if(abort.signal.aborted){cancelled();return;}
      decoded.src=url;
    });}
    catch(error){URL.revokeObjectURL(url);throw error;}
    if(epoch!==app.hostPreviewEpoch){URL.revokeObjectURL(url);return;}
    if(app.hostCaptureRequestActive || backendAgeMs+performance.now()-started>=PREVIEW_STALE_MS){
      if(!app.hostCaptureRequestActive)stat.discardedStaleFrames=(stat.discardedStaleFrames||0)+1;
      URL.revokeObjectURL(url);
      scheduleRecovery(app,epoch,context,true,POLL_MS);
      return;
    }
    stat.decodeMs=performance.now()-decodeStarted;stat.frames++;stat.consecutiveFailures=0;stat.lastFailure=null;stat.reconnectAttempts=0;
    stat.busyFrames=0;
    const at=performance.now();
    const samples=stat.samples??=[];
    const timing=name=>Number(response.headers.get('X-Preview-'+name)??NaN);
    const sample={at,sequence,httpMs:stat.httpMs,responseMs:stat.responseMs,bodyMs:stat.responseMs-stat.httpMs,backendMs:stat.backendMs,decodeMs:stat.decodeMs,
      intervalMs:samples.length?at-samples.at(-1).at:undefined,ageUpperBoundMs:backendAgeMs+stat.responseMs+stat.decodeMs,bytes:blob.size,
      ptpMs:timing('Acquisition-Ms'),workerMs:timing('Wia-Worker-Ms'),ipcMs:timing('Wia-Ipc-Overhead-Ms'),timerLateMs};
    samples.push(sample);
    if(samples.length>120)samples.shift();
    image.src=url;
    if(app.hostFrameUrl)URL.revokeObjectURL(app.hostFrameUrl);app.hostFrameUrl=url;
    if(image.hidden)image.hidden=false;
    app.hostFrameSequence=sequence;app.hostPreviewHealthy=true;app.hostCameraNeedsReconnect=false;
    app.hostLastFrameAt=performance.now();armWatchdog(app,epoch);
    if(!app.captureBusy)displayStatus(app,'','previewing');
    if(app.hostPreviewStats){
      if(stat.pendingPaint)cancelAnimationFrame(stat.pendingPaint);
      // Observe the next paint opportunity without making polling wait for it.
      stat.pendingPaint=requestAnimationFrame(()=>{
        stat.pendingPaint=null;
        if(epoch!==app.hostPreviewEpoch||app.hostFrameSequence!==sequence||!app.hostPreviewHealthy)return;
        sample.paintMs=performance.now()-at;
        sample.paintAgeUpperBoundMs=sample.ageUpperBoundMs+sample.paintMs;
        updatePreviewStats(app);
      });
    }
  }catch(error){
    if(epoch!==app.hostPreviewEpoch)return;
    const failure=abort.signal.aborted?abort.signal.reason:error;
    const reopen=REOPEN.includes(error.code),terminal=TERMINAL.includes(error.code);
    stat.busyFrames=error.code==='busy'?(stat.busyFrames||0)+1:0;
    stat.lastFailure=error.code==='busy'?'camera_busy':error.code||(phase==='decode'?'image_decode':abort.signal.aborted?'http_timeout':'http_network');
    stat.consecutiveFailures++;
    if(error.code==='preview_pending'||error.code==='not_ready'||error.code==='busy')stat.pendingResponses=(stat.pendingResponses||0)+1;
    else stat.failedRequests=(stat.failedRequests||0)+1;
    if(error.code==='busy'||app.captureBusy)displayStatus(app,'Camera is busy. Waiting for a fresh frame.','busy');
    else{
      const message=failure?.message||'HTTP preview interrupted. Retrying the frame; camera connection is unchanged.';
      if(reopen||terminal||error.code==='stale_preview'||!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>=PREVIEW_STALE_MS)previewUnavailable(app,message,reopen?'disconnected':terminal?'error':'waiting');
      else displayStatus(app,message,'waiting');
    }
    app.hostCameraNeedsReconnect=reopen;
    if(stat.busyFrames>=6&&!app.hostCaptureRequestActive){
      clearTimeout(app.hostPreviewWatchdog);
      previewUnavailable(app,'Camera is still busy. Select Reconnect when it is ready.');
      return;
    }
    if(!terminal)scheduleRecovery(app,epoch,context,!reopen,error.code==='preview_pending'?POLL_MS:undefined);
    return;
  }finally{clearTimeout(timeout);if(app.hostPreviewAbort===abort)app.hostPreviewAbort=null;}
  // Pace start-to-start, not "USB time + decode time + another 200 ms".
  // A slow producer remains single-flight; it cannot build an HTTP backlog.
  if(epoch===app.hostPreviewEpoch)scheduleRecovery(app,epoch,context,true,Math.max(0,FRAME_PERIOD_MS-(performance.now()-started)));
}

export async function enableHostCamera(app){
  app.clearTimers();app.stopCurrentStreams();app.cameraSource='host';app.cameraAdapter=null;
  document.getElementById('liveVideo').classList.add('hidden');document.getElementById('simLiveCanvas').classList.add('hidden');document.getElementById('cameraFallbackBar').classList.add('hidden');
  document.getElementById('hostCameraTools').hidden=false;
  if(new URLSearchParams(window.location.search).get('previewStats')==='1'){
    app.hostPreviewStats=document.getElementById('hostPreviewStats');
    app.hostPreviewStats.hidden=false;
    updatePreviewStats(app,true);
  }
  await app.refreshCameraList();
  try{await app.prepareHostCamera();}catch(error){
    if(!app.hostPreviewTimer)app.showToast(error.message,'error');
  }
}

export async function prepareHostCamera(app,{automatic=false}={}){
  if(app.cameraSource!=='host')return;
  if(app.hostConnectRequest)return app.hostConnectRequest;
  if(!automatic)metrics(app).reconnectAttempts=0;
  if(app.hostPreviewContext&&app.hostPreviewContext===app.sessionContext&&!app.hostCameraNeedsReconnect){
    if(app.hostPreviewHealthy&&performance.now()-app.hostLastFrameAt<PREVIEW_STALE_MS)return;
    await nextFrame(app,app.hostPreviewEpoch);
    if(app.hostPreviewHealthy)return;
    const error=new Error(cameraStatusDetails.get(app)||'Waiting for live preview.');
    error.previewRecoveryScheduled=true;throw error;
  }
  const requestedEpoch=app.hostPreviewEpoch;
  let connectionEpoch=requestedEpoch,connectionContext=app.sessionContext;
  app.hostConnectRequest=(async()=>{
    if(app.hostReleaseRequest)await app.hostReleaseRequest;
    if(requestedEpoch!==app.hostPreviewEpoch||app.cameraSource!=='host')throw new Error('Camera connection cancelled.');
    const context=await app.ensureSession();
    connectionContext=context;
    if(requestedEpoch!==app.hostPreviewEpoch||app.sessionContext!==context)throw new Error('The session changed. Reconnect the camera.');
    app.stopHostPreview();displayStatus(app,automatic?'Reconnecting...':'Connecting camera...',automatic?'recovering':'connecting');
    metrics(app).samples=[];
    const epoch=app.hostPreviewEpoch;
    connectionEpoch=epoch;app.hostPreviewContext=context;
    const checkCancelled=async()=>{
      if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host'||app.sessionContext!==context){
        await boothFetch(`/api/sessions/${context.id}/camera/disconnect`,{method:'POST',headers:{Authorization:`Bearer ${context.token}`},keepalive:true}).catch(()=>{});
        throw new Error('Camera connection cancelled for the previous session.');
      }
    };
    const connected=await (await cameraRequest(app,'/connect',{method:'POST',scope:context})).json();
    app.hostCameraLastConnectError='';
    await checkCancelled();app.hostCameraStatus=connected;
    displayStatus(app,'Waiting for camera...','connected');
    const cap=app.hostCameraStatus.capabilities;
    if(app.eventConfig?.event_mode&&(cap.demo||!cap.physical_shutter||!cap.original_file||!cap.hardware_verified))throw new Error('The real camera is not ready. Please ask event staff to check the equipment.');
    if(!cap.capture)throw new Error('This adapter does not support capture. The preview cannot be used as a substitute photo.');
    if(!cap.demo&&(!cap.physical_shutter||!cap.original_file))throw new Error('This camera does not support the shutter and original image file required.');
    await cameraRequest(app,'/live-view/start',{method:'POST',scope:context});
    await checkCancelled();
    app.hostFrameSequence=-1;
    await nextFrame(app,epoch);await checkCancelled();
    if(!app.hostPreviewHealthy){
      const error=new Error(cameraStatusDetails.get(app)||'The live view is not ready.');
      // nextFrame has already chosen retry versus a terminal capability error.
      error.previewRecoveryScheduled=true;throw error;
    }
  })();
  try{return await app.hostConnectRequest;}
  catch(error){
    if(connectionEpoch===app.hostPreviewEpoch&&app.sessionContext===connectionContext){
      app.hostCameraLastConnectError=error.message||'Camera connection failed.';
      if(!error.previewRecoveryScheduled)app.hostCameraNeedsReconnect=true;
      hidePreview(app);
      if(error.code==='busy')displayStatus(app,'Camera is busy. '+error.message,'busy');
      else if(error.code==='wia_device_unavailable')displayStatus(app,error.message,'error','usb_action');
      else if(REOPEN.includes(error.code))displayStatus(app,'Camera disconnected. '+error.message,'disconnected');
      else if(!error.previewRecoveryScheduled){
        const needsHelp=TERMINAL.includes(error.code)||/real camera is not ready|does not support/.test(error.message);
        displayStatus(app,error.message||'Reconnecting...','recovering',needsHelp?'error':'recovering');
      }
      if(!error.previewRecoveryScheduled&&!TERMINAL.includes(error.code))scheduleRecovery(app,connectionEpoch,connectionContext);
    }
    throw error;
  }finally{app.hostConnectRequest=null;}
}

export async function checkHostCaptureReadiness(app){
  const context=app.sessionContext;
  app.hostCaptureBlocker='';
  app.syncKioskStatus?.();
  try{await cameraRequest(app,'/status?check_capture=true',{scope:context,signal:AbortSignal.timeout(4000)});}
  catch(error){
    error.clear_pending=true; // This check cannot create a capture.
    if(app.sessionContext===context){
      app.hostCaptureBlocker=error.message;
      app.syncKioskStatus?.();
    }
    throw error;
  }
}

export function releaseHostCamera(app){
  app.hostCaptureBlocker='';
  app.stopHostPreview();app.syncHostCaptureUI();
  const context=app.sessionContext;
  if(app.cameraSource!=='host'||!context?.id)return;
  const release=boothFetch(`/api/sessions/${context.id}/camera/disconnect`,{method:'POST',headers:{Authorization:`Bearer ${context.token}`},keepalive:true}).catch(()=>null).finally(()=>{if(app.hostReleaseRequest===release)app.hostReleaseRequest=null;});
  app.hostReleaseRequest=release;
}

export function syncHostCaptureUI(app){
  const full=app.currentScreen==='capture'&&app.isCapturingSequence&&!app.sequencePaused;
  document.body.classList.toggle('host-capture-fullscreen',!!full);
  app.syncSetupLayout?.();
  const progress=document.getElementById('hostShotProgress');
  if(progress)progress.textContent=`${app.photos.filter(Boolean).length} / ${app.slotCount}`;
}

export function exitHostCapture(app){app.clearTimers();app.updateCaptureScreenUI();}

async function loadStoredPhoto(app,result,operation,context){
  const photo=result.session?.photos.find(p=>p.id===result.capture.photo_id&&p.slot_index===operation.slot);
  if(!photo)throw new Error('The backend did not confirm the correct photo slot. Retry the same request.');
  const response=await boothFetch(`/api/sessions/${context.id}/photos/${photo.id}/image`,{headers:{Authorization:`Bearer ${context.token}`},signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error('The photo was saved but could not be loaded on screen. Select Retry Save; you do not need to retake it.');
  const url=URL.createObjectURL(await response.blob());
  try{
    const image=await new Promise((resolve,reject)=>{
      const img=new Image();
      const finish=callback=>{clearTimeout(timer);img.onload=null;img.onerror=null;callback();};
      const timer=setTimeout(()=>finish(()=>reject(new Error('The saved photo could not be decoded in time. Select Retry Save.'))),20000);
      img.onload=()=>finish(()=>resolve(img));
      img.onerror=()=>finish(()=>reject(new Error('Could not read the saved camera photo.')));
      img.src=url;
    });
    const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
    canvas.getContext('2d').drawImage(image,0,0); // saved capture file, never the preview element
    return canvas;
  }finally{URL.revokeObjectURL(url);}
}

export async function captureHostPhoto(app,slot,{recoveryOnly=false}={}){
  let operation=app.hostCaptureOperation;
  const recovering=recoveryOnly||operation?.submitted===true;
  if(recoveryOnly&&!operation)return {accepted:false};
  if(operation&&operation.slot!==slot)throw new Error('A camera request is still in progress. Retry saving before changing slots.');
  if(!operation){
    app.hostCaptureBlocker='';
    operation={slot,key:newId(),submitted:false,completeAfterRecovery:app.singleRetakeIndex!==null||app.isCapturingSequence};
    app.hostCaptureOperation=operation;
  }
  let captureContext,shutterTransition;
  try{
    // Retry Save reuses the original key and permits retrieval only.
    if(!recovering&&(!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>PREVIEW_STALE_MS))await app.prepareHostCamera();
    captureContext=await app.ensureSession();
    const checkCurrent=()=>{
      if(app.sessionContext!==captureContext||app.hostCaptureOperation!==operation){
        const error=new Error('The Host saved this photo for the previous session.');
        error.code='capture_superseded';throw error;
      }
    };
    checkCurrent();
    operation.submitted=true;
    captureContext.cameraCapture={...operation};rememberSession(captureContext);
    const overlay=!recovering&&app.currentScreen==='capture'&&document.getElementById('captureShutter');
    if(overlay){
      finishShutterTransition(app,shutterTransitions.get(app));
      shutterTransition={context:captureContext,key:operation.key,overlay};
      shutterTransitions.set(app,shutterTransition);
    }
    app.hostCaptureRequestActive=true;
    displayStatus(app,'Capturing and receiving the image file from the host camera…','capturing');
    const submit=()=>cameraRequest(app,'/captures',{method:'POST',
      body:{slot_index:slot,...(recovering?{recovery_only:true}:{})},key:operation.key,scope:captureContext});
    let response;
    try{response=await submit();}
    catch(error){
      if(!recovering||!['not_connected','disconnected','disconnect','transport_failed'].includes(error.code))throw error;
      // A saved ACK needs no camera. An unfinished transfer may need one
      // explicit reconnect, but never waits for Live View to download its JPEG.
      checkCurrent();
      await cameraRequest(app,'/connect',{method:'POST',scope:captureContext});
      checkCurrent();
      await cameraRequest(app,'/live-view/start',{method:'POST',scope:captureContext});
      checkCurrent();
      response=await submit(); // Identical key; controller reconciles, never a new shutter.
    }
    const result=await response.json();
    checkCurrent();
    if(result.capture?.status==='captured')operation.savedOnHost=true;
    // A fast response can arrive between status polls. A successful capture
    // response also confirms this shot and can start the same curtain.
    if(shutterTransition&&app.currentScreen==='capture')closeShutter(shutterTransition);
    const canvas=await loadStoredPhoto(app,result,operation,captureContext);
    checkCurrent();
    app.hostCaptureRequestActive=false;
    if(shutterTransition?.closing&&app.currentScreen==='capture'){
      shutterTransition.imageReady=true;
      const closedAt=await shutterTransition.closing;
      const remaining=closedAt+SHUTTER_HOLD_MS-performance.now();
      if(remaining>0)await new Promise(resolve=>setTimeout(resolve,Math.ceil(remaining)));
      checkCurrent();
      if(app.currentScreen==='capture')await slideShutter(shutterTransition.overlay,false);
      checkCurrent();
    }
    app.photos[slot]=canvas;app.serverSession=result.session;app.hostCaptureOperation=null;app.hostCaptureBlocker='';
    delete captureContext.cameraCapture;rememberSession(captureContext);
    app.finalOperation=null;app.lastSavedImage='';app.activeShare=null;app.saveState='capturing';app.persistenceError='';
    app.transitionSession('PREVIEW');app.playShutterSound();if(!shutterTransition)app.triggerFlashEffect();app.updateCaptureScreenUI();
    displayStatus(app,'Saved the camera image to slot '+(slot+1),'captured');
    return {accepted:true,photo:result.capture};
  }catch(error){
    if(app.hostCaptureOperation!==operation||captureContext&&app.sessionContext!==captureContext)throw error;
    if(['capture_cancelled','capture_superseded'].includes(error.code)){
      app.hostCaptureOperation=null;
      if(captureContext){delete captureContext.cameraCapture;rememberSession(captureContext);}
      displayStatus(app,error.message,'ready');
      throw error;
    }
    operation.retryNewShot=false;
    if(!operation.submitted){
      error.clear_pending=true;
      error.shutter_dispatched=false;
    }
    if(error.clear_pending===true)app.hostCaptureOperation=null;
    if(captureContext){
      if(error.clear_pending===true)delete captureContext.cameraCapture;
      else captureContext.cameraCapture={...operation};
      rememberSession(captureContext);
    }
    if(error.shutter_dispatched===false){
      error.message = (error.message ? error.message+' ' : '')+'No new shutter command was sent.';
      if(error.clear_pending===true)app.hostCaptureBlocker=error.message;
      displayStatus(app,error.message,'error','capture_blocked');
    }else displayStatus(app,error.message||'Could not connect to the host. Retry saving with the same request.');
    throw error;
  }finally{
    finishShutterTransition(app,shutterTransition);
    if((!captureContext||app.sessionContext===captureContext)&&(!app.hostCaptureOperation||app.hostCaptureOperation===operation))app.hostCaptureRequestActive=false;
  }
}

export async function retryHostCapture(app){
  if(app.captureBusy||!app.hostCaptureOperation)return;
  const operation=app.hostCaptureOperation,context=app.sessionContext;
  const current=()=>app.sessionContext===context&&(!app.hostCaptureOperation||app.hostCaptureOperation===operation);
  app.captureBusy=true;app.syncHostCaptureUI();
  try{
    const restored=await app.captureHostPhoto(operation.slot,{recoveryOnly:true});
    if(restored?.accepted===false)return;
    if(!current())return;
    app.singleRetakeIndex=null;
    app.retakeReturnToReview=false;
    if(app.photos.every(Boolean)&&operation.completeAfterRecovery)app.onAllSixShotsCompleted();
  }catch(error){
    if(!current())return;
    if(['capture_cancelled','capture_superseded'].includes(error.code)){
      app.persistenceError='';app.saveState='capturing';app.transitionSession('PREVIEW');
      app.showToast(error.code==='capture_superseded'
        ?'This session has ended. Select New Session to continue.'
        :'The previous shot was cancelled. Select Capture Now to continue.','info');
    }else app.reportSaveError(error);
  }
  finally{if(current()){app.captureBusy=false;app.syncPersistenceUI();app.updateCaptureScreenUI();}}
}

export function useHostCameraByDefault(app){return defaults.hostCameraEnabled||app.eventConfig?.event_mode||app.eventConfig?.operation_mode==='rehearsal';}
