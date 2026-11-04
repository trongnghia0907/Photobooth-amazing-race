/** No fabricated share URL and no third-party requests in default demo. */
export function renderQRConnectionMode(app,config=app.sharingConfig){
  const element=document.getElementById('qrConnectionMode');
  if(!element)return;
  let label='QR connection not verified';
  if(config?.configured){
    if(config.tunnel_status==='connecting')label='Connecting to Cloudflare';
    else if(config.tunnel_status==='disconnected')label='Tunnel disconnected';
    else if(config.temporary&&config.tunnel_status==='ready')label=config.public_origin_verified?'Cloudflare HTTPS • verified':'Cloudflare HTTPS • checking';
    else if(config.local_only)label='Local QR • this laptop only';
    else if(config.lan_only)label='LAN QR • same Wi-Fi only';
    else label='HTTPS • configured by host';
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
    container.textContent = ({unconfirmed:'Photo not confirmed',processing:'Preparing QR code',loading:'Preparing QR code',
      tunnel_connecting:'Connecting to public photo service',tunnel_disconnected:'Public sharing disconnected',
      configuration_error:'Public sharing unavailable',unavailable:'Public sharing unavailable',expired:'QR code expired'})[phase] || 'Temporary sharing failure';
    if(['configuration_error','tunnel_disconnected','unavailable'].includes(phase) && typeof app.generateQRCodeForCurrentPhoto==='function'){
      const retry=document.createElement('button');
      retry.type='button';retry.className='btn-primary-blue px-4 py-3 rounded-xl mt-3';
      retry.textContent='Retry sharing';
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
    description.hidden=false;
    description.textContent=phase==='expired'?'This QR code has expired. Please ask an event staff member for help.':phase==='unconfirmed'?'Confirm your photo to get a QR code.':
      ['configuration_error','tunnel_disconnected','unavailable'].includes(phase)?'Your photo is saved. Ask event staff to start or reconnect public HTTPS sharing, then select Retry sharing.':
      ['processing','loading','tunnel_connecting'].includes(phase)?'Your photo is saved. Connecting and preparing your QR code…':
      'Your photo is saved. Retrying public photo access for up to one minute; ask event staff if sharing stays unavailable.';
  }
  document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
}
