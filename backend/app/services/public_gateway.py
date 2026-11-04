"""Bounded, read-only proof that an origin serves the isolated photo gateway."""
from concurrent.futures import ThreadPoolExecutor
import time
import httpx

DENIED = ['/', '/booth', '/admin', '/admin/assets/dashboard.js', '/api/admin/me',
          '/api/admin/login', '/api/admin/sessions', '/api/admin/print-jobs',
          '/api/admin/camera', '/api/booth/pair', '/api/sessions', '/api/print-config',
          '/event-display', '/gallery', '/runtime/photobooth.sqlite3', '/.env',
          '/docs', '/openapi.json', '/healthz', '/p/invalid', '/p/'+'x'*43]


class GatewayCheckError(RuntimeError):
    def __init__(self, route, detail, *, retryable=False):
        self.route, self.retryable = route, retryable
        super().__init__(f'Gateway verification: {route}: {detail}')


def verify_isolation(base, timeout=12):
    started=time.monotonic();deadline=started+timeout
    # Consistent with session registration: never send localhost/public probes
    # through a stale Windows/system proxy, and never accept a redirected proof.
    with httpx.Client(trust_env=False,follow_redirects=False,timeout=3,
                      limits=httpx.Limits(max_connections=8,max_keepalive_connections=8)) as client:
        def request(route,method='GET'):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise GatewayCheckError(route,'verification deadline exceeded',retryable=True)
            try:return client.request(method,base+route,timeout=min(3,remaining))
            except httpx.HTTPError as error:
                raise GatewayCheckError(route,type(error).__name__+': '+str(error)[:180]+' (direct HTTPS/DNS/connection)',retryable=True) from None
        identity=request('/p/invalid')
        if identity.status_code!=404 or b'AMAZING RACE 2026' not in identity.content:
            raise GatewayCheckError('/p/invalid',f'HTTP {identity.status_code}; branded photo gateway not identified',
                                    retryable=identity.status_code in (404,429,502,503,504))
        def check(route):
            for attempt in range(3):
                try:
                    response=request(route)
                    if route=='/gallery' and response.status_code==200 and b'data-photo-gallery' in response.content:
                        feed=request('/gallery/api/photos')
                        try:data=feed.json()
                        except (ValueError,TypeError):data={}
                        if feed.status_code==200 and data.get('page_size')==10 and isinstance(data.get('items'),list):return
                        raise GatewayCheckError('/gallery/api/photos',f'HTTP {feed.status_code}; invalid public feed')
                    if response.status_code==404:return
                    raise GatewayCheckError(route,f'HTTP {response.status_code}; expected 404',
                        retryable=response.status_code in (429,502,503,504))
                except GatewayCheckError as error:
                    if not error.retryable or attempt==2:raise
                    time.sleep(min(.2*(attempt+1),max(0,deadline-time.monotonic())))
        with ThreadPoolExecutor(max_workers=8,thread_name_prefix='gateway-proof') as pool:
            # Only failed routes retry. Do not repeat 20+ successful requests.
            list(pool.map(check,[route for route in DENIED if route!='/p/invalid']))
        mutation=request('/p/invalid','POST')
        if mutation.status_code not in (404,405):
            raise GatewayCheckError('/p/invalid [POST]',f'HTTP {mutation.status_code}; read-only gateway required')
    return {'isolation_ms':round((time.monotonic()-started)*1000,1),'routes':len(DENIED)+1}
