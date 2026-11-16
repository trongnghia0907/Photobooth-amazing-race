// Working photo canvases are immutable; retakes replace their identity. Never
// encode the original full-resolution canvas just to render a small UI tile.
const thumbnails=new WeakMap();

export function photoThumbnail(source){
  let entry=thumbnails.get(source);
  if(entry&&entry.width===source.width&&entry.height===source.height)return entry.url;
  const scale=Math.min(1,640/Math.max(source.width,source.height));
  const canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(source.width*scale));
  canvas.height=Math.max(1,Math.round(source.height*scale));
  canvas.getContext('2d').drawImage(source,0,0,canvas.width,canvas.height);
  entry={width:source.width,height:source.height,url:canvas.toDataURL('image/jpeg',.75)};
  thumbnails.set(source,entry);
  return entry.url;
}
