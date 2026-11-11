#!/usr/bin/env python3
"""Unlock the GNOME keyrings with a YubiKey touch after auto-login.

Auto-login has no password for pam_gnome_keyring, so every keyring stays locked and the first
app that needs a secret asks for its password. `setup` checks each keyring's current password,
registers a credential on the YubiKey and seals the passwords with the key's hmac-secret.
`unlock` (run at sign-in) opens GNOME's own keyring prompt, and the desktop extension answers it
with `password`: a touch, then the sealed password goes into the prompt. Apps that ask for the
keyring before that get the same prompt, so the touch works whoever asked first.

Keyring passwords don't change, so the usual password prompt still works without the key. The
sealed file is useless without the YubiKey; with it, a touch is enough (no PIN, by choice).
"""
import argparse
import base64
import getpass
import json
import os
import re
import shutil
import signal
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
WAIT_FOR_UNLOCK = 180  # login apps hold off this long at most, then start anyway


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

    def prompt_unlock(self, paths, timeout=600):
        """Asks gnome-keyring to unlock `paths` with its own prompt; True unless it was dismissed."""
        from gi.repository import GLib
        prompt = self._call(ROOT, SERVICE, 'Unlock', GLib.Variant('(ao)', (list(paths),)), '(aoo)').unpack()[1]
        if prompt == '/':
            return True
        loop, result = GLib.MainLoop(), {}

        def completed(_conn, _sender, _path, _iface, _signal, params):
            result['dismissed'] = params.unpack()[0]
            loop.quit()
        sub = self.bus.signal_subscribe(SECRETS, 'org.freedesktop.Secret.Prompt', 'Completed', prompt,
                                        None, 0, completed)
        try:
            self._call(prompt, 'org.freedesktop.Secret.Prompt', 'Prompt', GLib.Variant('(s)', ('',)), None)
            timer = GLib.timeout_add_seconds(timeout, loop.quit)
            loop.run()
            if 'dismissed' in result:
                GLib.source_remove(timer)
            else:
                try:
                    self._call(prompt, 'org.freedesktop.Secret.Prompt', 'Dismiss', None, None)
                except GLib.Error:
                    pass
        finally:
            self.bus.signal_unsubscribe(sub)
        return result.get('dismissed') is False

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


def wait_for_key(timeout=WAIT_FOR_KEY, text='Insert your YubiKey to unlock your keyring.', stop=None):
    """Connected key paths, waiting up to `timeout` for one; `text=None` waits without a dialog."""
    paths = fido.devices()
    if paths:
        return paths
    dialog = waiting(text) if text else None
    deadline = time.monotonic() + timeout
    try:
        while (time.monotonic() < deadline and (dialog is None or dialog.poll() is None)
               and not (stop and stop.is_set())):
            time.sleep(0.5)
            paths = fido.devices()
            if paths:
                return paths
        return []
    finally:
        close_dialog(dialog)


def with_touch(path, text, action, stop=None):
    """Runs `action(device)` while a 'touch your key' dialog shows; Cancel stops the key waiting.

    `text=None` shows no dialog; setting `stop` (SIGTERM from the desktop prompt) cancels too."""
    with fido.Device(path) as device:
        result, failure = [], []

        def run():
            try:
                result.append(action(device))
            except fido.FidoError as e:
                failure.append(e)

        worker = threading.Thread(target=run, daemon=True)
        dialog = waiting(text) if text else None
        worker.start()
        while worker.is_alive():
            worker.join(0.2)
            gave_up = (dialog and dialog.poll() is not None) or (stop and stop.is_set())
            if gave_up and worker.is_alive():
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


def done_marker():
    return Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}') / 'zorin11-yubikey-unlock.done'


def session_started():
    """When this graphical sign-in began (epoch seconds), or None before the desktop is up."""
    try:
        out = subprocess.run(['systemctl', '--user', 'show', 'graphical-session.target',
                              '-p', 'ActiveState', '-p', 'ActiveEnterTimestampMonotonic'],
                             capture_output=True, text=True, timeout=5).stdout
        props = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
        if props.get('ActiveState') != 'active':
            return None
        mono = int(props['ActiveEnterTimestampMonotonic']) / 1e6
        return time.time() - (time.monotonic() - mono)
    except Exception:
        return None


def prompt_collection(config, description):
    """The configured keyring a gnome-keyring unlock prompt is about, from its description."""
    records = (config or {}).get('keyrings', {})
    text = (description or '').strip()
    if 'login keyring' in text.lower():
        return next((p for p in records if p.rsplit('/', 1)[-1] == 'login'), None)
    match = re.search(r'[“"](.+?)[”"]', text)
    if not match:
        return None
    return next((p for p, r in records.items() if r.get('label') == match.group(1)), None)


def touch_for_key(config, paths, text=None, stop=None):
    """The hmac-secret from the first key holding our credential; None if none does."""
    credential, salt = unb64(config['credential']), unb64(config['salt'])
    for path in paths:
        try:
            return with_touch(path, text, lambda d: d.hmac_secret(config['rp'], credential, salt), stop=stop)
        except fido.FidoError as e:
            if e.code != fido.ERR_NO_CREDENTIALS:
                raise
    return None


def password(args):
    """For the desktop's keyring prompt: waits for a key and a touch, then prints the password.

    Exit 3 when the prompt isn't for a keyring set up here, 1 when the key is missing, fails or is
    cancelled (SIGTERM, when the prompt closes). The other set-up keyrings are unlocked on the way,
    so they don't each ask again."""
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    config = load_config()
    target = prompt_collection(config, args.prompt)
    if not target:
        return 3
    paths = wait_for_key(args.wait, text=None, stop=stop)
    if not paths or stop.is_set():
        return 1
    try:
        key = touch_for_key(config, paths, stop=stop)
    except fido.FidoError as e:
        print(f'YubiKey: {e}', file=sys.stderr)
        return 1
    secret = key and unseal(key, target, config['keyrings'][target])
    if not secret or stop.is_set():
        return 1
    keyring = None
    try:
        keyring = Keyring()
        existing = set(keyring.collections())
        for path, record in config['keyrings'].items():
            if path != target and path in existing and keyring.locked(path):
                other = unseal(key, path, record)
                if other:
                    keyring.unlock(path, other)
    except Exception as e:  # the prompted keyring still opens
        print(f'Other keyrings: {e}', file=sys.stderr)
    finally:
        if keyring:
            keyring.close()
    sys.stdout.buffer.write(secret)
    sys.stdout.flush()
    return 0


def desktop_prompt_ready(wait=10):
    """True when the desktop extension answers GNOME's keyring prompt with the YubiKey."""
    from gi.repository import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    except GLib.Error:
        return False
    deadline = time.monotonic() + wait
    while True:
        try:
            reply = bus.call_sync('local.zorin11.Gnome', '/local/zorin11/Gnome', 'local.zorin11.Gnome', 'Call',
                                  GLib.Variant('(s)', (json.dumps({'op': 'yubikey-prompt'}),)),
                                  GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            return json.loads(reply) is True
        except GLib.Error as e:
            if 'Unknown operation' in (e.message or '') or time.monotonic() > deadline:
                return False  # an older extension, or none: fall back to our own dialogs
            time.sleep(0.5)


def unlock(args):
    try:
        return _unlock()
    finally:
        # Tells `wait` this sign-in's unlock attempt is over, whatever the outcome.
        try:
            done_marker().touch()
        except OSError:
            pass


def wait(args):
    """Holds a login app back until the YubiKey unlock is over, so it doesn't pop GNOME's password box.

    Returns once the keyrings are unlocked, this sign-in's unlock attempt has finished (key
    missing, cancelled), or the timeout passes. Always exits 0: the app starts either way."""
    config = load_config()
    if not config:
        return 0
    began = time.time()
    deadline = time.monotonic() + args.timeout
    keyring = None
    while time.monotonic() < deadline:
        try:
            keyring = keyring or Keyring()
            existing = set(keyring.collections())
            if not any(p in existing and keyring.locked(p) for p in config['keyrings']):
                return 0
        except Exception:
            keyring = None  # secret service not up yet
        try:
            since = session_started() or began
            if done_marker().stat().st_mtime >= since - 1:
                return 0
        except OSError:
            pass
        time.sleep(1)
    return 0


def _unlock():
    config = load_config()
    if not config:
        return 0
    keyring = Keyring()
    try:
        existing = set(keyring.collections())
        locked = [p for p in config['keyrings'] if p in existing and keyring.locked(p)]
        if not locked:
            return 0
        if desktop_prompt_ready():
            # One prompt for everyone: GNOME's, which the desktop extension fills after a touch.
            keyring.prompt_unlock(locked)
            still = [p for p in locked if keyring.locked(p)]
            return 1 if still else 0
        return _unlock_with_dialogs(config, keyring, locked)
    finally:
        keyring.close()


def _unlock_with_dialogs(config, keyring, locked):
    """Without the desktop extension: our own 'insert' and 'touch' dialogs."""
    paths = wait_for_key()
    if not paths:
        return 1
    try:
        key = touch_for_key(config, paths, text='Touch your YubiKey to unlock your keyring.')
    except fido.FidoError as e:
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
    answer = sub.add_parser('password', help="for GNOME's keyring prompt: touch, then print the password")
    answer.add_argument('--prompt', required=True, help="the prompt's description")
    answer.add_argument('--wait', type=float, default=600, help='seconds to wait for the key to be plugged in')
    answer.set_defaults(fn=password)
    waiter = sub.add_parser('wait', help='hold a login app back until the YubiKey unlock is over')
    waiter.add_argument('--timeout', type=float, default=WAIT_FOR_UNLOCK)
    waiter.set_defaults(fn=wait)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
