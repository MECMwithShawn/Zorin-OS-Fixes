"""Inside a private D-Bus session (see test_yubikey.PrivateKeyring): starts its own
gnome-keyring-daemon, then checks password checking, unlocking and the whole `unlock` command
with a stand-in for the YubiKey."""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'yubikey'))
import keyring_unlock as ku  # noqa: E402
from gi.repository import Gio, GLib  # noqa: E402

assert os.environ['HOME'].startswith('/tmp') or 'tmp' in os.environ['HOME'], 'private HOME only'
daemon = subprocess.Popen(['gnome-keyring-daemon', '--start', '--foreground', '--components=secrets'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    for _ in range(100):
        if bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
                         GLib.Variant('(s)', (ku.SECRETS,)), GLib.VariantType('(b)'),
                         Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]:
            break
        time.sleep(0.1)
    k = ku.Keyring(bus)

    def create(label, password):
        props = {'org.freedesktop.Secret.Collection.Label': GLib.Variant('s', label)}
        return k._call(ku.ROOT, ku.INTERNAL, 'CreateWithMasterPassword',
                       GLib.Variant('(a{sv}(oayays))', (props, k._secret(password))), '(o)').unpack()[0]

    def lock(path):
        k._call(ku.ROOT, ku.SERVICE, 'Lock', GLib.Variant('(ao)', ([path],)), '(aoo)')

    one, two = create('One', b'pw-one'), create('Two', b'pw-one')
    three = create('Three', b'pw-three')
    assert not k.locked(one)
    assert not k.check_password(one, b'wrong')
    assert not k.locked(one), 'a wrong check leaves it unlocked'
    assert k.check_password(one, b'pw-one')
    assert k.check_password(one, b'pw-one'), 'checking changed nothing'
    lock(one)
    assert k.locked(one)
    assert not k.unlock(one, b'wrong') and k.locked(one)
    assert k.unlock(one, b'pw-one')

    # Setup asks once per distinct password: Two reuses One's.
    asked = []
    answers = iter([b'nope', b'pw-one', b'pw-three'])

    def ask(title, text):
        asked.append(text)
        return next(answers)
    found = ku.find_passwords(k, ask)
    assert {p: pw for p, (_, pw) in found.items() if p in (one, two, three)} == \
        {one: b'pw-one', two: b'pw-one', three: b'pw-three'}, found
    assert len(asked) == 3 and 'didn' in asked[1], asked

    # The whole unlock command, with a stand-in key.
    key = os.urandom(32)
    ku.save_config({'version': 1, 'rp': ku.RP, 'credential': ku.b64(b'id'), 'salt': ku.b64(b's' * 32),
                    'keyrings': {p: {'label': l, **ku.seal(key, p, pw)} for p, (l, pw) in found.items()}})
    ku.fido.devices = lambda: [b'/dev/fake']
    ku.with_touch = lambda path, text, action, stop=None: key
    ku.desktop_prompt_ready = lambda: False  # no desktop extension here: our own dialogs
    ku.notify = lambda text: print('notify:', text)
    for p in found:
        lock(p)
    assert all(k.locked(p) for p in found)
    assert ku.unlock(None) == 0
    assert not any(k.locked(p) for p in found), 'every keyring unlocked'
    assert ku.unlock(None) == 0, 'nothing locked: nothing to do'

    # Another key's secret unlocks nothing and says so.
    lock(one)
    ku.with_touch = lambda path, text, action, stop=None: os.urandom(32)
    assert ku.unlock(None) == 1 and k.locked(one)
    k.close()
    print('PASS')
finally:
    daemon.terminate()
    daemon.wait()
