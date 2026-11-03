/** No fabricated share URL and no third-party requests in default demo. */
export function renderQRConnectionMode(app,config=app.sharingConfig){
  const element=document.getElementById('qrConnectionMode');
  if(!element)return;
  let label='QR connection not verified';
  if(config?.configured){
    if(config.tunnel_status==='connecting')label='Connecting to Cloudflare';
    else if(config.tunnel_status==='disconnected')label='Tunnel disconnected';
    else if(config.temporary&&config.tunnel_status==='ready')label='Cloudflare HTTPS • verified';
    else if(config.local_only)label='Local QR • this laptop only';
    else if(config.lan_only)label='LAN QR • same Wi-Fi only';
    else label='HTTPS • configured by host';
  }
  element.textContent=label;
  element.dataset.state=config?.tunnel_status|| (config?.local_only?'local':'unverified');
}

export function showQRUnavailable(app, message, phase='unconfirmed') {
  app.qrPhase=phase;
  clearTimeout(app.qrUpdateDebounceTimer);
  app.qrUpdateDebounceTimer = null;
  app.lastUploadedUrl = '';
  const container = document.getElementById('qrCodeContainer');
  if (container) {
    container.dataset.phase=phase;
    container.textContent = phase==='unconfirmed' ? 'Photo not confirmed' : 'Could not create QR code';
  }
  const expiry=document.getElementById('qrExpiryMessage');if(expiry)expiry.hidden=true;
  const description=document.getElementById('qrDescriptionText');
  if(description){
    description.hidden=false;
    description.textContent=phase==='expired'?'This QR code has expired. Please ask an event staff member for help.':phase==='unconfirmed'?'Confirm your photo to get a QR code.':
      ['processing','loading','tunnel_connecting'].includes(phase)?'Your photo is saved. Preparing your QR code…':
      'Your photo is saved. The QR code is not ready yet; the system will retry automatically. Please ask a staff member if you need help.';
  }
  document.getElementById('qrLoadingOverlay')?.classList.add('hidden');
}
