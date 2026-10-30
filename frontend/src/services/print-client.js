import { request } from './api-client.js';
import { newId } from '../utils/ids.js';

function confirmed(app){
  return app.activeShare?.print_ready && app.serverSession?.status==='completed'
    && app.activeShare.composite_id===app.finalOperation?.compositeId
    && app.lastSavedImage===document.getElementById('compositeCanvas')?.toDataURL('image/png')
    && !app.hasPendingWork() && !app.persistenceBusy;
}

export function stopPrintPolling(app){clearTimeout(app.printPollTimer);app.printPollTimer=null;app.printPollingStopped=true;}

export async function loadPrintConfig(app){
  try{app.printConfig=await request('/print-config');app.printError='';}catch(error){app.printError=error.message;}
  app.syncPrintUI();
}

export function syncPrintUI(app){
  const button=document.getElementById('printPhotoBtn');if(!button)return;
  const ready=confirmed(app),share=app.activeShare;
  const preview=document.getElementById('printReadyPreview');document.getElementById('printReadyBox').hidden=!ready;
  const download=document.getElementById('printReadyDownload');
  if(ready)download.href=share.download_url;else download.removeAttribute('href');
  if(ready && preview.dataset.finalId!==share.final_id){
    preview.dataset.finalId=share.final_id;preview.src=share.image_url;
    preview.onerror=()=>{app.printError='Không tải được ảnh print-ready. Kiểm tra backend/storage rồi thử lại.';document.getElementById('printStatus').textContent=app.printError;};
  }else if(!ready){preview.removeAttribute('src');delete preview.dataset.finalId;}
  const copies=document.getElementById('printCopies'),max=app.printConfig?.max_copies||3;
  if(copies.options.length!==max)copies.replaceChildren(...Array.from({length:max},(_,i)=>new Option(`${i+1} bản`,String(i+1))));
  const current=app.printOperation?.finalId===share?.final_id?app.printOperation:null;
  const locked=!!current?.job&&['queued','processing','submitted','failed'].includes(current.job.status);
  button.disabled=!ready||app.printBusy||locked||app.printConfig?.available===false;copies.disabled=app.printBusy||locked||!!current?.sent;
  const labels={queued:'Đã đưa vào hàng đợi.',processing:'Đang gửi tới hệ thống in…',submitted:current?.job?.mode==='mock'?'Mock đã nhận yêu cầu — không in giấy.':'Đã gửi hệ thống in; chưa xác nhận bản giấy.',failed:'Gửi in thất bại. Nhờ Host kiểm tra và thử lại.',cancelled:'Host đã hủy yêu cầu.'};
  document.getElementById('printStatus').textContent=app.printError||(!ready?'Xác nhận & Tạo QR trước khi in.':app.printBusy?'Đang gửi yêu cầu…':labels[current?.job?.status]||app.printConfig?.message||'Chọn số bản và bấm In ảnh.');
}

export async function pollPrintJob(app){
  const operation=app.printOperation;if(!operation?.job||app.printPollingStopped)return;
  try{const job=await request(`/sessions/${operation.sid}/print-jobs/${operation.job.id}`,{token:operation.token});
    if(app.printOperation!==operation||app.printPollingStopped)return;operation.job=job;app.printError=job.error_message||'';app.syncPrintUI();
    if(['queued','processing'].includes(job.status))app.printPollTimer=setTimeout(()=>app.pollPrintJob(),1000);
  }catch(error){if(app.printOperation!==operation||app.printPollingStopped)return;app.printError='Chưa đọc được trạng thái in. Không gửi job mới; đang thử đọc lại.';app.syncPrintUI();app.printPollTimer=setTimeout(()=>app.pollPrintJob(),3000);}
}

export async function triggerPrint(app){
  if(app.printBusy)return;
  if(!confirmed(app)){app.showToast('Hãy bấm Xác nhận & Tạo QR trước khi in.','info');return;}
  const finalId=app.activeShare.final_id;
  let operation=app.printOperation;
  const copies=operation?.finalId===finalId&&operation.sent?operation.copies:Number(document.getElementById('printCopies').value);
  if(operation?.finalId===finalId&&operation.job&&operation.job.status!=='cancelled')return;
  if(!operation||operation.finalId!==finalId||operation.copies!==copies||operation.job?.status==='cancelled'){
    app.stopPrintPolling();operation={finalId,copies,key:newId(),sid:app.sessionContext.id,token:app.sessionContext.token,job:null};app.printOperation=operation;
  }
  operation.sent=true;app.printPollingStopped=false;app.printBusy=true;app.printError='';app.syncPrintUI();
  try{operation.job=await request(`/sessions/${operation.sid}/print-jobs`,{method:'POST',token:operation.token,key:operation.key,body:{final_id:finalId,copies}});if(app.printOperation===operation)app.pollPrintJob();}
  catch(error){if(app.printOperation===operation)app.printError=error.message;}finally{app.printBusy=false;app.syncPrintUI();}
}
