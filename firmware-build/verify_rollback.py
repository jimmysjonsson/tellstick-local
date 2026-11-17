"""Verify a prepared TellStick package offline; contains no network or write API."""
import hashlib
import json
from pathlib import Path
import re
import sys

from analyse_flash import analyse, load_hex, TABLE, BOOT_END, SIZE


def verify(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        if Path(name).name != name:
            raise ValueError('Invalid package filename')
        path = folder/name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing or invalid package file: '+name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Checksum mismatch: '+name)
    report = analyse(folder/'flash-read-1.bin', folder/'flash-read-2.bin',
                     folder/'stock-firmware-4.hex', folder/'rx-candidate.hex')
    if (folder/'flash-power-on.bin').read_bytes() != (folder/'flash-read-1.bin').read_bytes():
        raise ValueError('Startup recovery read does not match')
    if report['normalized_full_flash_mismatches'] != 0:
        raise ValueError('Stock application differs from backed-up application')
    if not report['configuration_matches_archive'] or not report['jump_table_matches_original_reset']:
        raise ValueError('Unexpected original configuration/vector layout')
    if report['installed_reset_goto'] != '0x1dc00' or report['jump_table_second_goto'] != '0x4':
        raise ValueError('Unexpected bootloader entry/jump table')
    stock = load_hex(folder/'stock-firmware-4.hex')
    if any(TABLE <= address < BOOT_END for address in stock):
        raise ValueError('Stock application HEX contains bootloader/jump-table bytes')
    proposed = report['candidate']
    if (proposed['overlap_jump_table_or_bootloader'] or proposed['overlap_conservative_reservation']
            or not proposed['configuration_matches_readback'] or not proposed['reset_is_goto']):
        raise ValueError('Candidate layout/configuration check failed')
    linkmap = (folder/'rx-candidate.map').read_text()
    forbidden = ('rfSend','rfSendExtended','rfStartTransmit','rfTransmitUpdate',
                 'activateTransmitter','sendCommand','sendExtendedCommand',
                 'sendArctechSelflearning','saveEEPROM','clearEEPROM','setIp',
                 'saveIp','RebootTask','handleMessage','EEByteWrite','EEPageWrite')
    for name in forbidden:
        if re.search(r'(?<![A-Za-z0-9_])_'+name+r'(?![A-Za-z0-9_])', linkmap):
            raise ValueError('Unexpected linked function: '+name)
    for name in ('registerListener','sendToLocalListeners','localAccessTask','EERandomRead1'):
        if not re.search(r'(?<![A-Za-z0-9_])_'+name+r'(?![A-Za-z0-9_])',linkmap):
            raise ValueError('Expected function missing: '+name)
    return report


if __name__ == '__main__':
    try:
        verify(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit('FAILED: '+str(exc))
    print('PASS: package checksums, three matching flash reads, exact stock application, bootloader exclusion, candidate configuration and linked-function checks.')
    print('Offline validation only. Restore writes and RF electrical behavior remain untested. No flash operation is authorized.')
