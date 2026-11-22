/** No fabricated share URL and no third-party requests in default demo. */
export function renderQRConnectionMode(app,config=app.sharingConfig){
  const element=document.getElementById('qrConnectionMode');
  if(!element)return;
  let label='Sharing unavailable';
  if(config?.configured){
    if(config.tunnel_status==='connecting')label='Preparing to share…';
    else if(config.tunnel_status!=='disconnected'&&!config.local_only&&!config.lan_only)label='Checking sharing…';
  }
  element.textContent=label;
  element.dataset.state=config?.tunnel_status|| (config?.local_only?'local':'unverified');
}

export function showQRUnavailable(app, message, phase='unconfirmed') {
  app.qrPhase=phase;
  clearTimeout(app.qrImageTimer);
  app.qrImageTimer=null;
  clearTimeout(app.qrUpdateDebounceTimer);
  app.qrUpdateDebounceTimer = null;
  app.lastUploadedUrl = '';
  const container = document.getElementById('qrCodeContainer');
  if (container) {
    container.dataset.phase=phase;
    container.textContent = ({unconfirmed:'Photo awaiting confirmation',processing:'Preparing QR code…',loading:'Preparing QR code…',
      tunnel_connecting:'Preparing to share…',tunnel_disconnected:'Sharing unavailable',
      configuration_error:'Sharing unavailable',unavailable:'Sharing unavailable',expired:'QR code expired'})[phase] || 'Sharing unavailable';
    if(['configuration_error','tunnel_disconnected','unavailable'].includes(phase) && typeof app.generateQRCodeForCurrentPhoto==='function'){
      const retry=document.createElement('button');
      retry.type='button';retry.className='btn-primary-blue px-4 py-3 rounded-xl mt-3';
      retry.textContent='Retry Sharing';
      retry.onclick=async()=>{
        if(app.shareBusy||app.persistenceBusy)return;
        retry.disabled=true;
        try{await app.generateQRCodeForCurrentPhoto(true);}finally{retry.disabled=false;}
      };
      container.appendChild(retry);
    }
  }
  const expiry=document.getElementById('qrExpiryMessage');if(expiry)expiry.hidden=true;
  const description=document.getElementById('qrDescriptionText');
  if(description){
    const pending=['processing','loading','tunnel_connecting'].includes(phase);
    description.hidden=pending;
    description.textContent=pending?'':phase==='unconfirmed'?'Confirm your photo to get the QR code.':
      phase==='error'?'Retrying. Ask event staff if the issue continues.':
      'Ask event staff for help.';
  }
  document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
}
