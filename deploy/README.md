# Router DNS deployment preparation

Router DNS changes are authorized as of 2026-11-16. This supersedes the earlier
no-router-DNS constraint in the investigation notes. RF transmission remains
unauthorized. These files are staged only: no router setting, system configuration,
or running service has been changed.

## Prepared files

- `dnsmasq-tellstick.conf`: DNS-only listener on Argus 192.168.1.149, with exact
  A records for api.telldus.com and local.telldus.com. Other requests forward to
  explicit upstream resolvers. It does not enable DHCP, TFTP, or query logging.
- `http/server/assign`: exact historical assignment response, without a newline.
  A future HTTP endpoint must serve it on TCP 80 at /server/assign, including
  requests with query parameters. Do not run a generic HTTP file server that logs
  request URLs: firmware requests may contain sensitive registration information.

Configuration syntax was checked with:

```sh
/usr/sbin/dnsmasq --test --conf-file=/opt/tellstick/tellstick-local/deploy/dnsmasq-tellstick.conf
```

This checks syntax only. It does not establish end-to-end DNS forwarding or stock
firmware session compatibility. Do not install the configuration or change router
DNS until the HTTP endpoint and receive-only TCP session handler are ready.

## Current host observations

Read-only checks on 2026-11-16 found:

- enp3s0: 192.168.1.149/24, currently dynamic via DHCP.
- Default gateway: 192.168.1.1.
- systemd-resolved active on loopback 127.0.0.53 and 127.0.0.54.
- dnsmasq service inactive; dnsmasq executable available.
- No listener on LAN address port 53, TCP 80, or TCP 45002.

Reserve 192.168.1.149 for Argus through the router's normal DHCP reservation UI
before assigning it as DNS. Reserving the TellStick's 192.168.1.193 address is also
useful for source restrictions. Confirm existing reservations first.

## Router settings to identify

“Mint 17.2” names the firmware release, not a unique hardware model. It appears
on Technicolor devices, including the TG799vac Xtream. The user has confirmed hardware model TG799vn v2; its exposed DNS controls
on the installed firmware are not yet confirmed. Use the normal router admin UI; no root
access, firmware downgrade, or unofficial router modifications are part of this
setup. Telia documents access via 192.168.1.1 or 192.168.1.254:
https://www.telia.se/support/bredband/guider/koppla-in-bredband-via-fiber

Choose in this order, if the UI supports it:

1. Exact local host overrides for api.telldus.com and local.telldus.com, both to
   192.168.1.149. If the router already provides DNS to the TellStick, this avoids
   adding a separate forwarding resolver. Our dnsmasq config is unnecessary then.
2. Per-device DHCP DNS of 192.168.1.149 for the TellStick only.
3. LAN DHCP DNS of 192.168.1.149 for all clients, or router DNS forwarding to Argus.
   This makes household DNS availability depend on Argus. Ordinary requests must
   work before rollout. A router may reject upstream DNS on its own LAN; this
   must be verified in the actual UI rather than assumed.

Record the original values for rollback. Do not add an ordinary public resolver
as secondary DNS for the TellStick: clients can use it independently and bypass
our overrides. Redundant DNS requires another resolver with matching local records.
The staged dnsmasq upstreams are explicitly 1.1.1.1 and 1.0.0.1 and can be changed
to preferred resolvers; they must not forward back to a router that forwards to
Argus. No resolver choice has been applied to the host or router.

The staged records affect any client that uses this resolver, not only the
TellStick. They redirect just two names; they do not wildcard telldus.com.
The `local` rules keep other query types for these names from leaking upstream
and prevent a public IPv6 answer bypassing the local IPv4 endpoint. No WAN port
forwarding is needed. Restrict TCP/UDP 53 to LAN clients and TCP 80/45002 to the
TellStick where practical. Do not alter existing firewall rules blindly.

## Rollout order

1. Confirm router model and supported DNS controls; reserve Argus's address.
2. Finish and test the assignment HTTP endpoint and bounded TCP framing/session
   handler locally. Keep secrets transient and output public metadata only.
3. Bind the services to the intended LAN address; test the two DNS records and
   an unrelated name, and test HTTP assignment without involving the device.
4. Apply the selected router DNS change, retaining the original values.
5. Let the TellStick renew DNS/DHCP or reconnect. A physical power cycle may be
   needed if it keeps its existing TCP session or cached DNS; no reset command
   will be sent automatically.
6. Confirm registration, keepalives, and receive-only sensor events. Send no RF.
7. If unsuccessful, restore the original router values and let clients refresh
   DHCP/DNS before stopping any DNS service they still depend on.

The stock TCP framing/authentication remains an implementation dependency.
Having router DNS permission resolves redirection; it does not by itself prove
we can sign accepted RF commands. First prove a cloud-independent receive-only
session, then investigate RF control under separate explicit authorization.
