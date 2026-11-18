import { defaults } from '../config/defaults.js';
import { newId } from '../utils/ids.js';
import { boothFetch } from './booth-access.js';
import { setCapturePaused } from '../features/capture/countdown.js';
import { rememberSession } from './session-recovery.js';

const FRAME_TIMEOUT_MS=4000, DECODE_TIMEOUT_MS=1000, POLL_MS=200;
const FRAME_PERIOD_MS=100;
// One complete HTTP/body + decode + poll budget, rather than expiring before HTTP.
const PREVIEW_STALE_MS=FRAME_TIMEOUT_MS+DECODE_TIMEOUT_MS+POLL_MS;
const TERMINAL=['unsupported','disabled','event_hardware_required','dependency_missing','worker_stalled'];
const REOPEN=['disconnected','disconnect','not_connected','preview_stopped','adapter_changed','camera_read_failed'];
const CAPTURE_STAGES={waiting_io:'Waiting for the current camera operation…',reconciling:'Checking previous camera transfers…',
  shutter:'Sending the camera shutter request…',recovering:'Recovering the same capture; no new shutter…',
  waiting_buffer:'Waiting for the original JPEG from the camera…',object_info:'Checking the captured image…',
  jpeg_transfer:'Receiving the original JPEG…',jpeg_validation:'Validating the original JPEG…',
  durable_cache:'Safely saving the original JPEG…',buffer_drain:'Checking camera readiness…',
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

function displayStatus(app,text,state='error'){
  app.hostCameraState=state;
  const status=document.getElementById('hostCameraStatus');
  const hidden=app.cameraSource!=='host';
  if(status.hidden!==hidden)status.hidden=hidden;
  if(status.textContent!==text)status.textContent=text;
  if(status.dataset.state!==state)status.dataset.state=state;
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
  if(!frameOnly&&stat.reconnectAttempts>=3){displayStatus(app,'Đã dừng kết nối lại sau 3 lần thử. '+(app.hostCameraLastConnectError||'')+' Kiểm tra camera rồi chọn Kết nối lại camera.','disconnected');return;}
  clearTimeout(app.hostPreviewTimer);
  const wait=delay??(frameOnly?Math.min(2000,POLL_MS*2**Math.min(stat.consecutiveFailures,3)):2000*2**stat.reconnectAttempts);
  const due=performance.now()+wait;
  app.hostPreviewTimer=setTimeout(()=>{
    app.hostPreviewTimer=null;
    if(epoch!==app.hostPreviewEpoch||app.sessionContext!==context||app.cameraSource!=='host')return;
    if(app.captureBusy&&!(frameOnly&&app.hostCaptureRequestActive)){scheduleRecovery(app,epoch,context,frameOnly,POLL_MS);return;}
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
    try{
      const status=await (await cameraRequest(app,'/status',{scope:context,signal:AbortSignal.timeout(2000)})).json();
      if(epoch===app.hostPreviewEpoch&&app.sessionContext===context&&app.hostCaptureRequestActive){
        const progress=status.capture_progress;
        const stage=progress?.stage==='receiving_original'&&status.camera_progress?.capture_id===progress.capture_id
          ?status.camera_progress.stage:progress?.stage;
        if(CAPTURE_STAGES[stage])displayStatus(app,CAPTURE_STAGES[stage],'transferring');
      }
    }catch{/* The capture request owns errors; a status poll must never reconnect or retry a shutter. */}
    if(epoch===app.hostPreviewEpoch)scheduleRecovery(app,epoch,context,true,1000);
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
    if(!app.captureBusy)displayStatus(app,`${app.hostCameraStatus?.capabilities?.name||'Camera host'} • Đang xem trực tiếp`, 'previewing');
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
    if(error.code==='busy'||app.captureBusy)displayStatus(app,'Camera đang bận. Đang chờ khung hình mới.','busy');
    else{
      const message=failure?.message||'HTTP preview interrupted. Retrying the frame; camera connection is unchanged.';
      if(reopen||terminal||error.code==='stale_preview'||!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>=PREVIEW_STALE_MS)previewUnavailable(app,message);
      else displayStatus(app,message,'waiting');
    }
    app.hostCameraNeedsReconnect=reopen;
    if(stat.busyFrames>=6&&!app.hostCaptureRequestActive){
      clearTimeout(app.hostPreviewWatchdog);
      previewUnavailable(app,'Camera vẫn bận. Khi camera rảnh, chọn Kết nối lại camera.');
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
  for(const id of ['hostCameraTools','hostCameraStatus'])document.getElementById(id).hidden=false;
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
    app.stopHostPreview();displayStatus(app,automatic?'Đang khôi phục kết nối camera…':'Đang kết nối camera trên laptop…',automatic?'recovering':'connecting');
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
    displayStatus(app,'Đã kết nối camera. Đang mở Live View…','connected');
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
      app.hostCameraLastConnectError=error.message||'Camera connection failed.';
      if(!error.previewRecoveryScheduled)app.hostCameraNeedsReconnect=true;
      hidePreview(app);
      if(error.code==='busy')displayStatus(app,'Camera đang bận. '+error.message,'busy');
      else if(REOPEN.includes(error.code))displayStatus(app,'Camera mất kết nối. '+error.message,'disconnected');
      else if(!error.previewRecoveryScheduled)displayStatus(app,error.message||'Đang khôi phục kết nối camera…','recovering');
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

async function loadStoredPhoto(app,result,operation,context){
  const photo=result.session?.photos.find(p=>p.id===result.capture.photo_id&&p.slot_index===operation.slot);
  if(!photo)throw new Error('The backend did not confirm the correct photo slot. Retry the same request.');
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
    const checkCurrent=()=>{
      if(app.sessionContext!==captureContext||app.hostCaptureOperation!==operation){
        const error=new Error('Ảnh trả về thuộc phiên cũ; ảnh được giữ trên Host và không đưa vào phiên mới.');
        error.code='capture_superseded';throw error;
      }
    };
    checkCurrent();
    operation.submitted=true;
    captureContext.cameraCapture={...operation};rememberSession(captureContext);
    app.hostCaptureRequestActive=true;
    displayStatus(app,'Capturing and receiving the image file from the host camera…','capturing');
    const submit=()=>cameraRequest(app,'/captures',{method:'POST',body:{slot_index:slot},key:operation.key,scope:captureContext});
    let response;
    try{response=await submit();}
    catch(error){
      if(!recovering||!['not_connected','disconnected','disconnect'].includes(error.code))throw error;
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
    const canvas=await loadStoredPhoto(app,result,operation,captureContext);
    checkCurrent();
    app.photos[slot]=canvas;app.serverSession=result.session;app.hostCaptureOperation=null;
    delete captureContext.cameraCapture;rememberSession(captureContext);
    app.finalOperation=null;app.lastSavedImage='';app.activeShare=null;app.saveState='capturing';app.persistenceError='';
    app.transitionSession('PREVIEW');app.playShutterSound();app.triggerFlashEffect();app.updateCaptureScreenUI();
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
    operation.retryNewShot=['capture','timeout','disconnect','disconnected'].includes(error.code)&&error.stage!=='transfer'&&!error.uncertain;
    if(captureContext){captureContext.cameraCapture={...operation};rememberSession(captureContext);}
    displayStatus(app,error.message||'Could not connect to the host. Retry saving with the same request.');throw error;
  }finally{
    if((!captureContext||app.sessionContext===captureContext)&&(!app.hostCaptureOperation||app.hostCaptureOperation===operation))app.hostCaptureRequestActive=false;
  }
}

export async function retryHostCapture(app){
  if(app.captureBusy||!app.hostCaptureOperation)return;
  const operation=app.hostCaptureOperation,context=app.sessionContext;
  const current=()=>app.sessionContext===context&&(!app.hostCaptureOperation||app.hostCaptureOperation===operation);
  app.captureBusy=true;app.syncHostCaptureUI();
  try{
    await app.captureHostPhoto(operation.slot);
    if(!current())return;
    app.singleRetakeIndex=null;
    app.retakeReturnToReview=false;
    if(app.photos.every(Boolean)&&operation.completeAfterRecovery)app.onAllSixShotsCompleted();
  }catch(error){
    if(!current())return;
    if(['capture_cancelled','capture_superseded'].includes(error.code)){
      app.persistenceError='';app.saveState='capturing';app.transitionSession('PREVIEW');
      app.showToast(error.code==='capture_superseded'
        ?'This session has been replaced. Select New Session; previous photos are preserved.'
        :'The old capture was cancelled. Saved photos are unchanged; choose Capture Now or New Session.','info');
    }else app.reportSaveError(error);
  }
  finally{if(current()){app.captureBusy=false;app.syncPersistenceUI();app.updateCaptureScreenUI();}}
}

export function useHostCameraByDefault(app){return defaults.hostCameraEnabled||app.eventConfig?.event_mode||app.eventConfig?.operation_mode==='rehearsal';}
