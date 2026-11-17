# Read-only Telldus account configuration export

`export_telldus.py` uses OAuth 1.0a to contact only
`https://pa-api.telldus.com/json/` through a fixed allowlist of GET endpoints.
It does not call RF/device control, account-edit, or scheduler-edit functions.
Dependencies are requests and oauthlib (already available on this Argus host).
They are optional for the discovery project; use its export dependency extra on
another host. Python client/discovery functionality itself remains standard-library.

## Login and run

1. Open https://pa-api.telldus.com/keys/showToken and sign in to Telldus directly.
2. Run `python3.12 scripts/export_telldus.py --web` on Argus.
3. Copy the page's Public key and Private key into the local browser form.
   If Token and Token secret are empty on Telldus, leave both empty locally and
   click Start read-only export. The program opens Telldus's official OAuth
   authorization page; approve access there. A loopback callback then obtains
   account tokens in memory. If you already have both tokens, supply them instead. Do not enter the account password
   in that form. If the token page is unavailable or subscription-restricted, stop
   and report the restriction; do not send credentials through chat.

Without --web the program prompts privately through getpass in a terminal.
The browser form listens only on 127.0.0.1, uses an unpredictable path, validates
Host/Origin, disables response caching and request logging, and loads no external
scripts or styles. It closes the input server after receiving the values. When tokens are missing,
a separate nonce-protected loopback callback waits up to fifteen minutes and
validates that the returned token matches the request token. All three OAuth
endpoints are on pa-api.telldus.com; no tokens are persisted. Credentials
are not written to disk; they remain in process memory while requests are signed.
No third-party OAuth proxy is used. The older AutomaTD implementation was used to
identify historical endpoint names only; its token-forwarding service is not used.

Requests are spaced at least thirty seconds apart. HTTP 429 triggers two bounded
backoff retries (at least 90 then 180 seconds, also considering Retry-After);
if throttling persists, remaining network calls stop and the export stays partial. Redirects are rejected and TLS
verification remains enabled. Errors store a generic category and HTTP status,
not authentication headers or server error text. Authentication/access failures
stop further network calls in that run. The user may need account API access;
logging into the website does not itself grant this program an API session.

## Output

Exports are owner-only JSON files:
`secrets/recovery/telldus-account-<UTC timestamp>.json`.
The status file is `secrets/recovery/telldus-export-status.json`.
Files use 0600; directories use 0700; secrets/ is excluded from Git. These are
plaintext account records with private filesystem permissions, not encrypted files.

The export preserves raw successful list and detail responses for:

- Locations/gateways (including requested coordinates and timezone information).
- Devices, including ignored entries and detailed fields the API exposes.
- Sensors, including ignored entries and current values.
- Schedule jobs and each job's details.
- Events and each event's details.

It records per-section errors, unrecognized list schemas, count mismatches that
could imply pagination, and a completion flag. Partial checkpoints are written
after detail calls so retrieved data remains available if interrupted. A successful
flag means the requested configuration calls succeeded; it is not a guarantee
that Telldus exposes every account field. Verify RF protocol/model/house/unit
coverage before using the export to recreate a controller.

Historical sensor readings and device activity history are explicitly outside this
first configuration export. No claim that they were downloaded may be made. This
export is also separate from the TellStick's firmware/bootloader/EEPROM backup and
does not make firmware flashing recoverable.

## Checks

`python3.12 -m unittest discover -s tests -v` includes mocked exporter tests for
endpoint allowlisting, raw-detail retention, private output permissions, access
failures, and unknown schemas. No live API calls are made by unit tests.

Sources: [official API guide](https://developer.telldus.com/wiki/Guides/Telldus%20Live%20API),
[historical endpoint implementation](https://www.powershellgallery.com/packages/AutomaTD/1.4.1/Content/AutomaTD.psm1).

## Resume a partial export

Run `python3.12 scripts/export_telldus.py --web --resume`. It reads the most recent
account-export JSON, reuses successful list/detail records, and retries missing
or failed calls into a new private output file. It does not overwrite the old
checkpoint. Reauthorization is needed because API credentials are not persisted.
Use the same account when resuming: account identity matching has not yet been
implemented, so do not mix accounts.

## Verified account export — 2026-11-17

Final private JSON:
`/opt/tellstick/tellstick-local/secrets/recovery/telldus-account-20261117T163843Z.json`

The export finished with no recorded failures. List/detail identifier sets and
counts match for all five sections: 1 location/gateway, 40 devices/groups,
3 sensors, 46 schedule jobs and 1 event. File size is 128223 bytes, mode 0600,
and Git exclusion was verified. API credentials were kept in process memory and
were not saved. Earlier partial checkpoints remain in the same private directory.

Of the 40 device entries, 35 have protocol/model/RF parameters. The other five
are groups with membership retained. This distinguishes expected group metadata
from a missing RF-code backup.

All 46 raw schedule records include configuration fields (device/action, time,
weekdays, offsets, repeat/retry/random settings, active status). Four independently
fetched jobInfo responses exactly matched their corresponding jobList records.
To avoid redundant throttled calls, the remaining 42 detail records were retained
from that complete list representation. Each final detail record carries its
source_endpoint and the schedule section retains the comparison note; no
unperformed per-job API calls are claimed.

This is complete for the requested configuration scope, not every possible item
stored by Telldus: historical readings and activity history were not requested,
and account/billing/profile data were not included. It does not establish device
firmware/bootloader/EEPROM recoverability. No control or configuration-write
endpoint was called.
