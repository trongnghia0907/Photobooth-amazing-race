import {defaults} from '../../config/defaults.js';
import {photoThumbnail as thumbnail} from '../../utils/photo-thumbnail.js';

export function initializeKioskUI(app){
  // Technical controls belong to the authenticated Host Dashboard. Remove
  // their legacy DOM entry points from the Guest document entirely.
  document.getElementById('kioskExtraControls')?.remove();
  document.getElementById('settingsModal')?.remove();
  const home=document.getElementById('screenHome');
  const [launch,options]=Array.from(home.children);
  launch.id='setupLaunchCard';options.id='setupOptions';
  const workspace=document.createElement('div');workspace.id='setupWorkspace';
  const preview=document.createElement('div');preview.id='setupPreviewMount';preview.setAttribute('aria-label','Camera Preview');
  workspace.append(preview,launch,options);
  const sidebar=document.createElement('aside');sidebar.id='setupRecentSidebar';sidebar.setAttribute('aria-label','Amazing Race Moments');
  sidebar.innerHTML='<h2>Amazing Race Moments</h2><p id="recentGalleryStatus" role="status" hidden></p><div id="recentPhotoList" aria-live="polite"></div><p id="recentEmptyState">No photos yet.</p>';
  home.replaceChildren(workspace,sidebar);
  const panel=document.getElementById('cameraPreviewPanel'),anchor=document.createElement('div');anchor.id='capturePreviewMount';
  panel.parentNode.insertBefore(anchor,panel);anchor.append(panel);
  const start=launch.querySelector('button[onclick="app.startAutomaticSession()"]');start.id='setupStartCaptureBtn';start.setAttribute('aria-label','Start Capturing');
  const cameraStatus=document.createElement('p');cameraStatus.id='setupCameraStatus';cameraStatus.setAttribute('role','status');launch.querySelector('.glass-card').append(cameraStatus);
  const choices=document.getElementById('frameCardGrid2x3')?.parentElement;choices.id='setupFrameChoices';
  const result=document.getElementById('screenResult'),resultLayout=document.createElement('div'),resultWorkspace=document.createElement('div');
  resultLayout.id='guestResultLayout';resultWorkspace.id='guestResultWorkspace';resultWorkspace.append(...Array.from(result.children));const reviewProgress=document.createElement('p');reviewProgress.id='guestReviewProgress';reviewProgress.className='font-bold text-brand-700';reviewProgress.setAttribute('role','status');const reviewShots=document.createElement('div');reviewShots.id='guestReviewShots';reviewShots.className='guest-review-shots';const capturedPanel=document.createElement('aside');capturedPanel.id='guestCapturedPanel';capturedPanel.setAttribute('aria-label','Captured Photos');const capturedHeading=document.createElement('h2');capturedHeading.textContent='Captured Photos';capturedPanel.append(capturedHeading,reviewProgress,reviewShots);resultLayout.append(resultWorkspace,capturedPanel);result.append(resultLayout);
  document.getElementById('qrCodeContainer').closest('.glass-card').id='guestDeliveryPanel';
  const actions=document.createElement('div');actions.id='guestDeliveryActions';actions.className='w-full';
  const copies=document.getElementById('printCopies').closest('label'),printStatus=document.getElementById('printStatus'),printerCheck=printStatus.nextElementSibling,printButtons=document.getElementById('printPhotoBtn').parentElement;
  const previewCard=document.getElementById('compositeCanvas').closest('.glass-card');
  previewCard.id='guestCompositeCard';
  const previewColumn=previewCard.parentElement;
  previewColumn.id='guestPreviewColumn';
  previewColumn.parentElement.id='guestResultColumns';
  const download=printButtons.querySelector('button[onclick="app.downloadCompositeImage()"]');
  download.id='downloadPhotoBtn';
  actions.append(download,copies,document.getElementById('printPhotoBtn'),printStatus,printerCheck);
  printButtons.remove();
  const confirm=document.getElementById('confirmSessionBtn');confirm.className='w-full mt-4 px-5 py-4 rounded-xl btn-primary-blue font-bold';
  previewCard.append(document.getElementById('printReadyBox'),document.getElementById('finalPhotoNotice'),confirm);
  document.getElementById('guestDeliveryPanel').parentElement.append(actions);
  resultWorkspace.querySelector(':scope > .glass-card button').id='legacyReviewBack';
  document.body.classList.toggle('kiosk-host',!defaults.demoEnabled);
  app.kioskInitialized=true;app.syncSetupLayout();app.renderRecentPhotos();
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('host-capture-fullscreen'))app.exitHostCapture();});
}

export function syncSetupLayout(app){
  if(!app.kioskInitialized)return;
  const target=document.getElementById(app.currentScreen==='home'?'setupPreviewMount':'capturePreviewMount');
  const panel=document.getElementById('cameraPreviewPanel');if(panel.parentElement!==target)target.append(panel);
  document.body.dataset.screen=app.currentScreen;
  app.syncGuestWorkflowUI();
  app.syncKioskStatus();app.renderRecentPhotos();
}

export function syncGuestWorkflowUI(app){
  if(!app.kioskInitialized)return;
  const active=app.guestWorkflowActive,delivered=!!app.serverSession?.finalized;
  const reviewing=app.currentScreen==='result'&&!delivered;
  const sidebar=document.getElementById('setupRecentSidebar'),result=document.getElementById('guestResultLayout'),home=document.getElementById('screenHome');
  if(sidebar.parentElement!==home)home.append(sidebar);
  result.classList.toggle('automatic-layout',reviewing);
  document.body.dataset.guestFlow=String(active);
  document.body.dataset.workflow=app.guestStarting?'preparing':app.currentScreen==='home'?'setup':app.currentScreen==='capture'?'capture':delivered?'delivery':'review';
  document.getElementById('guestResultTitle').textContent=delivered?'Your Photo':'Customize Your Photo';
  for(const id of ['guestDeliveryPanel','guestDeliveryActions'])document.getElementById(id).hidden=reviewing;
  document.getElementById('guestReviewShots').hidden=delivered;
  document.getElementById('guestCapturedPanel').hidden=!reviewing||!app.photos.some(Boolean);
  const review=document.getElementById('guestReviewProgress');review.hidden=!reviewing;review.textContent=`${app.photos.filter(Boolean).length} / ${app.slotCount} photos captured`;
  const starting=app.guestStarting||app.persistenceBusy||app.captureBusy||app.shareBusy;
  document.getElementById('setupStartCaptureBtn').disabled=starting||app.hasPendingWork()||!app.eventConfigurationReady||app.resumeRecoveryPending;
  document.getElementById('newSessionButton').disabled=app.guestStarting||app.persistenceBusy||app.captureBusy;
  document.getElementById('setupOptions').inert=starting;
  if(active&&!delivered)document.getElementById('confirmSessionBtn').textContent='Confirm & Display';
}

export function syncKioskStatus(app){
  const status=document.getElementById('setupCameraStatus');if(!status)return;
  const overlay=document.getElementById('hostCameraStatus');
  const text=app.cameraSource==='host'
    ? app.hostCaptureBlocker || (!app.hostPreviewHealthy&&!app.persistenceError&&overlay?.hidden ? 'Connecting camera...' : '')
    : '';
  if(status.textContent!==text)status.textContent=text;
}

export function renderRecentPhotos(app){
  const list=document.getElementById('recentPhotoList');if(!list)return;
  const reviewShots=document.getElementById('guestReviewShots');
  if(!app.recentRenderedPhotos||app.recentRenderedPhotos.length!==app.photos.length||app.photos.some((canvas,index)=>canvas!==app.recentRenderedPhotos[index])){
  app.recentRenderedPhotos=app.photos.slice();reviewShots.replaceChildren();
  app.photos.forEach((canvas,index)=>{if(!canvas)return;const button=document.createElement('button');button.type='button';button.className='guest-review-photo';button.setAttribute('aria-label',`Retake photo ${index+1}`);const image=document.createElement('img');image.src=thumbnail(canvas);image.alt=`Photo ${index+1}`;const number=document.createElement('span');number.className='guest-review-number';number.textContent=`#${index+1}`;button.append(image,number);button.addEventListener('click',()=>{app.goToScreen('capture');app.triggerSingleRetake(index);});reviewShots.append(button);});
  }
  const items=app.recentGalleryItems||[],galleryKey=JSON.stringify(items.map(item=>[item?.id,item?.image_url]));
  if(galleryKey!==app.recentGalleryRenderedKey){app.recentGalleryRenderedKey=galleryKey;
  const existing=new Map(Array.from(list.children,card=>[card.querySelector('img')?.dataset.displayId,card])),next=[];
  for(const item of items){
    if(!item||typeof item.image_url!=='string'||!item.image_url.startsWith('/api/booth/recent-photos/'))continue;
    const previous=existing.get(item.id);
    if(previous?.querySelector('img')?.getAttribute('src')===item.image_url){next.push(previous);continue;}
    const card=document.createElement('figure');card.className='recent-gallery-card';
    const image=document.createElement('img');image.src=item.image_url;image.alt='Amazing Race 2026 event photo';image.loading='lazy';image.decoding='async';image.dataset.displayId=item.id;
    card.append(image);next.push(card);
  }
  for(const card of Array.from(list.children))if(!next.includes(card))card.remove();
  next.forEach((card,index)=>{if(list.children[index]!==card)list.insertBefore(card,list.children[index]||null);});
  }
  const empty=document.getElementById('recentEmptyState');empty.hidden=list.childElementCount>0;
  empty.hidden=empty.hidden||!!app.recentGalleryError;
  empty.textContent=app.recentGalleryLoaded?'No photos yet.':'Loading photos…';
  const status=document.getElementById('recentGalleryStatus');status.hidden=!app.recentGalleryError;status.textContent=app.recentGalleryError?'Could not load photos. Retrying…':'';
}

export async function refreshRecentGallery(app){
  if(app.eventConfig?.recent_gallery_available===false){app.recentGalleryLoaded=true;app.renderRecentPhotos();return;}
  if(app.recentGalleryBusy)return;app.recentGalleryBusy=true;
  let failureMessage='Could not connect to the host laptop. Check the backend and Wi-Fi; the system will retry automatically.';
  try{
    const response=await fetch('/api/booth/recent-photos?limit=8',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(5000)});
    if(!response.ok){
      if(response.status===404)failureMessage='The backend is outdated or the address is incorrect (404). On the host laptop, stop Photobooth and restart it with scripts/run_host.py --build.';
      else if(response.status===401)failureMessage='Pair this kiosk with the host to load approved photos.';
      else if(response.status===403)failureMessage='This kiosk is not allowed to view approved photos. Check access on the host laptop.';
      else failureMessage=`The photo feed is unavailable (HTTP ${response.status}). Check the backend on the host laptop; the system will retry automatically.`;
      throw new Error('Recent gallery request failed');
    }
    failureMessage='The photo feed returned an invalid response. Open Photobooth from the host laptop and check the backend.';
    const body=await response.json();if(!Array.isArray(body.items))throw new Error('Invalid recent gallery response');
    app.recentGalleryItems=body.items;app.recentGalleryLoaded=true;app.recentGalleryError='';
  }catch{app.recentGalleryError=failureMessage;}
  finally{app.recentGalleryBusy=false;app.renderRecentPhotos();}
}

export function confirmNewGuestSession(app){
  if(!app.serverSession?.finalized&&(app.photos.some(Boolean)||app.hostCaptureOperation)&&!window.confirm(app.hostCaptureOperation
    ?'Your photo is being processed. Start a new session?'
    :'Your photo has yet to be confirmed. Start a new session?'))return;
  app.startNewGuestSession();
}

export function confirmResetShots(app){
  if(app.photos.some(Boolean)&&!window.confirm('Discard the current shots and start over?'))return;
  return app.resetSessionShots();
}
