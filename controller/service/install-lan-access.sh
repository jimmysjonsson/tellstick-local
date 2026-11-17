#!/bin/sh
# Install only the two reviewed LAN proxy units. Does not alter router/DNS,
# firewall, Tailscale, surveillance, firmware, or the controller database.
set -eu
if [ "$(id -u)" != 0 ]; then
    echo 'Run this installer with sudo; binding HTTP port 80 requires it.' >&2
    exit 1
fi
source_dir=/opt/tellstick/tellstick-local/controller/service
/usr/bin/systemd-analyze verify "$source_dir/tellstick-dashboard-lan.socket" "$source_dir/tellstick-dashboard-lan.service"
/usr/bin/install -m 0644 "$source_dir/tellstick-dashboard-lan.socket" /etc/systemd/system/tellstick-dashboard-lan.socket
/usr/bin/install -m 0644 "$source_dir/tellstick-dashboard-lan.service" /etc/systemd/system/tellstick-dashboard-lan.service
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable --now tellstick-dashboard-lan.socket
/usr/bin/systemctl is-active tellstick-dashboard-lan.socket
echo 'LAN dashboard proxy enabled: http://192.168.1.149/ and port 8768.'
echo 'After router DNS aliases are added, use http://tellstick/ or http://tellstick.lan/.'
