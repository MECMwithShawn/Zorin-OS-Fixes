#!/bin/bash
# Add "Windows 11 Desktop" to the login screen's session list.
# Run as your desktop user; asks for sudo once for the two session files.
#   bash install.sh           install
#   bash install.sh remove    remove (leaves the current desktop as it is)
set -euo pipefail
cd "$(dirname "$0")"
dropin="$HOME/.config/systemd/user/org.gnome.Shell@.service.d"

if [ "${1:-}" = remove ]; then
    rm -f "$HOME/.local/bin/zorin11-session-select" "$dropin/zorin11-session.conf"
    rmdir "$dropin" 2>/dev/null || true
    systemctl --user daemon-reload
    sudo rm -f /usr/share/wayland-sessions/zorin-windows11.desktop \
               /usr/share/xsessions/zorin-windows11-xorg.desktop
    echo "Removed. The login screen goes back to the Zorin sessions only."
    exit 0
fi

install -Dm 0755 zorin11-session-select "$HOME/.local/bin/zorin11-session-select"
install -Dm 0644 zorin11-session.conf "$dropin/zorin11-session.conf"
systemctl --user daemon-reload
sudo install -m 0644 zorin-windows11.desktop /usr/share/wayland-sessions/zorin-windows11.desktop
sudo install -m 0644 zorin-windows11-xorg.desktop /usr/share/xsessions/zorin-windows11-xorg.desktop
echo "Installed. Sign out, click the gear on the login screen, and pick"
echo "\"Windows 11 Desktop\" or \"Zorin Desktop\"."
