"""Authorized X-TX1 install, recovery verification and one configured RF test."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,os,socket,sys,time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from controller.core import Store
from controller.server import DEFAULT_DB
from tellstick_local import TellStickClient
from tellstick_local.transmit import RFClient
from tftp_readback import receive
from test_rx_firmware import upload
from analyse_flash import load_hex,TABLE,BOOT_END,CONFIG

TX_SHA='f9ed220b5cffca1e8ef34d8788a3e156b9b6b1f59eed17bbfcf53926deb95596'
ORIGINAL=ROOT/'secrets/recovery/rollback-20261117T180531730937Z/flash-read-1.bin'
RX_BACKUP=ROOT/'secrets/recovery/rx-test-verify-startup-20261117T183010783355Z/startup.bin'


def identity():
    for _ in range(20):
        for d in TellStickClient('192.168.1.193',bind_address='192.168.1.149',timeout=2).discover():
            if d.mac=='AC:CA:54:00:71:C2' and d.firmware_version=='X-TX1':
                return {'ip':d.ip,'mac':d.mac,'firmware':d.firmware_version}
    return None


def expected(image):
    original=ORIGINAL.read_bytes();data=bytearray(b'\xff'*len(original));data[TABLE:BOOT_END]=original[TABLE:BOOT_END]
    for address,value in load_hex(image).items():data[address]=value
    data[TABLE:TABLE+4]=data[:4];data[:4]=original[:4]
    return bytes(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('install','verify-startup','test-radio'))
    args=parser.parse_args();store=Store(DEFAULT_DB)
    if not store.setting('rf_authorized',False):raise SystemExit('User RF authorization not recorded')
    folder=Path(store.setting('tx_candidate_path',''));image=folder/'firmware.hex'
    if hashlib.sha256(image.read_bytes()).hexdigest()!=TX_SHA:raise SystemExit('Pinned TX candidate checksum mismatch')
    os.umask(0o077)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    record=ROOT/'secrets/recovery'/('tx-test-'+args.action+'-'+stamp);record.mkdir(mode=0o700)
    report={'action':args.action,'started_utc':stamp,'candidate_sha256':TX_SHA,'upload_started':False,'rf_command_sent':False}
    def save(name,data):
        fd=os.open(record/name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    def metadata():save('metadata.json',(json.dumps(report,indent=2)+'\n').encode())
    metadata()
    if args.action=='test-radio':
        if not store.setting('tx_readback_verified',False):raise SystemExit('TX flash readback must pass before physical test')
        if not identity():raise SystemExit('Expected X-TX1 device not found')
        device=store.get('devices',store.setting('rf_test_device_id'))
        method=store.setting('rf_test_method',1)
        client=RFClient();client.probe()
        report.update(device_id=device['id'],device_name=device['name'],method=method,rf_command_sent=True);metadata()
        print('Sending one configured RF action to '+device['name']+': '+('ON' if method==1 else 'OFF')+'.',flush=True)
        client.send(device,method)
        store.set('rf_test_acknowledged',True)
        report.update(result='firmware_acknowledged',physical_receiver_confirmed=False)
        print('Firmware acknowledged RF completion. Waiting for the owner to confirm the lamp changed.',flush=True)
    else:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind(('192.168.97.149',0));sock.settimeout(.25)
            print('ARMED: GET-only at recovery IP, waiting for user power-on.',flush=True)
            data,info=receive(sock,'192.168.97.60',initial_retries=900,total_timeout=240)
        report['startup_read']=info
        if data is None:
            report['result']='read_failed';metadata();raise SystemExit('No recovery read. No write/RF sent.')
        save('startup.bin',data)
        original=ORIGINAL.read_bytes()
        report['bootloader_unchanged']=data[TABLE+8:BOOT_END]==original[TABLE+8:BOOT_END]
        report['configuration_unchanged']=data[CONFIG:CONFIG+4]==original[CONFIG:CONFIG+4]
        if not report['bootloader_unchanged'] or not report['configuration_unchanged']:
            report['result']='unexpected_boot_or_config';metadata();raise SystemExit('Boot/config mismatch; no write/RF sent')
        if args.action=='install':
            if data!=RX_BACKUP.read_bytes():
                report['result']='before_flash_mismatch';metadata();raise SystemExit('Expected verified RX image did not match; no upload sent')
            report['upload_started']=True;metadata()
            print('RX readback matches. Uploading only pinned X-TX1 firmware.',flush=True)
            info,stderr=upload(image,'192.168.97.60','192.168.97.149',TX_SHA)
            report['upload']=info;save('upload-stderr.txt',stderr);metadata()
            if not info['complete']:raise SystemExit('Upload incomplete; keep power connected and use prepared stock recovery if needed')
            report['tx_identity']=identity()
            if report['tx_identity']:
                RFClient().probe();report['nontransmitting_probe']='acknowledged'
                store.set('hardware_mode','X-TX1; awaiting readback verification')
                store.set('tx_firmware_installed',True)
            report['result']='tx_discovered' if report['tx_identity'] else 'tx_discovery_missing'
        else:
            report['matches_expected_tx_flash']=data==expected(image)
            report['tx_identity']=identity()
            if report['matches_expected_tx_flash'] and report['tx_identity']:
                RFClient().probe();report['nontransmitting_probe']='acknowledged'
                store.set('tx_readback_verified',True)
                store.set('hardware_mode','X-TX1; awaiting physical control test')
                report['result']='tx_startup_verified'
            else:report['result']='verification_mismatch_or_no_application'
    metadata();print(json.dumps(report,indent=2),flush=True);print('Private record:',record,flush=True)


if __name__=='__main__':main()
