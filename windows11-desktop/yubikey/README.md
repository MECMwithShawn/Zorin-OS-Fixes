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
  key's secret (AES-GCM) in `~/.config/zorin11-hub/yubikey-keyring.json`. Keyring passwords
  don't change; after changing your sign-in password, run setup again.
- **GNOME's keyring prompt takes the touch:** whichever app asks for a locked keyring first, GNOME
  shows its own "Unlock Keyring" prompt. The desktop extension (`gnome-extension/keyring-yubikey.js`)
  adds "Touch your YubiKey to unlock, or type the password" and runs `keyring_unlock.py password`.
  That command waits for the key (plug it in late if you like), asks for a touch, unlocks the
  other set-up keyrings and hands the prompted keyring's password to the prompt, which then
  completes. Typing the password still works; closing the prompt stops the key blinking. A stale
  saved password is tried once, then it's back to typing. At sign-in, `keyring_unlock.py unlock`
  opens that same prompt, so there's one prompt and one touch however the apps start. Without
  the extension it falls back to its own "insert" and "touch" dialogs.
- **Login apps wait:** setup.sh adds a `zorin11-yubikey-wait.conf` drop-in
  (`ExecStartPre=keyring_unlock.py wait`) to CloudDrive, its tray, Messages and the
  `alienware-rdp` system unit: each holds off until the keyring opens, the unlock attempt ends
  (key missing, Cancel), or 180 s pass, then starts as normal. `./setup.sh waits` installs only
  these.
- Touch only, no PIN: anyone holding both the laptop and the key can use them. A program running
  as you can start `sudo` and make the key blink — touch it only when you started something.

Tests: `python3 -m unittest tests.test_yubikey` (the keyring part runs against a private
gnome-keyring-daemon in its own D-Bus session) and `python3 tests/yubikey_prompt_live.py` (GNOME's
real prompt in a private headless Shell, private keyring daemon, stand-in key).
