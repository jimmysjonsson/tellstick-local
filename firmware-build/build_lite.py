"""Offline-only PICC18/Wine build. Contains no firmware-upload operation."""
from pathlib import Path
import os
import subprocess
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'firmware-work/source'
BUILD = ROOT / 'firmware-work/build-lite'
PREFIX = ROOT / 'firmware-work/wine-picc18'
COMPILER = PREFIX / 'drive_c/PICC18/9.65/bin/picc18.exe'


def win(path):
    path = Path(path).resolve()
    try:
        return 'C:\\' + str(path.relative_to(PREFIX / 'drive_c')).replace('/', '\\')
    except ValueError:
        return 'Z:' + str(path).replace('/', '\\')


def main():
    global SOURCE, BUILD, PREFIX, COMPILER
    parser = argparse.ArgumentParser(description=__doc__)
    profiles=parser.add_mutually_exclusive_group()
    profiles.add_argument('--readonly', action='store_true')
    profiles.add_argument('--transmit', action='store_true')
    parser.add_argument('--wine-prefix', type=Path, default=PREFIX)
    args = parser.parse_args()
    PREFIX = args.wine_prefix.resolve()
    COMPILER = PREFIX / 'drive_c/PICC18/9.65/bin/picc18.exe'
    if not COMPILER.is_file():
        parser.error('Compiler not found in this prefix; select the preserved Lite prefix with --wine-prefix')
    if args.readonly or args.transmit:
        SOURCE = ROOT / ('firmware-work/source-transmit' if args.transmit else 'firmware-work/source-readonly')
        BUILD = ROOT / ('firmware-work/build-transmit' if args.transmit else 'firmware-work/build-readonly')
    BUILD.mkdir(parents=True, exist_ok=True)
    for filename in ('TellStickNet-Lite.hex', 'TellStickNet-Lite.map'):
        (BUILD / filename).unlink(missing_ok=True)
    (BUILD / 'config.h').write_text('#ifndef CONFIG_H\n#define CONFIG_H\n#include "HardwareProfile.h"\n#endif\n')
    sources = {
        'firmware': 'common discovery eeprom livemessage localaccess main message pwm rf send tellsticknet transmit_arctech'.split(),
        'rf': 'arctech crc everflourish fineoffset hasta mandolyn oregon oregonv3 receive transmit x10'.split(),
        'tcpip/TCPIP Stack': 'ARP DHCP DNS ETH97J60 Hashes Helpers ICMP IP Reboot StackTsk TCP Tick UDP'.split(),
    }
    if args.readonly or args.transmit:
        sources['firmware'] = [name for name in sources['firmware'] if name not in ('send', 'transmit_arctech')]
        sources['rf'].remove('transmit')
        sources['tcpip/TCPIP Stack'].remove('Reboot')
        if args.transmit:
            sources['firmware'].append('txcontrol')
    includes = [SOURCE / 'firmware', SOURCE / 'rf', SOURCE / 'tcpip/Include', BUILD]
    env = dict(os.environ, WINEPREFIX=str(PREFIX), WINEDEBUG='-all', WINEDLLOVERRIDES='winedbg.exe=d')
    flags = ['--chip=18F67J60', '--mode=lite', '--runtime=+plib']
    if args.readonly or args.transmit:
        flags.append('--ROM=default,-1D000-1FFF7')
    objects = []
    failed = []
    for group, names in sources.items():
        out = BUILD / group.replace('/', '-')
        out.mkdir(parents=True, exist_ok=True)
        for name in names:
            src = SOURCE / group / (name + '.c')
            if not src.is_file():
                raise SystemExit(f'Missing source: {src}')
            cmd = ['wine', str(COMPILER), *flags, '--pass1', '--outdir=' + win(out),
                   *['-I' + win(p) for p in includes], win(src)]
            log = out / (name + '.log')
            with log.open('w') as stream:
                result = subprocess.run(cmd, env=env, cwd=BUILD, stdout=stream, stderr=subprocess.STDOUT, timeout=45)
            print(f'{group}/{name}: {"OK" if result.returncode == 0 else "FAILED"}', flush=True)
            if result.returncode:
                print(log.read_text(errors='replace')[-7000:])
                failed.append(f"{group}/{name}")
                continue
            objects.append(win(out / (name + '.p1')))
    if failed:
        print('Failed compilation units: ' + ', '.join(failed))
        return 1
    cmd = ['wine', str(COMPILER), *flags, '--outdir=' + win(BUILD), '-O' + win(BUILD / 'TellStickNet-Lite.hex'), '-M' + win(BUILD / 'TellStickNet-Lite.map'), *objects]
    log = BUILD / 'link.log'
    with log.open('w') as stream:
        result = subprocess.run(cmd, env=env, cwd=BUILD, stdout=stream, stderr=subprocess.STDOUT, timeout=45)
    print(log.read_text(errors='replace'))
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
