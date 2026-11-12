#!/usr/bin/env python3
"""Let a YubiKey touch answer sudo and the GNOME admin pop-ups (polkit), via pam_u2f.

Run as root: `pam_install.py install --mapping FILE`, `pam_install.py login on|off` or
`pam_install.py uninstall`.

- `login on`: the same line in /etc/pam.d/gdm-password, so a touch signs in at the login screen
  and unlocks the lock screen, and GDM's auto-login is turned off (it skips the login screen).
  `login off` puts both back; auto-login only comes back if it was on before.

- One `auth sufficient pam_u2f.so …` line goes above `@include common-auth`, so a touch is
  enough and the password still works when the key is missing or the touch times out.
- sudo: /etc/pam.d/sudo is edited in place. polkit: its file ships in /usr/lib/pam.d, so a copy
  with the line goes in /etc/pam.d/polkit-1, which takes precedence. common-auth is never touched.
- The key mapping lives in a root-owned file, so a program running as the user can't add its
  own key. Uninstall removes exactly what install added.
"""
import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

MARK = '# zorin11-yubikey'
ORIGIN = 'pam://zorin-yubikey'
MAPPING = Path('/etc/Yubico/u2f_mappings')
SUDO = Path('/etc/pam.d/sudo')
POLKIT = Path('/etc/pam.d/polkit-1')
POLKIT_VENDOR = Path('/usr/lib/pam.d/polkit-1')
GDM = Path('/etc/pam.d/gdm-password')
GDM_CONF = Path('/etc/gdm3/custom.conf')
AUTOLOGIN_MARK = f'{MARK}: auto-login was on; YubiKey sign-in turned it off'
MODULE_DIRS = [Path('/usr/lib/x86_64-linux-gnu/security'), Path('/lib/x86_64-linux-gnu/security'),
               Path('/usr/lib/security'), Path('/lib/security')]
BACKUPS = Path('/var/backups/zorin11-yubikey')


def auth_line(mapping=MAPPING):
    """The marker comment on its own line (PAM has no end-of-line comments), then the rule."""
    return (f'{MARK}: a YubiKey touch instead of the password\n'
            f'auth\tsufficient\tpam_u2f.so authfile={mapping} cue origin={ORIGIN} appid={ORIGIN}')


def add_line(text, line):
    """`text` with `line` above the first `@include common-auth`; unchanged if already there."""
    if MARK in text:
        return text
    lines = text.splitlines(keepends=True)
    for i, current in enumerate(lines):
        if re.match(r'\s*@include\s+common-auth\b', current):
            lines.insert(i, line + '\n')
            return ''.join(lines)
    raise ValueError('no "@include common-auth" line to put the YubiKey line above')


def remove_line(text):
    """`text` without the marker line and the pam_u2f rule right after it."""
    lines, out, skip = text.splitlines(keepends=True), [], False
    for line in lines:
        if line.startswith(MARK):
            skip = True
            continue
        if skip and 'pam_u2f.so' in line:
            skip = False
            continue
        skip = False
        out.append(line)
    return ''.join(out)


def valid_mapping(text, user):
    """One `user:credential,...` line from pamu2fcfg for `user`."""
    lines = [l for l in text.splitlines() if l.strip()]
    return len(lines) == 1 and re.fullmatch(rf'{re.escape(user)}:[A-Za-z0-9+/=_\-,:%]+', lines[0]) is not None


def write_atomic(path, text, mode=0o644):
    tmp = path.with_name(f'.{path.name}.zorin11-yubikey.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def backup(paths, backups=BACKUPS):
    backups.mkdir(parents=True, exist_ok=True)
    stamp, n = time.strftime('%Y%m%d-%H%M%S'), 1
    while True:  # Never reuse a folder: a second run in the same second keeps the first backup.
        folder = backups / (stamp if n == 1 else f'{stamp}-{n}')
        try:
            folder.mkdir()
            break
        except FileExistsError:
            n += 1
    for p in paths:
        if p.exists():
            shutil.copy2(p, folder / p.name)
    return folder


def autologin_off(text):
    """custom.conf with AutomaticLoginEnable=false, marked if it was on, so `login off` can restore it."""
    if AUTOLOGIN_MARK in text:
        return text
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if re.fullmatch(r'\s*AutomaticLoginEnable\s*=\s*(true|1)\s*', line.strip('\n'), re.I):
            lines[i:i + 1] = [AUTOLOGIN_MARK + '\n', 'AutomaticLoginEnable=false\n']
            return ''.join(lines)
    return text  # auto-login isn't on: nothing to turn off


def autologin_restore(text):
    """custom.conf with auto-login back on, only where autologin_off turned it off."""
    lines, out, restore = text.splitlines(keepends=True), [], False
    for line in lines:
        if line.startswith(AUTOLOGIN_MARK):
            restore = True
            continue
        if restore and re.match(r'\s*AutomaticLoginEnable\s*=', line):
            line = 'AutomaticLoginEnable=true\n'
        restore = False
        out.append(line)
    return ''.join(out)


def login_on(gdm=GDM, conf=GDM_CONF, mapping=MAPPING, backups=BACKUPS, check_module=True):
    if check_module and not module_present():
        raise SystemExit('pam_u2f.so is missing: run `sudo apt install libpam-u2f pamu2fcfg` first.')
    if not mapping.exists():
        raise SystemExit(f'{mapping} is missing: run setup.sh (sudo set-up) first.')
    new_gdm = add_line(gdm.read_text(), auth_line(mapping))
    new_conf = autologin_off(conf.read_text()) if conf.exists() else None
    saved = backup([gdm, conf], backups)
    write_atomic(gdm, new_gdm)
    if new_conf is not None:
        write_atomic(conf, new_conf)
    return saved


def login_off(gdm=GDM, conf=GDM_CONF, backups=BACKUPS):
    gdm_text = gdm.read_text() if gdm.exists() else ''
    conf_text = conf.read_text() if conf.exists() else ''
    if MARK not in gdm_text and AUTOLOGIN_MARK not in conf_text:
        return None
    saved = backup([gdm, conf], backups)
    if MARK in gdm_text:
        write_atomic(gdm, remove_line(gdm_text))
    if AUTOLOGIN_MARK in conf_text:
        write_atomic(conf, autologin_restore(conf_text))
    return saved


def module_present():
    return any((d / 'pam_u2f.so').exists() for d in MODULE_DIRS)


def install(mapping_file, user, sudo=SUDO, polkit=POLKIT, polkit_vendor=POLKIT_VENDOR,
            mapping=MAPPING, backups=BACKUPS, check_module=True):
    if check_module and not module_present():
        raise SystemExit('pam_u2f.so is missing: run `sudo apt install libpam-u2f pamu2fcfg` first.')
    text = Path(mapping_file).read_text()
    if not valid_mapping(text, user):
        raise SystemExit(f'{mapping_file} is not a single pamu2fcfg line for {user}.')
    sudo_text = sudo.read_text()
    polkit_text = polkit.read_text() if polkit.exists() else polkit_vendor.read_text()
    new_sudo = add_line(sudo_text, auth_line(mapping))
    new_polkit = add_line(polkit_text, auth_line(mapping))
    saved = backup([sudo, polkit, mapping], backups)
    mapping.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(mapping, text.strip() + '\n')
    write_atomic(sudo, new_sudo)
    write_atomic(polkit, new_polkit)
    return saved


def uninstall(sudo=SUDO, polkit=POLKIT, polkit_vendor=POLKIT_VENDOR, mapping=MAPPING, backups=BACKUPS,
              gdm=GDM, conf=GDM_CONF):
    login_off(gdm, conf, backups)  # the login screen first: it needs the mapping
    saved = backup([sudo, polkit, mapping], backups)
    if MARK in sudo.read_text():
        write_atomic(sudo, remove_line(sudo.read_text()))
    if polkit.exists() and MARK in polkit.read_text():
        rest = remove_line(polkit.read_text())
        # The copy was ours: drop it if nothing else changed, so the vendor file applies again.
        if polkit_vendor.exists() and rest == polkit_vendor.read_text():
            polkit.unlink()
        else:
            write_atomic(polkit, rest)
    mapping.unlink(missing_ok=True)
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    i = sub.add_parser('install')
    i.add_argument('--mapping', required=True, help='pamu2fcfg output for the user')
    i.add_argument('--user', default=os.environ.get('SUDO_USER'))
    l = sub.add_parser('login', help='YubiKey touch at the login and lock screens (auto-login off)')
    l.add_argument('state', choices=['on', 'off'])
    sub.add_parser('uninstall')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo.')
    if args.command == 'install':
        if not args.user:
            raise SystemExit('Pass --user.')
        saved = install(args.mapping, args.user)
        print(f'YubiKey touch added to sudo and admin pop-ups. Previous files: {saved}')
    elif args.command == 'login':
        if args.state == 'on':
            saved = login_on()
            print(f'YubiKey touch added to the login and lock screens; auto-login is off. Previous files: {saved}')
        else:
            saved = login_off()
            print('YubiKey sign-in removed from the login and lock screens'
                  + (f'. Previous files: {saved}' if saved else ' (it was not on).'))
    else:
        saved = uninstall()
        print(f'YubiKey touch removed from sudo, admin pop-ups and the login screen. Previous files: {saved}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
