"""Interactive read-only Telldus configuration export. Credentials stay in memory."""
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from urllib.parse import urlencode
import json
import copy
import os
import time
import secrets
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
import requests
from oauthlib.oauth1 import Client

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT/'secrets/recovery'
ALLOWED = frozenset(('clients/list','client/info','devices/list','device/info',
    'sensors/list','sensor/info','scheduler/jobList','scheduler/jobInfo','events/list','event/info'))


def private_json(path, data):
    if path.is_symlink():
        raise ValueError('Unsafe output path')
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,indent=2,ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def entries(payload, singular, plural):
    if not isinstance(payload,dict):
        raise ValueError('Unexpected list response')
    value = payload.get(singular, payload.get(plural))
    if not isinstance(value,list):
        raise ValueError('Unrecognized collection schema')
    if any(not isinstance(item,dict) or 'id' not in item for item in value):
        raise ValueError('Collection item missing identifier')
    return value


def collect(fetch, checkpoint, previous=None):
    export = {'schema_version':1, 'created_utc':datetime.now(timezone.utc).isoformat(),
              'scope':'Account configuration and current sensor values',
              'limitations':['Historical readings/device history not requested',
                 'No guarantee of fields the API does not expose',
                 'Cloud export is separate from device flash/EEPROM backup'],
              'sections':{},'failures':[], 'complete':False}
    if previous:
        export = copy.deepcopy(previous)
        export['resumed_utc'] = datetime.now(timezone.utc).isoformat()
        export['failures'] = []
        export['complete'] = False
    specs = [('clients','clients/list','client/info','client','clients',{}),
             ('devices','devices/list','device/info','device','devices',{'supportedMethods':4095,'includeIgnored':1}),
             ('sensors','sensors/list','sensor/info','sensor','sensors',{'includeIgnored':1,'includeValues':1,'includeScale':1}),
             ('schedules','scheduler/jobList','scheduler/jobInfo','job','jobs',{}),
             ('events','events/list','event/info','event','events',{'listOnly':1})]
    for section, endpoint, detail, singular, plural, params in specs:
        old = export['sections'].get(section,{})
        cached = old.get('list_response',{})
        response = cached if cached and 'failure' not in cached else fetch(endpoint,params)
        old_details = {str(item['id']):item['response'] for item in old.get('details',[]) if 'failure' not in item['response']}
        old_sources = {str(item['id']):item.get('source_endpoint',detail) for item in old.get('details',[])}
        export['sections'][section] = {**{k:v for k,v in old.items() if k not in ('list_response','details')},'list_response':response,'details':[]}
        if 'failure' in response:
            export['failures'].append({'section':section,**response})
            checkpoint(export)
            continue
        try:
            items = entries(response,singular,plural)
        except ValueError:
            export['failures'].append({'section':section,'failure':'unrecognized_list_schema'})
            checkpoint(export)
            continue
        total = response.get('total')
        if total is not None and str(total) != str(len(items)):
            export['failures'].append({'section':section,'failure':'possible_pagination_or_count_mismatch'})
        for item in items:
            query = {'id':item['id']}
            if section == 'clients':query['extras']='coordinate,suntime,timezone,tzoffset'
            if section == 'devices':query['supportedMethods']=4095
            result = old_details.get(str(item['id']))
            if result is None:result = fetch(detail,query)
            export['sections'][section]['details'].append({'id':item['id'],'response':result,'source_endpoint':old_sources.get(str(item['id']),detail)})
            if 'failure' in result:
                export['failures'].append({'section':section,'id':item['id'],**result})
            checkpoint(export)
        checkpoint(export)
    export['complete'] = not export['failures']
    export['completed_utc'] = datetime.now(timezone.utc).isoformat()
    checkpoint(export)
    return export


class API:
    def __init__(self, keys):
        self.signer = Client(keys[0],client_secret=keys[1],resource_owner_key=keys[2],resource_owner_secret=keys[3])
        self.session = requests.Session()
        self.session.trust_env = False
        self.last_call = 0
        self.auth_failed = False
        self.rate_limited = False

    def fetch(self, endpoint, params):
        if endpoint not in ALLOWED:
            raise ValueError('Endpoint is not read-only allowlisted')
        if self.auth_failed:
            return {'failure':'authentication_or_access_denied'}
        if self.rate_limited:
            return {'failure':'rate_limit_pause','http_status':429}
        url='https://pa-api.telldus.com/json/'+endpoint
        if params:url += '?' + urlencode(params)
        for attempt in range(3):
            time.sleep(max(0,30-(time.monotonic()-self.last_call)))
            self.last_call=time.monotonic()
            uri, headers, _ = self.signer.sign(url,http_method='GET')
            try:
                with self.session.get(uri,headers=headers,timeout=30,allow_redirects=False) as response:
                    if response.status_code == 429:
                        if attempt==2:
                            self.rate_limited=True
                            return {'failure':'rate_limit_pause','http_status':429}
                        try:delay=float(response.headers.get('Retry-After','90'))
                        except ValueError:delay=90
                        if not 0<=delay<=900:delay=900
                        print('Telldus rate limit: pausing before retry.',flush=True)
                        time.sleep(max(90*(2**attempt),delay))
                        continue
                    if response.status_code in (401,403):self.auth_failed=True
                    if response.status_code != 200:
                        return {'failure':'http_error','http_status':response.status_code}
                    data=response.json()
                    if not isinstance(data,dict):return {'failure':'unexpected_json_type'}
                    if data.get('error') or data.get('status') == 'error':return {'failure':'api_error'}
                    return data
            except (requests.RequestException,ValueError):
                return {'failure':'network_or_json_error'}
        return {'failure':'rate_limit_pause','http_status':429}


def form_authorized(origin, authority, supplied, expected):
    # Browsers may serialize navigation POST Origin as null under privacy policies.
    # An independent, unpredictable form token remains mandatory in every case.
    return origin in (None, 'null', 'http://'+authority) and secrets.compare_digest(supplied,expected)


def browser_keys():
    nonce=secrets.token_urlsafe(24)
    path='/'+nonce
    page=('<!doctype html><meta charset="utf-8"><title>Private Telldus export</title>'
        '<h1>Read-only Telldus account export</h1><p>Copy these four values from the official Telldus private-token page. '
        'Leave Token and Token secret empty if unavailable: Telldus will ask you to authorize access. Do not enter your account password here. Values stay in memory.</p>'
        '<form method="post" autocomplete="off"><input type="hidden" name="csrf" value="'+nonce+'">'+''.join(
            '<p><label>'+label+' <input type="password" '+('required ' if name in ('public','private') else '')+'name="'+name+'" autocomplete="off"></label></p>'
            for name,label in zip(('public','private','token','secret'),('Public key','Private key','Token','Token secret')))
        +'<button>Start read-only export</button></form>').encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,body):
            self.send_response(code)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        def valid(self):
            return self.path==path and self.headers.get('Host')==self.server.authority
        def do_GET(self):
            self.reply(200,page) if self.valid() else self.reply(404,b'Not found')
        def do_POST(self):
            if not self.valid():
                self.reply(403,b'Request rejected');return
            try:
                length=int(self.headers.get('Content-Length','0'))
            except ValueError:
                self.reply(400,b'Invalid input');return
            if not 0<length<=16384:
                self.reply(400,b'Invalid input');return
            try:
                values=parse_qs(self.rfile.read(length).decode(),max_num_fields=8)
            except (ValueError,UnicodeError):
                self.reply(400,b'Invalid input');return
            if not form_authorized(self.headers.get('Origin'),self.server.authority,values.get('csrf',[''])[0],nonce):
                self.reply(403,b'Request rejected. Reload the current export form and retry.');return
            keys=[values.get(name,[''])[0].strip() for name in ('public','private','token','secret')]
            if not all(keys[:2]) or bool(keys[2]) != bool(keys[3]):
                self.reply(400,b'Both application keys are required. Supply both tokens or leave both empty.');return
            self.server.keys=keys
            self.reply(200,b'Export started. You can close this tab. Return to the conversation for results.')
    with HTTPServer(('127.0.0.1',0),Handler) as server:
        server.authority='127.0.0.1:'+str(server.server_port)
        server.keys=None
        url='http://'+server.authority+path
        webbrowser.open(url)
        print('Private local credential form opened in browser.',flush=True)
        while server.keys is None:server.handle_request()
        return server.keys


def authorize_keys(keys):
    """Obtain account tokens through official OAuth endpoints; never persist them."""
    if keys[2] and keys[3]:
        return keys
    callback_path='/callback/'+secrets.token_urlsafe(24)
    session=requests.Session()
    session.trust_env=False
    def exchange(signer, endpoint):
        url='https://pa-api.telldus.com/oauth/'+endpoint
        uri,headers,body=signer.sign(url,http_method='POST',body='',
            headers={'Content-Type':'application/x-www-form-urlencoded'})
        with session.post(uri,headers=headers,data=body,timeout=30,allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError('OAuth exchange failed')
            fields=parse_qs(response.text,max_num_fields=20)
            token=fields.get('oauth_token',[''])[0]
            secret=fields.get('oauth_token_secret',[''])[0]
            if not token or not secret:raise ValueError('OAuth token missing')
            return token,secret
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            parsed=urlsplit(self.path)
            if parsed.path != callback_path or self.headers.get('Host') != self.server.authority:
                self.send_error(404);return
            query=parse_qs(parsed.query,max_num_fields=20)
            token=query.get('oauth_token',[''])[0]
            verifier=query.get('oauth_verifier',[''])[0]
            if not secrets.compare_digest(token,self.server.expected_token) or not verifier:
                self.send_error(403);return
            self.server.verifier=verifier
            self.send_response(200)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers()
            self.wfile.write(b'Authorization received. Account export is starting. You may close this tab.')
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        server.authority='127.0.0.1:'+str(server.server_port)
        callback='http://'+server.authority+callback_path
        signer=Client(keys[0],client_secret=keys[1],callback_uri=callback)
        request_token,request_secret=exchange(signer,'requestToken')
        server.expected_token=request_token
        server.verifier=None
        server.timeout=1
        webbrowser.open('https://pa-api.telldus.com/oauth/authorize?'+urlencode({'oauth_token':request_token}))
        deadline=time.monotonic()+900
        while server.verifier is None and time.monotonic()<deadline:server.handle_request()
        if not server.verifier:raise ValueError('OAuth authorization timed out')
        signer=Client(keys[0],client_secret=keys[1],resource_owner_key=request_token,
            resource_owner_secret=request_secret,verifier=server.verifier)
        token,secret=exchange(signer,'accessToken')
        return [keys[0],keys[1],token,secret]


def main():
    os.umask(0o077)
    for path in (ROOT/'secrets',PRIVATE):
        if path.is_symlink():raise ValueError('Unsafe private directory')
        path.mkdir(mode=0o700,exist_ok=True)
        path.chmod(0o700)
    status_path=PRIVATE/'telldus-export-status.json'
    previous=None
    if '--resume' in __import__('sys').argv:
        candidates=sorted(PRIVATE.glob('telldus-account-*.json'))
        if candidates:
            previous=json.loads(candidates[-1].read_text())
    private_json(status_path,{'state':'waiting_for_keys'})
    print('Read-only Telldus export. Enter both application keys. Account tokens are optional.')
    print('Values will not echo and will not be saved. Press Enter after each value.')
    keys=browser_keys() if '--web' in __import__('sys').argv else [getpass(label+': ').strip() for label in ('Public key','Private key','Token','Token secret')]
    if not all(keys[:2]) or bool(keys[2]) != bool(keys[3]):
        private_json(status_path,{'state':'stopped','reason':'missing_keys'})
        return
    private_json(status_path,{'state':'authorizing'})
    keys=authorize_keys(keys)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination=PRIVATE/('telldus-account-'+stamp+'.json')
    private_json(status_path,{'state':'exporting','destination':str(destination)})
    print('Exporting configuration at no more than one request per 30 seconds. This may take several minutes.')
    api=API(keys)
    del keys
    result=collect(api.fetch,lambda data:private_json(destination,data),previous=previous)
    private_json(status_path,{'state':'finished','destination':str(destination),
        'complete_for_requested_scope':result['complete'],'failure_count':len(result['failures']),
        'counts':{name:len(section['details']) for name,section in result['sections'].items()}})
    print('Export saved to '+str(destination))
    print('All requested configuration calls succeeded.' if result['complete'] else 'Export is PARTIAL; some sections could not be retrieved.')


if __name__ == '__main__':
    try:
        main()
    except (Exception,KeyboardInterrupt):
        # Never expose a traceback containing authorization/session internals.
        if PRIVATE.exists():
            private_json(PRIVATE/'telldus-export-status.json',{'state':'stopped','reason':'authorization_or_export_interrupted'})
        print('Export stopped. No credentials or response bodies displayed.')
    if '--web' not in __import__('sys').argv:
        input('Press Enter to close this window.')
