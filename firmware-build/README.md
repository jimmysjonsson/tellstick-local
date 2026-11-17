# Custom local firmware build preparation

Server emulation and router DNS work are paused. The user authorized investigation
and build preparation for modifying the original TellStick Net. Flashing hardware
and RF transmission still need separate explicit authorization.

## Recovered sources

The original `/opt/tellstick/tellstick-net` remains unchanged. An isolated export
is staged in `../firmware-work/source`, which is ignored by Git. Exact revisions
and provenance are recorded in `dependencies.json`.

The [antpata/telldus-common mirror](https://github.com/antpata/telldus-common)
contains these exact original Git commit objects:

- CMake: `0bbe97dd9dc98f54a09a4f6f60cb97d746b22691`
- RF: `3e76e2b34cfe94613c5f5aa840b0218515482c96`

Both were exported into the isolated tree. They are not approximate replacements.
The temporary bare mirror is `/tmp/tellstick-common-mirror.git`; it can be fetched
again from that URL. Each submodule uses a different revision of the same original
repository; checking out the mirror's master for every submodule is incorrect.

## Remaining build dependencies

The TCP/IP revision `aa640ce96c39704bd55fb7a828253f25ffcddedd` is not in that mirror.
Inspected forks Nalle-sv/tellstick-net_backup, petterreinholdtsen/tellstick-net, and
alfs/tellstick-net retain the same missing gitlink rather than vendored sources.
Public repository search and Internet Archive index checks did not locate it.
The archive check covered `git.telldus.com/telldus-common.git*`; absence there is
not proof no copy exists elsewhere.

The firmware requires the legacy Microchip stack, including Telldus's
FindTCPIP.cmake, TCPIP_BOOTLOAD helper, configuration and Ethernet support. A current
Harmony stack is not a drop-in replacement. Recovering this exact revision is
preferred; reconstruction would require porting and independent review.

The upstream Dockerfile specifies HI-TECH PICC18 9.66.8870. The original vendor
URL currently returns HTTP 403:
https://ww1.microchip.com/downloads/en/DeviceDoc/picc-18-pro_9.66.8870-linux.zip

No archive entry was found for that exact URL. This does not establish permanent
unavailability or the reason for the 403. No compiler was downloaded, executed,
or installed. The upstream README warns that 9.80 is incompatible with its TCP/IP
stack. SDCC/current XC8 must not be assumed to build it unchanged.

Argus currently has no `picc18`, `cmake`, `docker`, `podman`, or `sdcc` executable
on PATH. Python 3.12 is used by the host controller; the device firmware is C for
a PIC18F67J60 and needs its own compiler. The upstream Dockerfile is based on
obsolete Debian Jessie, so recreating it may also require archived distribution
repositories and compatible 32-bit libraries. That has not been attempted.

## Build without any flashing

The upstream build invokes TCPIP_BOOTLOAD and can upload automatically. The
recovered FindPICC18.cmake also has a PICkit post-build flash option. A future
configuration must explicitly disable both:

```sh
cmake -S firmware-work/source/firmware -B firmware-work/build \
  -DPICC18_PATH=/path/to/picc18 \
  -DDEBUG=OFF \
  -DDO_BOOTLOADING_OVER_TCPIP=OFF \
  -DFLASH_PICKIT2=OFF
```

This is a proposed command from the tellstick-local directory, not a successful
configuration. Do not run it until TCP/IP build helpers have been recovered and
reviewed for all post-build actions. Do not supply DEVICE_ADDRESS during a build.
No CMake configure, make, bootloader probe, or firmware upload was run here.

## Changes to review before producing a hardware candidate

First aim for a reproducible baseline build with a map file, HEX checksums and
explicit bootloader/application memory placement. Verify preservation of external
EEPROM identity/configuration and the recovery path independently. The stock
firmware-4 HEX downloaded earlier is a reference image, not an EEPROM backup or
verified readback of this device.

The public local firmware needs hardening before normal LAN use. For example,
LMAppendChar searches for a NUL without reserving space for a terminator; a full
200-byte datagram can leave the buffer unterminated. String append and parsing
routines also need bounds checks. UDP commands include reset and network writes
without authentication. Planned changes should enforce bounded parsing, preserve
identity, avoid returning the discovery secret, and disable RF transmission at
compile time in the initial receive-only candidate. Review RF startup behavior
in the recovered dependencies too; a disabled command handler alone is insufficient
to prove the hardware never transmits.

No source patches have been made yet: without the stack/compiler, their device
behavior and memory layout cannot be validated. No flashable candidate exists.

The immediate missing inputs are an authentic copy of the TCP/IP revision (or its
original source archive) and a usable licensed PICC18 9.66 installation/installer.
Continue by locating those, then review build hooks, reproduce the baseline, and
prepare/test the receive-only hardening in the isolated tree before asking to flash.

## Expanded search results (2026-11-16)

### TCP/IP: recoverable upstream reference, exact Telldus revision still missing

A direct Git fetch of the exact revision from antpata/telldus-common failed with
`not our ref`. That mirror's advertised branches are master (README only), picc,
beta and mymod; it has no TCP/IP branch or tags. Its README confirms the original
repository used separate branches for each project. GitHub's public commit search
returned no match for the exact missing revision. Public GitLab project search
for telldus-common returned no projects. The original git.telldus.com endpoint
timed out; the code.telldus.com endpoint closed the connection. These observations
do not prove that all private or unindexed copies are gone.

Two useful legacy Microchip **v5.42** mirrors were located and pinned:

| Repository | Inspected commit | Root |
| --- | --- | --- |
| [xioTechnologies/OSC-Sync-Master](https://github.com/xioTechnologies/OSC-Sync-Master/tree/38689c9e5fe4cfe11e6fa64df4507d19bb3445b1/mla/Microchip) | 38689c9e5fe4cfe11e6fa64df4507d19bb3445b1 | mla/Microchip |
| [mentatpsi/Microchip](https://github.com/mentatpsi/Microchip/tree/ae5dabf9a9152953ea46f6de11a2b3c185535117/Microchip) | ae5dabf9a9152953ea46f6de11a2b3c185535117 | Microchip |

From each, TCPIP.h, ETH97J60.h, ETH97J60.c and TCPIP Stack Version.txt were retrieved
under `firmware-work/reference-stacks/`. The corresponding files were identical
between these two mirrors. TCPIP.h identifies v5.42. The Ethernet driver includes
PIC18F67J60 among supported targets. This is relevant legacy code rather than a
modern Harmony stack, but is **not** proof it matches the Telldus fork or contains
its DHCP/compiler patches. Reference files have not been inserted into source/tcpip.

Reference SHA-256 values (both mirrors):

- TCPIP.h: `7488a6724f77c069b2a79aa68ae29e05973151cfdb178941eec167a6d148ddc6`
- ETH97J60.h: `f5f6d8dc5cc94445f8404a6492aa3c9ec8d2f0539c2c2a4d96a627a2bc3c424b`
- ETH97J60.c: `73170b575a7ae21b551b403edebcada0bc480ea755e219cfc021b3ecaded40ae`
- Version.txt: `0225d9bc9af6e1a27b52a137afc0c5ce4f7e5f1fed8d9d9e0a9f17187f83d1ff`

An additional mirror, x893/Microchip at bbfb7daa9fb1cb7c13322bb7389116f1e8b23b16,
has v5.42 TCPIP.h and a UDP.h with the compatible legacy UDPOpen macro and
remote.remoteNode socket layout. However its complete file tree lacks ETH97J60.c,
so it is a poorer reconstruction base than the two references above.

The original firmware's TCP/IP gitlink changed several times, most recently in
November 2013. Earlier changes include one described as fixing slow DHCP servers.
An unpatched vendor v5.42 stack cannot therefore be assumed equivalent. A fallback
would reconstruct FindTCPIP.cmake/source selection, apply only understood platform
fixes, and validate it as a port. It would not be an exact baseline reproduction.
No such substitution or port has been made during this search.

Microchip itself still lists historical application-library downloads on its
[MLA archive page](https://www.microchip.com/en-us/tools-resources/develop/libraries/microchip-libraries-for-applications),
including releases from 2011-2013. The page identifies pre-December-2013 releases
as the legacy source for Ethernet TCP/IP. No large MLA installer was downloaded
or executed here.

### Compiler: official access route identified, no usable 9.66 installer yet

Microchip's current [MPLAB ecosystem archive](https://www.microchip.com/en-us/tools-resources/archives/mplab-ecosystem)
lists HI-TECH PIC18 PRO **9.65** and **9.80**, not 9.66. Its HI-TECH section states
that activation is no longer supported and new installations require a custom
license; the contact it supplies is SW.Licensing@microchip.com. Its
[legacy compiler support document](https://ww1.microchip.com/downloads/en/DeviceDoc/DS50002918A.pdf)
describes account-based archive access and obtaining activation through licensing.
Do not assume a downloadable installer alone provides a working licensed compiler.

An alternate path was checked:
`https://ww1.microchip.com/downloads/secure/aemDocuments/documents/DEV/ProductDocuments/SoftwareTools/picc-18-pro_9.66.8870-linux.zip`

It returned HTTP 200 after redirects, but the downloaded content was a Microchip
sign-in HTML page, **not a ZIP**. Archive-format verification caught this. Thus
this URL does not establish that the file exists or is available after login.
The original path and the shorter 9.66 Linux .run filename returned HTTP 403.
A broader Internet Archive index query for the old picc-18 download prefix returned
no entries. No installer was run, no activation was attempted, and no licensed
compiler is installed.

A concrete vendor inquiry, ready for the user to send if needed:

> I am restoring a legacy PIC18F67J60 firmware build using HI-TECH PICC18 PRO
> 9.66.8870 for Linux, as specified in telldus/tellstick-net's Dockerfile. Please
> confirm availability of the original installer, its checksum, and the supported
> licensing or Lite-mode options for a new installation. The original download
> URL returns 403. If 9.66 is unavailable, is a compatible 9.63PL3 or 9.65 release
> available for this target, and what host environment does it require?

No inquiry was sent. The compiler remains the external prerequisite even if we
choose to reconstruct the TCP/IP dependency from the recovered upstream sources.

## Wine compiler installed (2026-11-17)

The user supplied the Windows 9.65 installer and installed Wine with 32-bit support.
The verified local filename is `firmware-work/hcpic18.pro-9.65.exe` (lowercase).
SHA-256: `3fb9ec099b8dccbb90abd1ffaf8c33ee2b2a64d9031c69059f21709632e028ca`.
It is a PE32 x86 executable, not the HTML returned by the earlier unauthenticated
download. Wine reports `wine-9.0 (Ubuntu 9.0~repack-4build3)`.

The installer was run in a dedicated win32 prefix:
`firmware-work/wine-picc18`. Its help option opened a GUI; the restarted installer
used `--setTrue-HeadlessInstall`, the licence-agreement switch, an installation
directory of `C:\PICC18\9.65`, and `--no-hitide`. It exited with code 120, so
installation success was not inferred from its exit status. Instead, the installed
compiler was independently executed and tested:

- `bin/picc18.exe --ver` exits 0 and identifies PICC18 9.65 **Lite**.
- A minimal infinite-loop C program compiled and linked successfully for
  `--chip=18F67J60`, producing a test HEX under `drive_c/picc18-smoke`.
- This smoke-test image is **not device firmware** and must never be flashed.
- No licence key was passed, logged, or added to project files. PRO activation has
  not been attempted. Lite mode's code-size/optimization limits may matter for the
  full build; a successful smoke test does not establish full firmware compatibility.

Version check from the project directory:

```sh
WINEPREFIX="$PWD/firmware-work/wine-picc18" WINEDEBUG=-all \
  wine "$PWD/firmware-work/wine-picc18/drive_c/PICC18/9.65/bin/picc18.exe" --ver
```

Wine needs execution outside this session's restrictive sandbox. No machine-wide
compiler setup or default Wine prefix was used. Files are within ignored
firmware-work. Full firmware compilation still needs TCP/IP dependency recovery
or a reviewed reconstruction, Windows path handling in the CMake wrapper, and
verification that all flash hooks remain disabled.

## Full Lite build succeeded (2026-11-17)

The activation installer was closed at the user's request. PRO activation was
unsuccessful; the working compiler remains Lite. The first complete offline build
now succeeds using legacy Microchip TCP/IP v5.42 reconstructed from
xioTechnologies/OSC-Sync-Master at the pinned commit above. This supersedes the
prior build-blocker status, but does not recover the missing original Telldus fork.

Build results:

- All 36 firmware, RF and selected TCP/IP C units compiled; link exited 0.
- Program: 73135 bytes (55.8% of available program space).
- RAM: 2098 bytes (56.5% of available RAM).
- HEX: `firmware-work/build-lite/TellStickNet-Lite.hex`, 205772 file bytes.
- SHA-256: `3e69cdf643708a2721b296fe1e5d5d3da5fc99df6afb9a45d3afd14a657c72ef`.
- Map: `firmware-work/build-lite/TellStickNet-Lite.map`.
- Logs: per-unit logs in build-lite group directories, plus `link.log`.
- Intel HEX validation passed record length, checksum, EOF and overlap checks.
  There are 73140 defined bytes, including non-program configuration data.

### Build method and compatibility patch

`build_lite.py` is a direct Python/Wine driver based on the source lists from the
upstream CMake files. It invokes only the compiler; it has no upload command,
bootloader helper, device address, RF transport, or CMake post-build actions. It
uses explicit Windows path conversion, file-based logs, per-command timeouts,
and suppresses Wine crash dialogs. Old top-level HEX/map artifacts are removed
at build start, so a failed run cannot leave an earlier top-level image looking
like a new result.

`lite-compat.patch` records changes **only** to the isolated firmware/RF export
and reconstructed stack. The original firmware repository is clean and unchanged.
Reverse application was checked with patch's batch dry-run mode.

1. The old compiler fails on a minimal test passing multiple inline string literals
   to a function: parser error 301, or a p1.exe access violation. The same test using
   named constant arrays succeeds. Firmware/RF call-site literals were therefore
   replaced with named `static const char[]` arrays. The discovery version string
   is also named. No API strings or command names were changed.
2. One always-disabled printf diagnostic in tellsticknet.c was replaced by a no-op.
   The compiler does not support a variadic macro replacement for the upstream
   non-debug printf macro, so that attempted change was reverted.
3. Helpers.c's ADC conversion-start field was changed from ADCON0bits.GO to
   ADCON0bits.GODONE, matching PICC18 9.65's 18f67j60.h declaration.

The dedicated Wine prefix was tested with Windows XP compatibility. That setting
alone did not resolve the string bug; named arrays did. No native runtime DLLs,
compiler patches, licence workarounds, or evaluation activation were used.

For a fresh source export, populate firmware and RF at the exact locked revisions,
copy `mla/Microchip/` from the pinned xioTechnologies source into source/tcpip,
then apply the patch **once**:

```sh
patch --batch -p1 -d firmware-work/source < firmware-build/lite-compat.patch
python3.12 firmware-build/build_lite.py
python3.12 firmware-build/inspect_hex.py firmware-work/build-lite/TellStickNet-Lite.hex
```

The current source tree is already patched. Do not apply the patch to the original
repository. Dependency source remains under ignored firmware-work; source licences
and copyright notices are preserved in the downloaded tree. The direct build
avoids the unavailable FindTCPIP.cmake and omits unused stack modules.

### Limits before hardware use

**This artifact is not approved or ready to flash.** It contains a reset vector
at address 0x0 and configuration data through 0x1fffb. Bootloader/application
placement and the actual upload format still need independent review. A valid
HEX checksum does not prove correct placement or bootability. This build has not
disabled the firmware's RF paths; do not load it as a receive-only candidate.

Link warnings remain for signed/constant comparisons in the Ethernet driver and
compiler I2C library, plus a TCP array variable reported as potentially uninitialized
around its sizeof/read-buffer use. They were not hidden. Hardware networking,
EEPROM compatibility, bootloader preservation, and RF behavior are untested.
The public parser's bounds issues and unauthenticated reset/network-write commands
also remain; no security hardening is implied by successful compilation.

Next work is to inspect the map/image against the device's bootloader layout,
review EEPROM handling and remaining warnings, and prepare a hardened receive-only
candidate. Flashing and RF transmission still require explicit authorization.

## Receive-only research candidate and image-layout review (2026-11-17)

A separate profile is now prepared under `firmware-work/source-readonly`. The
working Lite baseline remains in `firmware-work/source`. Neither is the original
firmware repository.

### Image layout findings

Offline inspection of the archived stock firmware-4 image found program data
through 0x1cfff, configuration bytes at 0x1fff8..0x1fffb, and no data in
0x1d000..0x1fff7. The first unrestricted Lite build did place program data in that
upper region. This is a real compatibility concern, although the image alone does
not prove the region's purpose. The RX profile conservatively excludes that range
using `--ROM=default,-1D000-1FFF7`.

Both the stock and custom images contain the same four reset-vector bytes at zero
(`14ef00f0`). Therefore presence of a reset vector at zero, by itself, does not
establish incompatibility. The bootloader may rewrite vectors or protect regions
while accepting application HEX; its actual behavior has not been verified. The
configuration-byte erase/write behavior remains another unknown. No upload should
be attempted based solely on these comparisons.

### Receive-only changes

`prepare_readonly.py` generates the separate profile from the already compatible
baseline. It copies only firmware, RF sources, and the stack's include/TCPIP trees.
It then makes these explicit changes:

- Omits firmware/send.c, firmware/transmit_arctech.c and rf/transmit.c from the build.
  Timer-three transmit ISR code is removed. Transmit enable and data latches are
  held low by initialization; timers one and three and their interrupts are disabled.
  Initialization sets latches low before changing GPIO direction. Receiver setup
  and timer-four sampling remain. This is source-level intent, not measured RF
  silence: electrical behavior at power-on and during bootloader operation is
  still untested.
- Replaces local UDP dispatch with a bounded recognizer accepting exactly
  `B:reglistener`. No RF send, disconnect, setip, or saveip command is dispatched.
  Listener registration is an intentional volatile state change; it does not
  persist configuration. It is unauthenticated and another LAN client could
  replace the single listener.
- Disables the stack's remote reboot service and excludes its source from the link.
- Removes clearEEPROM/saveEEPROM implementations. Initialization reads only the six
  presumed MAC identity bytes and selects DHCP. It neither reads the discovery
  secret nor loads the custom source's network configuration fields from stock
  EEPROM. The six-byte identity location is assumed from public source history;
  it has not been verified against this physical device's stock EEPROM. The source's
  fallback MAC behavior for blank EEPROM is retained and remains a review concern.
- Replaces discovery's secret field with a public `LOCALONLY` marker. The wire
  format is retained for the existing discovery client. Version becomes `X-RX1`.
  The marker is not an activation secret and cannot replace a Telldus credential.
- Bounds outgoing message append operations, keeps the buffer NUL-terminated, and
  drops listener messages if overflow occurs. The general inbound hash parser is
  not exposed through local UDP. This is not a complete third-party stack audit.

### Build and validation

```sh
python3.12 firmware-build/prepare_readonly.py
python3.12 firmware-build/build_lite.py --readonly
python3.12 firmware-build/test_readonly.py -v
python3.12 firmware-build/validate_readonly.py
```

The generation step refreshes the RX profile from the compatible baseline; changes
made directly to source-readonly will be overwritten. Hardware tests are not part
of these commands. The host C tests require `cc` and exercise code extracted from
the generated C sources with mocked UDP calls, not a parallel Python reimplementation.

Results:

- All 32 selected C units compile and link in Lite mode.
- Program: 67841 bytes (51.8% of the compiler's nominal device capacity; the excluded
  region also reduces the actual permitted application capacity).
- RAM: 1824 bytes (49.1%).
- HEX: `firmware-work/build-readonly/TellStickNet-Lite.hex`.
- SHA-256: `983d53973f77b717e18daf7b425895883b59ed015b8cbb8fe4643c9cc6ccb7a5`.
- Map: `firmware-work/build-readonly/TellStickNet-Lite.map`.
- HEX record checks pass and no defined bytes lie in 0x1d000..0x1fff7.
- Map checks confirm RF-send, transmit ISR, EEPROM-write, configuration-write,
  command dispatcher and remote-reboot symbols are absent. Registration and
  local-event delivery symbols remain.
- Two C behavioral tests pass: exact registration plus malformed/oversized command
  rejection; outgoing append boundary/overflow handling and recovery after clear.
- The original twelve Python client/codec tests continue to pass.

The Ethernet comparison warnings involve an unsigned receive-ring value compared
with RXSTART (zero) in a wraparound condition; these are retained, not suppressed.
The TCP warning concerns `sizeof(buffer)` on a local array before TCPRAMCopy fills
it; sizeof does not read array contents in this case. This suggests a diagnostic
limitation, but generated code and pointer handling still need review. The I2C
write-library warnings from the baseline disappear when EEPROM writes are omitted.

**Still not flash-ready:** the physical bootloader's reserved range, vector and
configuration handling, identity layout, RF hardware startup behavior, and network
operation remain unverified. Telldus's recovery documentation describes a recovery
IP of 192.168.97.60, but no recovery mode or bootloader operation has been invoked
on this device. No firmware flash or RF transmission has occurred.

## Recovery investigation

Before any hardware test, see [RECOVERY.md](RECOVERY.md). A private partial
identity/secret record now exists with explicit user approval; its exact path and
permissions are documented there without exposing its contents. Full device
backup and recovery remain unverified. No flash is authorized.

## Fresh PRO activation attempt requested (2026-11-17)

Microchip advised the user to retry online activation with Off-line unchecked.
At the user's request, the prior Wine installation was removed from the active
compiler path by moving the complete environment to:
`firmware-work/wine-picc18-before-pro-20261117T164229Z` (directory mode 0700).
This preserves the working Lite installation for rollback; it is excluded from Git.
A fresh win32 prefix at firmware-work/wine-picc18 was created and the original
installer launched interactively, with destination C:\PICC18\9.65. No licence key
was supplied through command-line arguments. Activation remains unverified until
the user completes the wizard and the compiler is checked again. Existing HEX,
source, cloud-account backups and device state were not changed.

### Continue Lite work without changing the fresh PRO environment

The user reported that the fresh online activation also failed and has contacted
Microchip. The wizard was closed. Select the preserved Lite prefix explicitly:

```sh
python3.12 firmware-build/build_lite.py --readonly \
  --wine-prefix /opt/tellstick/tellstick-local/firmware-work/wine-picc18-before-pro-20261117T164229Z
```

The fresh active prefix is left intact for the licensing investigation. Recovery
reference storage and the four matching configuration-byte values are documented
in RECOVERY.md. They do not authorize a hardware flash.


## Validated private rollback package

Rollback preparation completed on 2026-11-17. Final package:
`secrets/recovery/rollback-20261117T180531730937Z/`. It includes the verified stock application,
three matching full flash readbacks, rebuilt receive-only candidate, checksums,
static review, and offline verifier. See RECOVERY.md for coverage and remaining
limits. Verify without device access using:

```sh
python3.12 secrets/recovery/rollback-20261117T180531730937Z/verify_rollback.py
```

`prepare_rollback.py` can create a fresh private package from the retained inputs;
`verify_rollback.py` checks package integrity, stock/application identity and
candidate layout/linked functions. Neither implements device writes. The package
contains private readbacks and must remain excluded from Git. Firmware flashing
and RF testing remain unauthorized.


## Stock firmware restore test verified

On 2026-11-17 the user explicitly authorized a same-version stock firmware-4 write.
`test_stock_restore.py` verified package, pinned stock checksum, exact device identity
and matching pre-read before transferring the stock HEX. The post-write 128 KiB
flash readback matches all original backups exactly; normal firmware-4 discovery
and the privately compared advertised credential are unchanged. Details and private
record location are in RECOVERY.md. No custom firmware was installed and no RF
command sent. Experimental RX installation is not authorized by that stock test.
The test script is a write-capable, stock-only tool; it must not be confused with
the GET-only readback tools and has not been added to the immutable rollback package.


## Receive-only hardware test verified

On 2026-11-17, the authorized pinned X-RX1 image was installed after a matching
stock pre-read. Local discovery at 192.168.1.193 and five received UDP events
confirmed operation. A user-coordinated power-on GET subsequently matched the
complete expected flash image and confirmed unchanged bootloader/configuration;
X-RX1 then restarted normally. See RECOVERY.md for private test-record locations.
The device currently runs X-RX1. Intentional RF transmission is excluded; light
control and local schedules are not implemented by this receive-only profile.
