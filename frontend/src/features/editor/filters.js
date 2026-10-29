/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function renderFilterButtons(app) {
  const container = document.getElementById('filterGridContainer');
  if (!container) return;
  container.innerHTML = app.filters.map(f => {
    const active = f.id === app.selectedFilter;
    return `
      <button onclick="app.selectFilter('${f.id}')" class="p-3 rounded-2xl border-2 transition-all flex flex-col items-center gap-2 ${active ? 'border-brand-600 bg-brand-50/90 shadow-sm' : 'border-brand-100 bg-white hover:border-brand-300'}">
        <div class="w-12 h-8 rounded-full shadow-inner" style="background:${f.color}; filter:${f.css};"></div>
        <span class="text-xs font-extrabold ${active ? 'text-brand-700' : 'text-slate-700'}">${f.name}</span>
      </button>
    `;
  }).join('');
}

export function selectFilter(app, filterId) {
  app.selectedFilter = filterId;
  app.renderFilterButtons();
  app.renderCompositeCanvas();
  app.scheduleQRCodeUpdate();
}
