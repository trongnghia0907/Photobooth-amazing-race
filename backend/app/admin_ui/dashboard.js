const $=id=>document.getElementById(id);
let csrf='',timer,offset=0,total=0,jobsOffset=0,refreshing=false,maxCopies=3,detailEpoch=0;
const retryOperations=new Map();
const message=text=>{$('message').textContent=text;};
async function api(path,{method='GET',body,key}={}){
  const headers={};
  if(body) headers['Content-Type']='application/json';
  if(csrf) headers['X-CSRF-Token']=csrf;
  if(key) headers['Idempotency-Key']=key;
  if(path==='/login') headers['X-OSA-Login']='1';
  const response=await fetch('/api/admin'+path,{method,headers,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
  const data=await response.json();
  if(!response.ok){if(response.status===401 && path!=='/login') loggedOut();throw new Error(data.error?.message || `API ${response.status}`);}
  return data;
}
function loggedOut(){++detailEpoch;clearInterval(timer);csrf='';$('login').hidden=false;$('dashboard').hidden=true;$('detail').hidden=true;$('eventDisplayCode').textContent='';for(const id of ['gallery','jobs','composites','eventDisplayApproval'])$(id).replaceChildren();}
function el(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
function button(text,action){const node=el('button',text);node.type='button';node.addEventListener('click',async()=>{node.disabled=true;try{await action();}catch(error){message(error.message);}finally{node.disabled=false;}});return node;}
function imageLink(card,url,label){const img=el('img');img.src=url;img.alt=label;card.append(img);const link=el('a','Tải '+label);link.href=url+'?download=true';card.append(link);}
async function showDetail(sid){
  const epoch=++detailEpoch;$('detail').hidden=true;$('composites').replaceChildren();$('eventDisplayApproval').replaceChildren();
  const session=await api('/sessions/'+sid);if(epoch!==detailEpoch)return;
  $('detail').hidden=false;$('sessionInfo').textContent=`${sid} • ${session.status} • ${session.created_at}`;
  if(session.composites.length){
    const controls=el('section');controls.id='displayApprovalControls';
    controls.append(el('p',session.event_display.approved?'ĐÃ DUYỆT trình chiếu sự kiện':'CHƯA DUYỆT trình chiếu sự kiện'));
    const basis=el('select');basis.id='displayApprovalBasis';basis.setAttribute('aria-label','Cơ sở duyệt trình chiếu');
    for(const [value,label] of [['','Chọn cơ sở duyệt'],['guest_consent','Khách đã đồng ý trình chiếu'],['event_authorization','Có ủy quyền phù hợp của sự kiện']]){
      const option=el('option',label);option.value=value;basis.append(option);
    }
    const label=el('label');const consent=el('input');consent.type='checkbox';consent.id='displayConsentConfirmed';label.append(consent,document.createTextNode(' Tôi xác nhận đã có sự đồng ý / ủy quyền hợp lệ cho ảnh này.'));
    const approve=button('Duyệt trình chiếu',async()=>{
      await api('/event-display/photos/'+sid,{method:'PUT',body:{approved:true,approval_basis:basis.value,consent_confirmed:consent.checked}});
      message('Đã duyệt. Màn hình tự cập nhật trong vài giây.');await showDetail(sid);await refreshGallery();
    });approve.id='approveDisplayPhoto';approve.disabled=true;
    const ready=()=>{approve.disabled=!consent.checked||!basis.value;};consent.addEventListener('change',ready);basis.addEventListener('change',ready);
    controls.append(basis,label,approve);
    if(session.event_display.approved){
      const hide=button('Ẩn khỏi màn hình',async()=>{
        await api('/event-display/photos/'+sid,{method:'PUT',body:{approved:false}});
        message('Đã ẩn khỏi màn hình; composite gốc vẫn được giữ.');await showDetail(sid);await refreshGallery();
      });hide.id='hideDisplayPhoto';controls.append(hide);
    }
    $('eventDisplayApproval').append(controls);
  }
  for(const c of session.composites){
    const card=el('article');card.append(el('p',`Composite revision ${c.revision}`));imageLink(card,c.image_url,'composite gốc');
    if(c.print_ready_url){
      imageLink(card,c.print_ready_url,'bản in có QR');
      const copies=el('input');copies.type='number';copies.min=1;copies.max=maxCopies;copies.value=1;copies.setAttribute('aria-label','Số bản in lại');card.append(copies);
      let operation;
      card.append(button('In lại',async()=>{
        const n=Number(copies.value);if(!Number.isInteger(n)||n<1||n>maxCopies)throw new Error(`Chọn 1–${maxCopies} bản.`);
        if(!operation||operation.copies!==n)operation={key:crypto.randomUUID(),copies:n};
        copies.disabled=true;
        const job=await api('/print-jobs',{method:'POST',body:{session_id:sid,final_id:c.final_id,copies:n},key:operation.key});
        operation=null;copies.disabled=false;message('Đã tạo job '+job.id);await refreshJobs();
      }));
    }$('composites').append(card);
  }
}
async function refreshGallery(){
  const data=await api(`/sessions?limit=20&offset=${offset}`);total=data.total;$('gallery').replaceChildren();
  for(const s of data.items){const card=el('article');card.append(el('p',`${s.created_at} • ${s.status} • ${s.slot_count} ảnh`));
    if(s.composite_id){const img=el('img');img.src=`/api/admin/sessions/${s.id}/images/composites/${s.composite_id}`;img.alt='Composite của phiên';card.append(img);card.append(el('p',s.display_approved?'Sự kiện: đã duyệt':'Sự kiện: chưa duyệt'));}
    card.append(button('Xem phiên / In lại',()=>showDetail(s.id)));$('gallery').append(card);}
  $('pagination').textContent=` ${total?offset+1:0}–${Math.min(offset+20,total)} / ${total} `;$('previous').disabled=offset===0;$('next').disabled=offset+20>=total;
}
async function refreshJobs(){
  const data=await api(`/print-jobs?offset=${jobsOffset}`);$('jobs').replaceChildren();
  for(const job of data.items){const card=el('article');card.append(el('p',`${job.id} • ${job.mode} • ${job.copies} bản • ${job.status}`));if(job.error_message)card.append(el('p',job.error_message));
    if(job.status==='failed'){if(!retryOperations.has(job.id))retryOperations.set(job.id,crypto.randomUUID());const retryKey=retryOperations.get(job.id);card.append(button('Thử in lại job lỗi',async()=>{
      if(!confirm(job.uncertain?'Chưa rõ job đã in hay chưa. Bạn đã kiểm tra spooler và giấy, đồng ý có thể in thêm?':'Tạo một lần thử in mới?'))return;
      await api(`/print-jobs/${job.id}/retry`,{method:'POST',body:{acknowledge_uncertain:job.uncertain},key:retryKey});await refreshJobs();}));}
    if(job.status==='queued')card.append(button('Hủy job đang chờ',async()=>{await api(`/print-jobs/${job.id}/cancel`,{method:'POST'});await refreshJobs();}));$('jobs').append(card);}
  $('olderJobs').disabled=data.items.length<50;$('latestJobs').disabled=jobsOffset===0;
}
async function refresh(){
  if(refreshing||!csrf)return;refreshing=true;
  try{const status=await api('/status');maxCopies=status.printer.max_copies;
    $('system').textContent=`Backend online • ${status.sessions} phiên • ${status.photos} ảnh cuối đã chốt • Chờ ${status.queued} • Đang gửi ${status.processing} • Lỗi ${status.failed}`;
    $('printerStatus').textContent=status.printer.message;await refreshGallery();await refreshJobs();
    const display=await api('/event-display/status');$('eventDisplayStatus').textContent=(display.enabled?'Đã bật mã màn hình':'Màn hình chưa được bật')+' • '+display.approved_count+' ảnh được duyệt';
    const camera=await api('/camera'),cap=camera.capabilities;
    $('cameraDiagnostics').textContent=`${cap.name} • ${camera.connected?'Kết nối':'Ngắt kết nối'} • ${camera.state} • Live View: ${cap.live_view?'có':'không'} (${camera.preview_healthy?'frame mới':'chưa có frame mới'}) • Shutter thật: ${cap.physical_shutter?'có':'không'} • File gốc từ camera: ${cap.original_file?'có':'không'} • ${cap.hardware_verified?'HARDWARE VERIFIED':'HARDWARE NOT VERIFIED'}${camera.last_error?' • Lỗi: '+camera.last_error:''}`;
  }catch(error){$('system').textContent='Backend không truy cập được / phiên hết hiệu lực';message(error.message);}finally{refreshing=false;}
}
async function enter(){
  $('login').hidden=true;$('dashboard').hidden=false;message('');const printers=await api('/printers');$('printers').replaceChildren();
  const camera=await api('/camera');$('cameraAdapter').value=camera.capabilities.adapter;$('cameraGuestEnabled').checked=camera.guest_enabled;
  for(const p of printers.items){const option=el('option',p.name);option.value=p.id;option.selected=p.id===printers.selected;$('printers').append(option);}
  await refresh();clearInterval(timer);timer=setInterval(refresh,3000);
}
$('login').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget;const submit=form.querySelector('button');submit.disabled=true;
  try{const data=await api('/login',{method:'POST',body:{username:form.elements.username.value,password:form.elements.password.value}});csrf=data.csrf_token;await enter();}
  catch(error){message(error.message);}finally{form.elements.password.value='';submit.disabled=false;}});
$('logout').addEventListener('click',async()=>{try{await api('/logout',{method:'POST'});loggedOut();}catch(error){message(error.message);}});
$('createDisplayCode').addEventListener('click',async event=>{
  if(!confirm('Tạo mã mới sẽ thu hồi quyền của tất cả màn hình đang mở. Tiếp tục?'))return;
  event.currentTarget.disabled=true;
  $('eventDisplayCode').textContent='';
  try{const data=await api('/event-display/access',{method:'POST'});$('eventDisplayCode').textContent='Mã màn hình (chỉ hiển thị lần này): '+data.code;await refresh();}
  catch(error){message(error.message);}finally{$('createDisplayCode').disabled=false;}
});
$('revokeDisplayCode').addEventListener('click',async event=>{
  event.currentTarget.disabled=true;
  try{await api('/event-display/access/revoke',{method:'POST'});$('eventDisplayCode').textContent='';await refresh();}
  catch(error){message(error.message);}finally{$('revokeDisplayCode').disabled=false;}
});
$('selectPrinter').addEventListener('click',async()=>{try{await api('/printers/selected',{method:'PUT',body:{printer_id:$('printers').value}});await refresh();}catch(error){message(error.message);}});
$('saveCamera').addEventListener('click',async()=>{try{await api('/camera/config',{method:'PUT',body:{adapter:$('cameraAdapter').value,guest_enabled:$('cameraGuestEnabled').checked}});message('Đã cập nhật camera host.');await refresh();}catch(error){message(error.message);}});
$('disconnectCamera').addEventListener('click',async()=>{try{await api('/camera/disconnect',{method:'POST'});message('Đã ngắt camera host.');await refresh();}catch(error){message(error.message);}});
$('previous').addEventListener('click',()=>{offset=Math.max(0,offset-20);refresh();});$('next').addEventListener('click',()=>{offset+=20;refresh();});
$('olderJobs').addEventListener('click',()=>{jobsOffset+=50;refresh();});$('latestJobs').addEventListener('click',()=>{jobsOffset=0;refresh();});
window.addEventListener('pagehide',()=>clearInterval(timer));
try{const me=await api('/me');csrf=me.csrf_token;await enter();}catch{loggedOut();}
