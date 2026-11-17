"""GET-only startup test at the dedicated recovery IP; no normal-IP requests."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import socket

from tftp_readback import receive, ROOT


def main():
    os.umask(0o077)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # Fail before sending anything unless the temporary address is configured.
        sock.bind(('192.168.97.149', 0))
        sock.settimeout(0.25)
        print('ARMED: GET-only requests to recovery IP 192.168.97.60 for up to 240 seconds.', flush=True)
        data, result = receive(sock, '192.168.97.60', initial_retries=900, total_timeout=240)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT/'secrets/recovery'/('startup-tftp-'+stamp)
    folder.mkdir(mode=0o700)
    result.update(target='192.168.97.60', local_ip='192.168.97.149',
                  scope='Power-on recovery-IP GET only; external EEPROM excluded')
    if data is not None:
        reference = ROOT/'secrets/recovery/tftp-20261117T174934573218Z/flash.bin'
        result['sha256'] = hashlib.sha256(data).hexdigest()
        result['matches_existing_flash_backup'] = data == reference.read_bytes()
        fd = os.open(folder/'flash.bin', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
    fd = os.open(folder/'metadata.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2), flush=True)
    print('Private record:', folder, flush=True)


if __name__ == '__main__':
    main()
