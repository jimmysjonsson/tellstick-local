"""Local sensor ingestion; Fine Offset layout follows Telldus's own decoder."""
import json
import time
from tellstick_local import TellStickListener


def fineoffset(value):
    if not isinstance(value,int) or not 0<=value<1<<40:return None
    data=value.to_bytes(5,'big')
    crc=0
    for byte in data[:4]:
        crc^=byte
        for _ in range(8):crc=((crc<<1)^0x31)&255 if crc&128 else (crc<<1)&255
    if crc!=data[4]:return None
    humidity=data[3]
    if humidity>100 and humidity!=255:return None
    raw=(value>>16)&0xFFF
    result={'protocol':'fineoffset','sensorId':str((value>>28)&255),
            'temp':round((-1 if raw&0x800 else 1)*(raw&0x7FF)/10,1)}
    if humidity!=255:result['humidity']=humidity
    return result


def ingest(store,engine,event,now=None):
    now=time.time() if now is None else now
    fields=event.fields
    # Retain decoded raw frames for unrecognized sensors/protocols, with a bounded
    # recent-observation table; do not invent values for unsupported encodings.
    with store.connect() as db:
        db.execute('INSERT INTO observations(received,kind,data) VALUES(?,?,?)',(now,event.kind,json.dumps(fields)))
        db.execute('DELETE FROM observations WHERE id NOT IN (SELECT id FROM observations ORDER BY id DESC LIMIT 1000)')
    store.set('receiver_last_event',now)
    decoded=fineoffset(fields.get('data')) if fields.get('protocol')=='fineoffset' else None
    if not decoded:return
    matches=[s for s in store.list('sensors') if s.get('protocol')=='fineoffset' and str(s.get('sensorId'))==decoded['sensorId']]
    for sensor in matches:
        previous=json.loads(json.dumps(sensor))
        readings={r['name']:r for r in sensor.get('data',[])}
        for name in ('temp','humidity'):
            if name in decoded:
                readings[name]=dict(readings.get(name,{}),name=name,value=str(decoded[name]),lastUpdated=int(now),scale='0')
        sensor.update(data=list(readings.values()),lastUpdated=int(now),state_source='local RF')
        store.save('sensors',sensor)
        store.record_sensor_reading(sensor['id'],now,decoded.get('temp'),decoded.get('humidity'))
        engine.signal('sensor',sensor,previous,now)


def backfill_history(store):
    """Recover only actual local readings in the bounded pre-history RF buffer."""
    if store.setting('sensor_history_backfilled'):return
    sensors=store.list('sensors')
    with store.connect() as db:
        frames=db.execute('SELECT received,data FROM observations ORDER BY received').fetchall()
    cutoff=time.time()-90*86400
    for frame in frames:
        if frame['received']<cutoff:continue
        fields=json.loads(frame['data'])
        decoded=fineoffset(fields.get('data')) if fields.get('protocol')=='fineoffset' else None
        if not decoded:continue
        for sensor in sensors:
            if sensor.get('protocol')=='fineoffset' and str(sensor.get('sensorId'))==decoded['sensorId']:
                store.record_sensor_reading(sensor['id'],frame['received'],decoded.get('temp'),decoded.get('humidity'))
    store.set('sensor_history_backfilled',True)


def receiver_loop(store,engine,stop):
    while not stop.is_set():
        try:
            with TellStickListener(store.setting('target','192.168.1.193'),bind_address=store.setting('bind','192.168.1.149'),timeout=2) as listener:
                store.set('receiver_status','listening')
                while not stop.is_set():
                    for event in listener.events(duration=2):ingest(store,engine,event)
        except (OSError,ValueError,RuntimeError):
            store.set('receiver_status','unavailable; retrying')
            stop.wait(10)
    store.set('receiver_status','stopped')
