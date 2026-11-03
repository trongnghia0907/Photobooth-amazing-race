const $=id=>document.getElementById(id);
let csrf='',timer,offset=0,total=0,jobsOffset=0,refreshing=false,maxCopies=3,detailEpoch=0;
const retryOperations=new Map();
let frameDetectedSlots=[],noticeTimer,selectedPage='overview',authEpoch=0;
let latestCamera=null,diagnosticSignature=null,galleryKey='',jobsKey='',recentKey='';
const titles={overview:'Tổng quan',photos:'Ảnh đã chụp',prints:'Hàng đợi in',camera:'Camera',frames:'Khung ảnh',event:'Màn hình sự kiện',network:'Mạng & QR',system:'Hệ thống'};
const message=text=>{clearTimeout(noticeTimer);$('message').textContent=text;$('message').hidden=!text;if(text)noticeTimer=setTimeout(()=>{$('message').hidden=true;},7000);};
const dateLabel=value=>value?new Date(value).toLocaleString('vi-VN'):'—';
function showPage(page,{focus=true}={}){
  if(!titles[page])page='overview';selectedPage=page;
  document.querySelectorAll('[data-panel]').forEach(panel=>{panel.hidden=panel.dataset.panel!==page;});
  document.querySelectorAll('nav [data-page]').forEach(node=>{if(node.dataset.page===page)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');});
  $('pageTitle').textContent=titles[page];
  if(location.hash!=='#'+page)history.replaceState(null,'','#'+page);
  if(page!=='event')$('eventDisplayCode').textContent='';
  if(focus)$('pageTitle').focus();
  if(csrf&&page==='photos')refreshGallery().catch(error=>{$('galleryStatus').textContent=error.message;});
  if(csrf&&page==='prints')refreshJobs().catch(error=>{$('jobsStatus').textContent=error.message;});
}
document.querySelectorAll('[data-page]').forEach(node=>node.addEventListener('click',()=>showPage(node.dataset.page)));
window.addEventListener('hashchange',()=>showPage(location.hash.slice(1)));
async function api(path,{method='GET',body,key}={}){
  const headers={};
  if(body) headers['Content-Type']='application/json';
  if(csrf) headers['X-CSRF-Token']=csrf;
  if(key) headers['Idempotency-Key']=key;
  if(path==='/login') headers['X-OSA-Login']='1';
  const epoch=authEpoch;
  const response=await fetch('/api/admin'+path,{method,headers,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000),cache:'no-store'});
  const data=await response.json();
  if(epoch!==authEpoch)throw new Error('Phiên Host đã thay đổi.');
  if(!response.ok){if(response.status===401 && path!=='/login') loggedOut();throw new Error(data.error?.message || `API ${response.status}`);}
  return data;
}
function loggedOut(){++authEpoch;++detailEpoch;clearInterval(timer);csrf='';latestCamera=null;diagnosticSignature=null;galleryKey=jobsKey=recentKey='';$('login').hidden=false;$('dashboard').hidden=true;$('detail').hidden=true;$('eventDisplayCode').textContent='';for(const id of ['gallery','jobs','composites','eventDisplayApproval','overviewPhotos','cameraDiagnosticChecks'])$(id)?.replaceChildren();}
function el(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
function button(text,action){const node=el('button',text);node.type='button';node.addEventListener('click',async()=>{node.disabled=true;try{await action();}catch(error){message(error.message);}finally{node.disabled=false;}});return node;}
function exclusive(id,action){$(id).addEventListener('click',async()=>{const node=$(id);if(node.dataset.busy)return;node.dataset.busy='true';node.disabled=true;try{await action();}catch(error){message(error.message);}finally{node.disabled=false;delete node.dataset.busy;}});}
function imageLink(card,url,label){const preview=el('figure');preview.className='image-preview';const img=el('img');img.src=url;img.alt=label;preview.append(img);const link=el('a','Tải '+label);link.href=url+'?download=true';preview.append(link);card.append(preview);}
function renderFrames(data){
  const list=$('frameList');if(!list)return;list.replaceChildren();
  for(const frame of data.items||[]){const card=el('article');card.append(el('strong',frame.name||frame.id));card.append(el('p',`${frame.layout||'preset'} • ${frame.slot_count||'?'} ảnh • ${frame.configured?'Đã cấu hình':'Chưa cấu hình'}${frame.layout==='grid3x2'?' • LEGACY — Guest không dùng':''}`));if(frame.image_url){const img=el('img');img.src=frame.image_url+'?t='+Date.now();img.alt=frame.name||'Frame';card.append(img);}list.append(card);}
}
async function refreshFrames(){
  try{const data=await api('/frames');renderFrames(data);const custom=data.items.find(frame=>frame.id==='custom');if(custom){$('frameName').value=custom.name||'';$('frameLayout').value=custom.layout||'grid2x3';$('framePadX').value=custom.pad_x??6;$('framePadTop').value=custom.pad_top??7;$('framePadBottom').value=custom.pad_bottom??15;$('frameGap').value=custom.gap??3;$('frameEnabled').checked=custom.enabled!==false;frameDetectedSlots=custom.slots||[];$('framePreview').hidden=!custom.image_url;if(custom.image_url)$('framePreview').src=custom.image_url+'?t='+Date.now();}}
  catch(error){$('frameManagementStatus').textContent=error.message;}
}
async function uploadFrame(file){
  const form=new FormData();form.append('file',file);
  const response=await fetch('/api/admin/frames/custom/upload',{method:'POST',headers:{'X-CSRF-Token':csrf},body:form,signal:AbortSignal.timeout(30000)});const data=await response.json();if(!response.ok)throw new Error(data.error?.message||`API ${response.status}`);return data;
}
function detectTransparentSlots(image){
  const width=300,height=Math.max(1,Math.round(image.naturalHeight/image.naturalWidth*width)),canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0,width,height);const alpha=ctx.getImageData(0,0,width,height).data,seen=new Uint8Array(width*height),boxes=[];
  const transparent=(x,y)=>alpha[(y*width+x)*4+3]<50;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){const start=y*width+x;if(seen[start]||!transparent(x,y))continue;const queue=[start];seen[start]=1;let minX=x,maxX=x,minY=y,maxY=y,count=0;while(queue.length){const pos=queue.pop(),cx=pos%width,cy=Math.floor(pos/width);count++;minX=Math.min(minX,cx);maxX=Math.max(maxX,cx);minY=Math.min(minY,cy);maxY=Math.max(maxY,cy);for(const [nx,ny] of [[cx,cy-1],[cx,cy+1],[cx-1,cy],[cx+1,cy]])if(nx>=0&&nx<width&&ny>=0&&ny<height){const next=ny*width+nx;if(!seen[next]&&transparent(nx,ny)){seen[next]=1;queue.push(next);}}}const bw=maxX-minX+1,bh=maxY-minY+1;if(count>width*height*.03&&bw>width*.15&&bh>height*.12&&bw<width*.95)boxes.push({x:minX/width,y:minY/height,w:bw/width,h:bh/height});}
  boxes.sort((a,b)=>Math.abs(a.y-b.y)>.08?a.y-b.y:a.x-b.x);return boxes;
}
async function showDetail(sid){
  showPage('photos',{focus:false});$('galleryStatus').textContent='Đang tải chi tiết phiên…';
  const epoch=++detailEpoch;$('detail').hidden=true;$('composites').replaceChildren();$('eventDisplayApproval').replaceChildren();
  const session=await api('/sessions/'+sid);if(epoch!==detailEpoch)return;
  $('galleryStatus').textContent='';
  $('detail').hidden=false;$('sessionInfo').textContent=`${sid} • ${session.status} • ${dateLabel(session.created_at)}`;$('detail').scrollIntoView({block:'start'});
  if(session.composites.length){
    const controls=el('section');controls.id='displayApprovalControls';
    controls.append(el('p',session.event_display.approved?'ĐÃ DUYỆT trình chiếu sự kiện':'CHƯA DUYỆT trình chiếu sự kiện'));
    const basis=el('select');basis.id='displayApprovalBasis';basis.setAttribute('aria-label','Cơ sở duyệt trình chiếu');
    for(const [value,label] of [['','Chọn cơ sở duyệt'],['guest_consent','Khách đã đồng ý trình chiếu'],['event_authorization','Có ủy quyền phù hợp của sự kiện']]){
      const option=el('option',label);option.value=value;basis.append(option);
    }
    const label=el('label');label.className='check';const consent=el('input');consent.type='checkbox';consent.id='displayConsentConfirmed';label.append(consent,document.createTextNode(' Tôi xác nhận đã có sự đồng ý / ủy quyền hợp lệ cho ảnh này.'));
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
      const controls=el('div');controls.className='actions';const copies=el('input');copies.type='number';copies.min=1;copies.max=maxCopies;copies.value=1;copies.setAttribute('aria-label','Số bản in lại');controls.append(copies);card.append(controls);
      let operation;
      controls.append(button('In lại',async()=>{
        const n=Number(copies.value);if(!Number.isInteger(n)||n<1||n>maxCopies)throw new Error(`Chọn 1–${maxCopies} bản.`);
        if(!operation||operation.copies!==n)operation={key:crypto.randomUUID(),copies:n};
        copies.disabled=true;
        try{const job=await api('/print-jobs',{method:'POST',body:{session_id:sid,final_id:c.final_id,copies:n},key:operation.key});
          operation=null;message('Đã tạo job '+job.id.slice(0,8));await refreshJobs();
        }finally{copies.disabled=false;}
      }));
    }$('composites').append(card);
  }
}
async function refreshGallery(){
  const requestedOffset=offset;
  const data=await api(`/sessions?limit=20&offset=${requestedOffset}`);if(requestedOffset!==offset)return;total=data.total;
  $('galleryStatus').textContent=data.items.length?'':'Chưa có composite hoàn tất.';
  const signature=JSON.stringify(data);
  if(signature===galleryKey)return;galleryKey=signature;$('gallery').replaceChildren();
  $('galleryStatus').textContent=data.items.length?'':'Chưa có composite hoàn tất.';
  for(const s of data.items){const card=el('article');card.className='photo-card';
    if(s.composite_id){const img=el('img');img.src=`/api/admin/sessions/${s.id}/images/composites/${s.composite_id}`;img.alt='Composite cuối của phiên '+s.id.slice(0,8);img.loading='lazy';card.append(img);}
    card.append(el('p',dateLabel(s.created_at)),el('p',`${s.slot_count} ảnh • ${s.display_approved?'Đã duyệt sự kiện':'Chưa duyệt sự kiện'}`));
    card.append(button('Xem phiên / In lại',()=>showDetail(s.id)));$('gallery').append(card);}
  $('pagination').textContent=` ${total?offset+1:0}–${Math.min(offset+20,total)} / ${total} `;$('previous').disabled=offset===0;$('next').disabled=offset+20>=total;
}
async function refreshRecent(){
  const data=await api('/sessions?limit=6&offset=0'),signature=JSON.stringify(data.items);
  if(signature===recentKey)return;recentKey=signature;$('overviewPhotos').replaceChildren();
  if(!data.items.length)$('overviewPhotos').append(el('p','Chưa có composite hoàn tất.'));
  for(const session of data.items){const item=button('',()=>showDetail(session.id));item.setAttribute('aria-label','Xem ảnh '+dateLabel(session.created_at));const img=el('img');img.src=`/api/admin/sessions/${session.id}/images/composites/${session.composite_id}`;img.alt=`Composite ${session.slot_count} ảnh`;img.loading='lazy';item.append(img);$('overviewPhotos').append(item);}
}
async function refreshJobs(){
  const requestedOffset=jobsOffset;
  const data=await api(`/print-jobs?offset=${requestedOffset}`);if(requestedOffset!==jobsOffset)return;
  $('jobsStatus').textContent=data.items.length?'':'Chưa có job in.';
  const signature=JSON.stringify(data);if(signature===jobsKey)return;jobsKey=signature;$('jobs').replaceChildren();
  $('jobsStatus').textContent=data.items.length?'':'Chưa có job in.';
  const labels={queued:'Queued · Đang chờ',processing:'Processing · Đang xử lý',submitted:'Submitted · Đã gửi',failed:'Failed · Lỗi',cancelled:'Cancelled · Đã hủy'};
  for(const job of data.items){const row=el('tr'),identity=el('td'),actions=el('td');
    identity.append(button('Phiên '+job.session_id.slice(0,8),()=>showDetail(job.session_id)));
    const info=el('details');info.append(el('summary','Chi tiết job'),el('p',job.id));if(job.error_message)info.append(el('p',job.error_message));identity.append(info);
    const printer=el('td',job.mode==='mock'?'Mock / DEMO':job.printer_id||'—');
    row.append(identity,el('td',dateLabel(job.created_at)),printer,el('td',String(job.copies)),el('td',labels[job.status]||job.status),actions);
    if(job.status==='failed'){if(!retryOperations.has(job.id))retryOperations.set(job.id,crypto.randomUUID());const retryKey=retryOperations.get(job.id);actions.append(button('Thử in lại job lỗi',async()=>{
      if(!confirm(job.uncertain?'Chưa rõ job đã in hay chưa. Bạn đã kiểm tra spooler và giấy, đồng ý có thể in thêm?':'Tạo một lần thử in mới?'))return;
      await api(`/print-jobs/${job.id}/retry`,{method:'POST',body:{acknowledge_uncertain:job.uncertain},key:retryKey});await refreshJobs();}));}
    if(job.status==='queued')actions.append(button('Hủy job đang chờ',async()=>{await api(`/print-jobs/${job.id}/cancel`,{method:'POST'});await refreshJobs();}));$('jobs').append(row);}
  $('olderJobs').disabled=data.items.length<50;$('latestJobs').disabled=jobsOffset===0;
}
let cameraDiagnosticRunning=false;
function ensureCameraDiagnosticPanel(){
  let panel=$('cameraDiagnosticPanel');
  if(panel)return panel;
  panel=document.createElement('section');panel.id='cameraDiagnosticPanel';panel.className='camera-diagnostic-panel';panel.setAttribute('aria-live','polite');
  panel.innerHTML='<h3>Kết quả chẩn đoán</h3><p id="cameraDiagnosticSummary">Chưa chạy chẩn đoán.</p><p id="cameraDiagnosticStale" hidden>Kết quả đã cũ — trạng thái camera đã thay đổi. Hãy kiểm tra lại.</p><dl><dt>Adapter</dt><dd id="cameraDiagnosticAdapter">—</dd><dt>Kết nối lúc kiểm tra</dt><dd id="cameraDiagnosticConnection">—</dd><dt>Kiểm tra lần cuối</dt><dd id="cameraDiagnosticCheckedAt">—</dd></dl><div class="table-scroll"><table><thead><tr><th>Kiểm tra</th><th>Trạng thái</th><th>Chi tiết</th></tr></thead><tbody id="cameraDiagnosticChecks"></tbody></table></div>';
  $('cameraDiagnosticMount').append(panel);return panel;
}
function cameraSignature(data){return JSON.stringify([data.capabilities||data.adapter,data.connected??data.connection?.connected,data.previewing??data.connection?.previewing,data.state,data.last_error,data.preview_healthy??latestCamera?.preview_healthy??false]);}
function updateCameraCurrent(camera){
  latestCamera=camera;const cap=camera.capabilities;
  const label=cap.demo?'DEMO • '+(camera.connected?'Đã kết nối':'Ngắt kết nối'):camera.connected?'Đã kết nối • chưa xác minh hardware':'Ngắt kết nối';
  $('cameraDiagnostics').textContent=cap.name+' • '+label;
  $('overviewCamera').textContent=label;
  if(diagnosticSignature&&cameraSignature(camera)!==diagnosticSignature)$('cameraDiagnosticStale').hidden=false;
}
function diagnosticTime(value){return value?new Date(value).toLocaleString():'—';}
function renderDiagnostic(data, mode='diagnostic'){
  ensureCameraDiagnosticPanel();
  $('cameraAdvanced').open=true;
  diagnosticSignature=cameraSignature(data);$('cameraDiagnosticStale').hidden=false;
  if(!latestCamera||cameraSignature(latestCamera)===diagnosticSignature)$('cameraDiagnosticStale').hidden=true;
  const cap=data.adapter||data.capabilities||{};const connection=data.connection||{connected:data.connected,previewing:data.previewing};
  $('cameraDiagnosticAdapter').textContent=cap.name||cap.adapter||'—';
  $('cameraDiagnosticConnection').textContent=`${connection.connected?'Connected':'Not connected'}${data.state?` • ${data.state}`:''}`;
  $('cameraDiagnosticCheckedAt').textContent=diagnosticTime(data.last_checked_at)||new Date().toLocaleString();
  const checks=data.checks||[];$('cameraDiagnosticChecks').replaceChildren();
  for(const check of checks){const item=el('tr');item.append(el('td',check.name));const status=el('td',check.status.replaceAll('_',' '));status.className=`diag-${check.status}`;item.append(status,el('td',[check.detail,check.suggestion].filter(Boolean).join(' ')));$('cameraDiagnosticChecks').append(item);}
  const failed=checks.some(check=>check.status==='FAIL');$('cameraDiagnosticSummary').textContent=mode==='refresh'?'Refresh completed.':failed?'Diagnostic completed with failures.':'Diagnostic completed; see each check below.';
}
async function refreshCameraDiagnostics(){
  if(cameraDiagnosticRunning)return;cameraDiagnosticRunning=true;ensureCameraDiagnosticPanel();
  const button=$('refreshCameraDiagnostics'),label=button.textContent;button.disabled=true;$('runCameraDiagnostic').disabled=true;button.textContent='Đang kiểm tra…';$('cameraAdvanced').open=true;$('cameraDiagnosticSummary').textContent='Đang đọc trạng thái camera…';
  try{const data=await api('/camera');updateCameraCurrent(data);renderDiagnostic({...data,last_checked_at:new Date().toISOString(),checks:[
    {name:'Connection',status:data.connected?'PASS':'FAIL',detail:data.connected?'Đã kết nối':'Chưa kết nối'},
    {name:'Live Preview',status:!data.capabilities.live_view?'UNSUPPORTED':data.preview_healthy?'PASS':'NOT_TESTED',detail:data.preview_healthy?'Có frame mới':'Chưa xác minh frame mới'},
    {name:'Physical shutter',status:data.capabilities.physical_shutter?'NOT_TESTED':'UNSUPPORTED',detail:'Không phát shutter'},
    {name:'Original file',status:data.capabilities.original_file?'NOT_TESTED':'UNSUPPORTED',detail:'Chưa nhận file trong lần kiểm tra này'}
  ]},'refresh');message('Đã làm mới trạng thái camera.');}
  catch(error){$('cameraDiagnosticSummary').textContent=`Refresh failed: ${error.message}`;message(error.message);}
  finally{button.disabled=false;$('runCameraDiagnostic').disabled=false;button.textContent=label;cameraDiagnosticRunning=false;}
}
async function runCameraDiagnostics(){
  if(cameraDiagnosticRunning)return;cameraDiagnosticRunning=true;ensureCameraDiagnosticPanel();
  const refreshButton=$('refreshCameraDiagnostics'),runButton=$('runCameraDiagnostic'),label=runButton.textContent;refreshButton.disabled=true;runButton.disabled=true;runButton.textContent='Running…';$('cameraDiagnosticSummary').textContent='Running safe diagnostics…';
  try{const data=await api('/camera/diagnostic',{method:'POST',body:{confirm_physical_shutter:false}});renderDiagnostic(data);const current=await api('/camera');updateCameraCurrent(current);message('Đã hoàn tất chẩn đoán an toàn. Không phát lệnh shutter.');}
  catch(error){$('cameraDiagnosticSummary').textContent=`Diagnostic failed: ${error.message}`;message(error.message);}
  finally{refreshButton.disabled=false;runButton.disabled=false;runButton.textContent=label;cameraDiagnosticRunning=false;}
}
async function refreshNetwork(){
  try{
    const response=await fetch('/api/health',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error('HTTP '+response.status);
    const health=await response.json();if(!csrf)return;const sharing=health.sharing||{};
    $('overviewNetwork').textContent=sharing.configured?'Đã cấu hình • cần kiểm thử truy cập':'Chưa cấu hình';
    $('qrNetworkStatus').textContent='Kiểm tra cấu hình: '+new Date().toLocaleTimeString('vi-VN');
    $('networkRows').replaceChildren();
    const base=sharing.base_url||'',scope=base.includes('localhost')||base.includes('127.0.0.1')?'Chỉ laptop Host':base.startsWith('https:')?'HTTPS • cần kiểm thử điện thoại':'LAN / HTTP • kiểm tra cùng Wi-Fi';
    for(const values of [['Backend',health.status,health.status==='ok'?'Online':'Lỗi'],['PUBLIC_BASE_URL',base||'Chưa cấu hình',sharing.configured?'Hợp lệ theo cấu hình':'Chưa sẵn sàng'],['Guest Photo Page',sharing.configured?'Đã cấu hình':'Chưa sẵn sàng',scope],['Hạn QR','24 giờ từ lần cấp HTTPS đầu tiên',(sharing.temporary||base.includes('.trycloudflare.com'))?'Tunnel tạm không bảo đảm truy cập liên tục đủ 24 giờ; giữ laptop và tunnel hoạt động.':'URL và máy chủ phải duy trì hoạt động trong thời hạn QR.'],['Kết nối thực tế','Chưa kiểm thử từ điện thoại','NOT TESTED']]){
      const row=el('tr');for(const value of values)row.append(el('td',value));$('networkRows').append(row);
    }
  }catch{$('overviewNetwork').textContent='Không đọc được trạng thái';$('qrNetworkStatus').textContent='Mất kết nối backend. Hệ thống sẽ thử lại.';}
}
async function refresh(){
  if(refreshing||!csrf)return;refreshing=true;
  try{
    const status=await api('/status');maxCopies=status.printer.max_copies;
    $('backendBadge').textContent='Backend online';$('backendBadge').classList.remove('error');$('overviewBackend').textContent='Online';
    $('kpiSessions').textContent=status.sessions;$('kpiCompleted').textContent=status.composites;
    $('kpiPending').textContent=status.queued+status.processing;$('kpiFailed').textContent=status.failed;
    $('system').textContent='Backend online';$('printerStatus').textContent=status.printer.message;
    $('overviewPrinter').textContent=status.printer.mode==='mock'?'Mock / DEMO':status.printer.available?'Sẵn sàng theo cấu hình':'Chưa sẵn sàng';
    const readiness=status.readiness;
    $('systemFacts').replaceChildren();
    if(readiness){
      for(const [name,value] of [['Chế độ',readiness.operation_mode],['Hệ điều hành',readiness.os+' '+readiness.os_version],['Kiến trúc',readiness.architecture],['Dung lượng trống',readiness.free_space_mb+' MB'],['Dự phòng',readiness.reserve_mb+' MB']]){
        $('systemFacts').append(el('dt',name),el('dd',String(value)));
      }
      $('readinessStatus').textContent=[...readiness.blockers,readiness.hardware_acceptance,readiness.network_acceptance].join('\n');
    }
    const errors=[...(readiness?.blockers||[])];if(status.failed)errors.push(status.failed+' job in lỗi. Kiểm tra hàng đợi in.');
    try{const camera=await api('/camera');updateCameraCurrent(camera);if(camera.last_error)errors.push(camera.last_error);}
    catch{$('overviewCamera').textContent='Không đọc được trạng thái';$('cameraDiagnostics').textContent='Không đọc được trạng thái camera.';if(diagnosticSignature)$('cameraDiagnosticStale').hidden=false;errors.push('Không đọc được trạng thái camera.');}
    try{const display=await api('/event-display/status');$('eventDisplayStatus').textContent=(display.enabled?'Đã bật mã màn hình':'Màn hình chưa được bật')+' • '+display.approved_count+' ảnh được duyệt';$('overviewEvent').textContent=(display.enabled?'Enabled':'Disabled')+' • '+display.approved_count+' ảnh';}
    catch{$('overviewEvent').textContent='Không đọc được trạng thái';$('eventDisplayStatus').textContent='Không đọc được cấu hình màn hình sự kiện.';errors.push('Không đọc được trạng thái Event Gallery.');}
    $('activeErrors').replaceChildren();for(const error of errors.length?errors:['Không có lỗi vận hành được báo cáo.'])$('activeErrors').append(el('li',error));
    await refreshNetwork();
    await refreshRecent().catch(()=>{$('overviewPhotos').textContent='Chưa tải được ảnh gần đây. Sẽ tự thử lại.';recentKey='';});
    if(selectedPage==='photos')await refreshGallery().catch(error=>{$('galleryStatus').textContent='Không tải được kho ảnh: '+error.message;});
    if(selectedPage==='prints')await refreshJobs().catch(error=>{$('jobsStatus').textContent='Không tải được hàng đợi: '+error.message;});
  }catch(error){
    $('backendBadge').textContent='Backend không truy cập được';$('backendBadge').classList.add('error');
    $('overviewBackend').textContent='Không kết nối';$('system').textContent=error.message;
    $('activeErrors').replaceChildren(el('li','Không kết nối được backend hoặc phiên Host hết hiệu lực.'));
    if(diagnosticSignature)$('cameraDiagnosticStale').hidden=false;
  }finally{refreshing=false;}
}
async function enter(){
  $('login').hidden=true;$('dashboard').hidden=false;message('');ensureCameraDiagnosticPanel();showPage(location.hash.slice(1)||'overview',{focus:false});const printers=await api('/printers');$('printers').replaceChildren();
  const camera=await api('/camera');$('cameraAdapter').value=camera.capabilities.adapter;$('cameraGuestEnabled').checked=camera.guest_enabled;
  for(const p of printers.items){const option=el('option',p.name);option.value=p.id;option.selected=p.id===printers.selected;$('printers').append(option);}
  await refresh();await refreshFrames();clearInterval(timer);timer=setInterval(refresh,3000);
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
exclusive('selectPrinter',async()=>{await api('/printers/selected',{method:'PUT',body:{printer_id:$('printers').value}});message('Đã chọn máy in.');await refresh();});
exclusive('saveCamera',async()=>{await api('/camera/config',{method:'PUT',body:{adapter:$('cameraAdapter').value,guest_enabled:$('cameraGuestEnabled').checked}});message('Đã cập nhật camera host.');await refresh();});
exclusive('disconnectCamera',async()=>{await api('/camera/disconnect',{method:'POST'});message('Đã ngắt camera host.');await refresh();});
 $('refreshCameraDiagnostics').addEventListener('click',refreshCameraDiagnostics);
 $('runCameraDiagnostic').addEventListener('click',runCameraDiagnostics);
$('frameUpload').addEventListener('change',async event=>{const file=event.target.files?.[0];if(!file)return;try{const result=await uploadFrame(file);$('framePreview').hidden=false;$('framePreview').src=result.image_url+'?t='+Date.now();$('frameManagementStatus').textContent=`Đã lưu ${file.name} (${result.width}×${result.height}px).`;await refreshFrames();}catch(error){$('frameManagementStatus').textContent=error.message;}finally{event.target.value='';}});
$('detectFrameSlots').addEventListener('click',()=>{const image=$('framePreview');if(image.hidden||!image.complete){$('frameDetectStatus').textContent='Hãy tải và lưu PNG trước.';return;}const boxes=detectTransparentSlots(image);frameDetectedSlots=boxes.map(slot=>[slot.x,slot.y,slot.w,slot.h]);$('frameDetectStatus').textContent=boxes.length===($('frameLayout').value==='landscape_4'?4:6)?`Đã dò ${boxes.length} ô trong suốt.`:`Đã dò ${boxes.length} vùng; kiểm tra lại alpha trước khi lưu.`;});
exclusive('saveFrameConfig',async()=>{try{const layout=$('frameLayout').value;const payload={name:$('frameName').value.trim()||'Host custom frame',layout,slot_count:layout==='landscape_4'?4:6,pad_x:Number($('framePadX').value),pad_top:Number($('framePadTop').value),pad_bottom:Number($('framePadBottom').value),gap:Number($('frameGap').value),enabled:$('frameEnabled').checked,slots:frameDetectedSlots};await api('/frames/custom',{method:'PUT',body:payload});$('frameManagementStatus').textContent='Đã lưu cấu hình frame cho Guest.';await refreshFrames();}catch(error){$('frameManagementStatus').textContent=error.message;}});
$('previous').addEventListener('click',()=>{offset=Math.max(0,offset-20);refresh();});$('next').addEventListener('click',()=>{offset+=20;refresh();});
$('olderJobs').addEventListener('click',()=>{jobsOffset+=50;refreshJobs().catch(error=>message(error.message));});$('latestJobs').addEventListener('click',()=>{jobsOffset=Math.max(0,jobsOffset-50);refreshJobs().catch(error=>message(error.message));});
$('refreshGallery').addEventListener('click',()=>{galleryKey='';refreshGallery().catch(error=>{$('galleryStatus').textContent=error.message;});});
window.addEventListener('pagehide',()=>clearInterval(timer));
function mountDriveStorage(){
  const section=el('details');section.className='card';section.id='driveStorage';
  section.innerHTML='<summary>Google Drive · Lưu trữ riêng tư</summary><p id="driveStatus" role="status">Chưa kiểm tra cấu hình Drive.</p><div class="actions"><button id="driveConnect">Kết nối / cấp quyền lại</button><button id="driveCheck">Kiểm tra quyền folder</button><button id="driveTest">Upload ảnh test</button><button id="driveRetry">Thử lại upload lỗi</button><button id="driveRefresh">Làm mới</button></div><pre id="driveErrors"></pre>';
  document.querySelector('[data-panel="system"]').prepend(section);
  const render=data=>{
    const counts=data.counts||{};
    $('driveStatus').textContent=`${data.enabled?'Đã bật Drive':'Drive chưa bật (GOOGLE_DRIVE_ENABLED)'} • Folder: ${data.folder_id} • Privacy: ${data.privacy_verified?'Đã xác minh trong process hiện tại':'Chưa xác minh'}\nChờ: ${(counts.PENDING||0)+(counts.UPLOADING||0)} • SYNCED: ${counts.SYNCED||0} • Lỗi: ${counts.FAILED||0} • Cache: ${(data.staging_bytes/1048576).toFixed(1)} MB\n${data.last_result}`;
    const evidence=(data.privacy_audit?.evidence||[]).flatMap(folder=>(folder.permissions||[]).map(permission=>
      `Folder ${folder.file_id} • inheritedPermissionsDisabled=${folder.inheritedPermissionsDisabled??'UNKNOWN'} • ${permission.type}/${permission.role} • view=${permission.view??'unset'} • ${permission.content_access}: ${permission.reason}`));
    $('driveErrors').textContent=[...(data.errors||[]).map(item=>item.error),...evidence].join('\n');
  };
  const action=async path=>{try{render(await api('/storage/drive'+path,{method:path?'POST':'GET'}));}catch(error){$('driveStatus').textContent=error.message;}};
  exclusive('driveConnect',async()=>{const data=await api('/storage/drive/connect',{method:'POST'});$('driveStatus').textContent=data.instruction;});
  exclusive('driveCheck',()=>action('/check'));
  exclusive('driveRetry',()=>action('/retry'));
  exclusive('driveTest',async()=>{if(confirm('Upload một PNG test có chủ đích vào đúng folder Drive sau kiểm tra privacy?'))await action('/test');});
  exclusive('driveRefresh',()=>action(''));
  section.addEventListener('toggle',()=>{if(section.open&&csrf)action('');});
}
mountDriveStorage();
try{const me=await api('/me');csrf=me.csrf_token;await enter();}catch{loggedOut();}
