/** Extracted from legacy; explicit app context supplied by bootstrap. */

export async function initCameraDevices(app) {
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

    let optionsHtml = videoDevices.map((d, idx) => {
      const label = d.label || `Camera Sự Kiện #${idx + 1}`;
      const selected = (!app.isUsingSimulatedCamera && d.deviceId === app.selectedDeviceId) ? 'selected' : '';
      return `<option value="${d.deviceId}" ${selected}>📷 ${label}</option>`;
    }).join('');

    const simSelected = app.isUsingSimulatedCamera ? 'selected' : '';
    optionsHtml += `<option value="simulated_camera" ${simSelected}>✨ Camera Mô Phỏng Sự Kiện (Demo/Không cần quyền)</option>`;

    homeSelect.innerHTML = optionsHtml;
    liveSelect.innerHTML = optionsHtml;
  } catch (e) {}
}

export async function selectCameraDevice(app, deviceId) {
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
  await app.startCameraStream('', true);
  await app.refreshCameraList();
}
