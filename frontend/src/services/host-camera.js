import { defaults } from '../config/defaults.js';
import { newId } from '../utils/ids.js';
import { boothFetch } from './booth-access.js';

async function cameraRequest(app,path,{method='GET',body,key,signal,scope}={}){
  const context=scope||await app.ensureSession();
  const response=await boothFetch(`/api/sessions/${context.id}/camera${path}`,{
    method,headers:{Authorization:`Bearer ${context.token}`,...(body?{'Content-Type':'application/json'}:{}),...(key?{'Idempotency-Key':key}:{})},
    body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(130000),
  });
  if(!response.ok){const data=await response.json();const error=new Error(data.error?.message||'Camera host không phản hồi.');Object.assign(error,data.error);throw error;}
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
}

async function nextFrame(app,epoch){
  if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host')return;
  const abort=new AbortController();app.hostPreviewAbort=abort;
  const timeout=setTimeout(()=>abort.abort(),4000);
  try{
    const response=await cameraRequest(app,'/frame',{signal:abort.signal});
    const sequence=Number(response.headers.get('X-Frame-Sequence'));
    const stamp=Number(response.headers.get('X-Frame-Time'));
    // Server checks camera-clock age. Browser checks sequence progression and
    // network latency without assuming iPad/laptop clocks are synchronized.
    if(!Number.isFinite(stamp)||!Number.isFinite(sequence)||sequence<=app.hostFrameSequence)throw new Error('Live View đứng hình; kết nối lại camera.');
    const blob=await response.blob();if(epoch!==app.hostPreviewEpoch)return;
    const url=URL.createObjectURL(blob),image=document.getElementById('hostCameraPreview');
    try{await new Promise((resolve,reject)=>{
      const cancelled=()=>reject(new Error('Đã dừng preview.'));
      const finish=callback=>{abort.signal.removeEventListener('abort',cancelled);callback();};
      image.onload=()=>finish(resolve);image.onerror=()=>finish(()=>reject(new Error('Không đọc được frame camera.')));
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
      if(app.captureBusy)displayStatus(app,'Đang nhận file ảnh; preview tạm dừng.','transferring');
      else{displayStatus(app,'Live View không có frame mới. Kết nối lại camera.');app.clearTimers();app.updateCaptureScreenUI();}
    },3000);
    if(!app.captureBusy)displayStatus(app,`${app.hostCameraStatus?.capabilities?.name||'Camera host'} • Live View`, 'previewing');
  }catch(error){
    if(epoch!==app.hostPreviewEpoch)return;
    if(error.code==='busy'&&app.captureBusy){displayStatus(app,'Đang chụp/truyền file; preview tạm dừng.','transferring');}
    else{hidePreview(app);displayStatus(app,error.message||'Mất kết nối Live View. Bấm Kết nối lại.');app.clearTimers();app.updateCaptureScreenUI();return;}
  }finally{clearTimeout(timeout);}
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
  const requestedEpoch=app.hostPreviewEpoch;
  app.hostConnectRequest=(async()=>{
    if(app.hostReleaseRequest)await app.hostReleaseRequest;
    if(requestedEpoch!==app.hostPreviewEpoch||app.cameraSource!=='host')throw new Error('Đã hủy kết nối camera.');
    const context=await app.ensureSession();
    if(requestedEpoch!==app.hostPreviewEpoch||app.sessionContext!==context)throw new Error('Phiên đã đổi; hãy kết nối lại camera.');
    app.stopHostPreview();displayStatus(app,'Đang kết nối camera trên laptop…','connecting');
    const epoch=app.hostPreviewEpoch;
    const checkCancelled=async()=>{
      if(epoch!==app.hostPreviewEpoch||app.cameraSource!=='host'||app.sessionContext!==context){
        await boothFetch(`/api/sessions/${context.id}/camera/disconnect`,{method:'POST',headers:{Authorization:`Bearer ${context.token}`},keepalive:true}).catch(()=>{});
        throw new Error('Đã hủy kết nối camera cho phiên cũ.');
      }
    };
    const connected=await (await cameraRequest(app,'/connect',{method:'POST',scope:context})).json();
    await checkCancelled();app.hostCameraStatus=connected;
    const cap=app.hostCameraStatus.capabilities;
    if(!cap.capture)throw new Error('Adapter chưa hỗ trợ chụp. Không dùng preview làm ảnh thay thế.');
    if(!cap.demo&&(!cap.physical_shutter||!cap.original_file))throw new Error('Camera chưa hỗ trợ shutter + file ảnh gốc.');
    await cameraRequest(app,'/live-view/start',{method:'POST',scope:context});
    await checkCancelled();
    app.hostFrameSequence=-1;
    await nextFrame(app,epoch);await checkCancelled();
    if(!app.hostPreviewHealthy)throw new Error('Live View chưa sẵn sàng. Kết nối lại camera.');
    document.getElementById('demoModeBadge').textContent=cap.demo?'HOST CAMERA DEMO • '+cap.name+' • Không có shutter DSLR thật':'HOST CAMERA • '+cap.name+' • Chưa xác minh phần cứng tại trạm';
  })();
  try{return await app.hostConnectRequest;}finally{app.hostConnectRequest=null;}
}

export function releaseHostCamera(app){
  app.stopHostPreview();app.syncHostCaptureUI();
  const context=app.sessionContext;
  if(app.cameraSource!=='host'||!context?.id)return;
  const release=boothFetch(`/api/sessions/${context.id}/camera/disconnect`,{method:'POST',headers:{Authorization:`Bearer ${context.token}`},keepalive:true}).catch(()=>null).finally(()=>{if(app.hostReleaseRequest===release)app.hostReleaseRequest=null;});
  app.hostReleaseRequest=release;
}

export function syncHostCaptureUI(app){
  const full=app.currentScreen==='capture'&&(app.isCapturingSequence||app.captureBusy);
  document.body.classList.toggle('host-capture-fullscreen',!!full);
  app.syncSetupLayout?.();
  const next=app.singleRetakeIndex??app.photos.findIndex(p=>!p);
  const progress=document.getElementById('hostShotProgress');
  if(progress)progress.textContent=`${next<0?app.slotCount:next+1} / ${app.slotCount}`;
}

export function exitHostCapture(app){app.clearTimers();app.updateCaptureScreenUI();}

async function loadStoredPhoto(app,result,operation){
  const photo=result.session?.photos.find(p=>p.id===result.capture.photo_id&&p.slot_index===operation.slot);
  if(!photo)throw new Error('Backend chưa xác nhận đúng ảnh/slot. Thử lại cùng yêu cầu.');
  const context=app.sessionContext;
  const response=await boothFetch(`/api/sessions/${context.id}/photos/${photo.id}/image`,{headers:{Authorization:`Bearer ${context.token}`},signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error('Ảnh đã lưu nhưng chưa tải về màn hình. Bấm Thử lưu lại; không cần chụp lại.');
  const url=URL.createObjectURL(await response.blob());
  try{
    const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Không đọc được ảnh camera đã lưu.'));img.src=url;});
    const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
    canvas.getContext('2d').drawImage(image,0,0); // saved capture file, never the preview element
    return canvas;
  }finally{URL.revokeObjectURL(url);}
}

export async function captureHostPhoto(app,slot){
  let operation=app.hostCaptureOperation;
  if(operation&&operation.slot!==slot)throw new Error('Còn yêu cầu camera chưa nhận xong. Thử lưu lại trước khi đổi slot.');
  if(!operation){operation={slot,key:newId()};app.hostCaptureOperation=operation;}
  try{
    // A failed safe capture is retried only by an explicit user action. A lost
    // response/transfer failure keeps its key so it cannot trigger another shot.
    if(operation.retryNewShot){operation.key=newId();operation.retryNewShot=false;}
    if(!app.hostPreviewHealthy||performance.now()-app.hostLastFrameAt>3000)await app.prepareHostCamera();
    displayStatus(app,'Đang chụp và nhận file ảnh từ camera host…','capturing');
    const result=await (await cameraRequest(app,'/captures',{method:'POST',body:{slot_index:slot},key:operation.key})).json();
    const canvas=await loadStoredPhoto(app,result,operation);
    app.photos[slot]=canvas;app.serverSession=result.session;app.hostCaptureOperation=null;
    app.finalOperation=null;app.lastSavedImage='';app.activeShare=null;app.saveState='capturing';app.persistenceError='';
    app.transitionSession('PREVIEW');app.playShutterSound();app.triggerFlashEffect();app.updateCaptureScreenUI();
    displayStatus(app,'Đã lưu file ảnh camera cho ô '+(slot+1),'captured');
    return {accepted:true,photo:result.capture};
  }catch(error){
    operation.retryNewShot=['capture','timeout','disconnect','disconnected'].includes(error.code)&&error.stage!=='transfer'&&!error.uncertain;
    displayStatus(app,error.message||'Không kết nối được host. Thử lưu lại cùng yêu cầu.');throw error;
  }
}

export async function retryHostCapture(app){
  if(app.captureBusy||!app.hostCaptureOperation)return;
  app.captureBusy=true;app.syncHostCaptureUI();
  try{
    const slot=app.hostCaptureOperation.slot;
    await app.captureHostPhoto(slot);app.singleRetakeIndex=null;
    if(app.photos.every(Boolean))app.onAllSixShotsCompleted();
  }catch(error){app.reportSaveError(error);}
  finally{app.captureBusy=false;app.syncPersistenceUI();app.updateCaptureScreenUI();}
}

export function useHostCameraByDefault(){return defaults.hostCameraEnabled;}
