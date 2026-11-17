"""Local browser UI plus persistent schedule/event worker, without cloud access."""
import argparse
from datetime import datetime,timezone
import fcntl
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json
import os
import re
from pathlib import Path
import secrets
import signal
import sqlite3
import threading
import time
from urllib.parse import urlsplit,unquote

from .core import Store,Engine,enabled,next_run,validate_event
from .receiver import receiver_loop
from .radio import RadioProvider

ROOT=Path(__file__).resolve().parents[1]
STATIC=Path(__file__).resolve().parent/'static'
DEFAULT_DB=ROOT/'secrets/controller/controller.sqlite'
EXPORT=ROOT/'secrets/recovery/telldus-account-20261117T163843Z.json'


class Controller:
    def __init__(self,path,*,provider=None):
        self.store=Store(path);self.engine=Engine(self.store,provider=provider or RadioProvider(self.store))
        self.stop=threading.Event();self.threads=[]

    def start(self,receive=True):
        # A crash after an actual future transmit must not cause blind replay.
        with self.store.connect() as db:db.execute("UPDATE actions SET status='unknown',message='Service restarted during action; not replayed' WHERE status='running'")
        def worker():
            while not self.stop.is_set():
                try:
                    self.engine.tick()
                    if time.time()-self.store.setting('last_backup',0)>86400:
                        self.store.backup()
                        self.store.set('last_backup',time.time())
                    self.store.set('scheduler_error',None)
                except Exception:
                    self.store.set('scheduler_error','A job could not be evaluated; review configuration')
                self.stop.wait(1)
        targets=[worker]
        if receive:targets.append(lambda:receiver_loop(self.store,self.engine,self.stop))
        for target in targets:
            thread=threading.Thread(target=target,daemon=True);thread.start();self.threads.append(thread)

    def snapshot(self):
        now=time.time();store=self.store
        schedules=store.list('schedules')
        for job in schedules:
            try:job['localNextRun']=next_run(job,now,self.engine.settings());job['validation_error']=None
            except Exception:job['localNextRun']=None;job['validation_error']='Invalid schedule configuration'
        events=store.list('events')
        for event in events:
            try:validate_event(event);event['validation_error']=None
            except (ValueError,TypeError,KeyError):event['validation_error']='Block-heater event needs a locally defined rule; imported configuration is retained'
        with store.connect() as db:
            actions=[dict(r) for r in db.execute('SELECT * FROM actions ORDER BY updated DESC LIMIT 150')]
            observations=[dict(r) for r in db.execute('SELECT id,received,kind,data FROM observations ORDER BY id DESC LIMIT 15')]
            for item in observations:item['data']=json.loads(item['data'])
        return {'devices':store.list('devices'),'sensors':store.list('sensors'),'schedules':schedules,'events':events,
            'actions':actions,'observations':observations,'status':{
                'hardware_mode':store.setting('hardware_mode','receive-only'),'rf_enabled':bool(store.setting('rf_authorized',False) and store.setting('rf_enabled',False)),'scheduler_enabled':store.setting('scheduler_enabled',True),
                'scheduler_heartbeat':store.setting('scheduler_heartbeat'),'scheduler_error':store.setting('scheduler_error'),
                'rule_errors':store.setting('rule_errors',[]),
                'receiver_status':store.setting('receiver_status','starting'),'receiver_last_event':store.setting('receiver_last_event'),
                'timezone':store.setting('timezone','Europe/Stockholm'),'latitude':store.setting('latitude'),
                'longitude':store.setting('longitude'),'location_name':store.setting('location_name','Home'),
                'now':now,'imported':store.setting('imported')}}

    def mutate(self,path,data):
        parts=path.strip('/').split('/')
        if parts==['api','command']:
            ids=self.engine.enqueue(str(data['deviceId']),data['method'],data.get('value',0))
            return {'queued':ids,'physical_control':bool(self.store.setting('rf_enabled',False))}
        if parts==['api','settings']:
            if set(data)-{'scheduler_enabled'}:raise ValueError('Unknown setting')
            if not isinstance(data.get('scheduler_enabled'),bool):raise ValueError('Invalid scheduler setting')
            self.store.set('scheduler_enabled',data['scheduler_enabled'])
            if not data['scheduler_enabled']:
                with self.store.connect() as db:db.execute("UPDATE actions SET status='cancelled',message='Scheduler paused' WHERE source!='manual' AND status='pending'")
            return {'ok':True}
        if len(parts)==3 and parts[:2]==['api','items']:
            return self.store.save(parts[2],data)
        if len(parts)==4 and parts[:2]==['api','delete']:
            self.store.delete(parts[2],unquote(parts[3]));return {'ok':True}
        raise ValueError('Unknown operation')


def trusted_https_origin(value):
    """An exact external HTTPS origin, never a wildcard or forwarded-header hint."""
    try:
        url=urlsplit(value)
        port=url.port
    except ValueError:
        raise ValueError('Invalid trusted HTTPS origin') from None
    if (url.scheme!='https' or not url.hostname or url.username is not None or
        url.password is not None or url.path not in ('','/') or url.query or url.fragment or
        not re.fullmatch(r'[A-Za-z0-9.-]+',url.hostname)):
        raise ValueError('Trusted origins must be exact HTTPS URLs without credentials or paths')
    host=url.hostname.lower()
    return 'https://'+host+(':'+str(port) if port and port!=443 else '')


def trusted_lan_origin(value):
    """Explicit HTTP origin for a trusted LAN proxy; never inferred from headers."""
    try:
        url=urlsplit(value)
        port=url.port
    except ValueError:
        raise ValueError('Invalid trusted LAN origin') from None
    if (url.scheme!='http' or not url.hostname or url.username is not None or
        url.password is not None or url.path not in ('','/') or url.query or url.fragment or
        not re.fullmatch(r'[A-Za-z0-9.-]+',url.hostname) or port==0):
        raise ValueError('LAN origins must be exact HTTP URLs without credentials or paths')
    return 'http://'+url.hostname.lower()+(':'+str(port) if port and port!=80 else '')


def handler_for(controller,authority,trusted_origins=(),trusted_lan_origins=()):
    csrf=secrets.token_urlsafe(32)
    origins={'http://'+authority,'http://localhost:'+authority.rsplit(':',1)[1]}
    origins.update(trusted_https_origin(value) for value in trusted_origins)
    origins.update(trusted_lan_origin(value) for value in trusted_lan_origins)
    hosts={authority.lower(),'localhost:'+authority.rsplit(':',1)[1]}
    hosts.update(urlsplit(value).netloc for value in origins)
    class Handler(BaseHTTPRequestHandler):
        server_version='TellStickLocal'
        def log_message(self,*args):pass
        def send(self,code,body,content_type='application/json; charset=utf-8'):
            self.send_response(code)
            self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers();self.wfile.write(body)
        def valid_host(self):return self.headers.get('Host','').lower() in hosts
        def do_GET(self):
            if not self.valid_host():self.send_error(403);return
            path=urlsplit(self.path).path
            if path=='/api/state':
                state=controller.snapshot();state['csrf']=csrf
                self.send(200,json.dumps(state).encode());return
            if path=='/api/health':
                self.send(200,json.dumps({'ok':True,'heartbeat':controller.store.setting('scheduler_heartbeat'),'rf_enabled':bool(controller.store.setting('rf_enabled',False))}).encode());return
            names={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in names:self.send_error(404);return
            file=STATIC/names[path]
            mime='text/html' if file.suffix=='.html' else 'text/javascript' if file.suffix=='.js' else 'text/css'
            self.send(200,file.read_bytes(),mime+'; charset=utf-8')
        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin') not in origins:
                self.send_error(403);return
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),csrf):self.send_error(403);return
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON body required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024*1024:raise ValueError('Invalid request size')
                self.connection.settimeout(10)
                data=json.loads(self.rfile.read(size))
                if not isinstance(data,dict):raise ValueError('Expected an object')
                result=controller.mutate(urlsplit(self.path).path,data)
                self.send(200,json.dumps(result).encode())
            except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as exc:
                # Only static validation messages; never include request bodies.
                message=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,json.JSONDecodeError) else 'Invalid request'
                self.send(400,json.dumps({'error':message}).encode())
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--port',type=int,default=8768)
    parser.add_argument('--import-export',type=Path)
    parser.add_argument('--no-receiver',action='store_true')
    parser.add_argument('--init-only',action='store_true')
    parser.add_argument('--trusted-origin',action='append',type=trusted_https_origin,default=[],
                        help='Exact additional HTTPS origin for a trusted reverse proxy')
    parser.add_argument('--trusted-lan-origin',action='append',type=trusted_lan_origin,default=[],
                        help='Exact additional HTTP origin for a trusted LAN proxy')
    args=parser.parse_args()
    os.umask(0o077)
    controller=Controller(args.db)
    lock=open(args.db.parent/'controller.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('A controller already uses this database')
    if args.import_export:controller.store.import_export(args.import_export)
    if not controller.store.setting('imported') and not args.init_only:raise SystemExit('Import the private account export before starting')
    if args.init_only:
        print('Controller database initialized.');return
    with ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(controller,'127.0.0.1:'+str(args.port),args.trusted_origin,args.trusted_lan_origin)) as server:
        server.daemon_threads=True
        controller.start(receive=not args.no_receiver)
        def stop(*args):
            controller.stop.set()
            threading.Thread(target=server.shutdown,daemon=True).start()
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        print('Local controller ready: http://127.0.0.1:'+str(args.port),flush=True)
        server.serve_forever(poll_interval=0.5)
        controller.stop.set()
        for thread in controller.threads:thread.join(timeout=5)


if __name__=='__main__':main()
