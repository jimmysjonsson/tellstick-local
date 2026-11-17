"""One explicitly authorized stock firmware-4 reinstall, with before/after readback.
No custom image selection, external EEPROM write or RF command is implemented.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from tftp_readback import receive, ROOT, TARGET, BIND
from verify_rollback import verify

PACKAGE = ROOT/'secrets/recovery/rollback-20261117T180531730937Z'
STOCK_SHA = 'ba103630c1048178c59c8253a9e510ab3ac565c6ecf592b78aeb78fefacd8a90'
FLASH_SHA = 'd7fc988322cf846851b88783e1db1ae8fc23081819fd4985fa15a137c9dd3d37'
sys.path.insert(0,str(ROOT))
from tellstick_local.discovery import parse_response


def digest(data):return hashlib.sha256(data).hexdigest()


def read_flash():
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind((BIND,0));sock.settimeout(1)
        return receive(sock)


def discovery(timeout=25):
    started=time.monotonic()
    while time.monotonic()-started < timeout:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind((BIND,0));sock.settimeout(2)
            sock.sendto(b'D',(TARGET,30303))
            try:packet,peer=sock.recvfrom(65535)
            except socket.timeout:continue
        if peer != (TARGET,30303):continue
        device=parse_response(packet,TARGET)
        return {'mac':device.mac,'firmware':device.firmware_version,'ip':device.ip}
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-stock-restore',action='store_true')
    args=parser.parse_args()
    if not args.authorized_stock_restore:
        parser.error('Explicit authorization flag required for this stock-only write test')
    verify(PACKAGE)
    image=PACKAGE/'stock-firmware-4.hex'
    if digest(image.read_bytes()) != STOCK_SHA:raise SystemExit('Stock checksum mismatch; nothing sent')
    before_identity=discovery(8)
    if not before_identity or before_identity['firmware'] != '4' or before_identity['mac'].upper() != 'AC:CA:54:00:71:C2':
        raise SystemExit('Unexpected or missing device identity; no write sent')
    os.umask(0o077)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=ROOT/'secrets/recovery'/('stock-restore-test-'+stamp)
    folder.mkdir(mode=0o700)
    report={'scope':'User-authorized same-version stock firmware-4 restore test only',
            'started_utc':stamp,'target':TARGET,'stock_sha256':STOCK_SHA,
            'before_identity':before_identity,'upload_started':False}
    def save(name,data):
        fd=os.open(folder/name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    def record():save('metadata.json',(json.dumps(report,indent=2)+'\n').encode())
    record()
    print('Device identity verified. Reading current flash before the stock-only upload.',flush=True)
    data,info=read_flash();report['before_read']=info
    if data is None or digest(data) != FLASH_SHA:
        report['result']='prewrite_readback_mismatch_or_failure';record()
        raise SystemExit('Before-read did not match backups; no upload sent. Private record: '+str(folder))
    save('before.bin',data)
    # Start immediately while the GET-accessed bootloader is still active.
    report['upload_started']=True;record()
    print('Before-read matches. Uploading only the pinned stock firmware-4 HEX.',flush=True)
    command=['curl','--disable','--silent','--show-error','--noproxy','*',
             '--proto','=tftp','--tftp-no-options','--interface',BIND,
             '--max-time','180','--connect-timeout','10','--retry','0',
             '--upload-file',str(image),'--write-out','%{size_upload}',
             'tftp://'+TARGET+'/firmware.hex']
    try:
        result=subprocess.run(command,capture_output=True,timeout=190)
    except subprocess.TimeoutExpired:
        report.update(result='upload_process_timeout',upload_returncode=None);record()
        raise SystemExit('Upload timed out. Keep power connected; inspect recovery status. Private record: '+str(folder))
    save('upload-stderr.txt',result.stderr)
    report['upload_returncode']=result.returncode
    try:report['uploaded_bytes']=int(float(result.stdout.decode('ascii')))
    except (ValueError,UnicodeError):report['uploaded_bytes']=None
    report['expected_upload_bytes']=image.stat().st_size
    record()
    if result.returncode or report['uploaded_bytes'] != image.stat().st_size:
        report['result']='upload_failed_or_incomplete';record()
        raise SystemExit('Upload did not report full success. No automatic rewrite attempted. Keep power connected. Private record: '+str(folder))
    print('TFTP reports the complete stock HEX uploaded. Checking application discovery.',flush=True)
    report['after_upload_identity']=discovery(30);record()
    print('Downloading flash for byte-for-byte verification.',flush=True)
    after,info=read_flash();report['after_read']=info
    if after is not None:
        save('after.bin',after)
        report['after_sha256']=digest(after)
        report['flash_matches_before']=after==data
        report['different_bytes']=sum(a!=b for a,b in zip(after,data))+abs(len(after)-len(data))
    report['final_identity']=discovery(30)
    report['result']='verified' if (after==data and report['final_identity']==before_identity) else 'verification_incomplete_or_mismatch'
    record()
    print(json.dumps(report,indent=2),flush=True)
    print('Private test record:',folder,flush=True)
    if report['result']!='verified':raise SystemExit(1)


if __name__=='__main__':main()
