/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function renderStickerCategories(app) {
  const bar = document.getElementById('stickerCategoryBar');
  if (!bar) return;
  const labels = {
    'Yêu thích 💙': 'Favorites 💙',
    'Dễ thương 🐻': 'Cute 🐻',
    'Sự kiện 🥂': 'Event 🥂',
    'Biểu cảm 😍': 'Expressions 😍'
  };
  bar.innerHTML = Object.keys(app.stickerLibrary).map(cat => {
    const active = cat === app.activeStickerCategory;
    return `
      <button onclick="app.selectStickerCategory('${cat}')" class="px-3.5 py-1.5 rounded-full text-xs font-extrabold shrink-0 transition-all ${active ? 'btn-primary-blue text-white' : 'bg-brand-50 text-brand-800 hover:bg-brand-100'}">${labels[cat]||cat}</button>
    `;
  }).join('');
}

export function selectStickerCategory(app, cat) {
  app.activeStickerCategory = cat;
  app.renderStickerCategories();
  app.renderStickerItems();
}

export function renderStickerItems(app) {
  const grid = document.getElementById('stickerItemsGrid');
  if (!grid) return;
  const items = app.stickerLibrary[app.activeStickerCategory] || [];
  grid.innerHTML = items.map(emoji => `
    <button onclick="app.addEmojiSticker('${emoji}')" class="h-12 rounded-2xl bg-brand-50/60 hover:bg-brand-100 border border-brand-100 text-2xl flex items-center justify-center transition-transform hover:scale-110 active:scale-95">${emoji}</button>
  `).join('');
}

export function addEmojiSticker(app, emoji) {
  app.placedStickers.push({
    id: Date.now() + Math.random(),
    emoji,
    img: null,
    x: 0.2 + Math.random() * 0.6,
    y: 0.2 + Math.random() * 0.6,
    size: 0.085
  });
  app.renderCompositeCanvas();
  app.scheduleQRCodeUpdate();
}

export function handleCustomStickerUpload(app, event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      app.placedStickers.push({
        id: Date.now(),
        emoji: null,
        img,
        x: 0.5,
        y: 0.5,
        size: 0.14
      });
      app.renderCompositeCanvas();
      app.scheduleQRCodeUpdate();
      app.showToast('Custom sticker added!', 'success');
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
  event.target.value = '';
}

export function clearAllStickers(app) {
  app.placedStickers = [];
  app.renderCompositeCanvas();
  app.scheduleQRCodeUpdate();
}
