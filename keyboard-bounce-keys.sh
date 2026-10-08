#!/usr/bin/env bash
set -euo pipefail
# Stop a mechanical keyboard from double-typing (key chatter) by enabling Bounce Keys.
# Bounce Keys ignores a repeat press of the same key within DELAY ms.
# Usage: ./keyboard-bounce-keys.sh [delay_ms]   (default 40)
#        ./keyboard-bounce-keys.sh off
# Runs as the logged-in desktop user; no sudo needed. Persists across reboots.

ARG="${1:-40}"
DESKTOP="${XDG_CURRENT_DESKTOP:-}"

if [ "$ARG" = "off" ]; then
  ENABLE=false
else
  ENABLE=true
  if ! [[ "$ARG" =~ ^[0-9]+$ ]]; then
    echo "delay must be a number of milliseconds, or 'off'" >&2
    exit 1
  fi
fi

case "$DESKTOP" in
  *XFCE*)
    # Zorin OS Lite / XFCE: applied live by xfsettingsd.
    xfconf-query -c accessibility -p /BounceKeys -n -t bool -s "$ENABLE"
    [ "$ENABLE" = true ] && xfconf-query -c accessibility -p /BounceKeys/Delay -n -t int -s "$ARG"
    xfconf-query -c accessibility -lv | grep -i bounce
    ;;
  *GNOME*|*zorin*)
    # Zorin OS Core / GNOME.
    gsettings set org.gnome.desktop.a11y.keyboard enable true
    gsettings set org.gnome.desktop.a11y.keyboard bouncekeys-enable "$ENABLE"
    [ "$ENABLE" = true ] && gsettings set org.gnome.desktop.a11y.keyboard bouncekeys-delay "$ARG"
    echo "bouncekeys-enable: $(gsettings get org.gnome.desktop.a11y.keyboard bouncekeys-enable)"
    echo "bouncekeys-delay:  $(gsettings get org.gnome.desktop.a11y.keyboard bouncekeys-delay)"
    ;;
  *)
    echo "Unsupported desktop '$DESKTOP'. Enable Bounce Keys in Settings > Accessibility > Keyboard." >&2
    exit 1
    ;;
esac
