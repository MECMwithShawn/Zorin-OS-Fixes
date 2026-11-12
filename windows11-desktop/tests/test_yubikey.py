"""YubiKey sign-in pieces: the PAM line edits, sealing keyring passwords, and the keyring D-Bus
calls against a private gnome-keyring-daemon (never the user's own keyrings)."""
import contextlib
import io
import json
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


GDM_PASSWORD = """#%PAM-1.0
auth    requisite       pam_nologin.so
auth	required	pam_succeed_if.so user != root quiet_success
@include common-auth
auth    optional        pam_gnome_keyring.so
@include common-account
"""
GDM_CONF = """# GDM configuration storage
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=shawn

[security]
"""


class LoginScreen(unittest.TestCase):
    def files(self, d, conf=GDM_CONF):
        gdm, custom, mapping = d / 'gdm-password', d / 'custom.conf', d / 'u2f_mappings'
        gdm.write_text(GDM_PASSWORD)
        custom.write_text(conf)
        mapping.write_text(MAPPING)
        return dict(gdm=gdm, conf=custom, mapping=mapping, backups=d / 'b')

    def test_on_adds_the_touch_and_turns_auto_login_off_then_off_restores_both(self):
        with tempfile.TemporaryDirectory() as d:
            kw = self.files(Path(d))
            pam_install.login_on(check_module=False, **kw)
            lines = kw['gdm'].read_text().splitlines()
            i = lines.index('@include common-auth')
            self.assertTrue(lines[i - 1].startswith('auth\tsufficient\tpam_u2f.so '))
            self.assertLess(lines.index('auth\trequired\tpam_succeed_if.so user != root quiet_success'), i,
                            'root is still refused before the touch')
            conf = kw['conf'].read_text()
            self.assertIn('AutomaticLoginEnable=false', conf)
            self.assertNotIn('AutomaticLoginEnable=true', conf)
            pam_install.login_on(check_module=False, **kw)  # again: nothing doubled
            self.assertEqual(kw['gdm'].read_text().count('pam_u2f'), 1)
            self.assertEqual(kw['conf'].read_text(), conf)
            del kw['mapping']
            pam_install.login_off(**kw)
            self.assertEqual(kw['gdm'].read_text(), GDM_PASSWORD)
            self.assertEqual(kw['conf'].read_text(), GDM_CONF)

    def test_auto_login_that_was_off_stays_off(self):
        off = GDM_CONF.replace('AutomaticLoginEnable=true', 'AutomaticLoginEnable=false')
        with tempfile.TemporaryDirectory() as d:
            kw = self.files(Path(d), off)
            pam_install.login_on(check_module=False, **kw)
            self.assertEqual(kw['conf'].read_text(), off)
            del kw['mapping']
            pam_install.login_off(**kw)
            self.assertEqual(kw['conf'].read_text(), off)
            self.assertIsNone(pam_install.login_off(**kw), 'off twice changes nothing')

    def test_no_key_set_up_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            kw = self.files(Path(d))
            kw['mapping'].unlink()
            with self.assertRaises(SystemExit):
                pam_install.login_on(check_module=False, **kw)
            self.assertEqual(kw['gdm'].read_text(), GDM_PASSWORD)
            self.assertEqual(kw['conf'].read_text(), GDM_CONF)

    def test_uninstall_takes_the_login_screen_back_too(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            kw = self.files(d)
            (d / 'sudo').write_text(SUDO)
            (d / 'vendor').write_text(POLKIT)
            pam_install.login_on(check_module=False, **kw)
            pam_install.uninstall(sudo=d / 'sudo', polkit=d / 'polkit', polkit_vendor=d / 'vendor', **kw)
            self.assertEqual(kw['gdm'].read_text(), GDM_PASSWORD)
            self.assertEqual(kw['conf'].read_text(), GDM_CONF)


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


class WaitForUnlock(unittest.TestCase):
    """`wait` holds login apps back until the keyrings open or this sign-in's attempt is over."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.saved = (keyring_unlock.load_config, keyring_unlock.Keyring, keyring_unlock.done_marker,
                      keyring_unlock.session_started, keyring_unlock.time.sleep)
        self.addCleanup(self.restore)
        self.marker = Path(self.dir) / 'done'
        self.locked = {'/c/default': True}
        test = self

        class FakeKeyring:
            def collections(self):
                return list(test.locked)

            def locked(self, path):
                return test.locked[path]

        keyring_unlock.load_config = lambda: {'keyrings': {'/c/default': {}}}
        keyring_unlock.Keyring = FakeKeyring
        keyring_unlock.done_marker = lambda: self.marker
        keyring_unlock.session_started = lambda: None
        self.ticks = 0

        def sleep(_):
            self.ticks += 1
            if self.ticks == 3 and self.on_third_tick:
                self.on_third_tick()
        keyring_unlock.time.sleep = sleep
        self.on_third_tick = None

    def restore(self):
        (keyring_unlock.load_config, keyring_unlock.Keyring, keyring_unlock.done_marker,
         keyring_unlock.session_started, keyring_unlock.time.sleep) = self.saved

    def run_wait(self, timeout=30):
        return keyring_unlock.main(['wait', '--timeout', str(timeout)])

    def test_returns_when_the_keyring_opens(self):
        self.on_third_tick = lambda: self.locked.update({'/c/default': False})
        self.assertEqual(self.run_wait(), 0)
        self.assertEqual(self.ticks, 3)

    def test_returns_when_this_sign_ins_attempt_is_over(self):
        self.on_third_tick = self.marker.touch
        self.assertEqual(self.run_wait(), 0)
        self.assertEqual(self.ticks, 3)

    def test_a_marker_from_an_earlier_sign_in_is_ignored(self):
        self.marker.touch()
        old = time.time() - 3600
        os.utime(self.marker, (old, old))
        keyring_unlock.session_started = lambda: time.time() - 60
        self.on_third_tick = lambda: self.locked.update({'/c/default': False})
        self.run_wait()
        self.assertEqual(self.ticks, 3)

    def test_gives_up_after_the_timeout(self):
        self.assertEqual(self.run_wait(timeout=0.2), 0)

    def test_not_set_up_means_no_wait(self):
        keyring_unlock.load_config = lambda: None
        self.assertEqual(self.run_wait(), 0)
        self.assertEqual(self.ticks, 0)

    def test_unlock_always_leaves_the_marker(self):
        keyring_unlock.load_config = lambda: None
        keyring_unlock.main(['unlock'])
        self.assertTrue(self.marker.exists())



class PromptAnswer(unittest.TestCase):
    """`password` answers GNOME's keyring prompt: which keyring, the touch, the printed password."""

    CONFIG = {'rp': 'zorin-keyring', 'credential': 'aWQ=', 'salt': 'c2FsdA==', 'keyrings': {
        '/org/freedesktop/secrets/collection/login': {'label': 'Login'},
        '/org/freedesktop/secrets/collection/Default_5fkeyring': {'label': 'Default keyring'}}}

    def test_the_prompt_names_the_keyring(self):
        which = keyring_unlock.prompt_collection
        self.assertEqual(which(self.CONFIG, 'An application wants access to the keyring “Default keyring”, but it is locked'),
                         '/org/freedesktop/secrets/collection/Default_5fkeyring')
        self.assertEqual(which(self.CONFIG, 'The login keyring did not get unlocked when you logged into your computer.'),
                         '/org/freedesktop/secrets/collection/login')
        self.assertIsNone(which(self.CONFIG, 'An application wants access to the keyring “Work”, but it is locked'))
        self.assertIsNone(which(self.CONFIG, 'Enter the password for the certificate'))
        self.assertIsNone(which(None, 'An application wants access to the keyring “Login”, but it is locked'))

    def answer(self, description, key, devices=('/dev/fake',)):
        saved = (keyring_unlock.load_config, keyring_unlock.fido.devices, keyring_unlock.with_touch,
                 keyring_unlock.Keyring, keyring_unlock.signal.signal)
        self.addCleanup(lambda: (setattr(keyring_unlock, 'load_config', saved[0]),
                                 setattr(keyring_unlock.fido, 'devices', saved[1]),
                                 setattr(keyring_unlock, 'with_touch', saved[2]),
                                 setattr(keyring_unlock, 'Keyring', saved[3]),
                                 setattr(keyring_unlock.signal, 'signal', saved[4])))
        right = os.urandom(32)
        config = json.loads(json.dumps(self.CONFIG))
        for path, record in config['keyrings'].items():
            record.update(keyring_unlock.seal(right, path, b'pw:' + record['label'].encode()))
        unlocked = []

        class FakeKeyring:
            def collections(self):
                return list(config['keyrings'])

            def locked(self, path):
                return path not in unlocked

            def unlock(self, path, password):
                unlocked.append((path, password))
                return True

            def close(self):
                pass
        keyring_unlock.load_config = lambda: config
        keyring_unlock.fido.devices = lambda: list(devices)
        keyring_unlock.with_touch = lambda path, text, action, stop=None: right if key == 'right' else os.urandom(32)
        keyring_unlock.Keyring = FakeKeyring
        keyring_unlock.signal.signal = lambda *a: None
        out = io.BytesIO()
        stdout = io.TextIOWrapper(out, write_through=True)
        with contextlib.redirect_stdout(stdout):
            code = keyring_unlock.main(['password', '--prompt', description, '--wait', '0.1'])
        stdout.flush()
        printed = out.getvalue()
        stdout.detach()
        return code, printed, unlocked

    def test_a_touch_prints_the_password_and_opens_the_other_keyring(self):
        code, out, unlocked = self.answer('An application wants access to the keyring “Default keyring”, but it is locked', 'right')
        self.assertEqual((code, out), (0, b'pw:Default keyring'))
        self.assertEqual(unlocked, [('/org/freedesktop/secrets/collection/login', b'pw:Login')])

    def test_another_keyring_or_key_prints_nothing(self):
        self.assertEqual(self.answer('An application wants access to the keyring “Work”, but it is locked', 'right')[:2], (3, b''))
        self.assertEqual(self.answer('The login keyring did not get unlocked when you logged into your computer.', 'other')[:2], (1, b''))
        self.assertEqual(self.answer('The login keyring did not get unlocked when you logged into your computer.', 'right', devices=())[:2], (1, b''))


if __name__ == '__main__':
    unittest.main()
