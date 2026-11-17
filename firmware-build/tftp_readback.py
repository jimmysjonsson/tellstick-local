"""Authorized TFTP GET only; never implements writes or firmware upload."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import socket
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
TARGET = '192.168.1.193'
BIND = '192.168.1.149'
LIMIT = 128 * 1024
RRQ = b'\x00\x01firmware.bin\x00octet\x00'


def receive(sock, target=TARGET, *, initial_retries=7, total_timeout=35):
    """Return completed bytes and safe diagnostics; send only RRQ and ACK."""
    peer = None
    expected = 1
    data = bytearray()
    retries = 0
    request_count = 1
    outgoing = RRQ
    destination = (target, 69)
    sock.sendto(outgoing, destination)
    started = time.monotonic()
    deadline = started + total_timeout
    first_data_seconds = None
    while time.monotonic() < deadline:
        try:
            packet, sender = sock.recvfrom(2048)
        except socket.timeout:
            retries += 1
            if retries > (initial_retries if peer is None else 3):
                return None, {'result':'timeout','received_bytes':len(data),'read_requests':request_count}
            sock.sendto(outgoing, destination)
            if peer is None:request_count += 1
            continue
        if sender[0] != target or (peer is not None and sender != peer):continue
        if len(packet) < 4:continue
        opcode, block = struct.unpack('!HH',packet[:4])
        if opcode == 5:
            return None, {'result':'tftp_error','error_code':block,'received_bytes':len(data),'read_requests':request_count}
        if opcode != 3 or len(packet) > 516:continue
        if peer is None:
            if block != 1:continue
            peer = sender
            destination = peer
            first_data_seconds = round(time.monotonic() - started, 3)
        if block == expected:
            chunk = packet[4:]
            if len(data) + len(chunk) > LIMIT:
                return None, {'result':'oversized_response','received_bytes':len(data)}
            data.extend(chunk)
            outgoing = struct.pack('!HH',4,block)
            sock.sendto(outgoing, destination)
            retries = 0
            expected += 1
            if len(chunk) < 512:
                return bytes(data), {'result':'complete','received_bytes':len(data),'read_requests':request_count,
                                     'first_data_seconds':first_data_seconds}
        elif block == expected - 1:
            sock.sendto(outgoing, destination)
    return None, {'result':'deadline','received_bytes':len(data)}


def main():
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory = ROOT/'secrets/recovery'/('tftp-'+stamp)
    directory.mkdir(mode=0o700)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind((BIND,0))
        sock.settimeout(1)
        data, result = receive(sock)
    result.update(target=TARGET,request='TFTP RRQ firmware.bin octet',captured_utc=stamp,
                  scope='Internal-flash readback attempt only; excludes external EEPROM')
    if data is not None:
        fd = os.open(directory/'flash.bin',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        result['sha256'] = hashlib.sha256(data).hexdigest()
        result['expected_flash_size'] = len(data) == LIMIT
    fd = os.open(directory/'metadata.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
    print('Private record:',directory)


if __name__ == '__main__':main()
