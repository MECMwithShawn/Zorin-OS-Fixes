#!/usr/bin/env bash
set -euo pipefail
# Diagnose slow qBittorrent downloads caused by a closed listening port.
# Reads the port from qBittorrent's config (Flatpak or native), checks that
# qBittorrent is listening on it, looks for firewall (UFW) drops, and asks an
# external checker whether the port is reachable from the internet.
# Usage: ./qbittorrent-port-check.sh [port]
# No sudo needed. Sends your public IP and the port to canyouseeme.org.

FLATPAK_CONF="$HOME/.var/app/org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf"
NATIVE_CONF="$HOME/.config/qBittorrent/qBittorrent.conf"

PORT="${1:-}"
if [ -z "$PORT" ]; then
  if flatpak list 2>/dev/null | grep -q org.qbittorrent.qBittorrent && [ -f "$FLATPAK_CONF" ]; then
    CONF="$FLATPAK_CONF"
  else
    CONF="$NATIVE_CONF"
  fi
  PORT="$(grep -m1 '^Session\\Port=' "$CONF" 2>/dev/null | cut -d= -f2 || true)"
  [ -n "$PORT" ] || { echo "Couldn't read the port from $CONF; pass it as an argument." >&2; exit 1; }
  echo "config:    $CONF"
fi
echo "port:      $PORT"

if ss -tln | grep -qE ":${PORT}\b"; then
  echo "listening: yes (TCP)"
else
  echo "listening: NO, start qBittorrent or check Tools > Options > Connection" >&2
fi

# Only count drops arriving on physical interfaces (Wi-Fi/Ethernet), not Docker bridges.
drops="$(journalctl -k --since '-1 hour' --no-pager 2>/dev/null | grep -E "UFW BLOCK IN=(wl|en|eth)" | grep -c "DPT=${PORT} " || true)"
echo "firewall:  ${drops} UFW drop(s) on port ${PORT} from the network in the last hour"
[ "$drops" -gt 0 ] && echo "           fix: sudo ufw allow ${PORT} comment 'qBittorrent'"

page="$(curl -s -m 25 https://www.canyouseeme.org/ || true)"
ip="$(grep -oE 'name="IP"[^>]*value="[0-9.]+"|value="[0-9.]+"[^>]*name="IP"' <<<"$page" | grep -oE '[0-9]+(\.[0-9]+){3}' | head -1 || true)"
[ -n "$ip" ] || { echo "internet:  couldn't reach canyouseeme.org to test" >&2; exit 1; }
result="$(curl -s -m 25 -X POST https://www.canyouseeme.org/ --data "IP=${ip}&port=${PORT}" \
  | sed 's/<[^>]*>/ /g; s/&nbsp;//g' | tr -s ' \n\t' ' ' | grep -oiE '(Error|Success): .*' | sed -E 's/ Your ISP.*| Your IP:.*//' | head -1 || true)"
echo "internet:  ${result:-no result}"

if [[ "$result" == Success* ]]; then
  echo "OK: peers can connect to you."
else
  echo "Port is closed from the internet. Check, in order:" >&2
  echo "  1. sudo ufw allow ${PORT} comment 'qBittorrent'" >&2
  echo "  2. Router port forward ${PORT} TCP+UDP to this machine's LAN IP (and the forwarding master switch is ON)" >&2
  echo "  3. ISP gateway: bridge/IP passthrough to your router, or forward there too (double NAT)" >&2
  exit 1
fi
