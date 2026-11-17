import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
try:
    from scripts.export_telldus import ALLOWED, API, collect, private_json, authorize_keys, form_authorized
except ImportError:
    raise unittest.SkipTest('Optional requests/oauthlib export dependencies are unavailable')


class ExportTests(unittest.TestCase):
    def test_readonly_configuration_export(self):
        endpoints=[]
        list_keys={'clients/list':'client','devices/list':'device','sensors/list':'sensor',
                   'scheduler/jobList':'job','events/list':'event'}
        def fetch(endpoint, params):
            self.assertIn(endpoint, ALLOWED)
            endpoints.append(endpoint)
            if endpoint in list_keys:return {list_keys[endpoint]:[{'id':123}]}
            return {'id':123,'parameters':[{'name':'house','value':'SYNTHETIC'}]}
        saved=[]
        result=collect(fetch,lambda data:saved.append(json.loads(json.dumps(data))))
        self.assertTrue(result['complete'])
        self.assertEqual(len(endpoints),10)
        self.assertEqual(len(result['sections']),5)
        self.assertIn('parameters',result['sections']['devices']['details'][0]['response'])
        self.assertTrue(saved[-1]['complete'])

    def test_partial_response_is_not_success(self):
        result=collect(lambda endpoint,params:{'failure':'http_error','http_status':403},lambda data:None)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['failures']),5)

    def test_unrecognized_schema_is_not_empty_success(self):
        result=collect(lambda endpoint,params:{'unknown':[]},lambda data:None)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['failures']),5)

    def test_control_endpoint_rejected_before_network(self):
        api=API(['SYNTHETIC']*4)
        with self.assertRaises(ValueError):api.fetch('device/turnOn',{'id':1})
        with self.assertRaises(ValueError):api.fetch('scheduler/setJob',{})

    def test_private_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'export.json'
            private_json(path,{'synthetic':True})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(json.loads(path.read_text()),{'synthetic':True})
            private_json(path,{'updated':True})
            self.assertEqual(json.loads(path.read_text()),{'updated':True})


class OAuthTests(unittest.TestCase):
    def test_existing_tokens_need_no_browser(self):
        keys=['public','private','token','secret']
        with patch('scripts.export_telldus.webbrowser.open') as browser:
            self.assertEqual(authorize_keys(keys),keys)
            browser.assert_not_called()

    def test_two_keys_follow_official_oauth_flow(self):
        server=MagicMock()
        server.server_port=12345
        server.verifier=None
        def callback():server.verifier='synthetic-verifier'
        server.handle_request.side_effect=callback
        first=MagicMock(status_code=200,text='oauth_token=request&oauth_token_secret=request-secret&oauth_callback_confirmed=true')
        second=MagicMock(status_code=200,text='oauth_token=access&oauth_token_secret=access-secret')
        first.__enter__.return_value=first
        second.__enter__.return_value=second
        with patch('scripts.export_telldus.HTTPServer') as http, patch('scripts.export_telldus.requests.Session') as session, patch('scripts.export_telldus.webbrowser.open') as browser:
            http.return_value.__enter__.return_value=server
            session.return_value.post.side_effect=[first,second]
            self.assertEqual(authorize_keys(['public','private','','']),['public','private','access','access-secret'])
            self.assertEqual([call.args[0] for call in session.return_value.post.call_args_list],[
                'https://pa-api.telldus.com/oauth/requestToken','https://pa-api.telldus.com/oauth/accessToken'])
            self.assertTrue(browser.call_args.args[0].startswith('https://pa-api.telldus.com/oauth/authorize?'))


class FormSecurityTests(unittest.TestCase):
    def test_matching_token_supports_browser_privacy_origin(self):
        for origin in (None,'null','http://127.0.0.1:1234'):
            self.assertTrue(form_authorized(origin,'127.0.0.1:1234','synthetic-nonce','synthetic-nonce'))

    def test_missing_token_and_foreign_origin_rejected(self):
        self.assertFalse(form_authorized('null','127.0.0.1:1234','','synthetic-nonce'))
        self.assertFalse(form_authorized('https://example.com','127.0.0.1:1234','synthetic-nonce','synthetic-nonce'))


class ResumeAndRateTests(unittest.TestCase):
    def test_resume_reuses_successful_records(self):
        list_keys={'clients/list':'client','devices/list':'device','sensors/list':'sensor',
                   'scheduler/jobList':'job','events/list':'event'}
        def original(endpoint,params):
            if endpoint in list_keys:return {list_keys[endpoint]:[{'id':1}]}
            if endpoint=='device/info':return {'failure':'http_error','http_status':429}
            return {'id':1}
        previous=collect(original,lambda data:None)
        calls=[]
        def resume(endpoint,params):
            calls.append(endpoint)
            return {'id':1,'parameter':[]}
        result=collect(resume,lambda data:None,previous)
        self.assertTrue(result['complete'])
        self.assertEqual(calls,['device/info'])
        self.assertFalse(previous['complete'])

    def test_429_backs_off_and_retries(self):
        api=API(['SYNTHETIC']*4)
        limited=MagicMock(status_code=429,headers={'Retry-After':'0'})
        limited.__enter__.return_value=limited
        ok=MagicMock(status_code=200)
        ok.__enter__.return_value=ok
        ok.json.return_value={'client':[]}
        with patch.object(api.session,'get',side_effect=[limited,ok]) as get, patch('scripts.export_telldus.time.sleep') as sleep, patch('scripts.export_telldus.time.monotonic',return_value=1000):
            self.assertEqual(api.fetch('clients/list',{}),{'client':[]})
            self.assertEqual(get.call_count,2)
            self.assertTrue(any(call.args[0]>=90 for call in sleep.call_args_list))
