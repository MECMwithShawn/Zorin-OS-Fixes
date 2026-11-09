# YubiKey instead of passwords

A YubiKey touch answers `sudo`, the GNOME admin pop-ups (polkit) and the keyring prompt after
auto-login. Your password still works for all three when the key is missing.

```bash
sudo apt install libpam-u2f pamu2fcfg
./setup.sh            # keyring password once, three touches, sudo password once
./setup.sh uninstall  # undo
```

- **sudo and admin pop-ups:** `pam_install.py` puts one `auth sufficient pam_u2f.so` rule above
  `@include common-auth` in `/etc/pam.d/sudo` and in a copy of polkit's file at
  `/etc/pam.d/polkit-1`. The key mapping is root-owned (`/etc/Yubico/u2f_mappings`), so a program
  running as you can't add its own key. `common-auth` is never edited; backups go to
  `/var/backups/zorin11-yubikey/`.
- **Keyring:** auto-login gives `pam_gnome_keyring` no password, so the keyrings stay locked.
  `keyring_unlock.py setup` checks each keyring's current password, registers a
  non-discoverable credential with hmac-secret on the key, and seals the passwords with the
  key's secret (AES-GCM) in `~/.config/zorin11-hub/yubikey-keyring.json`. At sign-in,
  `keyring_unlock.py unlock` asks for a touch and unlocks them. Keyring passwords don't change;
  after changing your sign-in password, run setup again.
- Touch only, no PIN: anyone holding both the laptop and the key can use them. A program running
  as you can start `sudo` and make the key blink — touch it only when you started something.

Tests: `python3 -m unittest tests.test_yubikey` (the keyring part runs against a private
gnome-keyring-daemon in its own D-Bus session).
