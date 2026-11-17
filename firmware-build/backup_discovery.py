"""User-authorized private discovery recovery record; never a full device backup."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tellstick_local.discovery import parse_response


def main():
    target = '192.168.1.193'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('192.168.1.149', 0))
        sock.settimeout(3)
        sock.sendto(b'D', (target, 30303))
        packet, peer = sock.recvfrom(65535)
    if peer != (target, 30303):
        raise ValueError('Unexpected discovery peer')
    device = parse_response(packet, target)
    private = ROOT/'secrets'
    recovery = private/'recovery'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for directory in (private, recovery):
        if directory.is_symlink():
            raise ValueError('Private directory must not be a symlink')
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
    dest = recovery/stamp
    dest.mkdir(mode=0o700)
    def write(name, data):
        fd = os.open(dest/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    write('discovery-response.bin', packet)
    write('metadata.json', json.dumps({'device_ip':device.ip, 'mac':device.mac,
        'firmware':device.firmware_version, 'captured_utc':stamp,
        'scope':'Discovery identity/secret only; not flash, bootloader, or full EEPROM',
        'secret_file':'discovery-response.bin'},indent=2).encode())
    print('Partial recovery record: ' + str(dest))
    print('Files mode 0600; directories mode 0700. No secret printed.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        print('Capture failed; no packet contents displayed.',file=sys.stderr)
        raise SystemExit(1)
