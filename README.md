# TellStick Local

Python 3.12 local control for the original Telldus TellStick Net. Development lives
outside `/opt/tellstick/tellstick-net`; the original firmware source is unchanged.
The local application runs without Telldus Live and uses verified X-TX1 firmware.
Discovery and monitoring remain available independently; physical RF was explicitly
authorized and enabled after a successful observed lamp test.

Current hardware state (2026-11-17): X-TX1 installed; complete flash readback verified,
bootloader/configuration unchanged, power-on recovery confirmed. Stock firmware-4
restore was also tested successfully. See [recovery record](firmware-build/RECOVERY.md).
Earlier investigation sections record historical stages and their then-current limits.

## Local application and continuous scheduler

Open **http://127.0.0.1:8768/** on Argus. The enabled systemd user service
`tellstick-controller.service` runs across logout and reboot with lingering enabled.
All 40 devices/groups, 3 sensors, 46 schedules and the disabled event are imported.
The 42 active schedules are resumed with physical RF enabled; all three Fine Offset
sensors update locally. Manual ON/OFF and supported dimming are available in the UI.
RF acknowledgment confirms transmission, not the receiver's actual state. The
imported block-heater event still needs a locally defined rule before activation.
See [application operations and limitations](controller/README.md).
Private remote access is verified at **https://argus.tail265095.ts.net:8443/**
with Tailscale connected. Surveillance retains its existing HTTPS port443 mapping.
Setup and service operations are documented in the application guide.

## Run

From `/opt/tellstick/tellstick-local`:

```sh
python3.12 -m tellstick_local discover --bind 192.168.1.149
python3.12 -m tellstick_local status --target 192.168.1.193 --json
python3.12 -m tellstick_local discover --target 255.255.255.255
python3.12 -m unittest discover -s tests -v
```

No installation is needed. Optionally create a venv and `pip install -e .` to
install the `tellstick-local` console command. Core discovery/protocol/monitor tests use the standard library. Photo-upload tests
require Pillow; export tests use the optional export dependencies.
`--bind` selects a local IPv4 address (Argus's address on enp3s0), not an interface name.
Default discovery is unicast to 192.168.1.193; broadcast must be selected explicitly.
The timeout defaults to three seconds. Discovery collects replies until that deadline.
Exit codes: 0 = device found, 1 = no reply, 2 = argument or network error.
No reply means unknown status, not proof the device is offline. Check local UDP
access, address binding, and the network interface if discovery fails.

`status` performs discovery and reports reachability, MAC, and firmware version.
It cannot report RF state, device state, uptime, or cloud connectivity.

Library usage:

```python
from tellstick_local import TellStickClient

for device in TellStickClient(bind_address="192.168.1.149").discover():
    print(device.ip, device.mac, device.firmware_version)
```

Discovery packets contain a sensitive secret on the wire. The parser validates
and discards that field; returned objects, CLI output, and JSON contain only public
metadata. No packet logging or storage is implemented. Do not capture discovery
traffic, log raw packets, or add real discovery packets to fixtures. Test packets
contain only a synthetic token. Parsing necessarily handles the packet transiently
in process memory; Python does not guarantee secure memory erasure.

## Protocol investigation

This section records the initial stock-firmware investigation. Current X-RX1
monitoring support is documented under Receive-only event monitoring below;
earlier statements that commands had not been sent describe that historical stage.

Evidence: read-only inspection of `firmware/discovery.c`, `localaccess.c`,
`tellsticknet.c`, `livemessage.c`, `common.h`, and `client/send.py` in the original
firmware repository. Missing cmake/rf/tcpip submodules prevent a complete firmware
build or inspection of the underlying network stack.

### Discovery

Send exactly ASCII `D` to UDP port 30303. The source reads the first character
and ignores the remainder. The response is
`TellStickNet:<12 hexadecimal MAC digits>:<secret>:<firmware_version>`.
MAC digits have no separators on the wire. `common.h` allocates 11 bytes for the
secret, including its terminator. No assumption that firmware must be `X` is made.
The parser requires a nonempty printable secret and a bounded version identifier;
malformed packets are ignored with no raw packet in errors.

The firmware changes its reply destination to the sender and uses the request
source port. The client binds an ephemeral port and accepts replies from port
30303; for unicast, the sender IP must also match. Broadcast replies are deduplicated
by IP and MAC. Discovery is unauthenticated, so replies are claims, not identity proofs.

Live read-only verification on 2026-11-16: 192.168.1.193 responded with MAC
AC:CA:54:00:71:C2 and firmware **4**. This verified ephemeral-port discovery on the
installed firmware. The checked-in `common.h` defines firmware **X** and the Python 2
example insists on X. The installed command behavior has not been verified.

### Local messages and authentication

`localaccess.c` listens on UDP 42314. It clears the message buffer, appends the
received bytes with `LMAppendChar`, and calls `handleMessage()` directly.
There is no secret, challenge, or signature check on this source path.
`livemessage.c` also implements signed framing through `LMParseChar`, but the local
UDP handler does not call that parser. The original Python 2 send example also
sends a plain local message without the discovery secret.

Therefore local RF control requires **no authentication in the inspected source**.
Firmware 4 could differ; this remains unverified on the physical device because
no RF commands or other commands to 42314 were sent.

Local message strings are `<hex byte length>:<ASCII text>`, unsigned integers are
`i<hex value>s`, and flat hashes are `h<key><value>...s`. A command string may be
followed by a hash. Lengths and numbers are hexadecimal, including lengths above 9.
The firmware message buffer is 200 bytes; the offline codec limits messages to
199 bytes for the NUL terminator. It supports strings, unsigned 32-bit integers,
and flat hashes, and rejects malformed/trailing data. This is a strict supported
subset, not an emulation of the firmware's permissive parser.

`tellstick_local.protocol.encode_message` and `decode_message` are offline helpers
with independent wire-format unit tests. They do not send anything. There is no
local-command transport or RF option in this implementation.

### Commands found in tellsticknet.c

| Command | Behavior in inspected source |
| --- | --- |
| `reglistener` | Registers one local recipient for messages; changes listener state. |
| `send` | Transmits RF. Supports arctech/selflearning via `protocol` and `model`, or a raw `S` packet with optional `P` pause and `R` repeats. |
| `setip` | Sets IP, netmask, gateway and DNS values, or enables DHCP for IP 0xFFFFFFFF. |
| `saveip` | Persists network settings to EEPROM and resets. |
| `disconnect` | Resets the device. |

There is no status command in this handler. None of these commands is used by
this project. RF transmission must receive explicit authorization before any
future network implementation or hardware test sends `send` messages. The original
Python 2 example must not be run: it automatically transmits after discovery.

Tests cover discovery wire bytes, response validation and redaction, unexpected
senders, malformed replies, timeout handling, deduplication, CLI output, unknown
firmware versions, and offline message encoding/decoding and bounds. Unit tests
use mocked sockets and never contact hardware.

## Firmware 4 follow-up investigation (2026-11-16)

**Discovery support is confirmed; stock firmware 4 local RF control is not.**
The public repository must not be treated as a source-identical copy of the
installed firmware. Telldus's [local-access announcement](https://developer.telldus.com/blog/2012/03/02/help-us-develop-local-access-using-tellstick-net-build-your-own-firmware)
describes a separate custom firmware for local access and originally directs users
to branch `t114`. Its author later links the GitHub repository in the comments.
This explains why the client deliberately selects firmware X. It is evidence of
a distinct firmware lineage, not proof that stock firmware 4 lacks every local command.

The local checkout is not shallow and contains no tags. Its initial import
`a04e7db` already defines version X; searching available history found no definition
of firmware version 4. Local send/dispatch appeared in February/March 2012;
native Arctech selflearning was added in November 2013 (`c63cef7`), and listener
registration in January 2014 (`8d5657d`). These dates describe the public source,
not installed firmware 4's feature set. Telldus's [firmware changelog](https://developer.telldus.com/wiki/FirmwareVersion)
identifies version 4 as a past stable TellStick Net release but does not establish
support for the local send interface. Its newer Net v2/ZNet local API documentation
must not be applied to this original Net hardware.

Additional source details useful for a future authorized test:

- `transmit_arctech.c` emits 26 house bits, four unit bits, and a zero group bit.
  A future native encoder should validate house 0..67108863 and unit 0..15 rather
  than silently accepting truncation. The on bit is set only for `method == 1`;
  every other value emits off. The Python 2 example describes turning on but uses
  method 2, so its label is inconsistent with the implementation.
- The native selflearning path uses fixed defaults of ten repeats and 11 ms pause.
  Although `send()` parses `P` and `R`, these are applied only to the raw `S` path.
  Native dispatch supports exactly `arctech` / `selflearning`; no native dim or
  group command is implemented in this source.
- `send()` provides no application acknowledgement. A successful UDP `sendto`
  would not establish that the firmware accepted the command or transmitted RF.
- Discovery is a separate task and port. Its success says nothing about whether
  42314 has a listener. An empty or malformed UDP probe has no defined response;
  silence cannot distinguish an unsupported command from a dropped packet.
- Listener registration changes device state and has no acknowledgement in this
  source. A received event after registration could provide positive evidence of
  part of the local interface, but absence of events would remain inconclusive.
  No listener registration, reset, configuration, malformed-packet probing, or RF
  transmission was performed during this investigation.

Within the current no-flash/no-DNS constraints, the remaining options are to find
an authentic stock version-4 image for offline comparison of its UDP dispatch,
or perform a separately authorized, tightly scoped hardware test. No authentic
version-4 image was obtained or analysed in this investigation. A future RF test
needs the receiver model, an existing house/unit code, an explicitly chosen
ON/OFF action, and explicit authorization. Do not assume that changing the client's
firmware filter from X to 4 makes the installed device compatible.

## Archived stock firmware-4 image inspection (2026-11-16)

An image was subsequently retrieved from the Internet Archive's capture of the
historical official download host:

- Original URL: `http://download.telldus.com:80/TellStick/Software/firmware/old/tellstick_net_fw4.hex`
- [Archived image, captured 2015-04-19 13:34:18 UTC](https://web.archive.org/web/20150419133418id_/http://download.telldus.com:80/TellStick/Software/firmware/old/tellstick_net_fw4.hex)
- HEX SHA-256: `ba103630c1048178c59c8253a9e510ab3ac565c6ecf592b78aeb78fefacd8a90`
- HEX size: 216740 bytes; 78794 defined firmware bytes; highest defined address: `0x1fffb`.
- All Intel HEX record lengths and checksums validated; an EOF record was present
  and no conflicting byte definitions were found.
- Analysis binary fills undefined addresses with 0xFF through `0x1fffb`.
  SHA-256: `e4aac301c4fe61760a36013276702a0b3c18d0eb4278b3268323eae6de6fe938`.

This is historical official-host provenance via an archive, not a signed vendor
attestation. HEX checksums detect record corruption, not malicious modification.
It is not a readback of the installed device. Downloads and the analysis binary
remain in `/tmp`; nothing was executed, uploaded, or committed as a firmware asset.
The root firmware directory and root firmware-4 HEX/flasher guesses returned 404
over HTTP; the download host's HTTPS certificate failed hostname validation.
Certificate verification was not bypassed. Archive indexing revealed the `old/`
path, which was missed in the initial exact-URL search.

### Static evidence

| Indicator | Firmware byte address / result |
| --- | --- |
| `TellStickNet:` | 0xff24 |
| `selflearning` | 0xff32 |
| `disconnect` | 0xff57 |
| `arctech` | 0xff90 |
| `send` | 0xffcb |
| `api.telldus.com` | 0x10000 |
| `reglistener`, `setip`, `saveip` | Not found as contiguous ASCII strings |

The presence of `send` and Arctech strings does **not** establish local control:
stock firmware needs RF sending for cloud-delivered commands too. `secret`, `sha1`,
and signed-message framing marker `28:` are also present; their presence does not
establish which ingress paths authenticate messages.

An instruction-aligned scan for nearby PIC18 `MOVLW` instructions loading the two
port bytes found repeated 30303 (`0x765f`) candidates at 0x1a888/0x1a890 and
0x1a896/0x1a89e. It found no equivalent nearby literal-load pair for 42314
(`0xa54a`), nor a contiguous little-endian 42314 value. Candidate string-address
loads reference the discovery marker near 0x1a9b8 and send/disconnect near
0x3a72/0x3ab2. These are heuristic reference candidates, not a recovered call graph.
Compiler optimizations or other port-construction sequences can evade this scan.

**Assessment:** evidence now leans toward stock firmware 4 lacking the public
custom firmware's UDP-42314 handler. This remains an inference, not a proven
absence. Discovery is supported independently. No claim that stock local RF works,
or that it requires no authentication, can be made from these strings alone.

A stronger answer requires PIC18 disassembly and tracing UDP socket setup through
to the send command dispatcher. A general-purpose `objdump` is installed here but
no `gpdasm`/PIC18-specific disassembler was found. No such call-graph analysis has
yet been completed. All investigation in this section was offline; no packets
were sent to the TellStick.

## Stock-firmware server emulation: preferred investigation path

The project direction is now to replace the server used by stock firmware, rather
than assume the separate custom-firmware UDP interface is available. No firmware
change is required by this architecture. It is documented historically in
[Telldus's Java page](https://developer.telldus.com/wiki/Java) and in a
[first-hand server proof of concept](https://forum.telldus.com/viewtopic.php?p=19078).
These are historical compatibility evidence, not a hardware test of our unit.

### Connection sequence and services

1. TellStick obtains its address, gateway and DNS configuration by DHCP.
2. It resolves `api.telldus.com` and requests `/server/assign` over plain HTTP.
   The archived firmware contains `/server/assign?embedded=1&protocolVersion=2`,
   so the HTTP handler must tolerate query parameters.
3. The historical assignment response is `11:local.telldus.comiAFCAs`:
   0x11 is the hostname byte length (17), and 0xAFCA is TCP port 45002.
4. It resolves `local.telldus.com` and opens an outbound TCP connection to that
   server. On the existing LAN both DNS names would resolve to 192.168.1.149.
5. The replacement server handles registration, keepalives, and incoming events.
   Future RF control uses that connection, subject to verifying command signing
   and acknowledgement behavior.

Required components on Argus are a narrowly configured DNS resolver, assignment
HTTP endpoint on TCP 80, and device-protocol TCP listener on 45002. Router DNS need
not change **if the TellStick can be made to use Argus as its DNS server by another
means**. The five-letter host `local` is retained for initial compatibility because
historical documentation explicitly requires that length; whether firmware 4
actually requires it is unverified. A numeric-IP assignment should not be assumed
to work without checking its parser.

### What the historical implementation establishes

The published VB.NET proof of concept listens on TCP 45002, replies to registration,
answers keepalive pings, and displays received transmitter data. A later example
on the same thread also proxies to Telldus Live; that cloud-proxy variant is outside
this project's scope. The standalone example is evidence that a receive-only
replacement server is feasible without flashing firmware.

The example contains signed-message-looking frames starting `28:` followed by a
40-character digest, another hexadecimal length, and a payload. It uses a fixed
pong response and a special registration response. These details require
verification against stock firmware before implementation. TCP reads can split
or combine frames, so the example's assumption that a single read is a message
must not be copied. A new server must parse a bounded byte stream incrementally.

Authentication conclusions about UDP 42314 do **not** apply to this TCP path.
Successful registration and keepalive would prove only that session establishment
works. It would not prove we can generate accepted RF commands. Remaining work
includes recovering the stock framing/signature rules, distinguishing incoming
and outgoing authentication, handling acknowledgements, and identifying command
payloads. No device secret may appear in diagnostics or persisted registration
packets. Never copy the example's raw registration logging.

The reviewed `molobrakos/tellsticknet` Python project is a UDP-42314 client with
`reglistener`, not this TCP server emulator. Its README's local-access language
must not be used as evidence for a stock-firmware TCP implementation. Its source
was read in `/tmp`, not installed or executed.

### Router-DNS-free deployment choices

| Choice | Feasibility and limitation |
| --- | --- |
| Isolated Ethernet segment behind Argus | Best isolation. Argus serves DHCP/DNS only on that segment plus HTTP/TCP locally. Usually needs a second physical Ethernet adapter or an appropriately isolated VLAN. TellStick may receive a different IP. No Telldus Live access or router DNS changes are needed. |
| Per-device DHCP DNS option | If the existing DHCP server supports it, supply Argus as DNS only to this TellStick. This changes DHCP configuration, not global router DNS, but support and authorization must be established. No such change has been made. |
| Existing dedicated DNS resolver | A client-specific override can work if the TellStick already uses that resolver. No such resolver has been identified. |
| Argus `/etc/hosts` or its own DNS settings | Insufficient: these do not affect DNS lookups made by the TellStick. |
| Host firewall redirect on Argus alone | Insufficient on a normal switched LAN: the TellStick's traffic does not traverse Argus. It becomes relevant only if Argus is deliberately placed in the path. |

Do not start a competing DHCP server on shared `enp3s0`. Do not use ARP spoofing,
unsolicited DHCP replies, broad DNS interception, or change router settings as an
implicit implementation step. No network configuration or running service was
changed during this investigation. The only identified interface in the supplied
environment is enp3s0; access to live interface/routing details was sandbox-restricted,
so a second adapter or existing isolated segment has not been verified.

### Concrete next implementation scope

Build and test an offline, bounded TCP-frame parser using synthetic registration,
ping, and sensor frames; keep registration content transient and diagnostics limited
to message type and public metadata. Then implement a standalone receive-only
session handler and assignment endpoint, initially tested on loopback. Do not
include cloud forwarding or an RF-send API in that first server. Before connecting
the hardware, select an isolated segment or an explicitly agreed per-device DNS
configuration. Confirm firmware 4 registration/keepalive compatibility there before
planning an explicitly authorized RF transmission.

## Router DNS permission update

On 2026-11-16 the user authorized changing router DNS settings (reported firmware:
Telia Mint 17.2). This supersedes the earlier no-router-DNS restriction above.
See [deployment preparation](deploy/README.md) for the staged, syntax-checked
DNS configuration, assignment response, current host observations, rollout order,
and rollback. No router or system DNS settings have been changed. RF transmission
still requires explicit authorization.

## Custom firmware path resumed

Server emulation and router changes are paused at the user's request. Custom
firmware investigation and build preparation are authorized; hardware flashing
and RF transmission are not. See [firmware build preparation](firmware-build/README.md)
for recovered exact CMake/RF dependencies, the isolated source tree, compiler/TCPIP
blockers, and the required no-flash build settings.

## Lite firmware build available

On 2026-11-17 PICC18 9.65 Lite under Wine successfully compiled and linked the
isolated local firmware using a reconstructed Microchip TCP/IP v5.42 dependency.
Program usage is 55.8%; RAM usage is 56.5%. See the latest section of
[firmware build preparation](firmware-build/README.md) for the compatibility patch,
HEX/map outputs, validation, and limitations. The image is not ready to flash;
no firmware upload or RF transmission has occurred.


## Receive-only event monitoring (X-RX1 / X-TX1)

```sh
python3.12 -m tellstick_local monitor --bind 192.168.1.149 --duration 60
python3.12 -m tellstick_local monitor --bind 192.168.1.149 --duration 60 --json
```

The monitor first discovers the selected unicast device and requires version
X-RX1 or X-TX1. It then sends exactly `B:reglistener` to UDP42314 and receives on the same
host UDP socket. The firmware supports one listener: another monitor or diagnostic
listener replaces the previous registration. Closing the monitor closes its host
socket; firmware offers no unregister or registration acknowledgment. No received
events in a time window does not prove registration failed. Allow DHCP to settle
after startup; an early broadcast response can use fallback 192.168.0.51 before
192.168.1.193 is assigned.

Text output shows UTC receipt time, event kind and decoded fields. `--json` emits
one JSON object per event (NDJSON); summary counts go to stderr. Receipt time is
the Argus reception time, not a sensor's own timestamp. Ctrl-C closes the socket
and exits 130. Other monitor exits: 0 = observation completed, including zero
events; 2 = invalid configuration, missing X-RX1 or network error.

Only Data/RawData flat-hash messages from the selected device IP are accepted;
malformed frames and unexpected senders are counted without logging payloads.
The protocol is unauthenticated and UDP may duplicate/drop packets. Repeated RF
frames are kept rather than deduplicated, so packet counts are not unique-device
counts. Event fields can include RF identifiers and measurements: CLI output is
intentional, but the library/CLI writes no files unless the caller redirects it.
Discovery secrets remain discarded and are never included in events. Prefer
private output files if recording home-device data.

RawData can contain more than 32 bits. The event decoder accepts at most 128 hex
digits within the firmware's overall 199-byte message limit and uses Python
arbitrary-precision integers. The command codec's default integer limit remains
32 bits, and its encoder/decoder do not transmit. JSON consumers must support large
integers (JavaScript Number alone cannot preserve every raw frame). RawData fields
are transport-decoded RF frames, not yet converted into temperature/humidity or
mapped to named Telldus devices. Those interpretations are a subsequent step.

```python
from tellstick_local import TellStickListener

with TellStickListener(bind_address="192.168.1.149") as listener:
    for event in listener.events(duration=60):
        print(event.received_at, event.kind, event.fields)
```

`decode_event(packet, device_ip)` also decodes an offline event without opening a
socket. Synthetic test fixtures cover wide raw frames, command rejection, malformed
frames, sender filtering, exact registration bytes, finite timeout, stock-firmware
refusal, socket cleanup, and NDJSON output. Real saved frames decoded as Oregon
and Fine Offset; private captures are excluded from Git.


Live monitor verification on 2026-11-17: a 30-second CLI observation received and
decoded four RawData events (one Fine Offset, three Oregon), with zero malformed
or unexpected-source packets. The observation sent only discovery and listener
registration. All 38 unit tests passed. No firmware change or RF transmission was
performed while adding this monitor.


Controller validation (2026-11-17): 60 tests passed. Headless Firefox verified
record loading, device editing and event creation on an isolated test database,
plus the production dashboard and responsive layout. The active service has all
three Fine Offset sensors updating locally, 42 active schedules with next runs,
and daily private SQLite backups. Physical RF control remains blocked pending
transmit-capable firmware and explicit RF authorization.


## RF enablement verified (2026-11-17)

X-TX1 was subsequently installed with explicit authorization. Its complete readback
matched the prepared image and retained the original bootloader/configuration. The
owner confirmed Hall uppe fönster turned ON; the application queue/worker RF path
also completed successfully. Physical controls and the 42 active schedules are now
enabled. 72 unit tests pass; encoders were additionally compared against the pinned
original C++ implementation in 72 synthetic cases. Earlier RF-disabled notes above
refer to the preparation stages, not the current service state.


Direct home-LAN dashboard access is enabled at **http://tellstick.local/** through
a dedicated systemd proxy and persistent Avahi mDNS announcement. Argus resolution,
HTTP/API access, and Origin/CSRF validation are verified; phone testing is pending.
No per-device DNS or router DNS/IPv6 changes are required. See
[LAN access instructions](controller/LAN-ACCESS.md). Direct IP access remains
http://192.168.1.149/. Tailscale and surveillance configuration are unchanged.
