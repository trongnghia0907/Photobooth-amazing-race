/** Extracted from legacy; explicit app context supplied by bootstrap. */

export function triggerPrint(app) {
  app.renderCompositeCanvas();
  const canvas = document.getElementById('compositeCanvas');
  const printImg = document.getElementById('printImageElement');
  printImg.onload = () => {
    printImg.onload = null;
    window.print();
  };
  printImg.src = canvas.toDataURL('image/png', 1.0);
}
