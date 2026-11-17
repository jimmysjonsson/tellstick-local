"""Validate a build artifact's Intel HEX records without contacting hardware."""
from pathlib import Path
import hashlib
import json
import sys


def inspect(path):
    raw = Path(path).read_bytes()
    memory = {}
    base = 0
    eof = False
    for line in raw.splitlines():
        if eof or not line.startswith(b':'):
            raise ValueError('Invalid data or data after EOF')
        record = bytes.fromhex(line[1:].decode('ascii'))
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) % 256:
            raise ValueError('Invalid HEX record length/checksum')
        size, kind = record[0], record[3]
        address = int.from_bytes(record[1:3], 'big')
        payload = record[4:4+size]
        if kind == 0:
            for offset, value in enumerate(payload):
                key = base + address + offset
                if key in memory and memory[key] != value:
                    raise ValueError('Conflicting data')
                memory[key] = value
        elif kind in (2, 4) and size == 2 and address == 0:
            base = int.from_bytes(payload, 'big') << (4 if kind == 2 else 16)
        elif kind == 1 and size == 0 and address == 0:
            eof = True
        elif kind in (3, 5) and size == 4 and address == 0:
            pass
        else:
            raise ValueError('Unsupported or malformed record type')
    if not eof or not memory:
        raise ValueError('Missing EOF/data')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'file_bytes': len(raw),
            'defined_bytes': len(memory), 'minimum_address': hex(min(memory)),
            'maximum_address': hex(max(memory)),
            'contains_reset_vector': all(i in memory for i in range(4)),
            'upper_reserved_program_bytes': sum(0x1D000 <= i < 0x1FFF8 for i in memory)}


if __name__ == '__main__':
    print(json.dumps(inspect(sys.argv[1]), indent=2))
