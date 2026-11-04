import { defaults } from '../config/defaults.js';
import { newId } from '../utils/ids.js';
import { boothFetch } from './booth-access.js';

async function cameraRequest(app,path,{method='GET',body,key,signal,scope}={}){
  const context=scope||await app.ensureSession();
  const response=await boothFetch(`/api/sessions/${context.id}/camera${path}`,{
    method,headers:{Authorization:`Bearer ${context.token}`,...(body?{'Content-Type':'application/json'}:{}),...(key?{'Idempotency-Key':key}:{})},
    body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(130000),
  });
  if(!response.ok){const data=await response.json();const error=new Error(data.error?.message||'The host camera did not respond.');Object.assign(error,data.error);throw error;}
  return response;
}

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

export function stopHostPreview(app){
  app.hostPreviewEpoch++;clearTimeout(app.hostPreviewTimer);app.hostPreviewTimer=null;
  clearTimeout(app.hostPreviewWatchdog);app.hostPreviewWatchdog=null;
  app.hostPreviewAbort?.abort();app.hostPreviewAbort=null;hidePreview(app);
  app.hostPreviewContext=null;
}

function scheduleRecovery(app,epoch,context,frameOnly=false){
  if(!context||app.cameraSource!=='host'||epoch!==app.hostPreviewEpoch||app.sessionContext!==context||!['home','capture'].includes(app.currentScreen))return;
  clearTimeout(app.hostPreviewTimer);
  app.hostPreviewTimer=setTimeout(()=>{
    if(epoch!==app.hostPreviewEpoch||app.sessionContext!==context||app.cameraSource!=='host')return;
    if(app.captureBusy){scheduleRecovery(app,epoch,context,frameOnly);return;}
    if(frameOnly)nextFrame(app,epoch);
    else app.prepareHostCamera().catch(()=>{});
  },2000);
}

async function nextFrame(app,epoch){
  if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host')return;
  const abort=new AbortController();app.hostPreviewAbort=abort;
  const timeout=setTimeout(()=>abort.abort(new DOMException('Live preview timed out. Check the laptop/hotspot connection. Saved photos are safe.','TimeoutError')),4000);
  try{
    const response=await cameraRequest(app,'/frame',{signal:abort.signal,scope:app.hostPreviewContext});
    const sequence=Number(response.headers.get('X-Frame-Sequence'));
    const stamp=Number(response.headers.get('X-Frame-Time'));
    // Server checks camera-clock age. Browser checks sequence progression and
    // network latency without assuming iPad/laptop clocks are synchronized.
  if(!Number.isFinite(stamp)||!Number.isFinite(sequence)||sequence<=app.hostFrameSequence)throw new Error('The live view is frozen. Reconnect the camera.');
    const blob=await response.blob();if(epoch!==app.hostPreviewEpoch)return;
    const url=URL.createObjectURL(blob),image=document.getElementById('hostCameraPreview');
    try{await new Promise((resolve,reject)=>{
      const cancelled=()=>finish(()=>reject(abort.signal.reason||new Error('Preview stopped.')));
      const finish=callback=>{abort.signal.removeEventListener('abort',cancelled);image.onload=null;image.onerror=null;callback();};
      image.onload=()=>finish(resolve);image.onerror=()=>finish(()=>reject(new Error('Could not read a camera frame.')));
      abort.signal.addEventListener('abort',cancelled,{once:true});
      if(abort.signal.aborted){cancelled();return;}
      image.src=url;
    });}
    catch(error){URL.revokeObjectURL(url);throw error;}
    if(epoch!==app.hostPreviewEpoch){URL.revokeObjectURL(url);return;}
    if(app.hostFrameUrl)URL.revokeObjectURL(app.hostFrameUrl);app.hostFrameUrl=url;
    image.hidden=false;app.hostFrameSequence=sequence;app.hostPreviewHealthy=true;
    app.hostLastFrameAt=performance.now();
    clearTimeout(app.hostPreviewWatchdog);
    app.hostPreviewWatchdog=setTimeout(()=>{
      if(epoch!==app.hostPreviewEpoch)return;
      hidePreview(app);
      if(app.captureBusy)displayStatus(app,'Receiving the photo file; preview is paused.','transferring');
      else{displayStatus(app,'No new live-view frame. Reconnect the camera.');app.clearTimers();app.updateCaptureScreenUI();}
    },3000);
    if(!app.captureBusy)displayStatus(app,`${app.hostCameraStatus?.capabilities?.name||'Camera host'} • Live View`, 'previewing');
  }catch(error){
    if(epoch!==app.hostPreviewEpoch)return;
    if(error.code==='busy'&&app.captureBusy){displayStatus(app,'Capturing or transferring the file; preview is paused.','transferring');}
    else{
      const context=app.hostPreviewContext;hidePreview(app);
      const failure=abort.signal.aborted?abort.signal.reason:error;
      displayStatus(app,failure?.message||'Live preview interrupted. Retrying the connection to the laptop…');
      app.clearTimers();app.updateCaptureScreenUI();
      // A failed HTTP frame is not evidence of a disconnected camera. Retry
      // the read, retaining its session/lease; reconnect only on camera errors.
      if(!['unsupported','disabled','event_hardware_required','dependency_missing'].includes(error.code)){
        const cameraDisconnected=['disconnected','disconnect','not_connected','preview_stopped','adapter_changed'].includes(error.code);
        scheduleRecovery(app,epoch,context,!cameraDisconnected);
      }
      return;
    }
  }finally{clearTimeout(timeout);if(app.hostPreviewAbort===abort)app.hostPreviewAbort=null;}
  if(epoch===app.hostPreviewEpoch)app.hostPreviewTimer=setTimeout(()=>nextFrame(app,epoch),200);
}

export async function enableHostCamera(app){
  app.clearTimers();app.stopCurrentStreams();app.cameraSource='host';app.cameraAdapter=null;
  document.getElementById('liveVideo').classList.add('hidden');document.getElementById('simLiveCanvas').classList.add('hidden');document.getElementById('cameraFallbackBar').classList.add('hidden');
  for(const id of ['hostCameraTools','hostCameraStatus'])document.getElementById(id).hidden=false;
  await app.refreshCameraList();
  try{await app.prepareHostCamera();}catch(error){displayStatus(app,error.message);app.showToast(error.message,'error');}
}

export async function prepareHostCamera(app){
  if(app.cameraSource!=='host')return;
  if(app.hostConnectRequest)return app.hostConnectRequest;
  if(app.hostPreviewContext===app.sessionContext&&app.hostPreviewHealthy&&performance.now()-app.hostLastFrameAt<3000)return;
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
    await cameraRequest(app,'/live-view/start',{method:'POST',scope:context});
    await checkCancelled();
    app.hostFrameSequence=-1;
    await nextFrame(app,epoch);await checkCancelled();
    if(!app.hostPreviewHealthy){
      const error=new Error(document.getElementById('hostCameraStatus').textContent||'The live view is not ready.');
      // nextFrame has already chosen retry versus a terminal capability error.
      error.previewRecoveryScheduled=true;throw error;
    }
    document.getElementById('demoModeBadge').textContent=cap.demo?'HOST CAMERA DEMO • '+cap.name+' • Không có shutter DSLR thật':'HOST CAMERA • '+cap.name+' • Chưa xác minh phần cứng tại trạm';
  })();
  try{return await app.hostConnectRequest;}
  catch(error){
    if(connectionEpoch===app.hostPreviewEpoch&&app.sessionContext===connectionContext){
      hidePreview(app);displayStatus(app,error.message||'The camera is not ready. Reconnecting…');
      if(!error.previewRecoveryScheduled&&!['unsupported','disabled','event_hardware_required','dependency_missing'].includes(error.code))scheduleRecovery(app,connectionEpoch,connectionContext);
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
  if(operation&&operation.slot!==slot)throw new Error('A camera request is still in progress. Retry saving before changing slots.');
  if(!operation){operation={slot,key:newId(),completeAfterRecovery:app.singleRetakeIndex!==null||app.isCapturingSequence};app.hostCaptureOperation=operation;}
  try{
    // A failed safe capture is retried only by an explicit user action. A lost
    // response/transfer failure keeps its key so it cannot trigger another shot.
    if(operation.retryNewShot){operation.key=newId();operation.retryNewShot=false;}
    if(!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>3000)await app.prepareHostCamera();
    displayStatus(app,'Capturing and receiving the image file from the host camera…','capturing');
    const result=await (await cameraRequest(app,'/captures',{method:'POST',body:{slot_index:slot},key:operation.key})).json();
    const canvas=await loadStoredPhoto(app,result,operation);
    app.photos[slot]=canvas;app.serverSession=result.session;app.hostCaptureOperation=null;
    app.finalOperation=null;app.lastSavedImage='';app.activeShare=null;app.saveState='capturing';app.persistenceError='';
    app.transitionSession('PREVIEW');app.playShutterSound();app.triggerFlashEffect();app.updateCaptureScreenUI();
    displayStatus(app,'Saved the camera image to slot '+(slot+1),'captured');
    return {accepted:true,photo:result.capture};
  }catch(error){
    operation.retryNewShot=['capture','timeout','disconnect','disconnected'].includes(error.code)&&error.stage!=='transfer'&&!error.uncertain;
    displayStatus(app,error.message||'Could not connect to the host. Retry saving with the same request.');throw error;
  }
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
