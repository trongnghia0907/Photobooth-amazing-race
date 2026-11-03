/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function initCameraDevices(app) {
  if (app.useHostCameraByDefault()) return app.enableHostCamera();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    app.startSimulatedCamera('This browser does not support a live webcam. Event simulation mode has started.');
    return;
  }
  await app.startCameraStream('', false);
  await app.refreshCameraList();
}

export async function refreshCameraList(app) {
  try {
    const devices = navigator.mediaDevices?.enumerateDevices
      ? await navigator.mediaDevices.enumerateDevices() : [];
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    const homeSelect = document.getElementById('homeCameraSelect');
    const liveSelect = document.getElementById('liveCameraSelect');

    for(const select of [homeSelect,liveSelect]){
      select.replaceChildren();
      const option=(value,label,selected)=>{const node=document.createElement('option');node.value=value;node.textContent=label;node.selected=selected;select.append(node);};
      videoDevices.forEach((d,index)=>option(d.deviceId,`📷 ${d.label||`Camera ${index+1}`}`,app.cameraSource!=='host'&&!app.isUsingSimulatedCamera&&d.deviceId===app.selectedDeviceId));
      option('simulated_camera','✨ Event Simulation Camera (Demo / no permission needed)',app.cameraSource!=='host'&&app.isUsingSimulatedCamera);
      option('host_camera','Host laptop camera (backend adapter)',app.cameraSource==='host');
    }
  } catch (e) {}
}

export async function selectCameraDevice(app, deviceId) {
  if (app.hostCaptureOperation || app.captureBusy) {
    app.showToast('Wait for the camera photo to finish transferring or saving before switching sources. If there is an error, select Retry Save.', 'info');
    return app.refreshCameraList();
  }
  if (deviceId === 'host_camera') return app.enableHostCamera();
  if (app.cameraSource === 'host') {
    app.releaseHostCamera();app.cameraSource='browser_demo';
    document.getElementById('hostCameraTools').hidden=true;document.getElementById('hostCameraStatus').hidden=true;
  }
  if (deviceId === 'simulated_camera') {
    app.startSimulatedCamera('Switched to Event Simulation Camera mode.');
    await app.refreshCameraList();
    return;
  }
  app.selectedDeviceId = deviceId;
  await app.startCameraStream(deviceId, true);
  await app.refreshCameraList();
}

export async function requestRealCameraPermission(app) {
  if (app.cameraSource === 'host') return app.prepareHostCamera();
  await app.startCameraStream('', true);
  await app.refreshCameraList();
}
