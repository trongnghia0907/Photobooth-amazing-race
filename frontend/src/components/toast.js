/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function showToast(app, message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container||!message) return;
  const inline=document.getElementById('sessionSaveStatus')?.textContent;
  if((type==='error'&&app.persistenceError===message&&inline)||(type==='success'&&inline===message))return;
  if(type==='error'&&app.cameraSource==='host'){
    const status=document.getElementById('hostCameraStatus');
    if(status&&!status.hidden&&/camera|shutter|preview|wia|ptp|jpeg/i.test(message))return;
  }

  const colors = {
    success: 'bg-brand-600 text-white border-brand-400',
    info: 'bg-white text-brand-900 border-brand-300',
    warning: 'bg-amber-500 text-white border-amber-400',
    error: 'bg-rose-600 text-white border-rose-400'
  };

  const toast = document.createElement('div');
  toast.className = `pointer-events-auto px-4 py-3 rounded-2xl border shadow-lg text-xs sm:text-sm font-bold flex items-center justify-between gap-3 transition-all duration-300 ${colors[type] || colors.info}`;
  const text=document.createElement('span');text.textContent=type==='error'?'Could not complete the action. Ask event staff.':message;
  const close=document.createElement('button');close.type='button';close.textContent='✕';close.className='opacity-75 hover:opacity-100 font-extrabold';close.addEventListener('click',()=>toast.remove());toast.append(text,close);

  container.appendChild(toast);
  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 3800);
}

export function triggerFlashEffect(app) {
  try {
    const flash = document.getElementById('flashOverlay');
    if (!flash) return;
    flash.classList.remove('flash-active');
    void flash.offsetWidth;
    flash.classList.add('flash-active');
  } catch (e) {}
}
