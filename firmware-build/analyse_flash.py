"""Offline PIC18 flash comparison. Outputs addresses/counts, never memory strings."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from inspect_hex import inspect

SIZE = 0x20000
TABLE = 0x1DBC0
BOOT = 0x1DC00
BOOT_END = 0x1FC00
CONFIG = 0x1FFF8


def load_hex(path):
    inspect(path)  # Reject malformed records, checksums, overlaps and missing EOF.
    memory = {}
    base = 0
    for line in Path(path).read_bytes().splitlines():
        record = bytes.fromhex(line[1:].decode('ascii'))
        count, kind = record[0], record[3]
        address = int.from_bytes(record[1:3], 'big')
        payload = record[4:4+count]
        if kind == 0:
            memory.update((base+address+i, value) for i, value in enumerate(payload))
        elif kind in (2, 4):
            base = int.from_bytes(payload, 'big') << (4 if kind == 2 else 16)
    if any(address >= SIZE for address in memory):
        raise ValueError('HEX exceeds the target flash address range')
    return memory


def goto(data, address):
    first = int.from_bytes(data[address:address+2], 'little')
    second = int.from_bytes(data[address+2:address+4], 'little')
    if first & 0xFF00 != 0xEF00 or second & 0xF000 != 0xF000:
        return None
    return (((second & 0xFFF) << 8) | (first & 0xFF)) * 2


def analyse(first, second, reference, candidate=None):
    data, repeat = Path(first).read_bytes(), Path(second).read_bytes()
    if len(data) != SIZE or len(repeat) != SIZE or data != repeat:
        raise ValueError('Require two identical full-sized readbacks')
    memory = load_hex(reference)
    archive = bytearray(b'\xff' * SIZE)
    for address, value in memory.items():
        archive[address] = value
    normalized = bytearray(data)
    normalized[:4] = data[TABLE:TABLE+4]
    # Remove ONLY the inferred jump-table/bootloader reservation for comparison.
    normalized[TABLE:BOOT_END] = b'\xff' * (BOOT_END-TABLE)
    differences = [address for address, value in memory.items() if data[address] != value]
    outside_differences = sum(a != b for a, b in zip(normalized, archive))
    config_present = all(address in memory for address in range(CONFIG, CONFIG+4))
    result = {
        'flash_bytes': len(data),
        'matching_independent_reads': True,
        'sha256': hashlib.sha256(data).hexdigest(),
        'archived_defined_bytes': len(memory),
        'archived_mismatch_addresses': [hex(a) for a in differences],
        'installed_reset_goto': hex(goto(data, 0)) if goto(data, 0) is not None else None,
        'archived_reset_goto': hex(goto(archive, 0)) if goto(archive, 0) is not None else None,
        'jump_table_first_goto': hex(goto(data, TABLE)) if goto(data, TABLE) is not None else None,
        'jump_table_second_goto': hex(goto(data, TABLE+4)) if goto(data, TABLE+4) is not None else None,
        'jump_table_matches_original_reset': data[TABLE:TABLE+4] == archive[:4],
        'normalized_full_flash_mismatches': outside_differences,
        'configuration_matches_archive': config_present and data[CONFIG:CONFIG+4] == archive[CONFIG:CONFIG+4],
        'stored_cp0_requests_no_code_protection': bool(data[CONFIG+1] & 4),
        'bootloader_region_sha256': hashlib.sha256(data[BOOT:BOOT_END]).hexdigest(),
        'inferred_reserved_start': hex(TABLE),
        'inferred_reserved_end_inclusive': hex(BOOT_END-1),
        'blank_before_jump_table': all(v == 255 for v in data[0x1D000:TABLE]),
        'blank_after_bootloader_before_config': all(v == 255 for v in data[BOOT_END:CONFIG]),
        'external_eeprom_included': False,
        'restore_tested': False,
    }
    if candidate:
        proposed = load_hex(candidate)
        result['candidate'] = {
            'overlap_jump_table_or_bootloader': any(TABLE <= a < BOOT_END for a in proposed),
            'overlap_conservative_reservation': any(0x1D000 <= a < CONFIG for a in proposed),
            'configuration_matches_readback': all(a in proposed and proposed[a] == data[a] for a in range(CONFIG, CONFIG+4)),
            'reset_is_goto': goto(bytes(proposed.get(a, 255) for a in range(4)), 0) is not None,
            'hardware_validated': False,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = json.dumps(analyse(args.first, args.second, args.reference, args.candidate), indent=2)
    if args.output:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(report+'\n')
    print(report)


if __name__ == '__main__':
    main()
