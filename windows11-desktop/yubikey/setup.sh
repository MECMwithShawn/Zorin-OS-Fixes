#!/bin/bash
# YubiKey instead of passwords: sudo, the admin pop-ups and the keyring after auto-login.
#   ./setup.sh            set everything up (three touches, keyring password once, sudo password once)
#   ./setup.sh uninstall  undo it
#   ./setup.sh waits      only make the login apps wait for the YubiKey unlock
#   ./setup.sh login      also sign in with a touch at the login and lock screens (turns auto-login off)
#   ./setup.sh login off  back to password sign-in (and auto-login, if it was on)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.local/share/zorin11-hub/yubikey"
autostart="$HOME/.config/autostart/zorin11-yubikey-keyring.desktop"

# Login apps that read the keyring. Each waits for the YubiKey unlock (180 s at most) so it
# doesn't pop GNOME's password box first. alienware-rdp is a system unit running as this user.
wait_units=(axentra-onedrive axentra-onedrive-tray messages-service blueferry)
wait_system_units=(alienware-rdp)
dropin=zorin11-yubikey-wait.conf

write_dropin() {  # <unit dir> <unit> [sudo]
    local dir="$1/$2.service.d" run=()
    [ "${3:-}" = sudo ] && run=(sudo)
    "${run[@]}" mkdir -p "$dir"
    printf '%s\n' '[Service]' \
        "ExecStartPre=-/usr/bin/python3 $dest/keyring_unlock.py wait" \
        'TimeoutStartSec=240' | "${run[@]}" tee "$dir/$dropin" >/dev/null
}

install_waits() {
    local unit
    for unit in "${wait_units[@]}"; do
        [ "$(systemctl --user show "$unit" -p LoadState --value)" = loaded ] &&
            write_dropin "$HOME/.config/systemd/user" "$unit"
    done
    systemctl --user daemon-reload
    for unit in "${wait_system_units[@]}"; do
        [ "$(systemctl show "$unit" -p LoadState --value)" = loaded ] &&
            write_dropin /etc/systemd/system "$unit" sudo
    done
    sudo systemctl daemon-reload
}

remove_waits() {
    local unit
    for unit in "${wait_units[@]}"; do rm -f "$HOME/.config/systemd/user/$unit.service.d/$dropin"; done
    systemctl --user daemon-reload
    for unit in "${wait_system_units[@]}"; do sudo rm -f "/etc/systemd/system/$unit.service.d/$dropin"; done
    sudo systemctl daemon-reload
}

if [ "${1:-}" = uninstall ]; then
    remove_waits
    sudo python3 "$dest/pam_install.py" uninstall
    python3 "$dest/keyring_unlock.py" forget
    rm -f "$autostart"
    exit 0
fi

if [ "${1:-}" = waits ]; then  # just (re)install the login-app waits
    install -m 0755 "$here/keyring_unlock.py" "$dest/"
    install_waits
    exit 0
fi

if [ "${1:-}" = login ]; then
    mkdir -p "$dest"
    install -m 0644 "$here/pam_install.py" "$dest/"
    sudo python3 "$dest/pam_install.py" login "${2:-on}"
    [ "${2:-on}" = on ] && echo "Sign out to try it: pick your name, touch the key when it blinks. The password still works without the key."
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
install_waits

echo
echo "Done. Test in a NEW terminal:  sudo -k; sudo true   (touch the key)"
echo "If sudo misbehaves there, run '$here/setup.sh uninstall' in THIS terminal within 15 minutes."
