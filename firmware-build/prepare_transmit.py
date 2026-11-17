"""Make isolated X-TX1 source from the verified RX profile; never flash here."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'firmware-work/source-readonly';target=ROOT/'firmware-work/source-transmit'
for sub in ('firmware','rf','tcpip/Include','tcpip/TCPIP Stack'):
    shutil.copytree(source/sub,target/sub,dirs_exist_ok=True)
for name in ('localaccess.c','txcontrol.c','txcontrol.h'):
    shutil.copyfile(ROOT/'firmware-build/tx-profile'/name,target/'firmware'/name)
path=target/'firmware/common.h';path.write_text(path.read_text().replace('"X-RX1"','"X-TX1"'))
print('Prepared isolated X-TX1 source: bounded binary TX, no EEPROM writes, no remote reboot/config handlers.')
