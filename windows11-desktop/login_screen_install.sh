#!/bin/sh
# Installs the Windows 11 login screen. Run with sudo from a checkout; it writes
# only the paths below, and never restarts GDM or changes how passwords are checked.
# The next time the login screen starts it picks this up. --remove undoes it all.
set -eu
UUID=zorin11-login@zorin-os-fixes
EXTENSION=/usr/share/gnome-shell/extensions/$UUID
DCONF=/usr/share/gdm/dconf/95-zorin11-login
SHARED=/var/lib/zorin11-login
SOURCE=$(dirname "$(readlink -f "$0")")

[ "$(id -u)" = 0 ] || { echo 'Run this with sudo.' >&2; exit 1; }
if [ "${1:-}" = --remove ]; then
    rm -f "$DCONF" "$EXTENSION/metadata.json" "$EXTENSION/extension.js" "$EXTENSION/stylesheet.css" "$SHARED/background.jpg"
    rmdir "$EXTENSION" "$SHARED" 2>/dev/null || true
    /usr/share/gdm/generate-config
    echo 'Removed. The next login screen is the standard Zorin one.'
    exit 0
fi
OWNER=${SUDO_USER:?Run this with sudo from your own account.}
install -d -m 755 "$EXTENSION"
install -m 644 "$SOURCE/gnome-login-extension/metadata.json" "$SOURCE/gnome-login-extension/extension.js" \
    "$SOURCE/gnome-login-extension/stylesheet.css" "$EXTENSION/"
# Lets the daily lock-screen picture update reach the login screen without sudo.
install -d -m 755 -o "$OWNER" -g "$OWNER" "$SHARED"
install -m 644 "$SOURCE/login_screen_dconf" "$DCONF"
/usr/share/gdm/generate-config
HOME_DIR=$(getent passwd "$OWNER" | cut -d: -f6)
runuser -u "$OWNER" -- env HOME="$HOME_DIR" /usr/bin/python3 "$HOME_DIR/.local/share/zorin11-hub/lockscreen.py" --publish-login || true
echo 'Installed. You will see it the next time you sign out.'
