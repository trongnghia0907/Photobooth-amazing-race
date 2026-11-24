"""Minimal mobile guest page. No booth controls, identifiers or gallery links."""
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

router = APIRouter(prefix='/p')
PRIVATE_HEADERS = {
    'Cache-Control':'no-store', 'X-Robots-Tag':'noindex, nofollow',
    'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff',
}


@router.get('/assets/theme.png')
def theme_artwork():
    # Public, fixed presentation asset only; never resolve user input/storage paths.
    return FileResponse(Path(__file__).resolve().parents[2]/'frontend/public/assets/official-theme.png',
                        media_type='image/png',headers={'Cache-Control':'public, max-age=86400','X-Content-Type-Options':'nosniff'})


def page(content, status=200, script=''):
    nonce=secrets.token_urlsafe(18)
    headers={**PRIVATE_HEADERS,'Content-Security-Policy':
        f"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}
    html='''<!doctype html><html lang="vi" class="qr-photo-page"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow">
<title>Ảnh của bạn • AMAZING RACE 2026</title><style>
*{box-sizing:border-box}
html{min-height:100%;background:#78d9f2}
body{
  --safe-top:env(safe-area-inset-top,0px);
  --safe-bottom:env(safe-area-inset-bottom,0px);
  --safe-left:env(safe-area-inset-left,0px);
  --safe-right:env(safe-area-inset-right,0px);
  --brand-top:clamp(24px,13vh,118px);
  --photo-reserve:calc(var(--brand-top) + 136px + var(--safe-top) + var(--safe-bottom));
  margin:0;min-height:100vh;min-height:100dvh;isolation:isolate;
  color:#113454;font:16px/1.5 system-ui,sans-serif;overflow-wrap:anywhere;
  padding:var(--safe-top) var(--safe-right) var(--safe-bottom) var(--safe-left);
}
@supports(height:100dvh){body{--brand-top:clamp(24px,13dvh,118px)}}
body::before{
  content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:#78d9f2 url('/p/assets/theme.png') center center/cover no-repeat;
}
main{
  width:100%;max-width:680px;margin-inline:auto;
  padding:var(--brand-top) clamp(16px,5vw,28px) 20px;
  display:grid;justify-items:center;gap:14px;text-align:center;
}
.guest-brand{
  max-width:100%;padding:6px 14px;border-radius:100px;
  background:#e7faffeb;box-shadow:0 2px 10px #123c8326;
}
h1{margin:0;font-size:clamp(15px,2.4vw,19px);line-height:1.3;letter-spacing:.075em;color:#154965}
section{display:grid;justify-items:center;gap:14px;width:100%;min-width:0}
h2,p{margin:0}
h2{font-size:clamp(18px,4vw,23px);line-height:1.3;color:#163c66}
section>h2:not(.photo-heading),p[role=status],p[role=alert]{
  background:#eafaffed;border-radius:14px;padding:10px 14px;
}
#guestPhoto{
  display:block;max-width:100%;width:auto;height:auto;
  max-height:clamp(140px,calc(100vh - var(--photo-reserve)),820px);
  max-height:clamp(140px,calc(100dvh - var(--photo-reserve)),820px);
  object-fit:contain;outline:1px solid #f0fbffbf;
  box-shadow:0 10px 30px #0f366661;
}
[hidden]{display:none!important}
#guestDownload{
  display:flex;align-items:center;justify-content:center;width:min(100%,280px);min-height:52px;
  padding:12px 20px;border:1px solid #ffffff80;border-radius:14px;
  background:linear-gradient(110deg,#075878,#095e76);
  box-shadow:0 4px 14px #123c8345;color:#fff;text-decoration:none;
  font-weight:750;line-height:1.4;touch-action:manipulation;
}
#guestDownload:hover{background:#075f80}#guestDownload:active{background:#064f6b}
#guestDownload:focus-visible{outline:3px solid #9b429c;outline-offset:4px}
p[role=alert]{color:#8f2540;background:#fff0f1ed}
.photo-heading{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}

.qr-photo-page{background:#08090B;color-scheme:dark}
.qr-photo-page body{color:#e9ebef}
.qr-photo-page body::before{content:none}
.qr-photo-page main{max-width:960px;padding:20px 12px 16px;gap:12px}
.qr-photo-page .guest-brand{padding:0;background:none;box-shadow:none}
.qr-photo-page h1{font-size:13px;letter-spacing:.16em;color:#c8cbd2}
.qr-photo-page section{gap:12px}
.qr-photo-page h2:not(.photo-heading){background:none;color:#f1f2f5}
.qr-photo-page p[role=status],.qr-photo-page p[role=alert]{background:#191b20;color:#d7dbe3}
.qr-photo-page #guestPhoto{
  --photo-space:calc(122px + var(--safe-top) + var(--safe-bottom));
  max-height:max(140px,calc(100vh - var(--photo-space)));
  max-height:max(140px,calc(100dvh - var(--photo-space)));
  outline:1px solid #363941;box-shadow:0 6px 24px #0008;
}
.qr-photo-page #guestDownload{
  min-height:48px;padding:10px 16px;border:1px solid transparent;border-radius:10px;
  background:#eef0f4;color:#101217;box-shadow:none;
}
.qr-photo-page #guestDownload:hover{background:#fff}
.qr-photo-page #guestDownload:active{background:#dce0e7}
.qr-photo-page #guestDownload:focus-visible{outline:2px solid #aabfff;outline-offset:4px}
</style></head><body><main><header class="guest-brand"><h1>AMAZING RACE 2026</h1></header><section>'''+content+'</section></main>'
    if script:
        html+=f'<script nonce="{nonce}">{script}</script>'
    return HTMLResponse(html+'</body></html>',status_code=status,headers=headers)


@router.get('/{token}/status')
def photo_status(request:Request,token:str):
    row=request.app.state.repository.sharing.lookup(token,prepare_print=False)
    return JSONResponse({'registered':True,'fingerprint':row['sha256']},headers=PRIVATE_HEADERS)


@router.get('/{token}')
def guest(request: Request, token: str):
    service=request.app.state.repository.sharing
    try:
        row=service.lookup(token,prepare_print=False)
        service.file(row)
    except HTTPException as error:
        if error.status_code==503:
            return page('<h2>Ảnh đang được chuẩn bị</h2><p role="status">Vui lòng đợi một chút.</p>',202,
                        script='setTimeout(()=>location.reload(),5000);')
        return page('<h2>Không thể xem ảnh</h2><p role="alert">Liên kết đã hết hạn hoặc ảnh hiện không khả dụng.</p>',404)
    # token was validated as exactly 43 URL-safe characters by lookup; never
    # echo arbitrary input or embed customer-provided strings in the page.
    content=f'''<h2 class="photo-heading">Ảnh của bạn</h2><p id="loading" role="status">Đang tải ảnh…</p>
<p id="error" role="alert" hidden>Chưa thể tải ảnh. Đang thử lại…</p>
<img id="guestPhoto" alt="Ảnh của bạn" hidden>
<a id="guestDownload" href="/p/{token}/download" download hidden>Download</a>'''
    script=f'''const image=document.getElementById('guestPhoto');
image.onload=()=>{{image.hidden=false;document.getElementById('loading').hidden=true;document.getElementById('error').hidden=true;document.getElementById('guestDownload').hidden=false;}};
image.onerror=()=>{{image.hidden=true;document.getElementById('guestDownload').hidden=true;document.getElementById('loading').hidden=false;document.getElementById('loading').textContent='Ảnh đang được chuẩn bị';document.getElementById('error').hidden=false;setTimeout(()=>{{image.src='/p/{token}/image?retry='+Date.now();}},5000);}};
image.src='/p/{token}/image';'''
    return page(content,script=script)


@router.get('/{token}/image')
def view_image(request: Request, token: str, print_ready: bool=False, v: str | None=None):
    service=request.app.state.repository.sharing
    row=service.lookup(token,prepare_print=print_ready,print_version=v)
    if '_drive_bytes' in row:return Response(row['_drive_bytes'],media_type='image/png',headers=PRIVATE_HEADERS)
    return FileResponse(service.file(row),media_type='image/png',headers=PRIVATE_HEADERS)


@router.get('/{token}/download')
def download(request: Request, token: str, print_ready: bool=False, v: str | None=None):
    service=request.app.state.repository.sharing
    row=service.lookup(token,prepare_print=print_ready,print_version=v)
    filename=f"amazing-race-2026-{'print-ready' if print_ready else 'photo'}-{row['id']}.png"
    if '_drive_bytes' in row:
        return Response(row['_drive_bytes'],media_type='image/png',headers={**PRIVATE_HEADERS,'Content-Disposition':f'attachment; filename="{filename}"'})
    return FileResponse(service.file(row),media_type='image/png',filename=filename,headers=PRIVATE_HEADERS)


@router.get('/{token}/qr.png')
def qr_image(request: Request, token: str):
    service=request.app.state.repository.sharing
    row=service.lookup(token,metadata_only=True)
    try:origin=service.origin()
    except HTTPException:origin=row['public_base_url']
    return Response(service.qr_bytes(f'{origin}/p/{token}'),media_type='image/png',headers=PRIVATE_HEADERS)
