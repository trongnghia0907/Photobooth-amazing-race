import {defaults} from '../../config/defaults.js';

const thumbs=new WeakMap();
function thumbnail(canvas){if(!thumbs.has(canvas))thumbs.set(canvas,canvas.toDataURL('image/jpeg',.65));return thumbs.get(canvas);}

export function initializeKioskUI(app){
  const home=document.getElementById('screenHome');
  const [launch,options]=Array.from(home.children);
  launch.id='setupLaunchCard';options.id='setupOptions';
  const workspace=document.createElement('div');workspace.id='setupWorkspace';
  const preview=document.createElement('div');preview.id='setupPreviewMount';preview.setAttribute('aria-label','Camera preview');
  workspace.append(preview,launch,options);
  const sidebar=document.createElement('aside');sidebar.id='setupRecentSidebar';sidebar.setAttribute('aria-label','Ảnh của khách hiện tại');
  sidebar.innerHTML='<h2>Ảnh của bạn</h2><p id="recentShotProgress" role="status">0 / 6</p><div id="recentPhotoList"></div><p id="recentEmptyState">Chưa có ảnh. Ảnh chụp của phiên hiện tại sẽ xuất hiện ở đây.</p>';
  home.replaceChildren(workspace,sidebar);
  const panel=document.getElementById('cameraPreviewPanel'),anchor=document.createElement('div');anchor.id='capturePreviewMount';
  panel.parentNode.insertBefore(anchor,panel);anchor.append(panel);
  const start=launch.querySelector('button[onclick="app.startAutomaticSession()"]');start.id='setupStartCaptureBtn';start.setAttribute('aria-label','Bắt đầu chụp');
  const cameraStatus=document.createElement('p');cameraStatus.id='setupCameraStatus';cameraStatus.setAttribute('role','status');launch.querySelector('.glass-card').append(cameraStatus);
  const choices=document.getElementById('frameCardCustom').parentElement;choices.id='setupFrameChoices';choices.append(document.getElementById('frameCardLandscape4'));
  document.body.classList.toggle('kiosk-host',!defaults.demoEnabled);
  app.kioskInitialized=true;app.syncSetupLayout();app.renderRecentPhotos();
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('host-capture-fullscreen'))app.exitHostCapture();});
}

export function syncSetupLayout(app){
  if(!app.kioskInitialized)return;
  const target=document.getElementById(app.currentScreen==='home'?'setupPreviewMount':'capturePreviewMount');
  const panel=document.getElementById('cameraPreviewPanel');if(panel.parentElement!==target)target.append(panel);
  document.body.dataset.screen=app.currentScreen;
  app.syncKioskStatus();app.renderRecentPhotos();
}

export function syncKioskStatus(app){
  const status=document.getElementById('setupCameraStatus');if(!status)return;
  status.textContent=app.cameraSource==='host'
    ? (app.hostPreviewHealthy?`${app.hostCameraStatus?.capabilities?.name||'Camera host'} • Live View`:document.getElementById('hostCameraStatus').textContent||'Đang kết nối camera host…')
    : 'DEMO • Preview trình duyệt, không phải shutter máy ảnh thật';
}

export function renderRecentPhotos(app){
  const list=document.getElementById('recentPhotoList');if(!list)return;
  const final=app.serverSession?.finalized?app.lastSavedImage:'';
  const count=app.photos.filter(Boolean).length;
  document.getElementById('recentShotProgress').textContent=final?'Ảnh cuối đã chốt':`${count} / ${app.slotCount} ảnh`;
  document.getElementById('recentEmptyState').hidden=!!(count||final);
  if(app.recentRenderedPhotos?.every((p,i)=>p===app.photos[i])&&app.recentRenderedPhotos.length===app.photos.length&&app.recentRenderedFinal===final)return;
  app.recentRenderedPhotos=app.photos.slice();app.recentRenderedFinal=final;list.replaceChildren();
  if(final){const image=document.createElement('img');image.src=final;image.alt='Composite cuối của phiên hiện tại';list.append(image);return;}
  app.photos.forEach((canvas,index)=>{
    if(!canvas)return;
    const button=document.createElement('button');button.type='button';button.setAttribute('aria-label',`Chụp lại ảnh ${index+1}`);
    const image=document.createElement('img');image.src=thumbnail(canvas);image.alt=`Ảnh ${index+1} của phiên hiện tại`;
    button.append(image);button.addEventListener('click',()=>{app.goToScreen('capture');app.triggerSingleRetake(index);});list.append(button);
  });
}

export function confirmNewGuestSession(app){
  if(!app.serverSession?.finalized&&app.photos.some(Boolean)&&!window.confirm('Ảnh hiện tại chưa được chốt. Bắt đầu phiên mới?'))return;
  app.startNewGuestSession();
}

export function confirmResetShots(app){
  if(app.photos.some(Boolean)&&!window.confirm('Chụp lại toàn bộ ảnh của phiên đang chỉnh?'))return;
  return app.resetSessionShots();
}
