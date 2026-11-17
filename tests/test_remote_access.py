from email.message import Message
from io import BytesIO
import json
import unittest
from unittest.mock import MagicMock

from controller.server import handler_for,trusted_https_origin

REMOTE='https://argus.example.ts.net:8443'


class RemoteAccessTests(unittest.TestCase):
    def make_handler(self,host='argus.example.ts.net:8443',origins=(REMOTE,)):
        app=MagicMock();app.snapshot.return_value={'status':{'rf_enabled':False}}
        app.mutate.return_value={'ok':True}
        handler=object.__new__(handler_for(app,'127.0.0.1:8768',origins))
        handler.headers=Message();handler.headers['Host']=host
        handler.send=MagicMock();handler.send_error=MagicMock()
        handler.path='/api/state';handler.connection=MagicMock()
        return app,handler

    def prepare_post(self,handler,origin=REMOTE):
        handler.do_GET()
        token=json.loads(handler.send.call_args.args[1])['csrf']
        body=b'{"scheduler_enabled":true}'
        handler.path='/api/settings';handler.rfile=BytesIO(body)
        handler.headers['Origin']=origin;handler.headers['X-CSRF-Token']=token
        handler.headers['Content-Type']='application/json';handler.headers['Content-Length']=str(len(body))
        handler.send.reset_mock()

    def test_exact_remote_origin_and_csrf_accepted(self):
        app,handler=self.make_handler();self.prepare_post(handler)
        handler.do_POST()
        app.mutate.assert_called_once_with('/api/settings',{'scheduler_enabled':True})
        self.assertEqual(handler.send.call_args.args[0],200)

    def test_remote_access_rejected_without_explicit_configuration(self):
        app,handler=self.make_handler(origins=())
        handler.do_GET();handler.send_error.assert_called_once_with(403)
        app.snapshot.assert_not_called()

    def test_wrong_origin_rejected(self):
        app,handler=self.make_handler();self.prepare_post(handler,'https://attacker.example')
        handler.do_POST();handler.send_error.assert_called_once_with(403);app.mutate.assert_not_called()

    def test_missing_csrf_rejected(self):
        app,handler=self.make_handler();self.prepare_post(handler)
        del handler.headers['X-CSRF-Token']
        handler.do_POST();handler.send_error.assert_called_once_with(403);app.mutate.assert_not_called()

    def test_forwarded_header_is_not_used_as_authority(self):
        app,handler=self.make_handler(host='attacker.example')
        handler.headers['X-Forwarded-Host']='argus.example.ts.net:8443'
        handler.do_GET();handler.send_error.assert_called_once_with(403)

    def test_loopback_still_works(self):
        app,handler=self.make_handler(host='127.0.0.1:8768')
        handler.do_GET();self.assertEqual(handler.send.call_args.args[0],200)

    def test_origin_validation(self):
        self.assertEqual(trusted_https_origin('https://ARGUS.example.ts.net:8443/'),REMOTE)
        for value in ('http://argus.example.ts.net','https://*.example.ts.net','https://name:password@argus.example.ts.net',
                      'https://argus.example.ts.net/path','https://argus.example.ts.net?query=1','https://argus.example.ts.net:bad'):
            with self.subTest(value=value),self.assertRaises(ValueError):trusted_https_origin(value)
