import { defaults } from '../config/defaults.js';
import { newId } from '../utils/ids.js';
import { boothFetch } from './booth-access.js';
import { setCapturePaused } from '../features/capture/countdown.js';
import { rememberSession } from './session-recovery.js';

const FRAME_TIMEOUT_MS=4000, DECODE_TIMEOUT_MS=1000, POLL_MS=200;
// One complete HTTP/body + decode + poll budget, rather than expiring before HTTP.
const PREVIEW_STALE_MS=FRAME_TIMEOUT_MS+DECODE_TIMEOUT_MS+POLL_MS;
const TERMINAL=['unsupported','disabled','event_hardware_required','dependency_missing','worker_stalled'];
const REOPEN=['disconnected','disconnect','not_connected','preview_stopped','adapter_changed','camera_read_failed'];

async function cameraRequest(app,path,{method='GET',body,key,signal,scope}={}){
  const context=scope||await app.ensureSession();
  const response=await boothFetch(`/api/sessions/${context.id}/camera${path}`,{
    method,headers:{Authorization: `Bearer ${context.token}`,...(body?{'Content-Type':'application/json'}:{}),...(key?{'Idempotency-Key':key}:{})},
    body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(130000),
  });
  if(!response.ok){const data=await response.json();const error=new Error(data.error?.message||'The host camera did not respond.');Object.assign(error,data.error);throw error;}
  return response;
}

function metrics(app){return app.hostPreviewDiagnostics??={frames:0,consecutiveFailures:0,reconnectAttempts:0,lastFailure:null};}

function displayStatus(app,text,state='error'){
  app.hostCameraState=state;
  const status=document.getElementById('hostCameraStatus');
  status.hidden=app.cameraSource!=='host';status.textContent=text;status.dataset.state=state;
  app.syncKioskStatus?.();
}

function hidePreview(app){
  app.hostPreviewHealthy=false;
  const image=document.getElementById('hostCameraPreview');image.hidden=true;image.removeAttribute('src');
  if(app.hostFrameUrl)URL.revokeObjectURL(app.hostFrameUrl);app.hostFrameUrl=null;
}

function previewUnavailable(app,message){
  hidePreview(app);
  if(app.captureBusy){displayStatus(app,'Receiving the photo file; preview is paused.','transferring');return;}
  // Preserve the countdown's remaining time and all saved slots. Never auto-resume.
  if(app.isCapturingSequence&&!app.sequencePaused)setCapturePaused(app,true);
  displayStatus(app,message);
}

function armWatchdog(app,epoch){
  clearTimeout(app.hostPreviewWatchdog);
  app.hostPreviewWatchdog=setTimeout(()=>{
    if(epoch!==app.hostPreviewEpoch)return;
    previewUnavailable(app,'No fresh live preview. Capture is paused; waiting for a new frame.');
  },Math.max(0,PREVIEW_STALE_MS-(performance.now()-app.hostLastFrameAt)));
}

export function stopHostPreview(app){
  app.hostPreviewEpoch++;clearTimeout(app.hostPreviewTimer);app.hostPreviewTimer=null;
  clearTimeout(app.hostPreviewWatchdog);app.hostPreviewWatchdog=null;
  app.hostPreviewAbort?.abort();app.hostPreviewAbort=null;hidePreview(app);
  app.hostPreviewContext=null;
}

function scheduleRecovery(app,epoch,context,frameOnly=false,delay){
  if(!context||app.cameraSource!=='host'||epoch!==app.hostPreviewEpoch||app.sessionContext!==context||!['home','capture'].includes(app.currentScreen))return;
  const stat=metrics(app);
  if(!frameOnly&&stat.reconnectAttempts>=3){displayStatus(app,'Camera recovery stopped after 3 attempts. Check the host camera, then use Reconnect.');return;}
  clearTimeout(app.hostPreviewTimer);
  const wait=delay??(frameOnly?Math.min(2000,POLL_MS*2**Math.min(stat.consecutiveFailures,3)):2000*2**stat.reconnectAttempts);
  app.hostPreviewTimer=setTimeout(()=>{
    app.hostPreviewTimer=null;
    if(epoch!==app.hostPreviewEpoch||app.sessionContext!==context||app.cameraSource!=='host')return;
    if(app.captureBusy){scheduleRecovery(app,epoch,context,frameOnly,POLL_MS);return;}
    if(frameOnly)nextFrame(app,epoch);
    else{stat.reconnectAttempts++;prepareHostCamera(app,{automatic:true}).catch(()=>{});}
  },wait);
}

function nextFrame(app,epoch){
  if(app.hostFrameRequest&&app.hostFrameRequestEpoch===epoch)return app.hostFrameRequest;
  const pending=readFrame(app,epoch).finally(()=>{if(app.hostFrameRequest===pending)app.hostFrameRequest=null;});
  app.hostFrameRequest=pending;app.hostFrameRequestEpoch=epoch;
  return pending;
}

async function readFrame(app,epoch){
  if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host')return;
  const context=app.hostPreviewContext;
  if(app.captureBusy&&app.hostCaptureRequestActive){scheduleRecovery(app,epoch,context,true,POLL_MS);return;}
  const abort=new AbortController();app.hostPreviewAbort=abort;
  let phase='http',timeout=setTimeout(()=>abort.abort(new DOMException('Live preview timed out (HTTP); camera USB connection is unknown. Saved photos are safe.','TimeoutError')),FRAME_TIMEOUT_MS);
  const started=performance.now(),stat=metrics(app);
  try{
    const response=await cameraRequest(app,'/frame',{signal:abort.signal,scope:context});
    stat.httpMs=performance.now()-started;
    stat.backendMs=Number(response.headers.get('X-Preview-Processing-Ms'))||0;
    const sequence=Number(response.headers.get('X-Frame-Sequence'));
    const stamp=Number(response.headers.get('X-Frame-Time'));
    if(!Number.isFinite(stamp)||!Number.isFinite(sequence)||sequence<=app.hostFrameSequence){const error=new Error('Waiting for a newer live-view frame.');error.code='preview_pending';throw error;}
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
    stat.decodeMs=performance.now()-decodeStarted;stat.frames++;stat.consecutiveFailures=0;stat.lastFailure=null;stat.reconnectAttempts=0;
    image.src=url;
    if(app.hostFrameUrl)URL.revokeObjectURL(app.hostFrameUrl);app.hostFrameUrl=url;
    image.hidden=false;app.hostFrameSequence=sequence;app.hostPreviewHealthy=true;app.hostCameraNeedsReconnect=false;
    app.hostLastFrameAt=performance.now();armWatchdog(app,epoch);
    if(!app.captureBusy)displayStatus(app,`${app.hostCameraStatus?.capabilities?.name||'Camera host'} • Live View`, 'previewing');
  }catch(error){
    if(epoch!==app.hostPreviewEpoch)return;
    const failure=abort.signal.aborted?abort.signal.reason:error;
    const reopen=REOPEN.includes(error.code),terminal=TERMINAL.includes(error.code);
    stat.lastFailure=error.code==='busy'?'camera_busy':error.code||(phase==='decode'?'image_decode':abort.signal.aborted?'http_timeout':'http_network');
    stat.consecutiveFailures++;
    if(error.code==='busy'||app.captureBusy)displayStatus(app,'Camera is busy capturing/transferring; waiting for preview.','transferring');
    else{
      const message=failure?.message||'HTTP preview interrupted. Retrying the frame; camera connection is unchanged.';
      if(reopen||terminal||error.code==='stale_preview'||!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>=PREVIEW_STALE_MS)previewUnavailable(app,message);
      else displayStatus(app,message,'waiting');
    }
    app.hostCameraNeedsReconnect=reopen;
    if(!terminal)scheduleRecovery(app,epoch,context,!reopen,error.code==='preview_pending'||error.code==='busy'?POLL_MS:undefined);
    return;
  }finally{clearTimeout(timeout);if(app.hostPreviewAbort===abort)app.hostPreviewAbort=null;}
  if(epoch===app.hostPreviewEpoch)scheduleRecovery(app,epoch,context,true,POLL_MS);
}

export async function enableHostCamera(app){
  app.clearTimers();app.stopCurrentStreams();app.cameraSource='host';app.cameraAdapter=null;
  document.getElementById('liveVideo').classList.add('hidden');document.getElementById('simLiveCanvas').classList.add('hidden');document.getElementById('cameraFallbackBar').classList.add('hidden');
  for(const id of ['hostCameraTools','hostCameraStatus'])document.getElementById(id).hidden=false;
  await app.refreshCameraList();
  try{await app.prepareHostCamera();}catch(error){displayStatus(app,error.message);app.showToast(error.message,'error');}
}

export async function prepareHostCamera(app,{automatic=false}={}){
  if(app.cameraSource!=='host')return;
  if(app.hostConnectRequest)return app.hostConnectRequest;
  if(!automatic)metrics(app).reconnectAttempts=0;
  if(app.hostPreviewContext&&app.hostPreviewContext===app.sessionContext&&!app.hostCameraNeedsReconnect){
    if(app.hostPreviewHealthy&&performance.now()-app.hostLastFrameAt<PREVIEW_STALE_MS)return;
    await nextFrame(app,app.hostPreviewEpoch);
    if(app.hostPreviewHealthy)return;
    const error=new Error(document.getElementById('hostCameraStatus').textContent||'Waiting for live preview.');
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
    app.stopHostPreview();displayStatus(app,'Connecting to the laptop camera…','connecting');
    const epoch=app.hostPreviewEpoch;
    connectionEpoch=epoch;app.hostPreviewContext=context;
    const checkCancelled=async()=>{
      if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host'||app.sessionContext!==context){
        await boothFetch(`/api/sessions/${context.id}/camera/disconnect`,{method:'POST',headers:{Authorization:`Bearer ${context.token}`},keepalive:true}).catch(()=>{});
        throw new Error('Camera connection cancelled for the previous session.');
      }
    };
    const connected=await (await cameraRequest(app,'/connect',{method:'POST',scope:context})).json();
    await checkCancelled();app.hostCameraStatus=connected;
    const cap=app.hostCameraStatus.capabilities;
    if(app.eventConfig?.event_mode&&(cap.demo||!cap.physical_shutter||!cap.original_file||!cap.hardware_verified))throw new Error('The real camera is not ready. Please ask event staff to check the equipment.');
    if(!cap.capture)throw new Error('This adapter does not support capture. The preview cannot be used as a substitute photo.');
    if(!cap.demo&&(!cap.physical_shutter||!cap.original_file))throw new Error('This camera does not support the shutter and original image file required.');
    document.getElementById('demoModeBadge').textContent=cap.demo?'HOST CAMERA DEMO • '+cap.name+' • Không có shutter DSLR thật':'HOST CAMERA • '+cap.name+' • Chưa xác minh phần cứng tại trạm';
    await cameraRequest(app,'/live-view/start',{method:'POST',scope:context});
    await checkCancelled();
    app.hostFrameSequence=-1;
    await nextFrame(app,epoch);await checkCancelled();
    if(!app.hostPreviewHealthy){
      const error=new Error(document.getElementById('hostCameraStatus').textContent||'The live view is not ready.');
      // nextFrame has already chosen retry versus a terminal capability error.
      error.previewRecoveryScheduled=true;throw error;
    }
  })();
  try{return await app.hostConnectRequest;}
  catch(error){
    if(connectionEpoch===app.hostPreviewEpoch&&app.sessionContext===connectionContext){
      if(!error.previewRecoveryScheduled)app.hostCameraNeedsReconnect=true;
      hidePreview(app);displayStatus(app,error.message||'The camera is not ready. Reconnecting…');
      if(!error.previewRecoveryScheduled&&!TERMINAL.includes(error.code))scheduleRecovery(app,connectionEpoch,connectionContext);
    }
    throw error;
  }finally{app.hostConnectRequest=null;}
}

export function releaseHostCamera(app){
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

async function loadStoredPhoto(app,result,operation){
  const photo=result.session?.photos.find(p=>p.id===result.capture.photo_id&&p.slot_index===operation.slot);
  if(!photo)throw new Error('The backend did not confirm the correct photo slot. Retry the same request.');
  const context=app.sessionContext;
  const response=await boothFetch(`/api/sessions/${context.id}/photos/${photo.id}/image`,{headers:{Authorization:`Bearer ${context.token}`},signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error('The photo was saved but could not be loaded on screen. Select Retry Save; you do not need to retake it.');
  const url=URL.createObjectURL(await response.blob());
  try{
    const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Could not read the saved camera photo.'));img.src=url;});
    const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
    canvas.getContext('2d').drawImage(image,0,0); // saved capture file, never the preview element
    return canvas;
  }finally{URL.revokeObjectURL(url);}
}

export async function captureHostPhoto(app,slot){
  let operation=app.hostCaptureOperation;
  const recovering=!!operation&&operation.submitted===true&&!operation.retryNewShot;
  if(operation&&operation.slot!==slot)throw new Error('A camera request is still in progress. Retry saving before changing slots.');
  if(!operation){operation={slot,key:newId(),submitted:false,completeAfterRecovery:app.singleRetakeIndex!==null||app.isCapturingSequence};app.hostCaptureOperation=operation;}
  let captureContext;
  try{
    // A failed safe capture is retried only by an explicit user action. A lost
    // response/transfer failure keeps its key so it cannot trigger another shot.
    if(operation.retryNewShot){operation.key=newId();operation.retryNewShot=false;operation.submitted=false;}
    if(!recovering&&(!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>PREVIEW_STALE_MS))await app.prepareHostCamera();
    captureContext=await app.ensureSession();
    operation.submitted=true;
    captureContext.cameraCapture={...operation};rememberSession(captureContext);
    app.hostCaptureRequestActive=true;
    displayStatus(app,'Capturing and receiving the image file from the host camera…','capturing');
    const submit=()=>cameraRequest(app,'/captures',{method:'POST',body:{slot_index:slot},key:operation.key});
    let response;
    try{response=await submit();}
    catch(error){
      if(!recovering||!['not_connected','disconnected','disconnect'].includes(error.code))throw error;
      // A saved ACK needs no camera. An unfinished transfer may need one
      // explicit reconnect, but never waits for Live View to download its JPEG.
      await cameraRequest(app,'/connect',{method:'POST'});
      await cameraRequest(app,'/live-view/start',{method:'POST'});
      response=await submit(); // Identical key; controller reconciles, never a new shutter.
    }
    const result=await response.json();
    const canvas=await loadStoredPhoto(app,result,operation);
    app.photos[slot]=canvas;app.serverSession=result.session;app.hostCaptureOperation=null;
    delete captureContext.cameraCapture;rememberSession(captureContext);
    app.finalOperation=null;app.lastSavedImage='';app.activeShare=null;app.saveState='capturing';app.persistenceError='';
    app.transitionSession('PREVIEW');app.playShutterSound();app.triggerFlashEffect();app.updateCaptureScreenUI();
    displayStatus(app,'Saved the camera image to slot '+(slot+1),'captured');
    return {accepted:true,photo:result.capture};
  }catch(error){
    operation.retryNewShot=['capture','timeout','disconnect','disconnected'].includes(error.code)&&error.stage!=='transfer'&&!error.uncertain;
    if(captureContext){captureContext.cameraCapture={...operation};rememberSession(captureContext);}
    displayStatus(app,error.message||'Could not connect to the host. Retry saving with the same request.');throw error;
  }finally{app.hostCaptureRequestActive=false;}
}

export async function retryHostCapture(app){
  if(app.captureBusy||!app.hostCaptureOperation)return;
  app.captureBusy=true;app.syncHostCaptureUI();
  try{
    const operation=app.hostCaptureOperation,slot=operation.slot;
    await app.captureHostPhoto(slot);app.singleRetakeIndex=null;
    app.retakeReturnToReview=false;
    if(app.photos.every(Boolean)&&operation.completeAfterRecovery)app.onAllSixShotsCompleted();
  }catch(error){app.reportSaveError(error);}
  finally{app.captureBusy=false;app.syncPersistenceUI();app.updateCaptureScreenUI();}
}

export function useHostCameraByDefault(app){return defaults.hostCameraEnabled||app.eventConfig?.event_mode||app.eventConfig?.operation_mode==='rehearsal';}
