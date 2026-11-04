import * as client from './session-client.js';
import {boothFetch} from './booth-access.js';
import {newId} from '../utils/ids.js';

const storageKey='amazing-race-session-v1';

export function rememberSession(context){
  try{sessionStorage.setItem(storageKey,JSON.stringify({id:context.id,token:context.token,createKey:context.createKey,slotCount:context.slotCount,layout:context.layout,
    ...(context.cameraCapture?{cameraCapture:{slot:context.cameraCapture.slot,key:context.cameraCapture.key,
      submitted:context.cameraCapture.submitted!==false,completeAfterRecovery:!!context.cameraCapture.completeAfterRecovery,retryNewShot:!!context.cameraCapture.retryNewShot}}:{})}));}catch{/* Restricted storage: in-memory recovery still works until reload. */}
}

export function forgetRememberedSession(){try{sessionStorage.removeItem(storageKey);}catch{}}

async function imageCanvas(app,kind,id){
  const context=app.sessionContext;
  const response=await boothFetch(`/api/sessions/${context.id}/${kind}/${id}/image`,{headers:{Authorization:`Bearer ${context.token}`},signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error('Could not restore the saved photo. Ask event staff to check the connection or storage, then select Retry Save.');
  const url=URL.createObjectURL(await response.blob());
  try{
    const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Could not read the restored photo.'));img.src=url;});
    const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;canvas.getContext('2d').drawImage(image,0,0);return canvas;
  }finally{URL.revokeObjectURL(url);}
}

export async function restoreSavedSession(app){
  let context,raw;
  const invalid=()=>{app.resumeRecoveryPending=true;app.persistenceError='Event staff must check this session. Do not delete its data or create a replacement session.';app.syncPersistenceUI();return true;};
  try{raw=sessionStorage.getItem(storageKey);context=JSON.parse(raw||'null');}catch{return raw?invalid():false;}
  if(!context)return false;
  if(!/^[A-Za-z0-9_-]{32,128}$/.test(context.token)||!/^[A-Za-z0-9_-]{16,128}$/.test(context.createKey)||context.id&&!/^[0-9a-f-]{36}$/i.test(context.id)||![4,6].includes(context.slotCount)||!['grid2x3','grid3x2','landscape_4'].includes(context.layout)){
    return invalid();
  }
  const pending=context.cameraCapture;
  if(pending!==undefined&&(!pending||typeof pending!=='object'||!Number.isInteger(pending.slot)||pending.slot<0||pending.slot>=context.slotCount||!/^[A-Za-z0-9_-]{16,128}$/.test(pending.key)
      ||typeof pending.completeAfterRecovery!=='boolean'||typeof pending.retryNewShot!=='boolean'
      ||pending.submitted!==undefined&&typeof pending.submitted!=='boolean'))return invalid();
  app.persistenceBusy=true;app.syncPersistenceUI();
  try{
    app.sessionContext={...context,request:null};
    await app.ensureSession();
    const state=await client.getSession(app.sessionContext);app.serverSession=state;
    app.slotCount=state.slot_count;app.presetLayout=state.layout;app.photos=Array(app.slotCount).fill(null);app.pendingPhotos=Array(app.slotCount).fill(null);
    app.guestWorkflowActive=state.finalized||state.photos.length>0;
    app.persistenceError='';app.resumeRecoveryPending=false;
    if(state.finalized){
      delete app.sessionContext.cameraCapture;rememberSession(app.sessionContext);
      const saved=await imageCanvas(app,'composites',state.composite.id),canvas=document.getElementById('compositeCanvas');
      canvas.width=saved.width;canvas.height=saved.height;canvas.getContext('2d').drawImage(saved,0,0);
      app.lastSavedImage=canvas.toDataURL('image/png');app.finalOperation={compositeId:state.composite.id,confirmationStarted:true,finalizeKey:newId()};app.activeShare=state.share||null;app.saveState='saved';
      app.goToScreen('result');
      // Only restore/create the share artifact of a composite already confirmed on the backend.
      await app.generateQRCodeForCurrentPhoto(true);
    }else{
      for(const photo of state.photos)app.photos[photo.slot_index]=await imageCanvas(app,'photos',photo.id);
      app.saveState=state.photos.length?'capturing':'idle';app.renderSixSlotsGrid();app.renderCaptureDots();
      app.goToScreen(app.photos.every(Boolean)?'result':'home');
      if(pending){
        app.hostCaptureOperation={...pending,submitted:pending.submitted!==false};app.guestWorkflowActive=true;
        app.saveState='error';
        app.persistenceError='A camera request was interrupted. Select Retry Save to recover the same capture; do not take another photo.';
      }
      if(state.photos.length)app.showToast('Your captured photos have been restored. Review or adjust them before confirming.','info');
    }
    app.updateFrameSelectionUI();return true;
  }catch(error){app.resumeRecoveryPending=true;app.persistenceError=error.message;app.showToast(error.message,'error');return true;}
  finally{app.persistenceBusy=false;app.syncPersistenceUI();}
}
