"""Register only the RX listener; save incoming packets privately, print counts."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tellstick_local.discovery import TellStickClient


def main():
    devices=TellStickClient('192.168.1.193',bind_address='192.168.1.149',timeout=2).discover()
    if not any(d.mac=='AC:CA:54:00:71:C2' and d.firmware_version=='X-RX1' for d in devices):
        raise SystemExit('Expected RX firmware not found; no listener command sent')
    os.umask(0o077)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=ROOT/'secrets/recovery'/('rx-listener-'+stamp);folder.mkdir(mode=0o700)
    count=0;total=0;started=time.monotonic()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(('192.168.1.149',0));sock.settimeout(1)
        sock.sendto(b'B:reglistener',('192.168.1.193',42314))
        print('Receive-only registration sent at assigned address. Listening for 45 seconds.',flush=True)
        while time.monotonic()-started<45 and total<100*1024*1024:
            try:packet,peer=sock.recvfrom(65535)
            except socket.timeout:continue
            if peer[0]!='192.168.1.193':continue
            count+=1;total+=len(packet)
            fd=os.open(folder/('event-'+str(count)+'.bin'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(packet)
    report={'device_ip':'192.168.1.193','firmware':'X-RX1','listener_registration_sent':True,
            'registration_acknowledged':False,'received_events':count,'received_bytes':total,
            'listen_seconds':round(time.monotonic()-started,2),'rf_transmit_command_sent':False}
    fd=os.open(folder/'metadata.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(report,indent=2),flush=True)
    print('Private listener record:',folder,flush=True)


if __name__=='__main__':main()
