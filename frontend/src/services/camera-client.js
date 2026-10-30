/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function initCameraDevices(app) {
  if (app.useHostCameraByDefault()) return app.enableHostCamera();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    app.startSimulatedCamera('Trình duyệt không hỗ trợ Webcam trực tiếp. Đã bật Camera Mô Phỏng Sự Kiện.');
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
      option('simulated_camera','✨ Camera Mô Phỏng Sự Kiện (Demo/Không cần quyền)',app.cameraSource!=='host'&&app.isUsingSimulatedCamera);
      option('host_camera','Camera trên laptop host (theo adapter backend)',app.cameraSource==='host');
    }
  } catch (e) {}
}

export async function selectCameraDevice(app, deviceId) {
  if (app.hostCaptureOperation || app.captureBusy) {
    app.showToast('Đợi nhận/lưu ảnh camera trước khi đổi nguồn. Nếu lỗi, bấm Thử lưu lại.', 'info');
    return app.refreshCameraList();
  }
  if (deviceId === 'host_camera') return app.enableHostCamera();
  if (app.cameraSource === 'host') {
    app.releaseHostCamera();app.cameraSource='browser_demo';
    document.getElementById('hostCameraTools').hidden=true;document.getElementById('hostCameraStatus').hidden=true;
  }
  if (deviceId === 'simulated_camera') {
    app.startSimulatedCamera('Đã chuyển sang chế độ Camera Mô Phỏng Sự Kiện.');
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
