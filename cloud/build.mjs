import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const output = fileURLToPath(new URL('./public/', import.meta.url));
async function copy(source, target) {
  const destination = path.join(output,target);
  await mkdir(path.dirname(destination),{recursive:true});
  await copyFile(path.join(root,source),destination);
}

const assets = [
  ['backend/app/gallery_ui/index.html','gallery/index.html'],
  ['backend/app/gallery_ui/gallery.js','gallery/assets/gallery.js'],
  ['backend/app/gallery_ui/gallery.css','gallery/assets/gallery.css'],
  ['theme/theme-gallery.png','gallery/assets/theme-gallery.png'],
  ['backend/app/event_ui/index.html','event-display/index.html'],
  ['backend/app/event_ui/display.js','event-display/assets/display.js'],
  ['backend/app/event_ui/display.css','event-display/assets/display.css'],
  ['theme/Theme-display.png','event-display/assets/theme-display.png'],
  ['frontend/public/assets/official-theme.png','p/assets/theme.png'],
];
await Promise.all(assets.map(([source,target])=>copy(source,target)));
const guest = await readFile(path.join(root,'backend/app/guest.py'),'utf8');
const match = /<style>([\s\S]+?)<\/style>/.exec(guest);
if (!match) throw new Error('Guest photo stylesheet is missing');
await writeFile(path.join(output,'p/assets/photo.css'),match[1]);

// Keep the approved photo rotation. A TV needs updates within seconds;
// background tabs can wait, and the Gallery already polls more slowly.
const displayPath = path.join(output,'event-display/assets/display.js');
const display = await readFile(displayPath,'utf8');
if (!display.includes('poll(generation),2500')) throw new Error('Event Display polling changed');
await writeFile(displayPath,display.replace('poll(generation),2500','poll(generation),document.hidden?60000:12000'));
