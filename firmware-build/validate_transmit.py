"""Offline X-TX1 layout/source/link review, not a physical receiver test."""
from pathlib import Path
import hashlib,json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from inspect_hex import inspect
from analyse_flash import load_hex

ROOT=Path(__file__).resolve().parents[1]
image=ROOT/'firmware-work/build-transmit/TellStickNet-Lite.hex'
summary=inspect(image)
if summary['upper_reserved_program_bytes']:raise SystemExit('Candidate overlaps protected upper reservation')
memory=load_hex(image)
stock=(ROOT/'secrets/recovery/rollback-20261117T180531730937Z/flash-read-1.bin').read_bytes()
if not all(memory.get(a)==stock[a] for a in range(0x1fff8,0x1fffc)):raise SystemExit('Configuration differs from verified hardware')
linkmap=(image.parent/'TellStickNet-Lite.map').read_text()
for name in ('saveEEPROM','clearEEPROM','setIp','saveIp','RebootTask','handleMessage','rfSend','rfSendExtended','rfTransmitUpdate'):
 if re.search(r'(?<![A-Za-z0-9_])_'+name+r'(?![A-Za-z0-9_])',linkmap):raise SystemExit('Unexpected legacy function: '+name)
for name in ('txControl','transmitFrame','EERandomRead1','registerListener','localAccessTask'):
 if not re.search(r'(?<![A-Za-z0-9_])_'+name+r'(?![A-Za-z0-9_])',linkmap):raise SystemExit('Required function missing: '+name)
for name in ('EEByteWrite1','EEPageWrite1'):
 if re.search(r'(?<![A-Za-z0-9_])_'+name+r'(?![A-Za-z0-9_])',linkmap):raise SystemExit('Persistent write linked')
report={'firmware':'X-TX1','sha256':summary['sha256'],'bootloader_reservation_empty':True,
 'configuration_matches_original':True,'eeprom_write_functions_absent':True,
 'legacy_command_dispatch_absent':True,'transmit_api':'TX1 bounded binary pulse request + TA1 acknowledgment',
 'max_pulses':160,'pulse_units_us':10,'max_duration_units':600,'max_total_units':12000,
 'max_frames':100,'source_ip_allowlist':'192.168.1.149','deduplication_cache':16,
 'readback_verified':False,'physical_receiver_verified':False,
 'protocol_reference_commit':'2598bbed16ffd701f2a07c99582f057a3decbaf3'}
print(json.dumps(report,indent=2))
