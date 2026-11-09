#!/bin/bash
# YubiKey instead of passwords: sudo, the admin pop-ups and the keyring after auto-login.
#   ./setup.sh            set everything up (three touches, keyring password once, sudo password once)
#   ./setup.sh uninstall  undo it
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.local/share/zorin11-hub/yubikey"
autostart="$HOME/.config/autostart/zorin11-yubikey-keyring.desktop"

if [ "${1:-}" = uninstall ]; then
    sudo python3 "$dest/pam_install.py" uninstall
    python3 "$dest/keyring_unlock.py" forget
    rm -f "$autostart"
    exit 0
fi

command -v pamu2fcfg >/dev/null || { echo "Install the PAM module first: sudo apt install libpam-u2f pamu2fcfg"; exit 1; }

mkdir -p "$dest"
install -m 0644 "$here/fido.py" "$here/pam_install.py" "$dest/"
install -m 0755 "$here/keyring_unlock.py" "$dest/"

echo "1/3  Keyring: enter its password when asked, then touch the key twice."
python3 "$dest/keyring_unlock.py" setup

cat > "$autostart" <<EOF
[Desktop Entry]
Type=Application
Name=Unlock keyring with YubiKey
Comment=Asks for a YubiKey touch after sign-in and unlocks the keyring
Exec=/usr/bin/python3 $dest/keyring_unlock.py unlock
Icon=security-high
NoDisplay=true
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Phase=Applications
X-GNOME-Autostart-Delay=0
EOF

echo "2/3  sudo and admin pop-ups: touch the key when it blinks."
mapping=$(mktemp)
trap 'rm -f "$mapping"' EXIT
pamu2fcfg -u "$USER" -o pam://zorin-yubikey -i pam://zorin-yubikey > "$mapping"

echo "3/3  Installing the PAM line (your sudo password, one last time)."
sudo python3 "$dest/pam_install.py" install --mapping "$mapping" --user "$USER"

echo
echo "Done. Test in a NEW terminal:  sudo -k; sudo true   (touch the key)"
echo "If sudo misbehaves there, run '$here/setup.sh uninstall' in THIS terminal within 15 minutes."
