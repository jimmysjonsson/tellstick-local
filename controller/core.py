from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, date, time as daytime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import os
import sqlite3
import time
import threading
import uuid
from zoneinfo import ZoneInfo

UTC = timezone.utc
METHODS = {1: 'On', 2: 'Off', 16: 'Dim'}
KINDS = {'devices', 'sensors', 'schedules', 'events'}


def integer(value, low, high, label):
    if isinstance(value, bool):raise ValueError('Invalid '+label)
    try:n = int(str(value))
    except (ValueError, TypeError):raise ValueError('Invalid '+label) from None
    if not low <= n <= high:raise ValueError('Invalid '+label)
    return n


def enabled(value):return value in (1, '1', True)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.path.parent.chmod(0o700)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS items(kind TEXT,id TEXT,data TEXT,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS occurrences(key TEXT PRIMARY KEY,created REAL);
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,source TEXT,device TEXT,method INTEGER,value INTEGER,
              due REAL,status TEXT,attempts INTEGER,retries INTEGER,interval INTEGER,repeats INTEGER,message TEXT,updated REAL);
            CREATE INDEX IF NOT EXISTS due_actions ON actions(status,due);
            CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,received REAL,kind TEXT,data TEXT);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def backup(self):
        directory=self.path.parent/'backups'
        directory.mkdir(mode=0o700,exist_ok=True)
        name='auto-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite'
        destination=directory/name
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        target=sqlite3.connect(destination)
        try:
            with self.connect() as source:source.backup(target)
        finally:target.close()
        for old in sorted(directory.glob('auto-*.sqlite'))[:-7]:old.unlink()
        return destination

    def get(self, kind, ident):
        with self.connect() as db:r = db.execute('SELECT data FROM items WHERE kind=? AND id=?',(kind,str(ident))).fetchone()
        if not r:raise ValueError('Record not found')
        return json.loads(r[0])

    def list(self, kind):
        with self.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT data FROM items WHERE kind=? ORDER BY id',(kind,))]

    def setting(self, key, default=None):
        with self.connect() as db:r = db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set(self, key, value):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))

    def save(self, kind, record):
        if kind not in KINDS:raise ValueError('Unknown record type')
        record = dict(record)
        ident = str(record.get('id') or 'local-'+uuid.uuid4().hex)
        record['id'] = ident
        if kind == 'devices':
            if not str(record.get('name','')).strip():raise ValueError('A device name is required')
            if record.get('protocol') == 'group':
                members = record.get('devices', '')
                if isinstance(members,list):members = ','.join(map(str,members))
                if ident in str(members).split(','):raise ValueError('Group cannot include itself')
                record['devices'] = str(members)
        elif kind == 'schedules':
            self.get('devices',record.get('deviceId',''))
            record['method'] = str(integer(record.get('method',1),1,16,'action'))
            if int(record['method']) not in METHODS:raise ValueError('Unknown action')
            record['methodValue'] = str(integer(record.get('methodValue',0),0,255,'dim level'))
            if record.get('type') not in ('time','sunrise','sunset'):raise ValueError('Unknown schedule type')
            for k,lo,hi,default in [('hour',0,23,0),('minute',0,59,0),('offset',-1440,1440,0),
                    ('randomInterval',0,1440,0),('retries',0,10,3),('retryInterval',1,1440,5),('reps',1,10,1)]:
                record[k] = integer(record.get(k,default),lo,hi,k)
            days = str(record.get('weekdays','1,2,3,4,5,6,7')).split(',')
            record['weekdays'] = ','.join(str(d) for d in sorted({integer(x,1,7,'weekday') for x in days}))
            record['active'] = int(enabled(record.get('active',0)))
        elif kind == 'events':
            record['active'] = int(enabled(record.get('active',0)))
            record['minRepeatInterval'] = integer(record.get('minRepeatInterval',30),0,86400,'repeat interval')
            for key in ('trigger','condition','action'):
                if not isinstance(record.get(key,[]),list):raise ValueError('Invalid event '+key)
            if record['active']:
                validate_event(record)
                for action in record.get('action',[]):self.get('devices',action.get('deviceId',''))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO items VALUES(?,?,?)',(kind,ident,json.dumps(record)))
            if kind in ('schedules','events'):
                # Edits cancel old queued/retry actions; history remains intact.
                db.execute("UPDATE actions SET status='cancelled',message='Automation changed' WHERE source=? AND status='pending'",(('schedule:' if kind=='schedules' else 'event:')+ident,))
        return record

    def delete(self,kind,ident):
        if kind not in KINDS:raise ValueError('Unknown record type')
        self.get(kind,ident)
        if kind=='devices':
            if any(str(s.get('deviceId'))==ident for s in self.list('schedules')):raise ValueError('Remove linked schedules first')
            for d in self.list('devices'):
                if ident in str(d.get('devices','')).split(','):raise ValueError('Remove device from groups first')
            for e in self.list('events'):
                if any(str(a.get('deviceId'))==ident for a in e.get('action',[])):raise ValueError('Remove linked event actions first')
        with self.connect() as db:
            db.execute('DELETE FROM items WHERE kind=? AND id=?',(kind,ident))
            db.execute("UPDATE actions SET status='cancelled',message='Record deleted' WHERE source=? AND status='pending'",(kind.rstrip('s')+':'+ident,))

    def import_export(self,path):
        data = json.loads(Path(path).read_text())
        if not data.get('complete'):raise ValueError('A complete export is required')
        if self.setting('imported'):return False
        sections = data['sections']
        # One transaction: interrupted imports never leave a half-imported database.
        with self.connect() as db:
            if db.execute("SELECT 1 FROM settings WHERE key='imported'").fetchone():return False
            for kind in KINDS:
                for item in sections[kind]['details']:
                    record = dict(item['response'])
                    if 'failure' in record:raise ValueError('Export contains incomplete details')
                    record['imported'] = True
                    if kind in ('devices','sensors'):record['state_source'] = 'export'
                    db.execute('INSERT INTO items VALUES(?,?,?)',(kind,str(record['id']),json.dumps(record)))
            client = sections['clients']['details'][0]['response']
            settings={'timezone':client.get('timezone','Europe/Stockholm'),'latitude':client['latitude'],
                      'longitude':client['longitude'],'location_name':client.get('name','Home'),
                      'target':'192.168.1.193','bind':'192.168.1.149','scheduler_enabled':True,
                      'imported':datetime.now(UTC).isoformat(),'hardware_mode':'receive-only'}
            ZoneInfo(settings['timezone'])
            for key,value in settings.items():db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))
        return True


def local_occurrence(day, hour, minute, tz):
    """One run on a repeated wall time (fold=0); nonexistent spring times are skipped."""
    local = datetime.combine(day,daytime(hour,minute),tzinfo=tz)
    if local.astimezone(UTC).astimezone(tz).replace(tzinfo=None)!=local.replace(tzinfo=None):return None
    return local


def schedule_time(schedule, day, settings):
    tz = ZoneInfo(settings['timezone'])
    if day.isoweekday() not in {int(x) for x in str(schedule.get('weekdays','1,2,3,4,5,6,7')).split(',')}:return None
    kind = schedule['type']
    if kind == 'time':base = local_occurrence(day,int(schedule['hour']),int(schedule['minute']),tz)
    else:
        from astral import Observer
        from astral.sun import sunrise,sunset
        try:base = {'sunrise':sunrise,'sunset':sunset}[kind](Observer(settings['latitude'],settings['longitude']),date=day,tzinfo=tz)
        except ValueError:return None  # Polar day/night: no fabricated solar event.
    if base is None:return None
    random_minutes = int(schedule.get('randomInterval',0))
    # Stable per job/day: restarts and UI refresh never move the occurrence.
    seed = hashlib.sha256((str(schedule['id'])+':'+day.isoformat()).encode()).digest()
    jitter = int.from_bytes(seed[:8],'big') % (random_minutes*60+1) if random_minutes else 0
    return base.timestamp()+int(schedule.get('offset',0))*60+jitter


def next_run(schedule, now, settings):
    if not enabled(schedule.get('active',0)):return None
    day = datetime.fromtimestamp(now,ZoneInfo(settings['timezone'])).date()
    for delta in range(-2,370):
        value = schedule_time(schedule,day+timedelta(days=delta),settings)
        if value is not None and value>now:return value
    return None


def validate_event(event):
    if not event.get('trigger') or not event.get('action'):raise ValueError('An event needs a trigger and action')
    for trigger in event['trigger']:
        kind = trigger.get('type')
        if kind not in ('time','sunrise','sunset','sensor','device'):
            raise ValueError('Imported block-heater behaviour needs a local rule before enabling')
        if kind=='time':integer(trigger.get('hour',0),0,23,'hour');integer(trigger.get('minute',0),0,59,'minute')
        if kind=='sensor':
            if trigger.get('operator','above') not in ('above','below','equals'):raise ValueError('Unknown sensor comparison')
            if not math.isfinite(float(trigger.get('value',0))):raise ValueError('Invalid sensor threshold')
    for condition in event.get('condition',[]):
        if condition.get('type') not in ('time','weekdays','sensor','device'):raise ValueError('Unsupported event condition')
    for action in event['action']:
        if action.get('type','device')!='device' or int(action.get('method',1)) not in METHODS:raise ValueError('Unsupported event action')
        integer(action.get('delay',0),0,86400,'action delay')
        integer(action.get('repeats',1),1,10,'action repeats')


class Engine:
    def __init__(self,store,provider=None):
        self.store=store
        self.provider=provider or self.blocked_provider
        self.event_lock=threading.RLock()

    @staticmethod
    def blocked_provider(device,method,value,repeats):
        return 'blocked','X-RX1 is receive-only; physical RF control is not enabled'

    def settings(self):
        return {k:self.store.setting(k,d) for k,d in [('timezone','Europe/Stockholm'),('latitude',0),('longitude',0)]}

    def members(self,ident,path=()):
        if ident in path or len(path)>20:raise ValueError('Cyclic or excessively nested group')
        device=self.store.get('devices',ident)
        if device.get('protocol')!='group':return [device]
        members=[]
        for child in str(device.get('devices','')).split(','):
            if child:members.extend(self.members(child,path+(ident,)))
        return list({str(d['id']):d for d in members}.values())

    def enqueue(self,device,method,value=0,*,source='manual',due=None,repeats=1,retries=0,interval=5,key=None):
        method=integer(method,1,16,'action');value=integer(value,0,255,'dim level')
        if method not in METHODS:raise ValueError('Unknown action')
        targets=self.members(str(device))
        for target in targets:
            if not (int(target.get('methods',19)) & method):raise ValueError('Device does not support requested action')
        due=time.time() if due is None else due
        ids=[]
        with self.store.connect() as db:
            for target in targets:
                ident=(key+':'+str(target['id'])) if key else uuid.uuid4().hex
                db.execute('INSERT OR IGNORE INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ident,source,str(target['id']),method,value,due,'pending',0,retries,interval,repeats,'Queued',time.time()))
                ids.append(ident)
        return ids

    def claim_occurrence(self,key,now):
        with self.store.connect() as db:
            return db.execute('INSERT OR IGNORE INTO occurrences VALUES(?,?)',(key,now)).rowcount==1

    def plan_schedule(self,job,day,now):
        due=schedule_time(job,day,self.settings())
        if due is None or due>now:return
        key='schedule:'+str(job['id'])+':'+day.isoformat()
        # Deterministic action IDs make restart re-planning idempotent, including
        # the case where a process died between enqueue and the occurrence marker.
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM occurrences WHERE key=?',(key,)).fetchone():return
        if now-due<=300:
            self.enqueue(job['deviceId'],job['method'],job.get('methodValue',0),source='schedule:'+str(job['id']),due=due,
                         repeats=int(job.get('reps',1)),retries=int(job.get('retries',3)),interval=int(job.get('retryInterval',5)),key=key)
        self.claim_occurrence(key,now)

    def condition(self,condition,now):
        local=datetime.fromtimestamp(now,ZoneInfo(self.settings()['timezone']))
        kind=condition['type']
        if kind=='weekdays':return local.isoweekday() in {int(x) for x in str(condition.get('weekdays','')).split(',')}
        if kind=='time':
            current=local.hour*60+local.minute
            start=int(condition.get('fromHour',0))*60+int(condition.get('fromMinute',0))
            end=int(condition.get('toHour',23))*60+int(condition.get('toMinute',59))
            return start<=current<=end if start<=end else current>=start or current<=end
        if kind=='device':
            try:return int(self.store.get('devices',condition['deviceId']).get('state',0))==int(condition.get('method',1))
            except (ValueError,KeyError):return False
        if kind=='sensor':
            try:
                sensor=self.store.get('sensors',condition['sensorId'])
                reading=next(x for x in sensor.get('data',[]) if x['name']==condition.get('field','temp'))
                if now-float(reading.get('lastUpdated',0))>900:return False
                value=float(reading['value']);threshold=float(condition['value'])
                return {'above':value>threshold,'below':value<threshold,'equals':value==threshold}[condition.get('operator','above')]
            except (ValueError,KeyError,StopIteration):return False
        return False

    def conditions(self,event,now):
        groups={}
        for c in event.get('condition',[]):groups.setdefault(str(c.get('group','default')),[]).append(c)
        return not groups or any(all(self.condition(c,now) for c in group) for group in groups.values())

    def fire_event(self,event,now,key):
        with self.event_lock:
            return self._fire_event(event,now,key)

    def _fire_event(self,event,now,key):
        if not self.store.setting('scheduler_enabled',True):return
        if not enabled(event.get('active')):return
        validate_event(event)
        if not self.conditions(event,now):return
        last=self.store.setting('event_last:'+str(event['id']),0)
        if now-last<int(event.get('minRepeatInterval',30)):return
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM occurrences WHERE key=?',(key,)).fetchone():return
        for index,action in enumerate(event['action']):
            source='event:'+str(event['id'])
            if action.get('delayPolicy')=='restart':
                with self.store.connect() as db:db.execute("UPDATE actions SET status='cancelled',message='Event delay restarted' WHERE source=? AND device=? AND status='pending'",(source,str(action['deviceId'])))
            self.enqueue(action['deviceId'],action.get('method',1),action.get('methodValue',0),source=source,
                         due=now+int(action.get('delay',0)),repeats=int(action.get('repeats',1)),key=key+':'+str(index))
        self.claim_occurrence(key,now)
        self.store.set('event_last:'+str(event['id']),now)

    def signal(self,kind,record,previous,now):
        if not self.store.setting('scheduler_enabled',True):return
        for event in self.store.list('events'):
            if not enabled(event.get('active')):continue
            for index,trigger in enumerate(event.get('trigger',[])):
                if trigger.get('type')!=kind:continue
                if kind=='sensor' and str(trigger.get('sensorId'))==str(record['id']):
                    c=dict(trigger,type='sensor')
                    if self.condition(c,now):
                        old=dict(c)
                        # Fire threshold crossings; repeated in-range samples don't flood actions.
                        field=c.get('field','temp')
                        old_reading=next((x for x in previous.get('data',[]) if x['name']==field),{})
                        old_value=old_reading.get('value') if now-float(old_reading.get('lastUpdated',0))<=900 else None
                        new_value=next((x.get('value') for x in record.get('data',[]) if x['name']==field),None)
                        threshold=float(c['value']);op=c.get('operator','above')
                        old_match=old_value is not None and {'above':float(old_value)>threshold,'below':float(old_value)<threshold,'equals':float(old_value)==threshold}[op]
                        if new_value is not None and not old_match:self.fire_event(event,now,'signal:'+event['id']+':'+str(index)+':'+str(now))
                elif kind=='device' and str(trigger.get('deviceId'))==str(record['id']) and int(trigger.get('method',1))==int(record.get('state',0)) and previous.get('state')!=record.get('state'):
                    self.fire_event(event,now,'signal:'+event['id']+':'+str(index)+':'+str(now))

    def tick(self,now=None):
        now=time.time() if now is None else now
        errors=[]
        if self.store.setting('scheduler_enabled',True):
            day=datetime.fromtimestamp(now,ZoneInfo(self.settings()['timezone'])).date()
            for job in self.store.list('schedules'):
                if not enabled(job.get('active')):continue
                try:
                    for delta in (-2,-1,0,1):self.plan_schedule(job,day+timedelta(days=delta),now)
                except (ValueError,KeyError,TypeError,OverflowError):
                    errors.append({'kind':'schedule','id':str(job['id']),'message':'Review rule or device configuration'})
            for event in self.store.list('events'):
                if not enabled(event.get('active')):continue
                try:
                    validate_event(event)
                    for index,trigger in enumerate(event.get('trigger',[])):
                        if trigger.get('type') not in ('time','sunrise','sunset'):continue
                        job=dict(trigger,id='event:'+event['id']+':'+str(index),weekdays='1,2,3,4,5,6,7')
                        for delta in (-1,0,1):
                            anchor=day+timedelta(days=delta);due=schedule_time(job,anchor,self.settings())
                            if due is not None and 0<=now-due<=300:
                                self.fire_event(event,now,'event:'+event['id']+':'+str(index)+':'+anchor.isoformat())
                except (ValueError,KeyError,TypeError,OverflowError):
                    errors.append({'kind':'event','id':str(event['id']),'message':'Review event configuration'})
        self.execute(now)
        self.store.set('rule_errors',errors)
        self.store.set('scheduler_heartbeat',now)

    def execute(self,now):
        with self.store.connect() as db:
            db.execute("UPDATE actions SET status='missed',message='Missed during outage; not replayed',updated=? WHERE status='pending' AND due<?",(now,now-300))
        for _ in range(100):
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute("SELECT * FROM actions WHERE status='pending' AND due<=? ORDER BY due LIMIT 1",(now,)).fetchone()
                if not row:return
                db.execute("UPDATE actions SET status='running',attempts=attempts+1,updated=? WHERE id=?",(now,row['id']))
            try:
                device=self.store.get('devices',row['device'])
                status,message=self.provider(device,row['method'],row['value'],row['repeats'])
            except OSError:
                status,message='offline','Device unavailable'
            except Exception:
                status,message='failed','Action failed; inspect device configuration'
            due=row['due']
            if status=='offline' and row['attempts']<row['retries']:
                status='pending';due=now+row['interval']*60
            with self.store.connect() as db:
                db.execute('UPDATE actions SET status=?,due=?,message=?,updated=? WHERE id=?',(status,due,message,now,row['id']))
            if status in ('simulated','sent'):
                previous=device.copy();device.update(state=str(row['method']),statevalue=row['value'],state_source='simulation' if status=='simulated' else 'RF command (unconfirmed)')
                self.store.save('devices',device);self.signal('device',device,previous,now)
