from email.message import Message
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from controller.core import Store, Engine
from controller.receiver import backfill_history, ingest
from controller.server import Controller, handler_for
from tellstick_local import Event
import test_controller


class DashboardHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'private/controller.sqlite'
        self.store = Store(self.path)
        self.store.save('devices', {'id':'one','name':'Lamp','protocol':'arctech'})
        self.store.save('devices', {'id':'two','name':'Other lamp','protocol':'arctech'})
        self.store.save('sensors', {'id':'one','name':'Room','protocol':'fineoffset','sensorId':'42','data':[]})
        self.now = int(time.time())//60*60

    def test_mixed_dashboard_order_survives_reopen_and_deleted_tiles(self):
        items = [{'kind':'sensors','id':'one'}, {'kind':'devices','id':'two'}, {'kind':'devices','id':'one'}]
        self.store.save_dashboard(items)
        reopened = Store(self.path)
        self.assertEqual(reopened.dashboard(), items)
        reopened.delete('devices','two')
        self.assertEqual(reopened.dashboard(), [items[0], items[2]])
        reopened.save_dashboard([])
        self.assertEqual(reopened.dashboard(), [])

    def test_invalid_selection_is_atomic_and_does_not_change_other_settings(self):
        original = [{'kind':'devices','id':'one'}]
        self.store.save_dashboard(original)
        self.store.set('scheduler_enabled',True)
        for value in (None, {}, original*2, [{'kind':'events','id':'one'}],
                      [{'kind':'devices','id':'missing'}], [{'kind':'devices','id':1}],
                      [{'kind':'devices','id':'one','extra':1}], [{'kind':[],'id':'one'}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.save_dashboard(value)
            self.assertEqual(self.store.dashboard(),original)
        self.assertTrue(self.store.setting('scheduler_enabled'))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM actions').fetchone()[0],0)

    def test_latest_sample_per_minute_missing_values_and_persistence(self):
        self.store.record_sensor_reading('one', self.now+1, temp=-3, humidity=40)
        self.store.record_sensor_reading('one', self.now+20, temp=-2)
        self.store.record_sensor_reading('one', self.now+61, temp=0)
        result = Store(self.path).sensor_history('one',24,now=self.now+120)
        self.assertEqual(result['points'], [
            {'time':self.now,'temp':-2,'humidity':40},
            {'time':self.now+60,'temp':0,'humidity':None}])
        self.store.delete('sensors','one')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sensor_history').fetchone()[0],0)

    def test_history_retention_and_bounded_averaging(self):
        self.store.record_sensor_reading('one', self.now-91*86400, temp=99)
        # Dense minute data over seven days must remain bounded on the API.
        with self.store.connect() as db:
            db.executemany('INSERT INTO sensor_history VALUES(?,?,?,?)',
                [('one',self.now-i*60,10 if i%2 else 20,50) for i in range(7*24*60)])
        self.store.record_sensor_reading('one', self.now, temp=20)
        result = self.store.sensor_history('one',168,now=self.now)
        self.assertLessEqual(len(result['points']),1441)
        self.assertEqual(result['interval'],420)
        self.assertEqual(result['points'],sorted(result['points'],key=lambda x:x['time']))
        self.assertTrue(all(10<=p['temp']<=20 for p in result['points']))
        self.assertTrue(any(10<p['temp']<20 for p in result['points']))
        with self.store.connect() as db:
            self.assertGreaterEqual(db.execute('SELECT MIN(recorded) FROM sensor_history').fetchone()[0],self.now-90*86400)
        for hours in (0,1,99999):
            with self.assertRaises(ValueError):self.store.sensor_history('one',hours,now=self.now)
        for temp in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):self.store.record_sensor_reading('one',self.now,temp=temp)

    def test_ingestion_backfill_only_valid_local_matching_frames(self):
        frame = test_controller.ControllerTests.frame(temp=-12.3,humidity=55)
        fields = {'protocol':'fineoffset','data':frame}
        event = Event('2026-11-19','192.168.1.193','RawData',fields)
        ingest(self.store,Engine(self.store),event,now=self.now)
        self.assertEqual(self.store.sensor_history('one',now=self.now)['points'][0]['temp'],-12.3)
        # Simulate an upgrade: history absent, old raw reception buffer retained.
        with self.store.connect() as db:
            db.execute('DELETE FROM sensor_history')
            db.execute('INSERT INTO observations(received,kind,data) VALUES(?,?,?)',
                (self.now+1,'RawData',json.dumps({'protocol':'fineoffset','data':frame^1})))
        backfill_history(self.store)
        self.assertEqual(self.store.sensor_history('one',now=self.now+60)['points'],[
            {'time':self.now,'temp':-12.3,'humidity':55}])
        backfill_history(self.store)
        self.assertEqual(len(self.store.sensor_history('one',now=self.now+60)['points']),1)

    def test_imported_latest_values_are_not_fabricated_as_history(self):
        self.store.save('sensors',{'id':'imported','data':[{'name':'temp','value':'12'}],
            'state_source':'export','lastUpdated':self.now})
        backfill_history(self.store)
        self.assertEqual(self.store.sensor_history('imported',now=self.now)['points'],[])

    def test_api_history_and_dashboard_keep_host_validation(self):
        app = Controller(self.path, provider=MagicMock())
        items = [{'kind':'sensors','id':'one'}]
        app.mutate('/api/dashboard', {'items':items})
        self.assertEqual(app.snapshot()['dashboard'],items)
        self.store.record_sensor_reading('one',self.now-60,temp=21.5)
        handler = object.__new__(handler_for(app,'127.0.0.1:8768'))
        handler.headers=Message();handler.headers['Host']='127.0.0.1:8768'
        handler.path='/api/sensors/one/history?hours=24'
        handler.send=MagicMock();handler.send_error=MagicMock()
        handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],200)
        self.assertEqual(json.loads(handler.send.call_args.args[1])['points'][0]['temp'],21.5)
        handler.path='/api/sensors/one/history?hours=no'
        handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],400)
        handler.path='/api/sensors/missing/history'
        handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],400)
        handler.send.reset_mock();handler.headers.replace_header('Host','untrusted.local')
        handler.do_GET();handler.send_error.assert_called_once_with(403);handler.send.assert_not_called()
