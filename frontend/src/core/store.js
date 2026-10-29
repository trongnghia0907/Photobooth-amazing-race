import { filters } from '../config/filters.js';
import { defaults } from '../config/defaults.js';
import { createEmptyPhotos } from '../config/layouts.js';

/** Single state owner, no DOM access. A fresh store per app/test. */
export function createStore() {
  return {
currentScreen: 'home',
stream: null,
selectedDeviceId: '',
mirrorVideo: true,
countdownSeconds: 5,
fullAutoMode: true,
autoPrintPopup: defaults.autoPrintPopup,

presetLayout: 'grid2x3',
customFrameImg: null,
customFrameName: '',
detectedSlots: null,
slotMetrics: { padX: 6, padTop: 7, padBottom: 15, gap: 3 },

photos: createEmptyPhotos('grid2x3'),
isCapturingSequence: false,
singleRetakeIndex: null,
countdownTimerId: null,
sessionStartTimerId: null,
sequenceTimerId: null,
autoPrintTimerId: null,
autoGraceTimerId: null,
graceRemaining: 5,

activeCustomTab: 'filters',
selectedFilter: 'normal',
frameBgColor: '#1E40AF',
customTexts: {
  topText: 'OSA BOOTH',
  cardTitle: 'Osa first meeting ✨',
  brandingText: 'Osa first meeting - 23/10/2026'
},
placedStickers: [],
draggingSticker: null,
dragOffsetX: 0,
dragOffsetY: 0,

imgbbApiKey: '',
qrCloudProvider: 'tmpfiles_direct',
qrUpdateDebounceTimer: null,
lastUploadedUrl: '',

filters,


stickerLibrary: {
  'Yêu thích 💙': ['💙', '✨', '💎', '❄️', '👑', '🦋', '🌟', '🎀', '🎉', '💫', '🫧', '🤍'],
  'Dễ thương 🐻': ['🐻‍❄️', '🐰', '🐱', '🐶', '🐬', '🐳', '🦄', '🐣', '🌸', '🍀', '🌈', '☁️'],
  'Sự kiện 🥂': ['🥂', '🍾', '🎂', '🎁', '🎈', '🪩', '🏆', '🥇', '📸', '🎬', '🎤', '🎶'],
  'Biểu cảm 😍': ['😍', '🥰', '😎', '🤩', '🥳', '🫶', '✌️', '🫰', '💯', '🔥', '💌', '💋']
},
activeStickerCategory: 'Yêu thích 💙',

colorSwatches: ['#1E40AF', '#2563EB', '#0EA5E9', '#38BDF8', '#E0F2FE', '#FFFFFF', '#0F172A', '#1E293B', '#DBEAFE', '#93C5FD', '#60A5FA', '#EFF6FF'],
audioCtx: null,
isUsingSimulatedCamera: false,
simCanvas: null,
simAnimId: null,


  };
}
