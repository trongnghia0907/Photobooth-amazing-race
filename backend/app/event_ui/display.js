const $=id=>document.getElementById(id);
const prefix='/event-display';
let pollTimer,pollAbort,stopped=false,epoch=0,initialized=false,working=false,clock=0;
let eligible=new Map(),seen=new Set(),queue=[],queued=new Set(),lifecycle=new AbortController();
const slots=Array.from({length:4},(_,index)=>{
  const node=document.createElement('figure');node.dataset.slot=String(index);
  node.setAttribute('aria-label',['Top left','Top right','Bottom left','Bottom right'][index]);
  $('photoWall').append(node);return {node,key:null,since:0,revision:0};
});
const keyOf=item=>item.id+':'+item.approved_at;
async function api(path,options={}){
  const response=await fetch(prefix+path,{...options,headers:{'X-OSA-Display':'1',...options.headers},credentials:'same-origin',cache:'no-store',signal:options.signal||AbortSignal.timeout(5000)});
  if(!response.ok){await response.json().catch(()=>null);const message=response.status===401?'The display code is incorrect or the event display is not enabled.':`Could not connect to the event display (HTTP ${response.status}). It will retry automatically.`;const error=new Error(message);error.status=response.status;throw error;}
  return response.json();
}
function clearSlot(slot){slot.revision++;slot.key=null;slot.node.classList.remove('fading');slot.node.removeAttribute('data-photo-id');slot.node.replaceChildren();}
function clearPhotos(){
  lifecycle.abort();lifecycle=new AbortController();eligible.clear();seen.clear();queue=[];queued.clear();initialized=false;working=false;
  slots.forEach(clearSlot);$('displayEmpty').hidden=false;
}
function locked(message=''){clearPhotos();$('displayPresentation').hidden=true;$('displayLogin').hidden=false;$('displayLoginError').textContent=message;}
function wait(ms,signal){return new Promise(resolve=>{
  const done=()=>{clearTimeout(timer);signal.removeEventListener('abort',done);resolve();};
  const timer=setTimeout(done,ms);signal.addEventListener('abort',done,{once:true});if(signal.aborted)done();
});}
function preload(item,signal){return new Promise(resolve=>{
  const image=new Image();image.alt='Approved composite photo';image.decoding='async';
  const done=value=>{clearTimeout(timer);image.onload=null;image.onerror=null;signal.removeEventListener('abort',cancel);if(!value)image.removeAttribute('src');resolve(value);};
  const cancel=()=>done(null),timer=setTimeout(cancel,8000);
  image.onload=()=>done(image);image.onerror=cancel;signal.addEventListener('abort',cancel,{once:true});
  if(signal.aborted)cancel();else image.src=item.image_url;
});}
async function drain(){
  if(working||stopped)return;working=true;
  const signal=lifecycle.signal;
  try{while(queue.length&&!signal.aborted){
    const item=queue.shift(),key=keyOf(item);queued.delete(key);
    if(!eligible.has(key)||seen.has(key))continue;
    if(slots.some(slot=>slot.key===key)){seen.add(key);continue;}
    const image=await preload(item,signal);
    if(!image||signal.aborted||!eligible.has(key))continue;
    const slot=slots.find(slot=>!slot.key)||slots.reduce((oldest,next)=>next.since<oldest.since?next:oldest);
    const revision=slot.revision;
    slot.node.classList.add('fading');
    if(slot.key)await wait(500,signal);
    if(signal.aborted)break;
    if(revision!==slot.revision||!eligible.has(key)){slot.node.classList.remove('fading');continue;}
    slot.key=key;slot.since=++clock;slot.node.dataset.photoId=item.id;slot.node.replaceChildren(image);seen.add(key);
    $('displayEmpty').hidden=true;
    // Commit opacity 0 before fading the preloaded image in on this slot only.
    void slot.node.offsetWidth;slot.node.classList.remove('fading');await wait(500,signal);
  }}finally{if(!signal.aborted)working=false;}
}
function render(next){
  const valid=next.filter(item=>typeof item.id==='string'&&Number.isFinite(item.approved_at)&&item.image_url===prefix+'/media/'+item.id);
  eligible=new Map(valid.map(item=>[keyOf(item),item]));
  for(const slot of slots)if(slot.key&&!eligible.has(slot.key))clearSlot(slot);
  let incoming;
  if(!initialized){initialized=true;incoming=valid.slice(0,4);for(const item of valid.slice(4))seen.add(keyOf(item));}
  else incoming=valid.filter(item=>!seen.has(keyOf(item)));
  // The API returns newest approval first. Replay publications oldest first.
  incoming.sort((a,b)=>a.approved_at-b.approved_at||a.id.localeCompare(b.id));
  for(const item of incoming){const key=keyOf(item);if(!queued.has(key)){queued.add(key);queue.push(item);}}
  $('displayEmpty').hidden=slots.some(slot=>slot.key);
  drain();
}
async function poll(generation){
  if(stopped||generation!==epoch)return;
  const abort=new AbortController();pollAbort=abort;const timeout=setTimeout(()=>abort.abort(),5000);
  try{
    const result=await api('/api/photos?limit=100',{signal:abort.signal});if(stopped||generation!==epoch)return;
    if(!Array.isArray(result.items))throw new Error('Invalid photo feed response');
    $('displayPresentation').hidden=false;$('displayLogin').hidden=true;render(result.items);
    $('displayStatus').textContent='Live · Automatically updating approved photos';
  }catch(error){
    if(stopped||generation!==epoch)return;
    if(error.status===401)locked(error.message);
    else $('displayStatus').textContent='Connection lost · Retrying automatically…';
  }finally{clearTimeout(timeout);if(!stopped&&generation===epoch)pollTimer=setTimeout(()=>poll(generation),2500);}
}
function startPolling(){clearTimeout(pollTimer);pollAbort?.abort();poll(++epoch);}
$('displayLoginForm').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;
  try{await api('/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('displayCode').value})});$('displayLoginError').textContent='';startPolling();}
  catch(error){$('displayLoginError').textContent=error.message;}finally{$('displayCode').value='';button.disabled=false;}
});
window.addEventListener('pagehide',()=>{stopped=true;++epoch;clearTimeout(pollTimer);pollAbort?.abort();clearPhotos();});
window.addEventListener('pageshow',event=>{if(event.persisted){stopped=false;startPolling();}});
startPolling();
