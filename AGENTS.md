# TellStick Local — guidance for agents

This file records project context, operating constraints, architecture and recovery
knowledge. Last checked on **2026-11-19**. Runtime state and user instructions take
precedence over dated observations here. Preserve user changes in the database.

## Purpose and environment

Build and maintain a completely local controller for an original Telldus TellStick
Net: devices/groups, RF control, sensor reception/history, schedules and events.
Normal operation must not depend on Telldus Live or an external hosted application.

- Host: **argus**, Ubuntu 24.04, Python **3.12**, user `jimmy`.
- Working repository: `/opt/tellstick/tellstick-local`.
- Original firmware checkout: `/opt/tellstick/tellstick-net`.
- Network interface: `enp3s0`; home subnet: `192.168.1.0/24`.
- Argus: **192.168.1.149**, Ethernet MAC **1c:69:7a:f0:06:a2**.
- TellStick: **192.168.1.193**, MAC **AC:CA:54:00:71:C2**.
- Router/gateway: **192.168.1.1**, Telia Technicolor **TG799vn v2**, Mint 17.2.
- Home time zone: **Europe/Stockholm**. Schedule evaluation must respect it.
- Reserve the existing LAN addresses. A DHCP-managed interface can still correctly
  show `dynamic` while using a router reservation; verify reservations when needed.

## Operating rules and authorization

- Keep development outside the original firmware repository. Its source remains
  unchanged; firmware patches and new code belong in this repository.
- RF control was explicitly authorized and enabled after verified firmware and an
  observed lamp test. Normal user-requested controls and enabled automations are
  authorized; do not disable them merely because old documentation says RF was
  unauthorized. Do not send extra RF commands as routine testing of unrelated work.
- The confirmed first receiver was **Hall uppe fönster**, ON. The owner observed it
  turn on. A subsequent ON through the application queue received a firmware ACK.
  This does not establish physical testing of every other receiver or dimmer.
- Prior flash authorization covered the coordinated tests already performed. Do
  not treat it as permission for arbitrary new firmware uploads. For a new flash,
  obtain authorization for the concrete image/test and review recovery first.
- Never flash as part of a build, unit test, web UI update, or speculative probe.
  Do not promise 100% recoverability, including interrupted-write recovery.
- Do not reset, power-cycle, or reboot the TellStick or router unexpectedly. Recovery
  tests require coordinated power handling; keep Ethernet connected when requested.
- Router DNS changes were authorized during earlier investigation, but the current
  solution does not need them. Do not silently change household DNS, IPv6, DHCP,
  firewall rules, Tailscale routes, or the unrelated surveillance application.
- Prefer reversible changes and local standard-library implementations. Do not add
  cloud dependencies, public hosting, port forwarding, or Tailscale Funnel.
- `sudo` requires the user's password. Prepare and validate concrete files before
  asking the user to execute an administrator command. Execution escalation is not
  root access. Do not request passwords or put them in commands.
- Respect any current sandbox and Git-index permissions. Do not overwrite unrelated
  edits, reset the working tree, or make a commit unless asked.

## Secrets and private files

Never print, log, commit, paste into fixtures, or embed device secrets, OAuth keys
or tokens, compiler licence keys, raw discovery responses, or private exports in
public documentation. No real credentials belong in this file.

- `secrets/` is Git-ignored. Private directories use **0700**, files **0600**.
  These files are plaintext protected by permissions, not encrypted.
- The owner explicitly allowed private local recovery backups and access to device
  secrets for recovery. This does not authorize publishing them or general-purpose
  credential persistence. Keep credentials transient outside approved private data.
- Production database: `secrets/controller/controller.sqlite` (SQLite WAL).
  Backups: `secrets/controller/backups/`; `Store.backup()` uses the SQLite backup
  API and retains seven `auto-*.sqlite` snapshots. Preserve manual recovery backups.
- Complete account configuration export:
  `secrets/recovery/telldus-account-20261117T163843Z.json`.
  It includes RF device parameters, sensors, schedules and events, not account
  billing/profile data or downloaded historical sensor/activity data.
- Initial private discovery capture:
  `secrets/recovery/20261117T154111596804Z/discovery-response.bin`.
  It contains the stock discovery secret; do not display its contents. This is not
  a full EEPROM backup or a flashable image.
- Private firmware images, flash readbacks, recovery reports, board photos, upload
  session URLs and browser screenshots are under `secrets/`. Consult the recovery
  inventory rather than dumping entire directories or private JSON to tool output.
- `firmware-work/` is ignored and includes generated sources, vendor dependencies,
  compiler/Wine installations and possibly activation data. Do not force-add it.
- `*.obj` is ignored. The stray root `l.obj` was untracked while retaining the local
  copy; it is a generated compiler artifact, not required source or final firmware.
- Avoid raw network captures of discovery traffic. Stock discovery puts the secret
  on the wire. Do not run the original `client/send.py` as a harmless example: it
  can transmit RF. Do not enable generic request logging for credential-bearing URLs.

## Repository map

| Path | Responsibility |
| --- | --- |
| `tellstick_local/discovery.py`, `protocol.py` | UDP discovery and safe message parsing |
| `tellstick_local/listener.py` | Local event listener and source validation |
| `tellstick_local/transmit.py` | RF encoders, binary transport, readiness/ACK handling |
| `tellstick_local/__main__.py` | Discovery, status and monitoring CLI |
| `controller/core.py` | SQLite Store, schedule calculations, Engine, persistent actions, dashboard preferences/history |
| `controller/server.py` | Loopback HTTP API, static UI, scheduler/receiver threads, access checks |
| `controller/receiver.py` | Fine Offset decode, local ingestion, sensor-history backfill |
| `controller/radio.py` | Production RadioProvider and persisted RF gates |
| `controller/static/` | Buildless HTML/CSS/JavaScript; no external assets or chart CDN |
| `controller/service/` | User/system units and administrator installers |
| `tests/` | Mocked/offline Python tests and firmware C harness tests |
| `firmware-build/` | Tracked patches, build/preparation/validation/recovery tools and TX source overlay |
| `firmware-work/` | Ignored vendor trees, generated sources, build outputs and Wine prefix |
| `scripts/` | Historical read-only account exporter and audit tools |
| `photo-upload/` | Temporary private board-photo uploader; not the dashboard |
| `deploy/` | Historical cloud-redirection experiment; not current deployment |

Key references: `controller/README.md`, `controller/LAN-ACCESS.md`,
`firmware-build/README.md`, `firmware-build/RECOVERY.md`, `scripts/EXPORT.md`.
Several documents are chronological logs. Read their later sections before relying
on early claims such as stock firmware, receive-only operation, or no flash backup.
`firmware-build/dependencies.json` also contains historical build validation flags;
those do not override the subsequently verified X-TX1 installation.

## Live application and services

Verified on 2026-11-19:

- User `tellstick-controller.service`: enabled, active, with `Linger=yes`.
- User `tellstick-dashboard-mdns.service`: enabled and active.
- System `tellstick-dashboard-lan.socket` and its proxy service: active.
- Experimental system `tellstick-local-dns.service`: **disabled and inactive**.
- Firmware mode `X-TX1`; RF and scheduler enabled; receiver listening.
- **40** devices/groups, **3** sensors, **47** schedules (**43** active), **1** event,
  and **5** selected Dashboard tiles (subsequently assigned to **Jimmy**). These counts are observations, not invariants.
  The original import had 46 schedules, 42 active. Do not revert user additions.
- The imported block-heater event was left disabled pending an explicit local rule.
  Do not approximate its heating behavior or silently activate unsupported triggers.

User units in `/home/jimmy/.config/systemd/user/` link to source units in
`controller/service/`. The backend binds **127.0.0.1:8768**. Its systemd user service
runs the continuous scheduler and receiver independently of browser connections.
Do not start another controller against the production database; a process lock
also protects it. Never use production for destructive QA or synthetic readings.

Useful operations, from this repository:

```sh
systemctl --user status tellstick-controller.service tellstick-dashboard-mdns.service
systemctl --user restart tellstick-controller.service
journalctl --user -u tellstick-controller.service -n 30 --no-pager
systemctl status tellstick-dashboard-lan.socket tellstick-dashboard-lan.service
avahi-resolve-host-name -4 tellstick.local
curl --noproxy '*' http://127.0.0.1:8768/api/health
```

Before restarting for backend changes, make a consistent private SQLite backup and
check that no RF action is currently running. Do not replay an uncertain action.
Static assets are served directly from disk; a frontend-only fix needs a browser
reload, not a controller restart or scheduler interruption. System units installed
by the root installers are copies; changing their source files alone does not
update the installed copies. User unit changes require `daemon-reload`.

## LAN, mDNS and remote access

- Preferred home URL: **http://tellstick.local/**. The owner confirmed it works on
  Android. Avahi publishes an IPv4 A record for `192.168.1.149` with
  `avahi-publish-address --no-fail --no-reverse`; it does not rename Argus or replace
  its reverse record. Apple platforms support Bonjour; iPhone behavior was discussed
  but has not been independently observed in this project.
- Direct LAN: **http://192.168.1.149/** and port **8768**.
- Root LAN socket listens only on `192.168.1.149:80` and `:8768`, forwarding through
  `systemd-socket-proxyd` to `127.0.0.1:8768`. It uses FreeBind, DynamicUser and IP
  restrictions for loopback and `192.168.1.0/24`. Installer:
  `sudo /opt/tellstick/tellstick-local/controller/service/install-lan-access.sh`.
- Guest/client-isolated Wi-Fi can block mDNS or LAN access. `.local` discovery is
  local-link traffic; it is not the name used for remote access.
- Private remote dashboard: **https://argus.tail265095.ts.net:8443/** via Tailscale
  Serve to `127.0.0.1:8768`. Argus's observed tailnet IPv4 is `100.72.141.23`;
  verify current state instead of treating tailnet addresses as LAN addresses.
- Existing surveillance stays at **https://argus.tail265095.ts.net/** on **443**,
  proxying to `127.0.0.1:8766`. Never run `tailscale serve reset` or replace this
  mapping to install the dashboard. Dashboard Serve command used previously:
  `sudo tailscale serve --bg --https=8443 http://127.0.0.1:8768`.
- No public Funnel or WAN port forwarding is part of the setup. HTTPS/API tests
  from Argus succeeded; do not claim a mobile-data test without user confirmation.
- Preserve exact Host, Origin and CSRF checks. Trust only explicit configured HTTP
  LAN origins and the private HTTPS origin. Arbitrary forwarded headers/wildcards
  are not trusted. A proxy must preserve the expected Host and Origin behavior.

### Why the DNS experiment was abandoned

The router cannot expose static aliases or independent IPv6 DNS controls. It
advertises IPv6 DNS **fd1a:eac1:701::1**, which returned NXDOMAIN for `tellstick.lan`.
Android could use it despite manually setting IPv4 DNS to Argus. Temporarily
turning router IPv6 off made both `tellstick` and `tellstick.lan` work. The user then
restored router IPv6 and phone DHCP/previous settings. mDNS solved naming without
making Argus the household resolver or disabling IPv6.

The separate `tellstick-local-dns.service` and `/etc/tellstick-local-dns.conf` remain
installed but are now disabled/inactive. Their staged source remains under
`controller/service/`. Do not re-enable them as a dependency of `tellstick.local`.
The config forwards `.lan` queries to the router and public queries to explicit
upstreams; pointing the router's upstream DNS back at Argus could create a loop.
Normal `systemd-resolved` loopback DNS is separate and must not be disabled.
The old `deploy/dnsmasq-tellstick.conf` redirects Telldus domains: **do not install
it** as the dashboard DNS config. That cloud-server emulation path was abandoned.

### Changing Argus's LAN IP

This is not currently automatic. Update all dependencies deliberately:

1. X-TX1 firmware's source allowlist in `firmware-build/tx-profile/localaccess.c`
   hardcodes `192.168.1.149`; changing it requires a separately authorized firmware
   build/flash/recovery procedure. Updating Python alone cannot fix the allowlist.
2. Controller database `bind` setting and host transport defaults/configuration.
3. Root LAN listener addresses, subnet restrictions if changing subnet, and exact
   trusted LAN origins in the user controller unit.
4. mDNS publisher address and any retained experimental DNS config.
5. DHCP reservations and relevant documentation. Preserve unrelated network services.

## Dashboard behavior to preserve

- Default **Dashboard** tab contains an ordered selection of device/group and sensor
  tiles. **Customize dashboard** adds/removes items; up/down buttons set their order.
  Each named user has a separate selection/order in `dashboard_profiles`, shared
  only with clients choosing that name, and persistent across restarts. Names are
  entered without passwords, case-insensitive and whitespace/Unicode normalized.
  The browser remembers its last chosen name; another device can enter the same
  name to load the same layout. The previous shared selection belongs to **Jimmy**;
  new names start empty. Preserve the legacy `dashboard_items` setting as recovery
  data and never overwrite Jimmy's later edits during migration. Cancel does not
  save; removing a tile does not delete the underlying device or automation.
  Names are layout selectors, not authentication/access controls: people can select
  each other's names. Devices, controls, automations and sensor data remain shared.
  Do not add passwords unless the user requests them. Personal Dashboard device tiles
  show names, states and controls without protocol/model details; retain those
  details on the full Devices tab.
- **Devices** is compact and alphabetically sorted with a Swedish numeric-aware
  collator. Show the last recorded state, without the old "Imported state" prose.
  Do not restore the enabled-RF banner or overview counts for devices/groups,
  active schedules, or live sensors. An unavailable-RF warning remains appropriate.
- **Next scheduled action** belongs only on **Schedules**.
- **Sensors** exposes **Show history**, separate temperature/humidity graphs, period
  options 24 hours/7 days/30 days/90 days, and point/touch inspection. Dashboard
  sensor tiles link to Sensors history. Charts are local SVG, not cloud libraries.
- Every five-second UI refresh must preserve horizontal table scroll and vertical
  page position within the current tab. Preserve customization list offsets too.
  `data-scroll-key` identifies replaced Schedules/Activity table containers. Do not
  reintroduce resetting them by blindly replacing `innerHTML` without restoration.
- Keep mobile layouts usable, keyboard labels meaningful, and dynamic text escaped.
  Do not place implementation details in ordinary product flows unnecessarily.

## Storage, history and automation semantics

- SQLite contains items, settings, occurrences, actions, a bounded recent raw
  `observations` buffer (1000 frames) and `sensor_history`. Use parameterized SQL.
- `Store` opens short-lived connections; use SQLite's backup API for live backups,
  not a plain copy that can omit WAL data. Backups and production DB stay private.
- Valid matching Fine Offset RF packets update sensors and archive the latest
  temperature/humidity reading per minute, retained for **90 days**. Humidity 255
  means absent, not 255%; do not invent a reading or import cloud values as history.
- First-upgrade backfill decodes matching valid raw frames still in the old buffer,
  once, preserving their reception times. Older discarded data is unrecoverable.
- History GET supports only 24/168/720/2160 hours and returns at most 1441 averaged
  time buckets. Label averaging intervals; leave long reception gaps as breaks.
  Expanded histories refresh about once a minute, not on every state poll.
- State API: `GET /api/state`; minimal health: `GET /api/health`.
  History: `GET /api/sensors/<id>/history?hours=24`.
  Profile selection: `POST /api/profile` with `{"name":"Jimmy"}`. State may use
  `?profile=Jimmy`; without a chosen name the Dashboard is empty. Preferences:
  `POST /api/dashboard` with `profile` and ordered `{kind,id}` items under `items`.
  A save without an existing named profile is rejected; no global writes remain.
  Commands: `POST /api/command` — **transmits through the queue when authorized**.
  Mutations require exact Host/Origin and `X-CSRF-Token`; never use a real RF command
  as a CSRF/HTTP smoke test. Avoid printing complete `/api/state` responses.
- Scheduler runs every second; occurrence keys and stable random delays prevent
  duplicate execution after restart. DST gaps are skipped and folds execute once.
  Sunrise/sunset use Astral and configured location/time zone, without cloud calls.
- Repeats are RF repeats; offline retry intervals are in **minutes**. Actions more
  than five minutes overdue are not replayed after outages. A running action found
  after restart becomes `unknown`, never automatically replayed. One invalid rule
  should not stop other jobs. Pausing must prevent event/schedule execution too.
- Groups expand to deduplicated exact members; reject cycles. Do not activate
  unsupported block-heater rules or replace them with guessed behavior.
- Firmware ACK means transmission completed, not that a receiver changed state.
  Preserve `sent` versus `unknown` semantics and Activity delivery detail.

## Firmware source, build and protocol

The public source is pinned at `fbeda657e9e1dfdd80a4d39cd43b2b7fa2d402da`.
`firmware-build/dependencies.json` records dependencies and mirrors. Exact cmake/rf
objects were recovered from a mirror. The original TCP/IP Git revision remains
unavailable; the working stack was reconstructed from pinned Microchip **v5.42**
source in xioTechnologies/OSC-Sync-Master plus compatibility changes. Do not describe
it as the recovered exact original Telldus TCP/IP tree.

The Windows **PICC18 9.65 Lite** compiler under Wine produced the working firmware.
PRO activation attempts failed, and Microchip correspondence was handled by the
owner. Do not assume PRO is active or reuse/disclose a licence key from history.
Builds need ignored vendor/compiler files; a Git clone alone is not self-contained.
Read the build documentation before attempting reconstruction.

- `firmware-work/source`: isolated compatibility baseline.
- `firmware-work/source-readonly`: generated X-RX1 profile.
- `firmware-work/source-transmit`: generated **X-TX1**, the installed profile.
- `firmware-build/lite-compat.patch`: named constant-string compatibility changes,
  removal of one disabled diagnostic, and ADC register field adjustment for Lite.
- `prepare_readonly.py`: preserves reception; limits dispatch, removes EEPROM writes
  and remote reboot/configuration operations; reads only MAC bytes; uses DHCP;
  bounds outgoing messages; replaces discovery secret with public `LOCALONLY`.
- `prepare_transmit.py`: overlays tracked `tx-profile/localaccess.c`, `txcontrol.c`
  and `txcontrol.h` onto the RX profile and changes version to X-TX1. These tracked
  files are the authoritative transmit implementation, not just generated output.
- `build_lite.py --transmit` builds without flashing. Compiler source list excludes
  legacy send/reboot implementations. The conservative application reservation is
  **0x1D000–0x1FFF7**; do not remove it to make a larger image fit.
- Host encoders in `tellstick_local/transmit.py` implement Arctech self-learning,
  Arctech code-switch and Comen/Proove mappings. Supported exported devices include
  35 physical units, 14 dimmable, plus five groups. Encoders were compared in 72
  synthetic cases against pinned Telldus C++ reference commit
  `2598bbed16ffd701f2a07c99582f057a3decbaf3`.
- Discovery: ASCII **D**, UDP **30303**. Safe parser validates/discards secret fields
  and returns only public metadata. Stock installed version was **4**, although
  the public source/example used **X**; do not impose X on discovery clients.
- Local UDP: **42314**. Listener registration is exactly `B:reglistener`.
  TX1 packets carry alternating HIGH/LOW durations in 10-microsecond units.
  TP1 is a non-transmitting readiness probe; TA1 acknowledges status/completion.
- Validate before GPIO changes: max 160 pulses, 600 units per pulse, 12000 total,
  100 frames and 50ms gap. Cache 16 completed request identities to suppress repeats.
  The host sends once; missing final ACK is uncertain, not permission to resend.
- The Argus IPv4 allowlist is not cryptographic authentication. Keep this service
  on the trusted home network; never expose UDP control through WAN forwarding.

## Recovery evidence and limits

Read the **latest sections** of `firmware-build/RECOVERY.md` before any intervention.
Initial headings and tables there describe earlier, superseded uncertainty.

- PIC **18F67J60**, 128KiB program flash. External I2C identity/settings EEPROM is
  separate; a flash readback is not an EEPROM dump. No complete verified external
  EEPROM backup/restore procedure was established. The owner has no PIC programmer
  or EEPROM reader. USB was used for power, not established as a firmware readout.
- Original complete stock flash was read repeatedly over Ethernet/TFTP and matched:
  SHA-256 `d7fc988322cf846851b88783e1db1ae8fc23081819fd4985fa15a137c9dd3d37`.
- Stock firmware-4 application HEX, prepared for rollback:
  `secrets/recovery/rollback-20261117T180531730937Z/stock-firmware-4.hex`;
  SHA-256 `ba103630c1048178c59c8253a9e510ab3ac565c6ecf592b78aeb78fefacd8a90`.
- Installed X-TX1 candidate:
  `secrets/recovery/tx-candidate-20261117T190811546969Z/firmware.hex`;
  SHA-256 `f9ed220b5cffca1e8ef34d8788a3e156b9b6b1f59eed17bbfcf53926deb95596`.
- X-TX1 complete post-write readback:
  `secrets/recovery/tx-test-verify-startup-20261117T191203950993Z/startup.bin`.
  All 131072 bytes matched the expected application plus preserved original
  bootloader/configuration. Stock same-version restore was also tested and verified.
- Observed reset vector enters bootloader at **0x1DC00**. Application jump table is
  at **0x1DBC0**; bootloader reservation **0x1DC00–0x1FBFF**; configuration bytes at
  **0x1FFF8–0x1FFFB**. Raw flash BIN and application Intel HEX are not interchangeable.
  Never upload a complete raw flash backup as application firmware.
- Recovery device IP: **192.168.97.60**; Argus temporary recovery IP:
  **192.168.97.149/24** on `enp3s0`. The latter was still present on 2026-11-19.
  Do not remove it during recovery work or assume it is the normal device address.
- Stock TFTP/UDP69 traffic can trigger reboot. A TFTP GET is not necessarily
  operationally harmless. Custom X-TX1 omits the application reboot handler;
  readback entry uses a coordinated USB power-cycle with capture armed first.
- Bootloader survival and completed-image readback are proven for the recorded
  tests, not arbitrary images, loss of power during writing, or EEPROM damage.
- Files named `test_stock_restore.py`, `test_rx_firmware.py`, and
  `test_tx_firmware.py` are **hardware workflows that can upload firmware or send
  RF**. They are not ordinary unit tests. Read source and obtain applicable
  authorization before running them; do not recursively execute every `test*.py`.

## Development and validation workflow

Keep Python 3.12 and the standard library where practical. The installed virtual
environment has the controller's Astral dependency. Export tooling additionally
uses requests/oauthlib; photo-upload tests use Pillow. Do not reinstall dependencies
or add frontend build tooling for an ordinary CSS/JS change.

```sh
.venv/bin/python -m unittest discover -s tests -v
python3 -m compileall -q controller tellstick_local
git diff --check
```

The last completed suite had **100 passing tests**, including dashboard/history
and named-profile migration/isolation coverage. These tests use temporary databases/mocked transport; transmitter tests
also compile an offline C harness with `cc`. Do not replace mocks with live radio
calls. Run focused checks for small reversible changes and broader tests when
backend behavior changes; do not claim tests were rerun for documentation alone.

Browser verification used headless Firefox with `marionette_driver` installed
under `/tmp/tellstick-browser-check`. Existing helper scripts under `/tmp` are
session artifacts and may disappear. Snap Firefox needed its isolated temporary
profile under `/home/jimmy/snap/firefox/common`, not `/opt` or `/tmp`. Clean up owned
profiles/processes afterward and do not disturb the user's existing browser.
Native Firefox minimum window width can exceed a requested 390px; verify actual
content width or constrain the body when checking phone layouts.

For mutating UI QA, use an isolated private copy/fixture DB with RF authorization
and scheduler disabled, **no engine or receiver threads**, and a separate loopback
port (previously 8769). Synthetic history belongs only in that copy. Test selection,
ordering, persistence, cancel, graph ranges and real automatic-refresh scroll
behavior. Production checks should be read-only navigation/API validation; never
click physical control, pause, schedule-toggle, or save buttons for convenience.
No extra preview server needs to remain running after verification.

## Historical support tools and checkpoints

- The read-only account export is complete for its documented configuration scope.
  OAuth credentials were transient, not persisted. Re-exporting needs a user-driven
  local authorization flow; do not request their Telldus password or keys in chat,
  silently contact cloud services, or overwrite the only complete export.
- The photo uploader at port 8767 is a temporary private capability-URL tool for
  board photos, including multiple large images and QR-code access. Follow its
  README, keep its session URL private, and do not start duplicate instances.
- Recorded commits: `0289934` initial controller/firmware/recovery tooling;
  `18e624e` persistent mDNS/LAN DNS investigation; `7775461` personal dashboard,
  sensor history and scroll preservation; `251d142` ignored object files/untracked
  `l.obj`. Verify Git rather than assuming these remain the latest commits.
- Keep this file current when architecture or confirmed deployment changes, but
  distinguish historical observations from permanent constraints. Report what was
  actually tested, what remains uncertain, and any meaningful deployment limitation.
