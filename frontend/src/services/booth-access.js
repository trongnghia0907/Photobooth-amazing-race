let csrf='';

export function boothFetch(input,options={}){
  const headers=new Headers(options.headers||{});
  if(csrf&&!['GET','HEAD','OPTIONS'].includes((options.method||'GET').toUpperCase()))headers.set('X-Booth-CSRF',csrf);
  return fetch(input,{...options,headers,credentials:'same-origin',cache:'no-store'});
}

export async function initializeBoothAccess(){
  let response;
  try{response=await fetch('/api/booth/me',{cache:'no-store',signal:AbortSignal.timeout(10000)});}
  catch{document.getElementById('boothPairError').textContent='Could not connect to the backend. Check the laptop and try pairing again.';}
  if(response?.ok){const data=await response.json();csrf=data.csrf_token||'';if(!data.required||csrf)return;}
  const overlay=document.getElementById('boothPairOverlay'),form=document.getElementById('boothPairForm');
  overlay.hidden=false;document.getElementById('boothPairKey').focus();
  await new Promise(resolve=>form.addEventListener('submit',async event=>{
    event.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{
      const result=await fetch('/api/booth/pair',{method:'POST',headers:{'Content-Type':'application/json','X-OSA-Pair':'1'},body:JSON.stringify({key:document.getElementById('boothPairKey').value}),signal:AbortSignal.timeout(15000)});
      const data=await result.json();if(!result.ok)throw new Error(data.error?.message||'Could not pair this device.');
      csrf=data.csrf_token;overlay.hidden=true;resolve();
    }catch(error){document.getElementById('boothPairError').textContent=error.message;}
    finally{document.getElementById('boothPairKey').value='';button.disabled=false;}
  }));
}
