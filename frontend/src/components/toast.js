/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function showToast(app, message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const colors = {
    success: 'bg-brand-600 text-white border-brand-400',
    info: 'bg-white text-brand-900 border-brand-300',
    warning: 'bg-amber-500 text-white border-amber-400',
    error: 'bg-rose-600 text-white border-rose-400'
  };

  const toast = document.createElement('div');
  toast.className = `pointer-events-auto px-4 py-3 rounded-2xl border shadow-lg text-xs sm:text-sm font-bold flex items-center justify-between gap-3 transition-all duration-300 ${colors[type] || colors.info}`;
  toast.innerHTML = `<span>${message}</span><button onclick="this.parentElement.remove()" class="opacity-75 hover:opacity-100 font-extrabold">✕</button>`;

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
