# Argus local home controller

Open **http://127.0.0.1:8768/** on Argus. The application runs locally and loads no
cloud services, external scripts, fonts or images. It is installed as
`tellstick-controller.service` in Jimmy's systemd user manager, enabled at startup.
User lingering is enabled so it continues after logout and starts at boot without
an interactive login. Service startup/restart has been verified; the host has not
been rebooted as part of verification.

## Current physical control

The TellStick runs verified **X-TX1** firmware. After explicit RF authorization,
full flash readback matched the prepared image, bootloader/configuration remained
unchanged, and the owner confirmed **Hall uppe fönster turned ON**. A subsequent
ON action through the application API, persistent queue and service worker also
received the firmware acknowledgment. Manual ON/OFF/DIM controls are enabled and
all 42 previously active schedules are resumed. The block-heater event stays disabled.

The adapter supports all 35 physical exported devices for ON/OFF and 14 dimmable
devices for DIM, plus the five existing groups through deduplicated member expansion.
Formats are Comen self-learning, Arctech self-learning switch/dimmer and Arctech
code-switch. Encoders matched original Telldus C++ results in 72 synthetic cases;
the observed physical test used Comen. Other receivers have not each been separately
observed in person. DIM is quantized to the protocol's 16 brightness levels.

RF commands use bounded pulse requests and a non-transmitting readiness probe.
The firmware acknowledges completing transmission, not receiver state. Activity
therefore records `sent`, and device state labels remain unconfirmed. A command
with a missing final ACK is `unknown`, never blindly replayed. Offline readiness
failures can use configured retry intervals. No cloud API is involved.

`RadioProvider` in controller/radio.py is the production integration. Persisted
rf_authorized and rf_enabled gates must both be set; the browser cannot set these
flags. Firmware accepts the local command port only from Argus 192.168.1.149.
This is a narrow IP allowlist, not cryptographic authentication. Keep that Argus
address reserved. The original stock rollback package remains unchanged.

## Imported account records

The complete private export `secrets/recovery/telldus-account-20261117T163843Z.json`
was imported once, atomically, into `secrets/controller/controller.sqlite`:

- 40 devices/groups, including all 35 RF parameter definitions and 5 groups.
- 3 sensors with last-exported readings retained until replaced by local RF data.
- 46 schedules, preserving the original 42 active and 4 inactive settings.
- 1 disabled block-heater event with its complete original configuration retained.

All 42 active schedules have a calculated next run. Import is idempotent and never
silently overwrites local edits. The UI supports device/group editing, schedule
create/edit/delete/enable, event create/edit/delete, sensor display and action
history. Device deletion is refused while schedules/groups/event actions refer to it.
Group expansion detects cycles and deduplicates shared members.

The imported block-heater trigger is deliberately not approximated with an invented
heating formula. It remains disabled and visible with a configuration notice. It
can be replaced with a locally defined time/sensor rule in the event editor; its
original export is preserved. Enabling the unsupported original trigger is refused.
No automatic firmware changes or cloud operations are tied to editing records.

## Scheduler and event semantics

The worker runs every second independently of the browser. SQLite holds occurrence
identities, pending actions, retries and history across restarts. Two processes
cannot use the same controller database concurrently (a process lock is held).
An action found mid-execution after a restart is marked unknown rather than replayed.
Occurrences have deterministic action IDs so re-planning cannot duplicate them.

- Time zone is imported, currently Europe/Stockholm. Repeated autumn wall times
  run once at fold 0; nonexistent spring times are skipped.
- Astral 3.2 calculates sunrise/sunset locally from the imported coordinates; solar
  events absent during polar day/night are skipped. Offsets are minutes.
- Random delay is from zero to the selected interval, in minutes, independently
  deterministic per job/day so a restart never moves the planned occurrence.
- Repeats retain their RF-repeat meaning. Offline retries retain their count and
  interval **in minutes**. A permanently blocked action is not retried as offline.
- Occurrences/actions more than five minutes overdue are not replayed after an
  outage. This avoids a burst of old ON commands when Argus returns. The selected
  catch-up limit is a local policy, not claimed identical to every Telldus scenario.
- Events support time, sunrise, sunset, sensor thresholds and device-state triggers.
  Triggers are ORed; condition groups are ORed with AND inside each group. Sensor
  conditions require readings newer than 15 minutes. Threshold triggers fire on
  crossings, with minimum repeat intervals in seconds and delayed actions.
- Pausing automations cancels queued scheduled/event actions and stops new ones;
  fresh radio reception continues. Editing a schedule/event cancels its old pending
  actions. Inactive rules do not schedule actions.

Device-state triggers follow acknowledged local commands; radio receivers do not
confirm actual light state. Receiving and mapping every remote-control protocol
to device state is not implemented. Raw Oregon and other frames are retained without fabricated temperature
values. Fine Offset decoding uses the official Telldus bit layout plus the CRC
check already present in the firmware. Sensor matches use protocol and RF sensor ID,
not account API IDs or names.

The UI's event editor builds common single-primary-trigger/action rules, retaining
additional imported triggers/actions; it is not a complete clone of Telldus's drag
and drop editor. Existing imported data remains in the original private export.

## Service operations

```sh
systemctl --user status tellstick-controller.service
systemctl --user restart tellstick-controller.service
systemctl --user stop tellstick-controller.service
journalctl --user -u tellstick-controller.service -n 30
curl http://127.0.0.1:8768/api/health
```

Service definition: `controller/service/tellstick-controller.service`. Interpreter:
`/opt/tellstick/tellstick-local/.venv/bin/python`. `Restart=on-failure`, five-second
restart delay, private runtime files and a process umask of 0077 are configured.
The receive thread reconnects if the TellStick is unavailable. The hardware supports
one registered UDP listener, so another CLI monitor replaces the service's listener;
restart this service after using a separate monitor.

To recreate installation from this checkout:

```sh
python3.12 -m venv --system-site-packages .venv
.venv/bin/python -m pip install 'astral==3.2'
.venv/bin/python -m controller.server \
  --import-export secrets/recovery/telldus-account-20261117T163843Z.json --init-only
systemctl --user enable --now /opt/tellstick/tellstick-local/controller/service/tellstick-controller.service
loginctl enable-linger jimmy
```

For a foreground instance, stop the service first, then run
`.venv/bin/python -m controller.server`. It binds only to loopback. Access from
another machine can use SSH forwarding (`ssh -L 8768:127.0.0.1:8768 jimmy@argus`)
and then http://127.0.0.1:8768/ on that machine. No router changes are required.
The web UI relies on local loopback or the authenticated private Tailscale network
for access, rather than a separate dashboard login. The backend stays bound to
loopback. Exact Host/Origin checks and a per-process CSRF token protect mutations
from other sites; forwarded Host headers are not trusted.
Request logging and cached API responses are disabled.

## Data, backups and verification

The SQLite database, WAL/SHM, process lock and daily backups live under ignored
`secrets/controller/`. Directory permissions are 0700 and data files 0600. They
contain private device RF codes, names, coordinates and automation settings.
They are protected by filesystem permissions, not encryption. No Telldus API
credentials are used or saved by the controller. Raw observations retain the most
recent 1000 frames; this is not an unlimited sensor-history archive.

Automatic consistent SQLite backups use the online backup API once daily, retaining
seven files in `secrets/controller/backups/`. Copy these elsewhere if an independent
backup is wanted. Do not copy only an actively written SQLite file while ignoring
its WAL. To restore, stop the service, preserve the current database and WAL/SHM,
restore a selected complete backup as controller.sqlite with mode 0600, remove the
old WAL/SHM only after preserving them, then restart the service.

```sh
.venv/bin/python -m unittest discover -s tests -v
```

72 automated tests passed, including schedule DST/random/solar semantics, restart
and crash-window deduplication, retry units, expired pending actions, groups,
paused events, delayed actions, sensor crossings/CRC consistent database backups, and isolation of invalid rules so other jobs continue.
HTTP checks verified all assets, imported counts and CSRF/Origin/Host rejection.
Headless Firefox exercised loaded production data and mobile layout; mutations
(device editing and event creation) were tested only on an isolated QA database.
All three imported sensors were observed with fresh local readings. The production
service is enabled, active, and has a current scheduler heartbeat with RF enabled after the authorized firmware and physical tests.

Sources: [Telldus scheduler guide](https://download.telldus.com/TellStick/Guides/Telldus-Live-Schedule-Function.pdf),
[Telldus event guide](https://download.telldus.com/TellStick/Guides/Telldus_Guide_Events_en.pdf),
[official Fine Offset decoder](https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolFineoffset.cpp),
[Astral documentation](https://sffjunkie.github.io/astral/package.html).


## X-TX1 protocol and recovery

Host transport/encoders: tellstick_local/transmit.py. Firmware source overlay:
firmware-build/tx-profile/, generated only in firmware-work/source-transmit; the
original firmware repository is not modified. Build/validation tools are
firmware-build/prepare_transmit.py, build_lite.py --transmit, and validate_transmit.py.
The installed pinned HEX SHA-256 is
f9ed220b5cffca1e8ef34d8788a3e156b9b6b1f59eed17bbfcf53926deb95596.

The wire request contains a magic/version, 32-bit request identity, frame count,
gap and alternating HIGH/LOW durations in 10 µs units. Maximum 160 pulses, 600 units
per pulse, 12000 units total, 100 frames and 50 ms gap are checked before RF pins
change. The firmware caches 16 completed request identities. A protocol operation
uses the original ten waveform repeats, multiplied by the user's repeat setting.
Only ON, OFF and DIM are exposed by the host encoder; learn/bell/group-bit broadcasts
are not. Groups expand on Argus to their exact member devices.

The original Telldus protocol source is pinned at
2598bbed16ffd701f2a07c99582f057a3decbaf3 in the isolated reference checkout.
Specifically ProtocolNexa.cpp and ProtocolComen.cpp define pulse mappings, Comen
house conversion, 1-based unit handling and the dimmer-ON workaround. Tests cover
packet validation, GPIO-before-validation exclusion and duplicate suppression using
host-side C stubs; physical timing still depends on the real hardware clock.

Application firmware still has no remote reboot handler. Firmware readback or
rollback begins with a coordinated USB power-cycle at recovery IP 192.168.97.60,
using Argus temporary IP 192.168.97.149. Existing GET-only and stock rollback tools
remain available. Do not upload a complete raw BIN as an application HEX.
See firmware-build/RECOVERY.md for installation, readback and RF-test private records.


## Private remote access with the existing Tailscale installation

Argus already has Tailscale and HTTPS configured. Existing surveillance is served
at https://argus.tail265095.ts.net/ on 443, proxying to 127.0.0.1:8766.
The dashboard uses a separate private endpoint:
**https://argus.tail265095.ts.net:8443/**, proxying to 127.0.0.1:8768.

The controller side is configured and verified: its systemd ExecStart includes
`--trusted-origin=https://argus.tail265095.ts.net:8443`, while normal localhost
origins continue to work. Only that exact extra HTTPS origin is trusted; wildcard
hosts, arbitrary forwarded headers, other origins and missing CSRF tokens fail.
Seven added regression tests pass (79 tests total). The service was reloaded only
after checking no RF action was running. Schedules and RF remain enabled.

Tailscale's Serve configuration change requires administrator permission on this
host (no operator user is configured). The non-root attempt was denied by
Tailscale, not automatic approval review. The user completed the administrator command below. The private HTTPS dashboard,
API and exact remote Origin/CSRF path were then verified with TLS certificate
validation; the original surveillance mapping remained unchanged:

```sh
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8768
```

This adds a Serve endpoint within the tailnet; no public Funnel is enabled.
The original 443 mapping was captured privately under
secrets/controller/tailscale-serve-before-<timestamp>.json and verified unchanged.
Do not use `tailscale serve reset`, which would also remove surveillance routing.

After that command succeeds, connect the phone's existing Tailscale app, then open
the dashboard HTTPS link. Test outside Wi-Fi using mobile data. Tailscale access
policies must allow the phone to connect to Argus on TCP8443. The device's Tailscale
node key expiration and Argus uptime also affect remote access; scheduling itself
continues locally without a phone connection. No router port forwarding or DNS
change is required. See [Serve documentation](https://tailscale.com/docs/reference/tailscale-cli/serve).


Remote access verification completed on 2026-11-17: private HTTPS8443 serves the
actual dashboard and API successfully, and a deliberately non-mutating validation
request passed the trusted remote Origin/CSRF checks. HTTPS443 still proxies to
surveillance port8766; public Funnel is not enabled. Scheduling and RF remain
enabled with a current worker heartbeat. The verification was from Argus; testing
on the phone over mobile data is the final user-side connectivity check.
