from pathlib import Path
from datetime import datetime,timezone
import json,os,shutil,subprocess,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
os.umask(0o077)
result=subprocess.run([sys.executable,str(ROOT/'firmware-build/validate_transmit.py')],check=True,capture_output=True,text=True)
report=json.loads(result.stdout)
folder=ROOT/'secrets/recovery'/('tx-candidate-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
folder.mkdir(mode=0o700)
for source,name in [(ROOT/'firmware-work/build-transmit/TellStickNet-Lite.hex','firmware.hex'),
                    (ROOT/'firmware-work/build-transmit/TellStickNet-Lite.map','firmware.map'),
                    (ROOT/'firmware-work/build-transmit/link.log','link.log')]:
 shutil.copyfile(source,folder/name);(folder/name).chmod(0o600)
for name in ('txcontrol.c','localaccess.c','txcontrol.h'):
 shutil.copyfile(ROOT/'firmware-build/tx-profile'/name,folder/name);(folder/name).chmod(0o600)
(folder/'validation.json').write_text(json.dumps(report,indent=2)+'\n');(folder/'validation.json').chmod(0o600)
(folder/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(folder.iterdir()) if p.is_file()))
(folder/'SHA256SUMS').chmod(0o600)
sys.path.insert(0,str(ROOT))
from controller.core import Store
from controller.server import DEFAULT_DB
Store(DEFAULT_DB).set('tx_candidate_path',str(folder))
print('Pinned private transmit candidate:',folder)
print('Firmware SHA-256:',report['sha256'])
