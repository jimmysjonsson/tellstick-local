import json
from pathlib import Path
import tempfile
import unittest
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo

from controller.core import Store,Engine,local_occurrence,schedule_time,next_run
from controller.receiver import fineoffset,ingest
from controller.server import Controller
from tellstick_local import Event


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'private/controller.sqlite')
        for key,value in {'timezone':'Europe/Stockholm','latitude':59.33,'longitude':18.06}.items():self.store.set(key,value)
        self.store.save('devices',{'id':'lamp','name':'Test lamp','protocol':'arctech','methods':'19'})
        self.engine=Engine(self.store)
        self.job={'id':'job','deviceId':'lamp','method':'1','methodValue':'0','type':'time','hour':12,'minute':0,
            'offset':0,'randomInterval':0,'weekdays':'1,2,3,4,5,6,7','retries':3,'retryInterval':5,'reps':1,'active':1}
        self.now=datetime(2026,11,17,12,0,tzinfo=ZoneInfo('Europe/Stockholm')).timestamp()

    def actions(self):
        with self.store.connect() as db:return [dict(row) for row in db.execute('SELECT * FROM actions ORDER BY id')]

    def test_dst_gap_skipped_and_fold_runs_once(self):
        tz=ZoneInfo('Europe/Stockholm')
        self.assertIsNone(local_occurrence(date(2026,3,29),2,30,tz))
        occurrence=local_occurrence(date(2026,10,25),2,30,tz)
        self.assertEqual(occurrence.fold,0)
        self.assertEqual(occurrence.utcoffset().total_seconds(),7200)

    def test_random_delay_stable_and_positive(self):
        job=dict(self.job,randomInterval=10)
        t1=schedule_time(job,date(2026,11,17),self.engine.settings())
        self.assertEqual(t1,schedule_time(job,date(2026,11,17),self.engine.settings()))
        self.assertGreaterEqual(t1,self.now);self.assertLessEqual(t1,self.now+600)

    def test_sunrise_offset_and_weekdays(self):
        job=dict(self.job,type='sunrise',offset=-20)
        a=schedule_time(job,date(2026,11,17),self.engine.settings())
        b=schedule_time(dict(job,offset=0),date(2026,11,17),self.engine.settings())
        self.assertEqual(b-a,1200)
        self.assertIsNone(schedule_time(dict(job,weekdays='7'),date(2026,11,17),self.engine.settings()))

    def test_restart_idempotence(self):
        self.store.save('schedules',self.job)
        self.engine.tick(self.now+2)
        Engine(self.store).tick(self.now+3)
        self.assertEqual(len(self.actions()),1)
        self.assertEqual(self.actions()[0]['status'],'blocked')
        self.assertEqual(self.actions()[0]['attempts'],1)

    def test_crash_after_enqueue_before_marker(self):
        key='schedule:job:2026-11-17'
        self.engine.enqueue('lamp',1,source='schedule:job',due=self.now,key=key)
        self.store.save('schedules',self.job)
        self.engine.tick(self.now+2)
        self.assertEqual(len(self.actions()),1)

    def test_missed_jobs_not_replayed_after_long_outage(self):
        self.store.save('schedules',self.job)
        self.engine.tick(self.now+3600)
        self.assertEqual(self.actions(),[])

    def test_retry_interval_is_minutes(self):
        engine=Engine(self.store,lambda *args:('offline','Offline'))
        engine.enqueue('lamp',1,due=self.now,retries=1,interval=5)
        engine.tick(self.now)
        self.assertEqual(self.actions()[0]['due'],self.now+300)
        self.assertEqual(self.actions()[0]['status'],'pending')
        engine.tick(self.now+299);self.assertEqual(self.actions()[0]['attempts'],1)
        engine.tick(self.now+300);self.assertEqual(self.actions()[0]['attempts'],2)
        self.assertEqual(self.actions()[0]['status'],'offline')

    def test_group_dedup_and_cycle_detection(self):
        self.store.save('devices',{'id':'g','name':'Group','protocol':'group','devices':'lamp,lamp'})
        self.assertEqual(len(self.engine.enqueue('g',1)),1)
        self.store.save('devices',{'id':'a','name':'A','protocol':'group','devices':'b'})
        self.store.save('devices',{'id':'b','name':'B','protocol':'group','devices':'a'})
        with self.assertRaises(ValueError):self.engine.enqueue('a',1)
        self.assertEqual(len(self.actions()),1)

    def test_blocked_command_does_not_claim_physical_state(self):
        self.engine.enqueue('lamp',1,due=self.now)
        self.engine.execute(self.now)
        self.assertEqual(self.actions()[0]['status'],'blocked')
        self.assertNotIn('state',self.store.get('devices','lamp'))

    def test_event_delay_conditions_and_dedup(self):
        event={'id':'evt','active':1,'minRepeatInterval':30,'trigger':[{'type':'time','hour':12,'minute':0}],
          'condition':[{'type':'time','fromHour':11,'fromMinute':0,'toHour':13,'toMinute':0}],
          'action':[{'deviceId':'lamp','method':1,'delay':60,'repeats':1}]}
        self.store.save('events',event)
        self.engine.tick(self.now);self.engine.tick(self.now+1)
        self.assertEqual(len(self.actions()),1);self.assertEqual(self.actions()[0]['status'],'pending')
        self.engine.tick(self.now+60);self.assertEqual(self.actions()[0]['status'],'blocked')

    def test_unsupported_blockheater_cannot_be_enabled(self):
        event={'id':'evt','active':0,'trigger':[{'type':'blockheater'}],'action':[{'deviceId':'lamp','method':1}]}
        self.store.save('events',event)
        with self.assertRaises(ValueError):self.store.save('events',dict(event,active=1))

    def test_pause_cancels_pending_schedule_actions(self):
        app=Controller(self.store.path)
        self.engine.enqueue('lamp',1,due=self.now+3600,source='schedule:job')
        app.mutate('/api/settings',{'scheduler_enabled':False})
        self.assertEqual(self.actions()[0]['status'],'cancelled')

    def test_restart_running_action_is_not_replayed(self):
        app=Controller(self.store.path)
        self.engine.enqueue('lamp',1,due=self.now)
        with self.store.connect() as db:db.execute("UPDATE actions SET status='running'")
        app.start(receive=False);app.stop.set()
        for thread in app.threads:thread.join(3)
        self.assertEqual(self.actions()[0]['status'],'unknown')

    @staticmethod
    def frame(sensor=42,temp=-12.3,humidity=55):
        raw=int(round(abs(temp)*10)) | (0x800 if temp<0 else 0)
        value=(sensor<<28)|(raw<<16)|(humidity<<8)
        crc=0
        for b in value.to_bytes(5,'big')[:4]:
            crc^=b
            for _ in range(8):crc=((crc<<1)^0x31)&255 if crc&128 else (crc<<1)&255
        return value|crc

    def test_fineoffset_crc_and_negative_temperature(self):
        value=self.frame()
        self.assertEqual(fineoffset(value),{'protocol':'fineoffset','sensorId':'42','temp':-12.3,'humidity':55})
        self.assertIsNone(fineoffset(value^1))
        self.assertIsNone(fineoffset(self.frame(humidity=101)))

    def test_sensor_updates_only_matching_device(self):
        self.store.save('sensors',{'id':'s','protocol':'fineoffset','sensorId':'42','data':[]})
        event=Event('2026-11-17','192.168.1.193','RawData',{'protocol':'fineoffset','data':self.frame()})
        ingest(self.store,self.engine,event,now=self.now)
        sensor=self.store.get('sensors','s')
        self.assertEqual(sensor['state_source'],'local RF')
        self.assertEqual(sensor['data'][0]['name'],'temp')
        self.assertEqual(sensor['lastUpdated'],int(self.now))

    def test_import_is_atomic_idempotent_and_private(self):
        sections={k:{'details':[]} for k in ('clients','devices','sensors','schedules','events')}
        sections['clients']['details']=[{'response':{'timezone':'Europe/Stockholm','latitude':59,'longitude':18}}]
        path=Path(self.temp.name)/'export.json';path.write_text(json.dumps({'complete':True,'sections':sections}))
        self.assertTrue(self.store.import_export(path));self.assertFalse(self.store.import_export(path))
        self.assertEqual(self.store.path.stat().st_mode&0o777,0o600)
        bad=Store(Path(self.temp.name)/'bad/db')
        sections['events']['details']=[{'response':{'failure':'synthetic'}}]
        path.write_text(json.dumps({'complete':True,'sections':sections}))
        with self.assertRaises(ValueError):bad.import_export(path)
        self.assertIsNone(bad.setting('imported'))

    def test_schedule_save_rejects_invalid_days(self):
        with self.assertRaises(ValueError):self.store.save('schedules',dict(self.job,weekdays='0'))
        with self.assertRaises(ValueError):self.store.save('schedules',dict(self.job,method=3))

    def test_pending_actions_expire_after_long_outage(self):
        self.engine.enqueue('lamp',1,due=self.now-301)
        self.engine.execute(self.now)
        self.assertEqual(self.actions()[0]['status'],'missed')
        self.assertEqual(self.actions()[0]['attempts'],0)

    def test_paused_sensor_events_do_not_run(self):
        self.store.set('scheduler_enabled',False)
        self.store.save('sensors',{'id':'s','protocol':'fineoffset','sensorId':'42','data':[]})
        self.store.save('events',{'id':'evt','active':1,'trigger':[{'type':'sensor','sensorId':'s','field':'temp','operator':'below','value':0}],
            'action':[{'deviceId':'lamp','method':1}]})
        event=Event('2026-11-17','192.168.1.193','RawData',{'protocol':'fineoffset','data':self.frame()})
        ingest(self.store,self.engine,event,now=self.now)
        self.assertEqual(self.actions(),[])

    def test_sensor_threshold_crossing_not_repeated(self):
        self.store.save('sensors',{'id':'s','protocol':'fineoffset','sensorId':'42','data':[]})
        self.store.save('events',{'id':'evt','active':1,'minRepeatInterval':0,
          'trigger':[{'type':'sensor','sensorId':'s','field':'temp','operator':'below','value':0}],
          'action':[{'deviceId':'lamp','method':1}]})
        event=Event('2026-11-17','192.168.1.193','RawData',{'protocol':'fineoffset','data':self.frame()})
        ingest(self.store,self.engine,event,now=self.now)
        ingest(self.store,self.engine,event,now=self.now+1)
        self.assertEqual(len(self.actions()),1)

    def test_online_backup_contains_consistent_records(self):
        backup=self.store.backup()
        restored=Store(backup)
        self.assertEqual(restored.get('devices','lamp')['name'],'Test lamp')
        self.assertEqual(backup.stat().st_mode&0o777,0o600)

    def test_one_invalid_job_does_not_stop_other_jobs(self):
        self.store.save('schedules',self.job)
        self.store.save('schedules',dict(self.job,id='broken'))
        # Simulate a missing target in old imported data without permitting that
        # inconsistency through the normal user-facing save validation.
        broken=dict(self.job,id='broken',deviceId='missing')
        with self.store.connect() as db:db.execute("UPDATE items SET data=? WHERE kind='schedules' AND id='broken'",(json.dumps(broken),))
        self.engine.tick(self.now+1)
        self.assertEqual(len(self.actions()),1)
        self.assertEqual(self.actions()[0]['status'],'blocked')
        self.assertEqual(len(self.store.setting('rule_errors')),1)
        self.assertEqual(self.store.setting('scheduler_heartbeat'),self.now+1)
