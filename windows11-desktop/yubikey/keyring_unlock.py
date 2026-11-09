#!/usr/bin/env python3
"""Unlock the GNOME keyrings with a YubiKey touch after auto-login.

Auto-login has no password for pam_gnome_keyring, so every keyring stays locked and the first
app that needs a secret asks for its password. `setup` checks each keyring's current password,
registers a credential on the YubiKey and seals the passwords with the key's hmac-secret.
`unlock` (run at sign-in) asks for a touch, unseals them and unlocks the keyrings.

Keyring passwords don't change, so the usual password prompt still works without the key. The
sealed file is useless without the YubiKey; with it, a touch is enough (no PIN, by choice).
"""
import argparse
import base64
import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fido  # noqa: E402

RP = 'zorin-keyring'
SECRETS = 'org.freedesktop.secrets'
ROOT = '/org/freedesktop/secrets'
SERVICE = 'org.freedesktop.Secret.Service'
COLLECTION = 'org.freedesktop.Secret.Collection'
INTERNAL = 'org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface'
WAIT_FOR_KEY = 120


def config_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'zorin11-hub' / 'yubikey-keyring.json'


def b64(data):
    return base64.b64encode(data).decode()


def unb64(text):
    return base64.b64decode(text.encode())


# Sealing -------------------------------------------------------------------------------------

def seal(key, collection, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return {'nonce': b64(nonce), 'data': b64(AESGCM(key).encrypt(nonce, password, collection.encode()))}


def unseal(key, collection, record):
    """The password, or None if this key didn't seal it (or the record was changed)."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        return AESGCM(key).decrypt(unb64(record['nonce']), unb64(record['data']), collection.encode())
    except (InvalidTag, KeyError, ValueError):
        return None


def load_config(path=None):
    path = path or config_path()
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None


def save_config(config, path=None):
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, path)


# GNOME keyring over D-Bus ----------------------------------------------------------------------

class Keyring:
    def __init__(self, bus=None):
        from gi.repository import Gio
        self.bus = bus or Gio.bus_get_sync(Gio.BusType.SESSION)
        self.session = None

    def _call(self, path, iface, method, params, reply):
        from gi.repository import Gio, GLib
        return self.bus.call_sync(SECRETS, path, iface, method, params,
                                  GLib.VariantType(reply) if reply else None,
                                  Gio.DBusCallFlags.NONE, 30000, None)

    def _prop(self, path, iface, name):
        from gi.repository import GLib
        return self._call(path, 'org.freedesktop.DBus.Properties', 'Get',
                          GLib.Variant('(ss)', (iface, name)), '(v)').unpack()[0]

    def collections(self):
        """Stored keyrings; the in-memory session keyring is left out."""
        return [p for p in self._prop(ROOT, SERVICE, 'Collections') if not p.endswith('/session')]

    def label(self, path):
        return self._prop(path, COLLECTION, 'Label')

    def locked(self, path):
        return self._prop(path, COLLECTION, 'Locked')

    def _secret(self, password):
        from gi.repository import GLib
        if self.session is None:
            self.session = self._call(ROOT, SERVICE, 'OpenSession',
                                      GLib.Variant('(sv)', ('plain', GLib.Variant('s', ''))), '(vo)').unpack()[1]
        return (self.session, b'', password, 'text/plain')

    def check_password(self, path, password):
        """True if `password` opens the keyring. Changes it to the same password: nothing moves."""
        from gi.repository import GLib
        secret = self._secret(password)
        try:
            self._call(ROOT, INTERNAL, 'ChangeWithMasterPassword',
                       GLib.Variant('(o(oayays)(oayays))', (path, secret, secret)), None)
            return True
        except GLib.Error:
            return False

    def unlock(self, path, password):
        from gi.repository import GLib
        try:
            self._call(ROOT, INTERNAL, 'UnlockWithMasterPassword',
                       GLib.Variant('(o(oayays))', (path, self._secret(password))), None)
        except GLib.Error:
            pass
        return not self.locked(path)

    def close(self):
        if self.session:
            try:
                self._call(self.session, 'org.freedesktop.Secret.Session', 'Close', None, None)
            except Exception:
                pass
            self.session = None


# Dialogs ---------------------------------------------------------------------------------------

def graphical():
    return bool(os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY')) and shutil.which('zenity')


def notify(text):
    if shutil.which('notify-send'):
        subprocess.run(['notify-send', '--app-name=Keyring', '--icon=security-high', 'Keyring', text],
                       check=False)
    else:
        print(text, file=sys.stderr)


def ask_secret(title, text):
    if graphical():
        r = subprocess.run(['zenity', '--entry', '--hide-text', f'--title={title}', f'--text={text}'],
                           capture_output=True)
        return r.stdout.rstrip(b'\n') if r.returncode == 0 else None
    try:
        return getpass.getpass(f'{text} ').encode()
    except (EOFError, KeyboardInterrupt):
        return None


def error(text):
    if graphical():
        subprocess.run(['zenity', '--error', '--title=Keyring', f'--text={text}'], check=False)
    else:
        print(text, file=sys.stderr)


def waiting(text):
    """A pulsing dialog with Cancel; None when there's no display."""
    if not graphical():
        print(text, file=sys.stderr)
        return None
    return subprocess.Popen(['zenity', '--progress', '--pulsate', '--title=Keyring',
                             f'--text={text}', '--auto-close'], stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def close_dialog(dialog):
    if dialog and dialog.poll() is None:
        dialog.terminate()
        dialog.wait()


def wait_for_key(timeout=WAIT_FOR_KEY):
    paths = fido.devices()
    if paths:
        return paths
    dialog = waiting('Insert your YubiKey to unlock your keyring.')
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline and (dialog is None or dialog.poll() is None):
            time.sleep(0.5)
            paths = fido.devices()
            if paths:
                return paths
        return []
    finally:
        close_dialog(dialog)


def with_touch(path, text, action):
    """Runs `action(device)` while a 'touch your key' dialog shows; Cancel stops the key waiting."""
    with fido.Device(path) as device:
        result, failure = [], []

        def run():
            try:
                result.append(action(device))
            except fido.FidoError as e:
                failure.append(e)

        worker = threading.Thread(target=run, daemon=True)
        dialog = waiting(text)
        worker.start()
        while worker.is_alive():
            worker.join(0.2)
            if dialog and dialog.poll() is not None and worker.is_alive():
                device.cancel()
                worker.join()
        close_dialog(dialog)
        if failure:
            raise failure[0]
        return result[0]


# Commands --------------------------------------------------------------------------------------

def find_passwords(keyring, ask=ask_secret):
    """{collection: password} for every stored keyring, checked; None if the user cancels."""
    found, tried = {}, []
    for path in keyring.collections():
        label = keyring.label(path) or path.rsplit('/', 1)[-1]
        match = next((p for p in tried if keyring.check_password(path, p)), None)
        attempts = 0
        while match is None:
            text = f'Password for the “{label}” keyring.\nThis is usually your sign-in password.'
            if attempts:
                text = f'That password didn\'t open “{label}”. Try again.'
            password = ask('Set up YubiKey keyring unlock', text)
            if password is None:
                return None
            attempts += 1
            if keyring.check_password(path, password):
                match = password
                tried.append(password)
        found[path] = (label, match)
    return found


def setup(args):
    keyring = Keyring()
    try:
        passwords = find_passwords(keyring)
        if passwords is None:
            print('Cancelled; nothing changed.')
            return 1
        if not passwords:
            error('No stored keyrings were found.')
            return 1
        paths = wait_for_key()
        if not paths:
            error('No YubiKey found.')
            return 1
        if len(paths) > 1:
            print('More than one security key is connected; using the first.', file=sys.stderr)
        user = os.environ.get('USER') or getpass.getuser()
        try:
            credential = with_touch(paths[0], 'Touch your YubiKey to register it for keyring unlock (1 of 2).',
                                    lambda d: d.register(RP, user))
        except fido.FidoError as e:
            if e.code != fido.ERR_PIN_REQUIRED:
                raise
            pin = ask_secret('YubiKey PIN', 'This YubiKey needs its PIN to register (only this once).')
            if pin is None:
                return 1
            credential = with_touch(paths[0], 'Touch your YubiKey to register it (1 of 2).',
                                    lambda d: d.register(RP, user, pin))
        salt = os.urandom(32)
        key = with_touch(paths[0], 'Touch your YubiKey again (2 of 2).',
                         lambda d: d.hmac_secret(RP, credential, salt))
        sealed = {path: {'label': label, **seal(key, path, pw)} for path, (label, pw) in passwords.items()}
        assert all(unseal(key, p, r) == passwords[p][1] for p, r in sealed.items())
        save_config({'version': 1, 'rp': RP, 'credential': b64(credential), 'salt': b64(salt),
                     'keyrings': sealed})
        names = ', '.join(label for label, _ in passwords.values())
        print(f'Keyring unlock is set up for: {names}.')
        return 0
    except fido.FidoError as e:
        error(f'The YubiKey stopped: {e}.' if not e.cancelled else 'Cancelled; nothing changed.')
        return 1
    finally:
        keyring.close()


def unlock(args):
    config = load_config()
    if not config:
        return 0
    keyring = Keyring()
    try:
        existing = set(keyring.collections())
        locked = [p for p in config['keyrings'] if p in existing and keyring.locked(p)]
        if not locked:
            return 0
        paths = wait_for_key()
        if not paths:
            return 1
        credential, salt = unb64(config['credential']), unb64(config['salt'])
        key = None
        for path in paths:
            try:
                key = with_touch(path, 'Touch your YubiKey to unlock your keyring.',
                                 lambda d: d.hmac_secret(config['rp'], credential, salt))
                break
            except fido.FidoError as e:
                if e.code != fido.ERR_NO_CREDENTIALS:
                    if not e.cancelled:
                        notify(f'YubiKey unlock failed: {e}.')
                    return 1
        if key is None:
            notify('This YubiKey isn\'t set up to unlock the keyring.')
            return 1
        failed = []
        for path in locked:
            password = unseal(key, path, config['keyrings'][path])
            if password is None or not keyring.unlock(path, password):
                failed.append(config['keyrings'][path].get('label') or path)
        if failed:
            notify(f'Couldn\'t unlock {", ".join(failed)}. If its password changed, set up YubiKey unlock again.')
            return 1
        return 0
    finally:
        keyring.close()


def status(args):
    config = load_config()
    if not config:
        print('Not set up.')
        return 1
    keyring = Keyring()
    try:
        existing = set(keyring.collections())
        for path, record in config['keyrings'].items():
            state = ('locked' if keyring.locked(path) else 'unlocked') if path in existing else 'missing'
            print(f"{record.get('label') or path}: {state}")
    finally:
        keyring.close()
    return 0


def forget(args):
    try:
        config_path().unlink()
        print('Removed. Keyrings keep their passwords; the YubiKey holds nothing to delete.')
    except FileNotFoundError:
        print('Not set up.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    for name, fn in [('setup', setup), ('unlock', unlock), ('status', status), ('forget', forget)]:
        sub.add_parser(name).set_defaults(fn=fn)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
