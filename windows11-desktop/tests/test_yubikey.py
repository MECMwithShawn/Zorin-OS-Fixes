"""YubiKey sign-in pieces: the PAM line edits, sealing keyring passwords, and the keyring D-Bus
calls against a private gnome-keyring-daemon (never the user's own keyrings)."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'yubikey'))
import keyring_unlock  # noqa: E402
import pam_install  # noqa: E402

SUDO = """#%PAM-1.0

# Set up user limits from /etc/security/limits.conf.
session    required   pam_limits.so

session    required   pam_env.so readenv=1 user_readenv=0
session    required   pam_env.so readenv=1 envfile=/etc/default/locale user_readenv=0

@include common-auth
@include common-account
@include common-session-noninteractive
"""
POLKIT = """#%PAM-1.0

@include common-auth
@include common-account
@include common-password
session       required   pam_env.so readenv=1 user_readenv=0
session       required   pam_env.so readenv=1 envfile=/etc/default/locale user_readenv=0
@include common-session-noninteractive
"""
MAPPING = 'shawn:AbC+/=,dGVzdA==,es256,+presence\n'


class PamLines(unittest.TestCase):
    def test_line_goes_right_above_common_auth_once(self):
        text = pam_install.add_line(SUDO, pam_install.auth_line())
        lines = text.splitlines()
        i = lines.index('@include common-auth')
        self.assertTrue(lines[i - 1].startswith('auth\tsufficient\tpam_u2f.so '))
        self.assertNotIn('#', lines[i - 1], 'no end-of-line comment')
        self.assertTrue(lines[i - 2].startswith(pam_install.MARK))
        self.assertEqual(pam_install.add_line(text, pam_install.auth_line()), text)
        self.assertEqual(pam_install.remove_line(text), SUDO)

    def test_a_file_without_common_auth_is_refused(self):
        with self.assertRaises(ValueError):
            pam_install.add_line('auth required pam_unix.so\n', pam_install.auth_line())

    def test_only_one_mapping_line_for_the_user(self):
        self.assertTrue(pam_install.valid_mapping(MAPPING, 'shawn'))
        self.assertFalse(pam_install.valid_mapping(MAPPING, 'root'))
        self.assertFalse(pam_install.valid_mapping(MAPPING + 'shawn:x,y,es256,+presence\n', 'shawn'))
        self.assertFalse(pam_install.valid_mapping('shawn:a b\n', 'shawn'))
        self.assertFalse(pam_install.valid_mapping('', 'shawn'))

    def test_install_then_uninstall_leaves_the_files_as_they_were(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sudo, polkit, vendor = d / 'sudo', d / 'polkit-1', d / 'vendor-polkit-1'
            mapping, staged, backups = d / 'Yubico' / 'u2f_mappings', d / 'staged', d / 'backups'
            sudo.write_text(SUDO)
            vendor.write_text(POLKIT)
            staged.write_text(MAPPING)
            kw = dict(sudo=sudo, polkit=polkit, polkit_vendor=vendor, mapping=mapping, backups=backups)
            pam_install.install(staged, 'shawn', check_module=False, **kw)
            self.assertIn(f'authfile={mapping}', sudo.read_text())
            self.assertIn('pam_u2f.so', polkit.read_text())
            self.assertEqual(vendor.read_text(), POLKIT, 'the vendor file is never edited')
            self.assertEqual(mapping.read_text(), MAPPING)
            self.assertEqual(oct(mapping.stat().st_mode & 0o777), '0o644')
            pam_install.install(staged, 'shawn', check_module=False, **kw)  # again: no second line
            self.assertEqual(sudo.read_text().count('pam_u2f'), 1)
            self.assertTrue(any((b / 'sudo').read_text() == SUDO for b in backups.iterdir()))
            pam_install.uninstall(**kw)
            self.assertEqual(sudo.read_text(), SUDO)
            self.assertFalse(polkit.exists(), 'our polkit copy goes, so the vendor file applies')
            self.assertFalse(mapping.exists())

    def test_a_bad_mapping_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'sudo').write_text(SUDO)
            (d / 'vendor').write_text(POLKIT)
            (d / 'staged').write_text('')
            with self.assertRaises(SystemExit):
                pam_install.install(d / 'staged', 'shawn', sudo=d / 'sudo', polkit=d / 'polkit',
                                    polkit_vendor=d / 'vendor', mapping=d / 'map', backups=d / 'b',
                                    check_module=False)
            self.assertEqual((d / 'sudo').read_text(), SUDO)
            self.assertFalse((d / 'polkit').exists())


class Sealing(unittest.TestCase):
    def test_round_trip_and_binding(self):
        key, other = os.urandom(32), os.urandom(32)
        path = '/org/freedesktop/secrets/collection/login'
        record = keyring_unlock.seal(key, path, b'hunter2')
        self.assertNotIn('hunter2', str(record))
        self.assertEqual(keyring_unlock.unseal(key, path, record), b'hunter2')
        self.assertIsNone(keyring_unlock.unseal(other, path, record), 'another key')
        self.assertIsNone(keyring_unlock.unseal(key, path + 'x', record), 'another keyring')

    def test_config_is_private(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'sub' / 'c.json'
            keyring_unlock.save_config({'a': 1}, path)
            self.assertEqual(oct(path.stat().st_mode & 0o777), '0o600')
            self.assertEqual(keyring_unlock.load_config(path), {'a': 1})


@unittest.skipUnless(shutil.which('gnome-keyring-daemon') and shutil.which('dbus-run-session'),
                     'needs gnome-keyring-daemon and dbus-run-session')
class PrivateKeyring(unittest.TestCase):
    """Runs yubikey_keyring_live.py inside its own D-Bus session and keyring daemon."""

    def test_check_unlock_and_full_unlock_flow(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k not in ('DBUS_SESSION_BUS_ADDRESS', 'DISPLAY', 'WAYLAND_DISPLAY')}
            runtime = Path(d) / 'run'
            runtime.mkdir(mode=0o700)
            env.update(HOME=d, XDG_DATA_HOME=f'{d}/data', XDG_CONFIG_HOME=f'{d}/config',
                       XDG_RUNTIME_DIR=str(runtime))
            r = subprocess.run(['dbus-run-session', '--', sys.executable, str(HERE / 'yubikey_keyring_live.py')],
                               env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('PASS', r.stdout)


if __name__ == '__main__':
    unittest.main()
