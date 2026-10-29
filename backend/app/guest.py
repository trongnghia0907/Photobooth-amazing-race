"""Minimal mobile guest page. No booth controls, identifiers or gallery links."""
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

router = APIRouter(prefix='/p')
PRIVATE_HEADERS = {
    'Cache-Control':'no-store', 'X-Robots-Tag':'noindex, nofollow',
    'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff',
}


def page(content, status=200, script=''):
    nonce=secrets.token_urlsafe(18)
    headers={**PRIVATE_HEADERS,'Content-Security-Policy':
        f"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Ảnh của bạn • OSA BOOTH</title><style>
*{box-sizing:border-box}body{margin:0;background:#f0f7ff;color:#0f172a;font:16px system-ui,sans-serif}
main{width:min(100%,640px);margin:0 auto;padding:24px 16px 48px;text-align:center}
section{background:white;padding:20px;border:1px solid #bae0fd;border-radius:24px}
h1{font-size:24px;color:#1e40af}p{line-height:1.6}img{width:100%;height:auto;border-radius:12px;display:block;margin:16px 0}
[hidden]{display:none!important}a{display:block;border-radius:16px;background:#2563eb;color:white;padding:16px;text-decoration:none;font-weight:700}
.error{color:#b91c1c}small{color:#64748b}</style></head><body><main><h1>OSA BOOTH</h1><section>'''+content+'</section><p><small>Ảnh sự kiện của bạn • Giữ link riêng để xem lại</small></p></main>'
    if script:
        html+=f'<script nonce="{nonce}">{script}</script>'
    return HTMLResponse(html+'</body></html>',status_code=status,headers=headers)


@router.get('/{token}')
def guest(request: Request, token: str):
    service=request.app.state.repository.sharing
    try:
        row=service.lookup(token)
        service.file(row)
    except HTTPException:
        return page('<h2>Không tìm thấy ảnh</h2><p role="alert">Link không hợp lệ, đã hết hiệu lực hoặc ảnh không còn tồn tại.</p>',404)
    # token was validated as exactly 43 URL-safe characters by lookup; never
    # echo arbitrary input or embed customer-provided strings in the page.
    content=f'''<h2>Ảnh Photobooth của bạn</h2><p id="loading" role="status">Đang tải ảnh…</p>
<p id="error" role="alert" class="error" hidden>Không tải được ảnh. Hãy kiểm tra kết nối và tải lại trang.</p>
<img id="guestPhoto" alt="Ảnh Photobooth của bạn" hidden>
<a id="guestDownload" href="/p/{token}/download" hidden>Download Image • Tải ảnh</a>'''
    script=f'''const image=document.getElementById('guestPhoto');
image.onload=()=>{{image.hidden=false;document.getElementById('loading').hidden=true;document.getElementById('guestDownload').hidden=false;}};
image.onerror=()=>{{document.getElementById('loading').hidden=true;document.getElementById('error').hidden=false;}};
image.src='/p/{token}/image';'''
    return page(content,script=script)


@router.get('/{token}/image')
def view_image(request: Request, token: str):
    service=request.app.state.repository.sharing
    row=service.lookup(token)
    return FileResponse(service.file(row),media_type='image/png',headers=PRIVATE_HEADERS)


@router.get('/{token}/download')
def download(request: Request, token: str):
    service=request.app.state.repository.sharing
    row=service.lookup(token)
    return FileResponse(service.file(row),media_type='image/png',filename=f"osa-photo-{row['id']}.png",headers=PRIVATE_HEADERS)


@router.get('/{token}/qr.png')
def qr_image(request: Request, token: str):
    service=request.app.state.repository.sharing
    row=service.lookup(token)
    return FileResponse(service.file(row,qr=True),media_type='image/png',headers=PRIVATE_HEADERS)
