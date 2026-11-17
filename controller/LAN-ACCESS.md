# Direct LAN access and the name tellstick

## Current setup: tellstick.local through mDNS

Use **http://tellstick.local/** on the ordinary home network. This replaces the
router-DNS approach below: router IPv6 and DNS stay at their original settings,
and phones/computers use automatic DHCP/DNS. The user confirmed that disabling
router IPv6 temporarily made the earlier tellstick/tellstick.lan trial work, then
restored the previous settings. Router IPv6 DNS advertised fd1a:eac1:701::1 and
returned NXDOMAIN while Argus's IPv4 DNS returned the correct answer.

The enabled user service `tellstick-dashboard-mdns.service` runs
`avahi-publish-address --no-fail --no-reverse tellstick.local 192.168.1.149`.
It uses the existing Avahi daemon; it does not rename Argus or replace its reverse
DNS entry. Only an IPv4 A record is published because the LAN dashboard proxy
listens on IPv4. IPv6 remains usable normally for other traffic. Linger is enabled
for jimmy, so the service starts across boots without an interactive login.

The controller explicitly trusts http://tellstick.local and
http://tellstick.local:8768 alongside its existing origins. Its service was
reloaded and restarted. Verified on Argus: mDNS resolves the name to 192.168.1.149;
both dashboard ports serve HTTP/API; correct Origin/CSRF requests reach validation
without mutation; foreign Origin is rejected. All 89 unit tests pass. Existing
IP and Tailscale access still work; scheduler and RF remain enabled. No RF command
was sent as part of these checks. Android/iPhone validation remains user-side.

Test from a phone on normal home Wi-Fi with its network settings restored:
open http://tellstick.local/. Guest/client-isolated networks can block mDNS. The
name is local to the home network; remote access uses the existing Tailscale URL.
Modern Android and Apple's Bonjour support .local resolution:
[Android](https://source.android.com/docs/core/ota/modular-system/dns-resolver),
[Apple](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/NetServices/Articles/about.html).

Checks: `systemctl --user status tellstick-dashboard-mdns.service` and
`avahi-resolve-host-name -4 tellstick.local`. To remove the announcement:
`systemctl --user disable --now tellstick-dashboard-mdns.service`.
The earlier DNS-only trial service remains installed and available but clients
with their original DNS settings do not use it. No whole-home DNS change was made.

## Earlier unicast DNS investigation

The dashboard runs on **Argus, 192.168.1.149**, not the physical TellStick at
192.168.1.193. DNS names for the dashboard must therefore point to **192.168.1.149**.
The existing Tailscale URL remains https://argus.tail265095.ts.net:8443/ and the
surveillance mapping stays on its existing Tailscale HTTPS443 endpoint.

## Prepared Argus configuration

The controller still binds to 127.0.0.1:8768. Its service now explicitly trusts:

- http://tellstick/ and http://tellstick.lan/
- http://192.168.1.149/
- The same three authorities with port8768.
- The previously configured private Tailscale HTTPS origin.

Host, Origin and CSRF checks remain enabled; arbitrary names and forwarded headers
are not trusted. 89 automated tests pass. Both LAN proxy listener paths were tested
on temporary unprivileged ports, including Host/Origin/CSRF without mutation, and
existing Tailscale HTTPS access was rechecked successfully. No RF command was sent
while preparing LAN access.

The systemd LAN socket listens only on 192.168.1.149:80 and :8768 and forwards to the
existing loopback backend with systemd-socket-proxyd. The proxy uses a DynamicUser,
read-only filesystem, no home-directory access, and IP filters for loopback and
192.168.1.0/24. It does not run the RF controller as root. Socket activation makes
the proxy persistent across boots. FreeBind permits startup before DHCP completes;
Argus must still actually receive its reserved 192.168.1.149 address.

Installing port80 requires administrator permission. The tested installer is:

```sh
sudo /opt/tellstick/tellstick-local/controller/service/install-lan-access.sh
```

It installs only tellstick-dashboard-lan.socket/.service in /etc/systemd/system,
reloads systemd and enables the socket. It does not change router/DNS, Tailscale,
surveillance, firewall rules, firmware or the controller database. The administrator completed installation. Both actual LAN ports and all configured
IP/name Host+Origin paths were verified with non-mutating CSRF validation requests.
The socket and proxy service are active. Direct LAN URLs are:

- http://192.168.1.149/
- http://192.168.1.149:8768/

Service checks:

```sh
systemctl status tellstick-dashboard-lan.socket tellstick-dashboard-lan.service
curl http://192.168.1.149/api/health
```

Removing this LAN access can be done without changing the controller or Tailscale:
`sudo systemctl disable --now tellstick-dashboard-lan.socket` and
`sudo systemctl stop tellstick-dashboard-lan.service`.

## Router DNS entry

1. Open http://192.168.1.1/ and sign in privately to the router.
2. Ensure the DHCP reservation for **Argus** maps Ethernet MAC
   **1c:69:7a:f0:06:a2** to **192.168.1.149**. Keep its existing Argus name; add an
   alias rather than renaming it if the router supports aliases.
3. In a local DNS/static-host/hostname-record table, add the following A records:

   | Name | IPv4 address |
   | --- | --- |
   | tellstick | 192.168.1.149 |
   | tellstick.lan | 192.168.1.149 |

   If the router automatically appends its `lan` domain, enter host `tellstick`
   in that domain; a duplicate tellstick.lan entry is unnecessary.
4. Save/apply. Clients must use the router's LAN DNS, normally via DHCP. The
   current Argus resolver confirms DNS192.168.1.1 and search domain `lan`.
5. Test `nslookup tellstick.lan 192.168.1.1` (or `resolvectl query tellstick.lan` on
   Argus). The expected answer is 192.168.1.149. Reconnect Wi-Fi or clear stale DNS
   cache on devices if needed. Private DNS/DoH settings that bypass the router
   can prevent local-name lookup.
6. Open **http://tellstick/**. Entering a single word without `http://` can start
   a browser search; using the explicit URL once avoids that ambiguity. The
   fallback fully qualified local URL is **http://tellstick.lan/**.

### Important router UI limitation

A verified click-by-click path for adding local A records on this Telia Mint
TG799vn v2 interface has not been established. The router landing page requires
login, and local SSH/Telnet management ports were unavailable during read-only
checks. The manufacturer setup guide documents Dynamic DNS, not a verified
local-host alias editor. Do not apply commands copied from a different router's
firmware or assume a menu exists merely because the hardware supports DNS relay.

The previously seen `DNS Server: 192.168.1.1` setting selects a resolver; it is not
an A-record editor. Dynamic DNS and port forwarding also do not create local
aliases. If this firmware exposes no local host/alias table, an administrator
cannot add these records through that field alone. An alternate configurable LAN
DNS server (or a different router) is then required for all-device name resolution.
Pointing DHCP DNS at Argus would make it a network-wide DNS dependency; that has
not been configured. Per-device hosts files would not meet the all-devices goal.

No router settings have been changed by the agent. The aliases remain dependent
on the user's router DNS configuration, and should not be called working until
actual router/client DNS queries succeed.

Reference: [Technicolor-authored TG799vn v2 setup guide, mirrored PDF](https://setuprouter.com/router/technicolor/tg799vn-v2/10-4-0-o-telia/1059.pdf).


Verification completed on 2026-11-17: 192.168.1.149 ports80 and8768 both serve the
actual dashboard/API; all six configured IP/name authorities pass validation. The
private Tailscale HTTPS endpoint still works and the surveillance443 proxy is
unchanged. Scheduler/RF remain enabled. Router DNS queries currently return
argus.lan=192.168.1.149, no A answer for tellstick, and NXDOMAIN for tellstick.lan.
Thus IP access is enabled and verified, while the requested tellstick DNS aliases
are still pending router setup. Nothing changed the home's DNS-server setting.

## Android-only DNS trial (prepared 2026-11-17)

The user confirmed that the Telia router cannot add these aliases. A separate
DNS-only service is prepared; the router remains unchanged. Install with:

```sh
sudo /opt/tellstick/tellstick-local/controller/service/install-local-dns.sh
```

This installs `/etc/tellstick-local-dns.conf` and
`/etc/systemd/system/tellstick-local-dns.service`, binding UDP/TCP 53 only on
192.168.1.149. It uses the existing dnsmasq binary with an explicit standalone
configuration, never the old `deploy/dnsmasq-tellstick.conf` Telldus overrides.
The existing systemd-resolved loopback listeners remain independent. No DHCP
server, query logging, TFTP, or router advertisement is enabled. The daemon runs
as dnsmasq with only the port-binding capability.

`tellstick`, `tellstick.lan`, `argus`, and `argus.lan` resolve to 192.168.1.149.
Other `.lan` lookups use the existing router; ordinary Internet lookups go to
1.1.1.1/1.0.0.1. Do not point the router's upstream DNS back at Argus while this
conditional `.lan` forwarding is configured. Any future whole-network rollout
requires a separate review of DHCP DNS, router forwarding, and IPv6 DNS.

Configuration and service syntax passed validation. A temporary listener on port
1053 passed UDP and TCP tests for both dashboard aliases, argus.lan, empty local
AAAA answers, and public-domain resolution; it was stopped afterward. The administrator installed the service. Production UDP/TCP port 53 was then
verified on 192.168.1.149 for both aliases, empty local AAAA answers, and public
website lookups. The dashboard returned HTTP 200 with Host tellstick. Existing
systemd-resolved loopback listeners remain present. Android testing is pending.

After port 53 is verified, test only the Android phone:

1. Connect to home Wi-Fi. Temporarily disconnect the phone's Tailscale VPN.
   Record its existing Private DNS setting, then set Private DNS to Off for this
   trial (Connections > More connection settings > Private DNS on Samsung).
2. Open Connections > Wi-Fi > the connected network's gear > View more/Advanced.
   Note the phone's current LAN IPv4 address and switch IP settings to Static.
3. Retain that same phone IPv4 address, gateway 192.168.1.1 and prefix length 24.
   Set DNS 1 to 192.168.1.149. Leave DNS 2 empty if allowed; if the phone insists
   on a value, use 192.168.1.149 for this short trial. A public DNS alternative
   can bypass the local aliases. Do not put an IP into Private DNS's provider
   hostname field; that field requires a DNS-over-TLS hostname.
4. Save, reconnect, and test a normal website, http://tellstick/ and
   http://tellstick.lan/. Browser Secure DNS may need disabling if it bypasses
   the Wi-Fi resolver. IPv6-advertised DNS can also bypass this IPv4 setting;
   investigate rather than changing the router if the test fails.
5. To undo, restore IP settings to DHCP and restore Private DNS/Tailscale.
   This is a short trial using the phone's current DHCP lease, not a permanent
   static-address assignment; reserve its IP before considering permanent use.

Other devices continue using their existing DNS. The phone requires Argus for
DNS only while configured to use it. To stop the new service after the trial:
`sudo systemctl disable --now tellstick-local-dns.service`.

Reference: [Google's Android DNS configuration instructions](https://developers.google.com/speed/public-dns/docs/using/).
