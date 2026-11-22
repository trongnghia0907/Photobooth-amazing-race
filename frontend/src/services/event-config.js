import {boothFetch} from './booth-access.js';

export async function loadEventConfiguration(app){
  try{
    const response=await boothFetch('/api/booth/config',{signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw new Error('Could not load the event configuration. Please ask event staff to update or restart the app.');
    const config=await response.json();
    if(!['development','rehearsal','event'].includes(config.operation_mode)||typeof config.event_mode!=='boolean')throw new Error('The event configuration is invalid.');
    app.eventConfig=config;app.eventConfigurationReady=true;
    document.body.dataset.eventMode=String(config.event_mode);
    if(config.event_mode){
      // Camera selection, mirror/diagnostic controls and local frame uploads
      // are Host responsibilities in Event Mode. Keep the guest surface to
      // configured frame choices, timer, capture and delivery actions.
      for(const id of ['setupDeviceOptions','kioskExtraControls']){
        const node=document.getElementById(id);if(node)node.hidden=true;
      }
    }
    await loadConfiguredHostFrames(app);
    clearInterval(app.recentGalleryTimer);
    app.recentGalleryTimer=config.recent_gallery_available===false?null:setInterval(()=>app.refreshRecentGallery(),Math.max(3,config.gallery_poll_seconds||5)*1000);
    const seconds=Math.max(0,config.guest_idle_seconds||0);
    const schedule=()=>{
      clearTimeout(app.guestIdleTimer);
      if(seconds)app.guestIdleTimer=setTimeout(()=>{
        // Never discard unconfirmed captures, edits or pending saves on timeout.
        if(app.serverSession?.finalized&&!app.captureBusy&&!app.persistenceBusy&&!app.printBusy&&!app.shareBusy)app.startNewGuestSession();
        schedule();
      },seconds*1000);
    };
    const notice=document.createElement('p');notice.id='guestConnectionNotice';notice.hidden=true;notice.setAttribute('role','status');notice.className='text-center text-amber-800 p-2';document.querySelector('header').after(notice);
    const connection=()=>{notice.hidden=navigator.onLine;notice.textContent='Connection lost. Check your network.';if(navigator.onLine)app.refreshRecentGallery();};
    window.addEventListener('pointerdown',schedule,{passive:true});window.addEventListener('keydown',schedule);
    window.addEventListener('online',connection);window.addEventListener('offline',connection);schedule();connection();
    app.eventConfigCleanup=()=>{clearTimeout(app.guestIdleTimer);window.removeEventListener('pointerdown',schedule);window.removeEventListener('keydown',schedule);window.removeEventListener('online',connection);window.removeEventListener('offline',connection);};
    app.syncGuestWorkflowUI();return true;
  }catch(error){
    app.eventConfigurationReady=false;app.persistenceError=error.message;app.syncPersistenceUI();app.showToast(error.message,'error');return false;
  }
}

async function loadConfiguredHostFrames(app){
  try{
    const response=await boothFetch('/api/booth/frames',{signal:AbortSignal.timeout(8000)});
    if(!response.ok)return;
    const {items}=await response.json();
    if(!Array.isArray(items))return;
    const supported=[['grid2x3',6],['landscape_4',4]];
    await Promise.all(supported.map(async ([layout,count])=>{
      const url='/api/booth/frames/custom/image?layout='+layout;
      const frame=items.find(item=>item.layout===layout&&item.slot_count===count&&item.configured&&item.image_url===url);
      if(!frame)return;
      const image=new Image();
      const loaded=await new Promise(resolve=>{
        image.onload=()=>resolve(true);image.onerror=()=>resolve(false);image.src=url;
      });
      if(loaded)app.hostFrames[layout]={...frame,image};
    }));
    const frame=app.hostFrames[app.presetLayout]||Object.values(app.hostFrames)[0];
    if(!frame)return;
    app.presetLayout=frame.layout;app.slotCount=frame.slot_count;
    app.photos=Array(app.slotCount).fill(null);app.pendingPhotos=Array(app.slotCount).fill(null);
    app.applyConfiguredHostFrame();
    app.updateFrameSelectionUI();app.updateSlotLabels();
  }catch{ /* Presets remain available if the configured image cannot be loaded. */ }
}
