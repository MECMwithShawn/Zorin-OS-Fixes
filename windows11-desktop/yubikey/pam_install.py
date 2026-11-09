#!/usr/bin/env python3
"""Let a YubiKey touch answer sudo and the GNOME admin pop-ups (polkit), via pam_u2f.

Run as root: `pam_install.py install --mapping FILE` or `pam_install.py uninstall`.

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


def uninstall(sudo=SUDO, polkit=POLKIT, polkit_vendor=POLKIT_VENDOR, mapping=MAPPING, backups=BACKUPS):
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
    sub.add_parser('uninstall')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo.')
    if args.command == 'install':
        if not args.user:
            raise SystemExit('Pass --user.')
        saved = install(args.mapping, args.user)
        print(f'YubiKey touch added to sudo and admin pop-ups. Previous files: {saved}')
    else:
        saved = uninstall()
        print(f'YubiKey touch removed from sudo and admin pop-ups. Previous files: {saved}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
