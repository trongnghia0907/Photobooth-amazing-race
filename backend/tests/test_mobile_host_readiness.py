"""Terminal 2 preflight, without hardware, credentials or public tunnels."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest


@pytest.fixture
def mobile(monkeypatch):
    scripts=Path(__file__).resolve().parents[2]/'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('mobile_readiness_test',scripts/'mobile_qr_demo.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_host_startup_delay_recovers_with_direct_loopback(mobile,monkeypatch):
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        if len(calls)==1:raise URLError(ConnectionRefusedError(10061,'refused'))
        return 200,b'{"status":"ok","phase":6}',{}
    monkeypatch.setattr(mobile,'get',get)
    assert mobile.attached_host_health(8000)['phase']==6
    assert len(calls)==2
    assert all(url=='http://127.0.0.1:8000/api/health' and options['local'] for url,options in calls)


def test_refusal_reports_endpoint_and_terminal_one_action(mobile,monkeypatch):
    def offline(*args,**kwargs):raise URLError(ConnectionRefusedError(10061,'refused'))
    monkeypatch.setattr(mobile,'get',offline)
    with pytest.raises(RuntimeError) as caught:mobile.attached_host_health(8123,seconds=0)
    message=str(caught.value)
    assert '127.0.0.1:8123/api/health' in message and 'Terminal 1' in message
    assert '--host-port' in message and '10061' in message


@pytest.mark.parametrize('code,body',[(200,b'{}'),(404,b'{}'),(200,b'[]'),(503,b'{"status":"ok","phase":6}')])
def test_unrelated_or_unready_http_service_is_not_accepted(mobile,monkeypatch,code,body):
    monkeypatch.setattr(mobile,'get',lambda *args,**kwargs:(code,body,{}))
    with pytest.raises(RuntimeError,match='not a ready Photobooth Host'):
        mobile.attached_host_health(8000,seconds=0)


def test_fresh_tunnel_waits_for_host_dns(mobile,monkeypatch,tmp_path):
    calls=[]
    def resolve(host, port, *, type):
        calls.append((host,port,type))
        if len(calls)==1:raise mobile.socket.gaierror(11001,'host not found')
    monkeypatch.setattr(mobile.socket,'getaddrinfo',resolve)
    monkeypatch.setattr(mobile.time,'sleep',lambda delay:None)
    mobile.wait_for_tunnel_dns('https://new-test.trycloudflare.com',SimpleNamespace(poll=lambda:None),tmp_path/'stop')
    assert calls==[('new-test.trycloudflare.com',443,mobile.socket.SOCK_STREAM)]*2


def test_dns_deadline_reports_hostname_and_resolver_error(mobile,monkeypatch,tmp_path):
    def resolve(*args,**kwargs):raise mobile.socket.gaierror(11001,'host not found')
    monkeypatch.setattr(mobile.socket,'getaddrinfo',resolve)
    with pytest.raises(RuntimeError,match=r'Host DNS could not resolve new-test\.trycloudflare\.com.*11001'):
        mobile.wait_for_tunnel_dns('https://new-test.trycloudflare.com',SimpleNamespace(poll=lambda:None),tmp_path/'stop',seconds=0)
