const $=id=>document.getElementById(id);
let page=1,controller,timer,expiryTimer,renderKey,stopped=false;
const requestedPage=()=>new URL(location.href).searchParams.get('page')||'1';
function pageLink(number,label=String(number)){
  const link=document.createElement('a');link.href='/gallery?page='+number;link.textContent=label;
  if(number===page){link.setAttribute('aria-current','page');link.setAttribute('aria-label','Page '+number+', current page');}
  else link.setAttribute('aria-label',label===String(number)?'Page '+number:label+' page');
  link.addEventListener('click',event=>{
    if(event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    event.preventDefault();history.pushState(null,'',link.href);load(number);
  });
  return link;
}
function pagination(pages){
  const nav=$('pagination');nav.replaceChildren();if(pages<2)return;
  if(page>1)nav.append(pageLink(page-1,'Previous'));
  const numbers=new Set([1,pages]);
  for(let n=Math.max(1,page-2);n<=Math.min(pages,page+2);n++)numbers.add(n);
  let previous=0;
  for(const n of [...numbers].sort((a,b)=>a-b)){
    if(previous&&n>previous+1){const gap=document.createElement('span');gap.textContent='…';gap.setAttribute('aria-hidden','true');nav.append(gap);}
    nav.append(pageLink(n));previous=n;
  }
  if(page<pages)nav.append(pageLink(page+1,'Next'));
}
function render(items){
  const key=JSON.stringify([page,items]);if(key===renderKey)return;renderKey=key;
  const grid=$('photoGrid');grid.replaceChildren();clearTimeout(expiryTimer);
  for(const item of items){
    const card=document.createElement('a');card.className='photo-card';card.href=item.photo_url;card.dataset.photoId=item.id;
    card.setAttribute('aria-label','Open event photo '+((page-1)*10+grid.children.length+1));
    const image=document.createElement('img');image.alt='Published Amazing Race 2026 composite photo';image.src=item.preview_url;
    image.loading='lazy';image.decoding='async';image.width=item.width;image.height=item.height;
    image.onerror=()=>{card.remove();renderKey=null;$('galleryStatus').textContent='A photo is temporarily unavailable. The gallery will check again shortly.';};
    card.append(image);grid.append(card);
  }
  $('galleryEmpty').hidden=items.length>0;
  const expiry=Math.min(...items.map(item=>Date.parse(item.expires_at)));
  if(Number.isFinite(expiry))expiryTimer=setTimeout(()=>{
    // Remove expired content immediately, then reconcile pagination.
    grid.replaceChildren();renderKey=null;load(requestedPage(),true);
  },Math.max(0,expiry-Date.now()));
}
async function load(number=requestedPage(),quiet=false){
  if(stopped)return;clearTimeout(timer);controller?.abort();
  const current=new AbortController();controller=current;
  const timeout=setTimeout(()=>current.abort(),8000);
  $('photoGrid').setAttribute('aria-busy','true');$('retryGallery').hidden=true;
  if(!quiet)$('galleryStatus').textContent='Loading event photos…';
  try{
    const response=await fetch('/gallery/api/photos?page='+encodeURIComponent(number),{signal:current.signal,cache:'no-store'});
    if(!response.ok)throw new Error('Gallery unavailable');
    const data=await response.json();if(controller!==current||stopped)return;
    page=data.page;
    const url=new URL(location.href);if(url.searchParams.get('page')!==String(page)){url.searchParams.set('page',page);history.replaceState(null,'',url);}
    render(data.items);pagination(data.pages);
    $('galleryStatus').textContent=data.total?`Page ${page} of ${data.pages} · ${data.total} published photo${data.total===1?'':'s'}`:'';
  }catch(error){
    if(controller!==current||stopped)return;
    // Fail closed after connection loss: do not retain revoked/expired tiles.
    clearTimeout(expiryTimer);$('photoGrid').replaceChildren();renderKey=null;$('pagination').replaceChildren();$('galleryEmpty').hidden=true;
    $('galleryStatus').textContent='Photos are temporarily unavailable. Reconnecting…';$('retryGallery').hidden=false;
  }finally{
    clearTimeout(timeout);
    if(controller===current&&!stopped){$('photoGrid').setAttribute('aria-busy','false');timer=setTimeout(()=>load(requestedPage(),true),15000);}
  }
}
$('retryGallery').addEventListener('click',()=>load(requestedPage()));
window.addEventListener('popstate',()=>load(requestedPage()));
window.addEventListener('pagehide',()=>{stopped=true;controller?.abort();clearTimeout(timer);clearTimeout(expiryTimer);});
window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;load(requestedPage());}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)load(requestedPage(),true);});
load();
