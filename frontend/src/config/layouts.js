/** Legacy geometry stays intact; Phase 2 can enable the proposed four-shot layout. */
export const layouts = Object.freeze({
  grid2x3: { id: 'grid2x3', slotCount: 6, canvasWidth: 1200, canvasHeight: 1800, aspectRatio: 2 / 3, columns: 2, rows: 3 },
  grid3x2: { id: 'grid3x2', slotCount: 6, canvasWidth: 1800, canvasHeight: 1200, aspectRatio: 3 / 2, columns: 3, rows: 2 },
  landscape_4: { id: 'landscape_4', slotCount: 4, canvasWidth: 1800, canvasHeight: 1200, aspectRatio: 3 / 2, columns: 2, rows: 2, enabled: true },
});

export function createEmptyPhotos(layoutId) {
  const layout = layouts[layoutId];
  if (!layout) throw new Error(`Unknown layout: ${layoutId}`);
  return Array(layout.slotCount).fill(null);
}
