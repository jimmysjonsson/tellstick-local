"""Static RX-profile checks; these do not establish hardware/bootloader safety."""
from pathlib import Path
import re
from inspect_hex import inspect

root = Path(__file__).resolve().parents[1]
build = root/'firmware-work/build-readonly'
summary = inspect(build/'TellStickNet-Lite.hex')
if summary['upper_reserved_program_bytes']:
    raise SystemExit('Image overlaps the inferred upper bootloader reservation')
map_text = (build/'TellStickNet-Lite.map').read_text()
for name in ('rfSend', 'rfSendExtended', 'rfStartTransmit', 'rfTransmitUpdate',
             'activateTransmitter', 'sendCommand', 'sendExtendedCommand',
             'sendArctechSelflearning', 'saveEEPROM', 'clearEEPROM', 'setIp',
             'saveIp', 'RebootTask', 'handleMessage'):
    if re.search(r'(?<![A-Za-z0-9_])_' + name + r'(?![A-Za-z0-9_])', map_text):
        raise SystemExit('Forbidden symbol in RX profile: ' + name)
for name in ('registerListener', 'sendToLocalListeners', 'localAccessTask'):
    if not re.search(r'(?<![A-Za-z0-9_])_' + name + r'(?![A-Za-z0-9_])', map_text):
        raise SystemExit('Missing RX-profile entry point: ' + name)
print('RX profile checks passed: HEX valid, upper reservation empty, forbidden symbols absent.')
print('Hardware, pin behavior, and bootloader compatibility remain unverified.')
