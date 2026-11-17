"""Create a private, offline-verified rollback package; never contacts hardware."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'firmware-build'
RECOVERY=ROOT/'secrets/recovery'


def main():
    os.umask(0o077)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=RECOVERY/('rollback-'+stamp)
    folder.mkdir(mode=0o700)
    sources={
        'stock-firmware-4.hex':ROOT/'firmware-work/recovery-reference/tellstick_net_fw4.hex',
        'flash-read-1.bin':RECOVERY/'tftp-20261117T174934573218Z/flash.bin',
        'flash-read-2.bin':RECOVERY/'tftp-20261117T174949379573Z/flash.bin',
        'flash-power-on.bin':RECOVERY/'startup-tftp-20261117T180118524897Z/flash.bin',
        'power-on-metadata.json':RECOVERY/'startup-tftp-20261117T180118524897Z/metadata.json',
        'rx-candidate.hex':ROOT/'firmware-work/build-readonly/TellStickNet-Lite.hex',
        'rx-candidate.map':ROOT/'firmware-work/build-readonly/TellStickNet-Lite.map',
        'rx-link.log':ROOT/'firmware-work/build-readonly/link.log',
        'candidate-review.txt':TOOLS/'rollback_candidate_review.txt',
        **{name:TOOLS/name for name in ('analyse_flash.py','inspect_hex.py','verify_rollback.py',
                                       'prepare_readonly.py','build_lite.py','tftp_readback.py','startup_readback.py')},
    }
    for name,source in sources.items():
        shutil.copyfile(source,folder/name)
        (folder/name).chmod(0o600)
    source_root=ROOT/'firmware-work/source-readonly'
    hashes={str(path.relative_to(source_root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source_root.rglob('*')) if path.is_file() and path.suffix in ('.c','.h')}
    (folder/'candidate-source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    (folder/'README.txt').write_text('''TellStick Net rollback preparation — NOT FLASH AUTHORIZATION

This package is private and contains complete device flash readbacks.
Do not commit it or post it publicly. Keep the directory and files protected.

Verify offline, from this directory:
    python3.12 verify_rollback.py
This uses only Python's standard library and does not contact the TellStick.

stock-firmware-4.hex is the archived vendor application, checksum-validated and
compared exactly with this unit's application after reset-vector normalization.
It excludes the observed bootloader/jump-table reservation. Preserve its original
Intel HEX format; do not replace it with a raw full-flash BIN upload.

flash-read-1.bin, flash-read-2.bin and flash-power-on.bin are three matching
131072-byte internal-flash backups. These include the bootloader, reset patch and
configuration bytes. They are not TFTP application-upload files. They do not
include the separate 128-byte external EEPROM.

rx-candidate.hex is an experimental receive-only build, not stock firmware.
Its static validation passes, but it has not run on the physical TellStick.
Its remote reboot service is deliberately disabled. Recovery therefore relies
on power-on bootloader entry rather than a TFTP-induced application reboot.
Source hashes record the local source snapshot; compiler and dependency trees
remain in firmware-work, outside this package. Do not rebuild from this copy of
build_lite.py: that driver uses the project tree, not this package directory.

RECOVERY PLAN FOR A FUTURE, SEPARATELY AUTHORIZED WRITE TEST:
1. Verify this package offline first. Keep Argus's normal network configuration.
2. If absent, add temporary 192.168.97.149/24 to enp3s0 using administrator access:
       sudo ip addr add 192.168.97.149/24 dev enp3s0
3. Leave Ethernet connected. Power off the TellStick, arm the project's GET-only
   startup_readback.py, and reconnect USB power. Confirm readback at 192.168.97.60.
   The packaged startup script is a snapshot, not a portable runner: it refers
   to original project paths. Use firmware-build/startup_readback.py in the project.
4. STOP before any upload. No executable PUT/erase/upload command is provided.
   Future upload must use the stock application HEX and only follow explicit
   approval of the exact command and remaining risks. Do not upload full-flash BIN
   or write the bootloader/configuration to bypass protection.
5. After any separately authorized restore, repeat GET-only readback and compare
   against all three full backups. Confirm normal discovery at the actual DHCP
   address and firmware 4; then check account connectivity with the owner.
6. When recovery-subnet access is no longer needed, remove only the temporary IP:
       sudo ip addr del 192.168.97.149/24 dev enp3s0

Proven: startup recovery GET at 192.168.97.60, three matching flash reads, installed
application identity and reserved-region/configuration compatibility of candidate.
Unproven: actual restore writes, interrupted-write behavior, hardware/RF pin behavior
of candidate, and EEPROM recovery. Network settings are replaceable per owner.
No promise of 100% recovery and no permission to flash follows from this package.
''')
    files={path.name:hashlib.sha256(path.read_bytes()).hexdigest()
           for path in sorted(folder.iterdir()) if path.is_file()}
    manifest={'created_utc':stamp,'scope':'Offline rollback preparation; no flashing authorized',
              'files':files,'source_paths':{name:str(path.relative_to(ROOT)) for name,path in sources.items()}}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (folder/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n'
        for path in sorted(folder.iterdir()) if path.is_file() and path.name!='SHA256SUMS'))
    for path in folder.iterdir():path.chmod(0o600)
    subprocess.run([sys.executable,str(folder/'verify_rollback.py')],check=True)
    print('Prepared private package:',folder)


if __name__=='__main__':main()
