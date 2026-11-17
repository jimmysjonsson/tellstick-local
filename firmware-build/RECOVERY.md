# Recovery assessment — no flashing authorized

Updated 2026-11-17. The user requires confidence in restoring the current device
state before any flash. A same-version stock restore has now been explicitly
authorized and verified, including a byte-identical full flash readback; see the
final section. Broader custom-firmware recovery is not guaranteed. A previously authorized
TFTP GET test successfully downloaded internal flash twice and temporarily entered
the bootloader. Earlier no-flash statements below describe their historical
assessment stages. A stock application write was subsequently performed with the
user’s explicit authorization; no custom firmware or RF command was sent. An
absolute recovery guarantee cannot be made from documentation or build validation.

## Private file inventory

The user explicitly authorized access to device secrets and subsequently explicitly
approved private local recovery files, lifting the earlier no-persistence rule only
for recovery backups. An initial attempted save was rejected by automatic approval
review before this explicit persistence approval; that rejected action created no
files. The successful capture occurred only after the user's additional approval.

Private directory:
`/opt/tellstick/tellstick-local/secrets/recovery/20261117T154111596804Z/`

| File | Contents | Permissions |
| --- | --- | --- |
| discovery-response.bin | Raw discovery response containing MAC, device secret, and firmware version | 0600 |
| metadata.json | Public identity, capture time, and partial-backup limitation | 0600 |

The directory and its parents use 0700; both files were confirmed excluded from
Git by the existing secrets/ rule. Files are plaintext protected by filesystem
permissions, **not encrypted**. Neither the response nor its secret was printed.
The capture sent only ASCII D to 192.168.1.193:30303. The script is
`firmware-build/backup_discovery.py`; rerunning creates another timestamped record.

This preserves the discovery credential, not its verified EEPROM address or all
configuration. It is **not a full backup or a restore image**. No full flash,
bootloader, configuration-memory, or external-EEPROM dump exists. The captures/
directory was empty when inspected. Build HEX files are generated or downloaded
reference images, not backups taken from this unit. Licence activation files in
the compiler environment are separate from TellStick device secrets.

## What needs backing up

| State | Recovery evidence | Outstanding work |
| --- | --- | --- |
| Application firmware | Archived vendor-host firmware-4 HEX exists, checksums validated | Read physical unit and compare; archived image is not proof of identical installed bytes |
| Bootloader and application jump table | Upper-region reservation inferred from stock image; reference Microchip design available | Obtain this unit's complete flash dump and identify its bootloader, jump table, and protected range |
| Configuration words | PIC family stores them in program flash | Read actual settings, including code protection; retain them with flash backup |
| MAC/secret and persistent settings | Discovery identity/secret saved privately; public firmware accesses an external I²C EEPROM | Identify actual chip, capacity and layout; make repeated matching full dumps |
| Restore mechanism | Telldus documents network recovery; PIC supports ICSP | Verify hardware access and compatible tools, read protection, image conversion and verification method |

The PIC18F67J60 has 128 KiB of program flash and **zero internal data EEPROM**
([Microchip product specifications](https://www.microchip.com/en-us/product/PIC18F67J60)).
Public TellStick firmware uses I²C functions with device byte 0xA0 (7-bit address
0x50), separate from PIC flash. This suggests a 24xx-style serial EEPROM but does
not identify its part or capacity. A PIC ICSP flash dump would not automatically
include this separate chip. Do not guess its addressing scheme or apply an EEPROM
reader to it before identifying the part and power arrangement.

## Network recovery and readback

[Telldus recovery documentation](https://developer.telldus.com/wiki/restore_info)
describes recovery at 192.168.97.60 with network LED groups of seven flashes and
TFTP upload. This supports a repair path when the bootloader is intact; it neither
backs up current data nor proves survival of all custom-image failure modes.

The [Microchip Ethernet bootloader design](https://documentation.help/Microchip-TCP.IP-Stack/BootloaderDesign.html)
documents binary flash readback over TFTP and explains vector relocation, preserved
bootloader code and configuration-page rewriting. Its reference reservation is
not identical to our inference from the Telldus stock HEX. Telldus may have changed
these features. Readback is disabled by the reference implementation when code
protection is enabled. We have **not** verified Telldus's readback support.

Critically, the public stack's application RebootTask reacts to UDP traffic on port
69 by resetting into its bootloader. Therefore a TFTP read request to the running
unit is not assumed read-only with respect to operating state and was not sent.
It may be possible to investigate readback after deliberate bootloader entry, but
that requires a separately agreed outage/entry procedure, not an automatic probe.
No TFTP write, erase, or restore command should be run during backup investigation.

## Physical recovery and read protection

The [exact-family Microchip programming specification](https://ww1.microchip.com/downloads/en/DeviceDoc/39688d.pdf)
identifies ICSP access through MCLR, RB6/PGC, RB7/PGD, supply and ground. This is the
chip interface, **not a verified TellStick board-header pinout**. Board pads and
voltages must be traced before connecting a programmer. Use a programmer explicitly
supporting PIC18F67J60 and appropriate voltage levels; avoid simultaneous conflicting
power sources. No purchase/model recommendation has been validated here.

The [device datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/39762f.pdf)
states that CP0 controls external program-memory access. The programming
specification says clearing enabled code protection requires a bulk erase. Never
choose an erase/unprotect operation to obtain a backup: it would destroy the state
being preserved. If readout is protected, stop and reassess rather than treating
an all-zero/all-ones read as a valid backup.

The archived firmware-4 HEX's CONFIG1H value is 0xF7, requesting CP0=1 (unprotected).
That is encouraging **only for that file**. A bootloader can preserve or alter
configuration; the physical device's protection is unknown.

The user can open the case but has no programmer or EEPROM reader. Read-only USB
inventory found no recognizable attached PIC programmer/EEPROM reader. Its Microchip
USB entries were hubs/media-reader devices, not evidence of a programming tool.
The next physical evidence needed is clear photos of both PCB sides, especially
chip markings and unpopulated headers/pads. Hardware inspection can identify tools
and an exact read-only connection plan without applying power or programming.

## Required evidence before proposing a flash test

1. Identify the board revision, PIC, external EEPROM and actual programming pads.
2. Establish a supported read-only access path for flash/configuration and EEPROM.
3. Obtain at least two matching complete reads of each memory, preserving original
   files with private permissions; confirm size, content plausibility and identity.
4. Parse the bootloader/vector/configuration layout from this device's flash and
   compare it with archived firmware and the candidate. Do not equate a binary
   bootloader readback with an application HEX upload: vector relocation differs.
5. Establish an independent recovery path and correct backup-to-programmer format.
   Ideally demonstrate the restore workflow on equivalent spare hardware rather
   than destroying the only device's current state to test the backup.
6. Review any remaining uncertainty with the user. Absolute 100% certainty is not
   obtainable against every hardware/power fault; with the current absolute
   requirement, do not flash while uncertainty remains. No flash permission has
   been granted by this recovery investigation.

Current outcome: discovery credential preserved; application/bootloader/EEPROM
recovery unproven. **Do not flash.**

## Telldus Live configuration backup completed

A separate account-configuration export was verified on 2026-11-17:
`/opt/tellstick/tellstick-local/secrets/recovery/telldus-account-20261117T163843Z.json`.
It contains 1 gateway/location, 40 devices/groups (35 RF parameter definitions and
5 groups), 3 sensors, 46 schedules and 1 event. Files use 0600 and are excluded
from Git. Earlier partial exports remain under the same recovery directory.
API authentication credentials were not saved. Historical readings/activity and
account-profile/billing data are not included. See `../scripts/EXPORT.md` for
coverage checks and schedule-record provenance. This preserves cloud configuration;
it does not substitute for physical flash/bootloader/EEPROM backups. The no-flash
restriction remains in force.

## Follow-up while awaiting Microchip (2026-11-17)

The failed fresh PRO wizard was closed. The preserved installation still reports
PICC18 9.65 Lite. The active fresh prefix has no compiler executable at the expected
path. The build driver now accepts --wine-prefix so Lite work can continue without
disturbing the new environment relevant to Microchip's licensing response.

The archived stock firmware-4 HEX is now also retained persistently at
`firmware-work/recovery-reference/tellstick_net_fw4.hex`, rather than relying on
its /tmp copy. Intel HEX validation passed and its SHA-256 remains
`ba103630c1048178c59c8253a9e510ab3ac565c6ecf592b78aeb78fefacd8a90`.
This is a public archived reference, not a readback or a device-secret backup.

All four defined configuration bytes in the stock reference and current RX
candidate match:

| Address | Stock reference | RX candidate |
| --- | --- | --- |
| 0x1FFF8 | 0x9E | 0x9E |
| 0x1FFF9 | 0xF7 | 0xF7 |
| 0x1FFFA | 0xFD | 0xFD |
| 0x1FFFB | 0xFF | 0xFF |

This removes an image-to-reference configuration mismatch, but does not establish
the physical unit's settings, bootloader behavior, or ability to restore it.
No device state was read or changed in this follow-up. The next necessary input
remains clear photos of both PCB sides, especially memory chip markings and
unpopulated programming pads. No programmer, pinout or connection should be selected
from the external case/model name alone.


## First physical photographs (2026-11-17)

Two JPEG photographs were received privately in secrets/recovery/board-photos/,
showing the component and solder sides of the same board. Files are 0600.
The component-side silkscreen includes 205460; its meaning as an identifier or
revision has not been established. A large square IC at IC1, a small eight-pin IC
at IC4 near the upper left, and a row of six exposed circular pads above the
large crystal are visible, with Ethernet on the left and antenna on the right.
The six-pad row is a candidate programming/test interface only: no ICSP pinout,
pad order, voltage, or electrical connectivity is established by these photos.
The IC1 and IC4 part markings are not reliably readable. IC4 must not yet be
identified as the EEPROM solely from its package/location.

Next evidence needed: focused close-ups of IC1, IC4, and the six-pad row with its
surrounding traces, plus corresponding solder-side detail if practical. Use
angled diffuse lighting to make laser markings readable and keep the board
unpowered. Existing photographs establish layout but do not establish a supported
backup connection, protection state, or recoverability. No flashing or RF command
was performed.


## Second physical photographs (2026-11-17)

Two additional photographs show both board sides. IC1 is now legible as Microchip
PIC18F67J60-I/PT, confirming the previously assumed MCU family on this physical
unit. The six exposed round pads above the 25.000 crystal and a triangular
silkscreen marker at the right end are clearer. The marker alone establishes
neither numbering nor an ICSP pinout. IC4's eight-pin package is visible at the
upper left (Ethernet left, antenna right), but its marking remains unreadable.
Its part, memory capacity and required supply voltage remain unconfirmed. A
focused photo or direct transcription of IC4's marking is the next useful visual
evidence; further whole-board photos are unnecessary for MCU identification.
No electrical continuity measurements, programmer connection, memory readback,
flash operation or RF transmission was performed.


## IC4 close-up (2026-11-17)

The fifth uploaded photograph, 629db3bcb3c3419a9736d34a260c870f.jpg, makes
IC4's top line readable as 24AA01 with a Microchip logo. This visually identifies
a Microchip 24AA01 I2C serial EEPROM. Exact suffix/date markings were not needed
and are not transcribed as established identifiers. Manufacturer documentation
specifies 1 Kbit organized as 128 x 8 bits: a complete EEPROM read is 128 bytes,
not 1 KiB. Source: https://ww1.microchip.com/downloads/en/DeviceDoc/21711J.pdf

For the eight-pin package, the datasheet gives VSS pin 4, SDA pin 5, SCL pin 6,
WP pin 7 and VCC pin 8. These are chip pin functions, not a verified board pad
mapping or a connection instruction. Actual board supply, bus isolation and
programming-pad continuity remain unmeasured. No voltage should be selected from
the EEPROM's broad supply rating without checking the rest of the board.

Photos now identify both the PIC and external EEPROM. More whole-board photos are
not required. The next recovery step needs suitable measurement/readout equipment
or an electronics technician: verify ICSP connections and power arrangement, then
obtain repeated matching read-only flash/configuration and 128-byte EEPROM dumps.
In-circuit EEPROM readout may require isolation if the MCU loads the bus; suitability
is not established. Never use erase/unprotect to obtain a backup. Recovery remains
unproven and no flashing is authorized.


## Authorized Ethernet readback succeeded (2026-11-17)

The user explicitly authorized testing TFTP GET after reconnecting the device.
firmware-build/tftp_readback.py implements only RRQ opcode 1 and ACK opcode 4;
there is no upload/write opcode or erase command. Local fake-socket checks covered
complete transfer, duplicate block handling, remote error and timeout. Error text
and returned memory contents were not printed.

Two successful GET firmware.bin requests in octet mode each returned 131072 bytes:

- secrets/recovery/tftp-20261117T174934573218Z/flash.bin
- secrets/recovery/tftp-20261117T174949379573Z/flash.bin

Both files match byte for byte and have SHA-256
`d7fc988322cf846851b88783e1db1ae8fc23081819fd4985fa15a137c9dd3d37`.
Files are 0600 and directories 0700, under the ignored private recovery tree.
Each directory contains metadata.json; the first also contains validation.json.
Both transfers needed two RRQs, consistent with entering the bootloader before
serving the request. Readback is nonblank and upper flash contains data. Of 78794
bytes defined in the archived stock application HEX, only two differ in readback;
all four defined configuration bytes match. The two differences and bootloader
layout still need interpretation before any restore conversion is proposed.

Normal firmware-4 discovery was successful before testing. The immediate check
after the second transfer timed out; a later check succeeded at the original IP,
MAC and firmware version. No additional reset or recovery write was sent.

This establishes repeatable full-sized internal-flash readback over Ethernet on
this unit. It does not include the separate 128-byte 24AA01 EEPROM, prove that a
restore image can safely be written back, or authorize flashing. Physical tools
are no longer a prerequisite for obtaining this internal-flash backup. The next
investigation is offline analysis of the readback and EEPROM access options.

## Offline flash analysis (2026-11-17)

The user accepts that network settings can be restored and requested analysis of
existing flash backups. No device/network access was needed for this analysis.
`analyse_flash.py` validates the reference/candidate Intel HEX checksums and
compares both independent private readbacks before examining their contents.
The reproducible, secret-free report is saved privately as
`secrets/recovery/tftp-20261117T174934573218Z/analysis.json` (0600).

### Findings established from the bytes

| Region (byte addresses) | Observed interpretation |
| --- | --- |
| 0x00000–0x00003 | Reset GOTO 0x1DC00, entering bootloader |
| Below 0x1DBC0, excluding reset patch | Archived firmware-4 application plus erased gaps, exact match |
| 0x1DBC0–0x1DBC7 | Two GOTO instructions: original application entry 0x28 and fallback 0x4 |
| 0x1DBC8–0x1DBFF | Erased remainder of inferred jump-table reservation |
| 0x1DC00–0x1FBFF | Bootloader reservation; last non-FF byte is 0x1FB76 |
| 0x1FC00–0x1FFF7 | Erased space |
| 0x1FFF8–0x1FFFB | Four defined configuration bytes match archived firmware |

Only 0x00000 and 0x00002 differ among the archived HEX's 78794 defined bytes.
Those are the bootloader's reset-vector patch. Replacing the installed reset
instruction with the four bytes from its jump table, removing only the inferred
0x1DBC0–0x1FBFF bootloader/jump-table region, and filling omitted archived HEX
addresses with 0xFF yields **zero differences across all 131072 bytes**. Therefore
there are no unexplained application-image differences or additional nonblank
flash data outside the identified bootloader/jump-table region. This does not
identify every constant or instruction inside the bootloader itself.

The structure agrees with Microchip's documented bootloader layout and original
reset-vector relocation. Region boundaries are supported by the physical readback
and reference documentation, rather than merely inferred from an empty stock HEX.
Documentation: https://documentation.help/Microchip-TCP.IP-Stack/BootloaderDesign.html

Stored CONFIG1H has CP0=1 (not code-protected), consistent with successful TFTP
readback. Flash-stored configuration is being inspected here, not an independent
ICSP read of latched configuration registers. Device-family reference:
https://ww1.microchip.com/downloads/en/DeviceDoc/39762f.pdf (CONFIG1H, section 25).

### Candidate and recovery implications

The existing RX-only candidate defines no bytes in the observed bootloader/jump
reservation. Its broader exclusion of 0x1D000–0x1FFF7 is conservative and still
covers the observed region. Its four configuration bytes match this unit's
readback and its reset instruction is a PIC18 GOTO. These are static layout checks,
not proof of electrical behavior or bootloader write compatibility.

The archived vendor application HEX is an exact match for the application's bytes
once the bootloader reset patch is accounted for. It is therefore a strong stock
application restore candidate. The full raw flash.bin is a separate complete
readback containing both the patched reset vector and bootloader. It must not be
blindly used as a TFTP upload: the reference bootloader expects Intel HEX and
performs its own reset-vector relocation. A raw-flash-to-HEX conversion would also
include bootloader addresses and is not automatically a valid application upload.
No restore image was uploaded and no restore test was performed.

The RX profile deliberately omits RebootTask. If it were ever installed, TFTP
traffic to the running application would no longer provide the current reboot
entry path. Recovery entry by power-on and its window/IP behavior must be
established on this device before relying on Ethernet-only rollback. The reference
bootloader documents power-on entry, but the actual recovery write/erase paths and
power-failure behavior have not been validated or completely disassembled here.

Network settings are now treated as replaceable per the user's instruction. The
saved discovery record preserves the advertised device identity/secret. A full
EEPROM image would preserve any unknown remaining bytes, but its absence does not
prevent this offline analysis or invalidate the internal-flash backups. No EEPROM
writes, firmware flashing or RF transmission are authorized by this analysis.

Reproduce without contacting the TellStick:

```sh
python3.12 firmware-build/analyse_flash.py \
  secrets/recovery/tftp-20261117T174934573218Z/flash.bin \
  secrets/recovery/tftp-20261117T174949379573Z/flash.bin \
  --reference firmware-work/recovery-reference/tellstick_net_fw4.hex \
  --candidate firmware-work/build-readonly/TellStickNet-Lite.hex
```


## Power-on recovery-IP readback confirmed (2026-11-17)

The user configured temporary Argus address 192.168.97.149/24 on enp3s0 and
confirmed the TellStick's USB power was disconnected with Ethernet connected.
startup_readback.py was armed before the user was instructed to reconnect power.
It sent only TFTP RRQs to 192.168.97.60 and ACKs to that same recovery IP; it did
not send packets to the normal application IP. The client completed a 131072-byte
read, identical to both earlier internal-flash backups (SHA-256 unchanged).

Private record (0600 files, 0700 directory):
secrets/recovery/startup-tftp-20261117T180118524897Z/
Contains flash.bin and metadata.json. First data arrived 46.625 seconds after
arming; this includes the human delay before power-on and is not a measured boot
delay. 187 RRQs were sent while waiting. The startup script waited only at the
recovery IP, establishing access without the running application's RebootTask.
No TFTP write, erase, flash operation or RF command was sent.

This verifies power-on entry and GET readback at the documented recovery IP on
this unit with its current firmware. It does not test the bootloader's write
path, tolerance of interrupted writes, or recovery after particular image/config
changes. The matching candidate config and excluded boot region remain useful
static checks, not a restore guarantee. The next purely offline task is preparing
and validating an application-only rollback HEX; no flash approval follows from
this result. Temporary Argus IP cleanup requires the user's sudo access.


## Rollback preparation complete (2026-11-17)

Final private package: `secrets/recovery/rollback-20261117T180531730937Z/`.
All payload files are 0600; directory 0700 and excluded from Git. An earlier
intermediate package from this preparation remains privately under
rollback-20261117T180453285006Z; use the final package named above.

Contents include original stock firmware-4 application HEX; all three matching
full flash readbacks; startup-test metadata; freshly rebuilt RX-only HEX and link
map; compiler link log; candidate review; source hashes; offline analysis/verification
scripts; manifest and SHA256SUMS; and stepwise recovery instructions. No executable
firmware upload operation is included. The full flash BIN files are explicitly
marked as readbacks, not application-upload images.

Checks completed:

- Preserved PICC18 9.65 Lite compiler rebuilt RX candidate successfully. SHA-256 is
  still 983d53973f77b717e18daf7b425895883b59ed015b8cbb8fe4643c9cc6ccb7a5,
  reproducing the previous HEX exactly.
- 29 Python tests and 2 host C behavioral tests pass.
- Candidate source and final link map reviewed: EEPROM persistent-write, RF-send,
  command dispatch and remote-reboot functions absent; EEPROM read-address bus
  transactions are expected and do not constitute EEPROM memory programming.
- Candidate reserves boot/jump-table region and matches all four configuration
  bytes. Source uses DHCP and reads only six assumed MAC bytes from EEPROM.
- Stock HEX has no bootloader/jump-table bytes and exactly matches the backed-up
  application after normalizing bootloader reset relocation.
- Package verifier confirms all three backups match and all expected file hashes
  and static layout/function checks pass; an altered stock HEX in a temporary copy
  is rejected. SHA256SUMS verification passed for all packaged files.
- Original tellstick-net repository remains clean. No device/network test or
  device write was performed during this package preparation.

Warnings and limits are documented in candidate-review.txt and rx-link.log. The
legacy Ethernet boundary-expression warnings remain. TCPFindArrayEx has a local
buffer diagnostic around an integer-cast-pointer copy, but is absent from the
linked image; this does not validate every legacy stack routine. Lite optimization
limitations remain. No compiler warning was silently treated as hardware approval.

To recheck the final package offline:

```sh
python3.12 secrets/recovery/rollback-20261117T180531730937Z/verify_rollback.py
```

Preparation is complete; flashing remains unauthorized. Actual restore writes,
interrupted-write behavior, and candidate RF/electrical behavior are untested.
The fact that this static RX profile excludes intentional transmit code does not
constitute RF-test authorization or a guarantee of electrical silence. Network
settings are replaceable per the owner; saved discovery credentials remain private.


## Same-version stock restore test succeeded (2026-11-17)

After preparation, the user explicitly authorized the previously described stock
firmware-4 flash test and accepted testing despite the remaining uncertainty.
This superseded the earlier no-flash restriction only for this stock-to-stock test;
it did not authorize custom-firmware installation or RF commands.

`test_stock_restore.py --authorized-stock-restore` pins the stock image SHA-256,
validates the complete rollback package, verifies the exact firmware-4/MAC identity,
and requires a fresh full readback matching the prior backup before uploading.
It does not offer selection of a custom image. System curl 8.5.0 TFTP was first
checked against a temporary loopback receiver using the same public stock HEX;
octet mode without options delivered all 216740 bytes unchanged with a final ACK.

Actual device test:

- Initial discovery: original IP/MAC and firmware 4.
- Fresh before.bin: 131072 bytes, matching all earlier flash backups.
- Uploaded pinned stock-firmware-4.hex (216740 bytes) through TFTP in octet mode,
  with no options or automatic whole-transfer retries; curl return code 0.
- Normal firmware-4 discovery returned after the upload.
- Fresh after.bin: 131072 bytes, identical to before.bin, **zero differing bytes**.
  SHA-256 remains d7fc988322cf846851b88783e1db1ae8fc23081819fd4985fa15a137c9dd3d37.
- Final discovery returned at the original address with the original MAC and
  firmware 4. A separate private comparison of the whole discovery response with
  the original saved capture confirmed the advertised secret/identity unchanged.
  No credential was printed.

Private record: secrets/recovery/stock-restore-test-20261117T182158686174Z/
Contains before.bin, after.bin, metadata.json and upload-stderr.txt; files 0600,
directory 0700 and ignored by Git. The original rollback package remains unchanged
as a record of its pre-test preparation state; its old no-write-authorization
wording is historical and does not negate the subsequent explicit authorization.

The readback proves the entire internal flash, including bootloader and stored
configuration, matches its pre-test state. Full external EEPROM contents were not
read, but its advertised credential is unchanged. Cloud login/connection, scheduled
job execution and physical RF behavior were not exercised by this test; no RF
command was sent. The device is running stock firmware 4, not the RX candidate.

This establishes a successful stock application write/readback and normal startup
on this unit. It does not prove recovery from every custom-image failure or an
interrupted write. Any installation of the experimental RX image still requires
explicit authorization. No further firmware write was performed after the single
successful same-version transfer.


## RX test preparation after stock restore (2026-11-17)

Following the successful stock-to-stock test, the user requested trying the next
step. Work is proceeding toward the previously described receive-only X-RX1 test.
The temporary Argus recovery address is required before any new flash. A user
request is pending to add 192.168.97.149/24, since sudo needs their password.
No RX upload has been performed in this preparation stage.

`test_rx_firmware.py install` verifies the immutable package and pinned candidate,
requires recovery-address binding, confirms stock identity, and requires a fresh
full stock flash read matching the original backup before uploading X-RX1. After
upload it searches for the original MAC and X-RX1 by directed/broadcast discovery,
then sends only B:reglistener and listens for incoming events. Payloads, if any,
are private recovery files; only aggregate counts are printed. No RF-transmit
command is implemented. Listening alone cannot establish electrical silence.

`verify-startup` can be armed before a user power-cycle to read the new application
at 192.168.97.60 and compare full flash with an offline reconstruction of candidate
application plus unchanged bootloader/config and reset relocation. `rollback`
uses the same recovery read, checks boot/config, then restores the pinned stock
HEX and verifies readback against the original backup. No rollback or power-cycle
has been triggered automatically at this preparation stage. Both operations need
the temporary recovery IP and user cooperation for power-on entry.


## RX firmware installed; startup readback pending (2026-11-17)

After the user requested the next receive-only test and confirmed the temporary
recovery IP was configured, test_rx_firmware.py install ran. A fresh stock flash
read exactly matched the original backup before writing. The pinned RX candidate
HEX (SHA-256 983d53973f77b717e18daf7b425895883b59ed015b8cbb8fe4643c9cc6ccb7a5)
uploaded successfully: curl return code 0, all 190881 bytes transferred.
Discovery confirmed original MAC AC:CA:54:00:71:C2 and version X-RX1.

Initial discovery during DHCP negotiation used fallback 192.168.0.51. The first
45-second listener observation sent registration to that off-subnet address and
received zero events; it does not establish reception or registration success.
Later broadcast discovery confirmed DHCP address 192.168.1.193. A separate
listen_rx.py observation was therefore started at the assigned address. The
firmware has no listener ACK, so a sent registration alone is not confirmation.
No RF transmit command was sent.

Private installation record:
secrets/recovery/rx-test-install-20261117T182552009660Z/
Contains matching pre-write flash, upload stderr and metadata, permissions 0600.
The device is currently running experimental X-RX1, not stock firmware 4.
Post-install full flash comparison requires user-coordinated power-on recovery
because the RX profile intentionally omits the application reboot server. No
further firmware write is planned for that readback.


The repeat listener observation at assigned DHCP address 192.168.1.193 received
5 UDP event packets totaling 377 bytes in 45.11 seconds. This confirms successful
listener registration and event delivery on the physical RX firmware. Packet
contents are private under secrets/recovery/rx-listener-20261117T182745842286Z/;
only counts were printed. No RF-transmit command was sent. A user request is now
pending to disconnect USB power before arming a GET-only startup verification.


## RX power-on recovery verification succeeded (2026-11-17)

The user confirmed USB power was disconnected, then verify-startup was armed
before instructing them to reconnect it. The GET-only recovery read at
192.168.97.60 completed with 131072 bytes. The entire flash matches the offline
expected X-RX1 application image plus preserved bootloader/jump-table structure
and the validated reset-vector relocation. Bootloader and configuration bytes are
unchanged from the original stock backup. No upload was performed in this step.

Private record:
secrets/recovery/rx-test-verify-startup-20261117T183010783355Z/
Contains startup.bin (131072 bytes) and metadata.json, files 0600 and directory0700.
First data arrived 29.098 seconds after arming, including the user's power-on delay;
117 read requests were sent only to the recovery IP while waiting.

After this readback, discovery confirmed 192.168.1.193, original MAC
AC:CA:54:00:71:C2 and version X-RX1. Thus the physical device now has a verified
receive-only application, functioning local event delivery (five events observed
before this power-cycle), and independently accessible power-on recovery readback.
The active application is X-RX1, not stock firmware. Custom-to-stock rollback has
not been executed, although stock-to-stock write/readback previously succeeded
and the same bootloader/configuration survived RX installation unchanged. RF
transmission remains disabled in the RX profile and no RF command was sent.
No light-control or local-schedule functionality is provided by this RX image.
The earlier sections' pending/no-custom-flash statements are historical.


## Reusable Python listener and CLI verified (2026-11-17)

Added tellstick_local.listener with Event, decode_event and TellStickListener,
plus CLI monitor. Transport sends only discovery and exact B:reglistener after
requiring X-RX1 discovery. It filters sender IP, validates Data/RawData frames,
uses bounded observation deadlines and closes its socket. Event decoding allows
bounded raw-frame integers above 32 bits without broadening command encoding or
the default command decoder. Raw frames remain transport data; temperature,
humidity and named-device conversion are not implemented yet.

38 unit tests passed, including nine new listener/event cases. All five older
private observation frames now decode (three Oregon, two Fine Offset). A separate
30-second real CLI observation received four frames (three Oregon, one Fine Offset),
with zero malformed or unexpected-source packets. The CLI emitted NDJSON and summary
counts correctly. Private observation: secrets/recovery/cli-monitor-20261117T183500202682Z/,
events.ndjson and summary.json (0600), directory0700 and excluded from Git.
No firmware write, reboot, EEPROM write or RF transmit command was sent in this
monitor-development task. Device remains X-RX1 at its DHCP address 192.168.1.193.


## Authorized RF enablement prepared (2026-11-17)

The user explicitly authorized enabling RF. The controller's rf_authorized flag
records that authorization; rf_enabled remains false and the scheduler is held
until firmware/readback/control tests finish. The first requested receiver is
Hall uppe fönster, with ON selected from the preceding first-test question.

X-TX1 was built from a separate copy of verified RX source. It retains DHCP,
read-only EEPROM access (six MAC bytes), secret-free discovery, receiver event
support and the conservative 0x1D000–0x1FFF7 reservation. It does not restore
legacy send/configuration dispatch or the remote reboot task. New TX1 binary
requests carry bounded alternating pulse durations and a request nonce; TA1 ACK
reports firmware completion, not the physical receiver's state. TP1 is a separate
non-transmitting readiness probe. Source filtering accepts only Argus 192.168.1.149;
this is not cryptographic authentication. Firmware rejects malformed/boundedness
failures before touching RF pins, and caches sixteen completed request identities.
Client sends once: a missing final ACK is unknown and must not trigger blind replay.

Protocol implementation covers all 35 physical exported devices for ON/OFF and
all 14 dimmable devices for DIM. Comen house transform, 1-based exported units,
Arctech dimmer-ON workaround and pulse timing were independently compared with
original Telldus C++ encoders at commit 2598bbed16ffd701f2a07c99582f057a3decbaf3:
72 synthetic combinations matched. Host C tests cover malformed requests and
repeat suppression before simulated pin changes. 72 total unit tests pass.

Private pinned candidate:
secrets/recovery/tx-candidate-20261117T190811546969Z/firmware.hex
SHA-256 f9ed220b5cffca1e8ef34d8788a3e156b9b6b1f59eed17bbfcf53926deb95596.
Build: PICC18 9.65 Lite, 70717 program bytes, 2546 RAM bytes. Existing stack/Lite
warnings remain; bootloader reservation empty, config matches physical backup,
EEPROM-write and legacy command functions absent. Private candidate directory
includes map, source snapshots, validation and checksums, files0600/directory0700.

The user has been asked to disconnect USB power before arming the install GET.
No RF command or X-TX1 upload has yet occurred. test_tx_firmware.py implements
pinned install, full power-on readback verification and the single configured
physical test. Existing stock rollback tooling/package remains available and
unchanged. Controller support for manual ON/OFF/DIM and provider-based scheduled
commands is prepared but remains physically gated until setup is verified.


## X-TX1 installation succeeded; post-write verification pending (2026-11-17)

After the user confirmed USB power was disconnected, the authorized installer
was armed and the user was instructed to reconnect power. Recovery GET at
192.168.97.60 returned the exact verified X-RX1 image; bootloader/config matched
original backups. The pinned X-TX1 HEX then uploaded successfully (198973 bytes,
curl return 0). Normal discovery confirmed the original MAC and 192.168.1.193,
firmware X-TX1. TP1 non-transmitting readiness probe received the expected ACK.
No RF command was sent. Controller RF remains disabled and automations held.

Private record: secrets/recovery/tx-test-install-20261117T191003655327Z/.
Contains matching pre-write startup.bin, upload stderr and metadata; owner-only
files/directories, ignored by Git. Current device firmware is X-TX1. Full post-write
readback is not yet verified. User cooperation has been requested for a second
power-cycle to arm verify-startup before testing Hall uppe fönster ON.


## X-TX1 readback, physical RF and application path verified (2026-11-17)

User-coordinated power-on GET completed after X-TX1 installation:
secrets/recovery/tx-test-verify-startup-20261117T191203950993Z/.
The complete 131072-byte flash matches expected X-TX1 plus original bootloader and
configuration. Non-transmitting readiness probe acknowledged; original MAC/IP
returned, firmware X-TX1. No upload or RF command was sent during that readback.

The configured first RF command then sent Hall uppe fönster ON. Firmware completion
ACK was received, and the owner explicitly confirmed the lamp turned on. Private
record: secrets/recovery/tx-test-test-radio-20261117T191253328656Z/, with the physical
observation recorded. One subsequent ON request to the same already-on lamp through
POST /api/command exercised the persistent action queue and service RadioProvider;
its Activity row reached sent with a firmware ACK. No other manual test unit/action
was sent. ACKs do not independently establish physical receiver state.

RF is now enabled under the user's authorization, and the previously active 42
schedules are resumed. Next run at enablement: 2026-11-17 22:30 CET. The one imported
block-heater event remains disabled and needs a locally defined heating rule.
Service is active/enabled with lingering; scheduler heartbeat is current and
receiver is listening. All three imported sensors have fresh local readings.
72 unit tests pass. Dashboard shows enabled local RF controls, and Activity clearly
distinguishes transmission sent from receiver-state confirmation. No Telldus Live
connection or router setting change was introduced. Original firmware repository
remains clean; the old stock rollback package remains unchanged.

Current application provider uses local Comen/Arctech encoding for the exported
35 physical units and 14 dim-capable units, with group expansion on Argus. Original
Telldus C++ comparison matched 72 synthetic cases. Comen was observed physically;
other individual receivers/protocol modes have not all been tested in person.
This is an operational local RF controller, not an assertion of 100% recovery
under every power or hardware failure. Full raw flash snapshots remain private.
