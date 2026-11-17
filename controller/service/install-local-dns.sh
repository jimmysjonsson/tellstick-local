#!/bin/sh
# Install a separate DNS-only service. Does not change router, DHCP, resolver,
# Tailscale, firewall, dashboard, firmware, or RF settings.
set -eu
if [ "$(id -u)" != 0 ]; then
    echo 'Run with sudo: installing a system service and binding DNS port 53 requires it.' >&2
    exit 1
fi
source_dir=/opt/tellstick/tellstick-local/controller/service
/usr/sbin/dnsmasq --test --conf-file="$source_dir/local-dns.conf"
/usr/bin/systemd-analyze verify "$source_dir/tellstick-local-dns.service"
/usr/bin/install -m 0644 "$source_dir/local-dns.conf" /etc/tellstick-local-dns.conf
/usr/bin/install -m 0644 "$source_dir/tellstick-local-dns.service" /etc/systemd/system/tellstick-local-dns.service
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable tellstick-local-dns.service
/usr/bin/systemctl restart tellstick-local-dns.service
/usr/bin/systemctl is-active tellstick-local-dns.service
echo 'DNS available at 192.168.1.149 for explicitly configured clients.'
echo 'Router DNS and DHCP settings have not been changed.'
