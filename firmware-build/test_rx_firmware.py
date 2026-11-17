"""Controlled receive-only firmware test with pinned images and no RF transmit API."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from test_stock_restore import PACKAGE,FLASH_SHA,STOCK_SHA,read_flash,digest,discovery
from tftp_readback import ROOT,BIND,TARGET,receive
from verify_rollback import verify
from analyse_flash import load_hex,TABLE,BOOT_END,CONFIG
from tellstick_local.discovery import TellStickClient

RX_SHA='983d53973f77b717e18daf7b425895883b59ed015b8cbb8fe4643c9cc6ccb7a5'


def expected_rx_flash():
    original=(PACKAGE/'flash-read-1.bin').read_bytes()
    image=load_hex(PACKAGE/'rx-candidate.hex')
    expected=bytearray(b'\xff'*len(original))
    expected[TABLE:BOOT_END]=original[TABLE:BOOT_END]
    for address,value in image.items():expected[address]=value
    # Match the reset relocation established in the stock restore/readback.
    expected[TABLE:TABLE+4]=expected[:4]
    expected[:4]=original[:4]
    return bytes(expected)


def upload(path,target,bind,sha):
    if digest(path.read_bytes())!=sha:raise ValueError('Pinned image checksum mismatch')
    result=subprocess.run(['curl','--disable','--silent','--show-error','--noproxy','*',
        '--proto','=tftp','--tftp-no-options','--interface',bind,'--max-time','180',
        '--connect-timeout','10','--retry','0','--upload-file',str(path),
        '--write-out','%{size_upload}','tftp://'+target+'/firmware.hex'],
        capture_output=True,timeout=190)
    try:count=int(float(result.stdout.decode('ascii')))
    except (ValueError,UnicodeError):count=None
    return {'returncode':result.returncode,'uploaded_bytes':count,
            'expected_bytes':path.stat().st_size,
            'complete':result.returncode==0 and count==path.stat().st_size},result.stderr


def scan_rx(timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        for target in (TARGET,'255.255.255.255'):
            for device in TellStickClient(target,bind_address=BIND,timeout=1.5).discover():
                if device.firmware_version=='X-RX1' and device.mac=='AC:CA:54:00:71:C2':
                    return {'ip':device.ip,'mac':device.mac,'firmware':device.firmware_version}
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','rollback','verify-startup'))
    parser.add_argument('--listen-seconds',type=int,default=45)
    args=parser.parse_args()
    verify(PACKAGE)
    if digest((PACKAGE/'rx-candidate.hex').read_bytes())!=RX_SHA:raise SystemExit('RX checksum mismatch')
    # Require the independent recovery subnet BEFORE making any change.
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as check:check.bind(('192.168.97.149',0))
    os.umask(0o077)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=ROOT/'secrets/recovery'/('rx-test-'+args.action+'-'+stamp)
    folder.mkdir(mode=0o700)
    report={'action':args.action,'started_utc':stamp,'rf_transmit_commands_sent':False,'upload_started':False}
    def save(name,data):
        fd=os.open(folder/name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    def record():save('metadata.json',(json.dumps(report,indent=2)+'\n').encode())
    record()
    if args.action=='install':
        identity=discovery(8)
        if not identity or identity['firmware']!='4' or identity['mac']!='AC:CA:54:00:71:C2':
            raise SystemExit('Expected original stock device not found; no write sent')
        print('Reading stock flash before the pinned receive-only install.',flush=True)
        data,info=read_flash();report['before_read']=info
        if data is None or digest(data)!=FLASH_SHA:
            report['result']='prewrite_mismatch';record();raise SystemExit('Stock readback mismatch; no upload sent')
        save('before.bin',data)
        report['upload_started']=True;record()
        print('Stock matches. Uploading pinned X-RX1 receive-only HEX.',flush=True)
        info,stderr=upload(PACKAGE/'rx-candidate.hex',TARGET,BIND,RX_SHA)
        report['upload']=info;save('upload-stderr.txt',stderr);record()
        if not info['complete']:
            report['result']='upload_failed_or_incomplete';record()
            raise SystemExit('Upload incomplete. Keep power connected; recovery rollback may be needed.')
        print('Upload complete. Looking for X-RX1 discovery.',flush=True)
        identity=scan_rx();report['rx_identity']=identity;record()
        if not identity:
            report['result']='rx_discovery_missing';record()
            print('RX discovery missing. Power-on recovery investigation/rollback required. Private record:',folder,flush=True)
            raise SystemExit(1)
        print('X-RX1 discovered. Registering a receive-only listener; no RF transmit command.',flush=True)
        count=0;total=0;started=time.monotonic()
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind((BIND,0));sock.settimeout(1)
            sock.sendto(b'B:reglistener',(identity['ip'],42314))
            while time.monotonic()-started<max(0,min(args.listen_seconds,120)):
                try:packet,peer=sock.recvfrom(65535)
                except socket.timeout:continue
                if peer[0]!=identity['ip']:continue
                count+=1;total+=len(packet)
                save('event-'+str(count)+'.bin',packet)
        report.update(result='rx_discovered',received_events=count,received_event_bytes=total)
    else:
        print('ARMED: GET-only at 192.168.97.60; waiting for user power cycle.',flush=True)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind(('192.168.97.149',0));sock.settimeout(0.25)
            data,info=receive(sock,'192.168.97.60',initial_retries=900,total_timeout=240)
        report['startup_read']=info
        if data is None:
            report['result']='startup_read_failed';record();raise SystemExit('No startup read; no write sent')
        save('startup.bin',data)
        baseline=(PACKAGE/'flash-read-1.bin').read_bytes()
        report['matches_expected_rx_flash']=data==expected_rx_flash()
        report['bootloader_unchanged']=data[TABLE+8:BOOT_END]==baseline[TABLE+8:BOOT_END]
        report['configuration_unchanged']=data[CONFIG:CONFIG+4]==baseline[CONFIG:CONFIG+4]
        if args.action=='rollback':
            if not report['bootloader_unchanged'] or not report['configuration_unchanged']:
                report['result']='unexpected_boot_or_config';record();raise SystemExit('Unexpected boot/config; stopped before write')
            report['upload_started']=True;record()
            print('Recovery read complete. Restoring pinned stock firmware 4.',flush=True)
            info,stderr=upload(PACKAGE/'stock-firmware-4.hex','192.168.97.60','192.168.97.149',STOCK_SHA)
            report['upload']=info;save('upload-stderr.txt',stderr);record()
            if not info['complete']:raise SystemExit('Stock rollback upload incomplete; keep power connected')
            report['stock_identity']=discovery(30)
            if report['stock_identity']:
                restored,info=read_flash();report['restored_read']=info
                if restored is not None:save('restored.bin',restored)
                report['restored_flash_matches_original']=restored==baseline
                report['final_stock_identity']=discovery(30)
            report['result']='stock_rollback_verified' if report.get('restored_flash_matches_original') and report.get('final_stock_identity') else 'rollback_needs_verification'
        else:
            report['rx_identity_after_restart']=scan_rx()
            report['result']='rx_startup_verified' if report['matches_expected_rx_flash'] and report['rx_identity_after_restart'] else 'startup_needs_investigation'
    record()
    print(json.dumps(report,indent=2),flush=True)
    print('Private test record:',folder,flush=True)


if __name__=='__main__':main()
