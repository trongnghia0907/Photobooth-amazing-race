import {boothFetch} from './booth-access.js';

export async function loadEventConfiguration(app){
  try{
    const response=await boothFetch('/api/booth/config',{signal:AbortSignal.timeout(10000)});
    if(!response.ok)throw new Error('Could not load the event configuration. Please ask event staff to update or restart the app.');
    const config=await response.json();
    if(!['development','rehearsal','event'].includes(config.operation_mode)||typeof config.event_mode!=='boolean')throw new Error('The event configuration is invalid.');
    app.eventConfig=config;app.eventConfigurationReady=true;
    document.body.dataset.eventMode=String(config.event_mode);
    const badge=document.getElementById('demoModeBadge');badge.hidden=config.event_mode;
    if(config.operation_mode==='rehearsal')badge.textContent='REHEARSAL / DEMO • Check the camera and printer; real hardware has not been verified.';
    if(config.event_mode){
      // Camera selection, mirror/diagnostic controls and local frame uploads
      // are Host responsibilities in Event Mode. Keep the guest surface to
      // configured frame choices, timer, capture and delivery actions.
      for(const id of ['setupDeviceOptions','kioskExtraControls']){
        const node=document.getElementById(id);if(node)node.hidden=true;
      }
      await loadConfiguredHostFrame(app);
    }
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
    const connection=()=>{notice.hidden=navigator.onLine;notice.textContent='Network connection lost. Saved photos are safe; reconnect to open the photo download page.';if(navigator.onLine)app.refreshRecentGallery();};
    window.addEventListener('pointerdown',schedule,{passive:true});window.addEventListener('keydown',schedule);
    window.addEventListener('online',connection);window.addEventListener('offline',connection);schedule();connection();
    app.eventConfigCleanup=()=>{clearTimeout(app.guestIdleTimer);window.removeEventListener('pointerdown',schedule);window.removeEventListener('keydown',schedule);window.removeEventListener('online',connection);window.removeEventListener('offline',connection);};
    app.syncGuestWorkflowUI();return true;
  }catch(error){
    app.eventConfigurationReady=false;app.persistenceError=error.message;app.syncPersistenceUI();app.showToast(error.message,'error');return false;
  }
}

async function loadConfiguredHostFrame(app){
  try{
    const response=await boothFetch('/api/booth/frames',{signal:AbortSignal.timeout(8000)});
    if(!response.ok)return;
    const body=await response.json();const frame=body.items?.find(item=>item.id==='custom'&&item.configured);
    const card=document.getElementById('frameCardCustom');
    if(!frame){if(card)card.hidden=true;return;}
    // Keep legacy Host frame configurations stored, but apply only the two
    // layouts that are selectable in the Guest setup.
    if(!['grid2x3','landscape_4'].includes(frame.layout)||(frame.layout==='landscape_4'&&frame.slot_count!==4)||(frame.layout==='grid2x3'&&frame.slot_count!==6)){if(card)card.hidden=true;return;}
    const image=new Image();image.src=frame.image_url;await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;});
    app.customFrameImg=image;app.customFrameName=frame.name||'Host custom frame';app.presetLayout=frame.layout;app.slotCount=frame.slot_count;
    app.photos=Array(app.slotCount).fill(null);app.pendingPhotos=Array(app.slotCount).fill(null);
    app.slotMetrics={padX:frame.pad_x??6,padTop:frame.pad_top??7,padBottom:frame.pad_bottom??15,gap:frame.gap??3};
    app.detectedSlots=(frame.slots||[]).length===app.slotCount?(frame.slots||[]).map(slot=>({x:slot[0],y:slot[1],w:slot[2],h:slot[3]})):null;
    if(card){card.hidden=false;card.removeAttribute('onclick');card.style.cursor='default';const input=card.querySelector('input[type=file]');if(input)input.disabled=true;}
    app.updateFrameSelectionUI();app.updateSlotLabels();
  }catch{ const card=document.getElementById('frameCardCustom');if(card)card.hidden=true; /* Presets remain available when no host custom frame is configured. */ }
}
