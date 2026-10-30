const $=id=>document.getElementById(id);
const prefix='/event-display';
let items=[],mode='grid',current=0,signature='',pollTimer,slideTimer,stopped=false,pollAbort,epoch=0,manualLock=false;
const nodes=new Map();

async function api(path,options={}){
  const response=await fetch(prefix+path,{...options,headers:{'X-OSA-Display':'1',...options.headers},credentials:'same-origin',cache:'no-store',signal:options.signal||AbortSignal.timeout(5000)});
  if(!response.ok){const data=await response.json().catch(()=>null);const error=new Error(data?.error?.message||(response.status===401?'Nhập lại mã màn hình để tiếp tục.':'Không kết nối được. Màn hình sẽ tự thử lại.'));error.status=response.status;throw error;}
  return response.json();
}
function clearPhotos(){
  items=[];signature='';current=0;clearInterval(slideTimer);nodes.clear();$('photoWall').replaceChildren();$('slideImage').removeAttribute('src');$('slideCaption').textContent='';$('displayEmpty').hidden=false;updateModeVisibility();
}
function locked(message=''){
  clearPhotos();$('displayPresentation').hidden=true;$('displayLogin').hidden=false;$('displayLoginError').textContent=message;
}
function showSlide(){
  if(!items.length)return;
  const item=items[current%items.length],image=$('slideImage');
  image.src=item.image_url;image.classList.remove('slide-enter');void image.offsetWidth;image.classList.add('slide-enter');
  $('slideCaption').textContent=String(current%items.length+1)+' / '+items.length+(current===0?' · Mới nhất':'');
}
function restartSlides(){
  clearInterval(slideTimer);
  if(mode==='slideshow'&&items.length){showSlide();slideTimer=setInterval(()=>{current=(current+1)%items.length;showSlide();},Number($('slideInterval').value)*1000);}
}
function setMode(next){
  mode=next;updateModeVisibility();
  $('gridMode').setAttribute('aria-pressed',String(next==='grid'));$('slideshowMode').setAttribute('aria-pressed',String(next==='slideshow'));restartSlides();
}
function updateModeVisibility(){$('photoWall').hidden=mode!=='grid'||!items.length;$('slideshow').hidden=mode!=='slideshow'||!items.length;}
function render(next){
  const key=next.map(item=>item.id+':'+item.approved_at).join(',');
  if(key===signature)return;
  const oldFirst=items[0]?.id,oldCurrent=items[current]?.id;items=next;signature=key;
  current=oldFirst!==items[0]?.id?0:Math.max(0,items.findIndex(item=>item.id===oldCurrent));
  for(const [id,node] of nodes)if(!items.some(item=>item.id===id)){node.remove();nodes.delete(id);}
  items.forEach((item,index)=>{
    let figure=nodes.get(item.id);
    if(!figure){figure=document.createElement('figure');figure.dataset.photoId=item.id;const image=document.createElement('img');image.alt='Composite đã được duyệt';image.loading=index<5?'eager':'lazy';image.addEventListener('error',()=>{image.removeAttribute('src');signature='';});figure.append(image);nodes.set(item.id,figure);}
    const image=figure.querySelector('img');if(!image.getAttribute('src'))image.src=item.image_url;
    figure.querySelector('figcaption')?.remove();
    if(index===0){const caption=document.createElement('figcaption');caption.textContent='MỚI NHẤT';figure.append(caption);}
    $('photoWall').append(figure);
  });
  $('displayEmpty').hidden=items.length>0;
  updateModeVisibility();
  if(!items.length){$('slideImage').removeAttribute('src');$('slideCaption').textContent='';}
  restartSlides();
}
async function poll(generation){
  if(stopped||generation!==epoch)return;
  const abort=new AbortController();pollAbort=abort;const timeout=setTimeout(()=>abort.abort(),5000);
  try{
    const result=await api('/api/photos',{signal:abort.signal});if(stopped||generation!==epoch)return;
    $('displayPresentation').hidden=false;$('displayLogin').hidden=true;
    render(result.items);$('displayStatus').textContent='Đang trực tiếp · '+items.length+' ảnh đã được duyệt · Tự cập nhật';
  }catch(error){
    if(stopped||generation!==epoch)return;
    clearPhotos();
    if(error.status===401)locked(error.message);
    else $('displayStatus').textContent='Mất kết nối · Tạm ẩn ảnh · Đang tự thử lại…';
  }finally{clearTimeout(timeout);if(!stopped&&generation===epoch)pollTimer=setTimeout(()=>poll(generation),2500);}
}
function startPolling(){clearTimeout(pollTimer);pollAbort?.abort();poll(++epoch);}
$('displayLoginForm').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;
  try{await api('/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('displayCode').value})});manualLock=false;$('displayLoginError').textContent='';startPolling();}
  catch(error){$('displayLoginError').textContent=error.message;}finally{$('displayCode').value='';button.disabled=false;}
});
$('gridMode').addEventListener('click',()=>setMode('grid'));
$('slideshowMode').addEventListener('click',()=>setMode('slideshow'));
$('slideInterval').addEventListener('change',restartSlides);
$('slideImage').addEventListener('error',()=>{$('slideImage').removeAttribute('src');signature='';});
$('fullscreenDisplay').addEventListener('click',async()=>{
  try{if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else $('displayStatus').textContent='Dùng F11 hoặc chế độ trình chiếu của trình duyệt để vào fullscreen.';}
  catch{$('displayStatus').textContent='Không vào được fullscreen. Hãy nhấn F11 trên laptop.';}
});
$('lockDisplay').addEventListener('click',async()=>{
  manualLock=true;++epoch;clearTimeout(pollTimer);pollAbort?.abort();locked();
  try{await api('/lock',{method:'POST'});}catch{$('displayLoginError').textContent='Đã khóa màn hình tại đây. Chưa thu hồi được cookie do mất kết nối; Host có thể thu hồi mã.';}
});
window.addEventListener('pagehide',()=>{stopped=true;++epoch;clearTimeout(pollTimer);clearInterval(slideTimer);pollAbort?.abort();clearPhotos();});
window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;if(!manualLock)startPolling();}});
startPolling();
