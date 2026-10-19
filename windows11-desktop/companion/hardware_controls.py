"""Validated power, radio and paired-device controls through native services."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import dbus

PROPERTIES = 'org.freedesktop.DBus.Properties'
POWER_SERVICES = (('org.freedesktop.UPower.PowerProfiles', '/org/freedesktop/UPower/PowerProfiles'),
                  ('net.hadess.PowerProfiles', '/net/hadess/PowerProfiles'))
PROFILE_NAMES = {'power-saver': 'Best power efficiency', 'balanced': 'Balanced', 'performance': 'Best performance'}
RFKILL = 'org.gnome.SettingsDaemon.Rfkill'
RFKILL_PATH = '/org/gnome/SettingsDaemon/Rfkill'
PROFILE_STATE = Path(os.environ.get('ZORIN11_CONFIG_DIR', str(Path.home()/'.config/zorin11-hub')))/'power-profile.json'
POWER_LOCK = threading.Lock()


@contextmanager
def connection(system=True):
    bus = dbus.SystemBus(private=True) if system else dbus.SessionBus(private=True)
    try: yield bus
    finally: bus.close()


def power_service(bus):
    for name, path in POWER_SERVICES:
        try:
            props = dbus.Interface(bus.get_object(name, path), PROPERTIES)
            return name, props, props.GetAll(name, timeout=2)
        except dbus.DBusException:
            continue
    raise ValueError('Power modes are unavailable on this system.')


def power_snapshot():
    try:
        with connection() as bus:
            _, _, data = power_service(bus)
        profiles = [str(p['Profile']) for p in data.get('Profiles', []) if p.get('Profile') in PROFILE_NAMES]
        active = str(data.get('ActiveProfile', ''))
        return dict(powerProfiles=[dict(id=p, name=PROFILE_NAMES[p]) for p in profiles], powerProfile=active,
                    batterySaver=active == 'power-saver', batterySaverAvailable='power-saver' in profiles,
                    powerDegraded=str(data.get('PerformanceDegraded') or data.get('PerformanceInhibited') or ''))
    except (dbus.DBusException, ValueError, OSError):
        return dict(powerProfiles=[], powerProfile='', batterySaver=False, batterySaverAvailable=False,
                    powerDegraded='', powerUnavailable='Power modes are unavailable on this system.')


def remember_profile(profile):
    PROFILE_STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.power-', dir=PROFILE_STATE.parent)
    try:
        with os.fdopen(fd, 'w') as stream: json.dump({'previous': profile}, stream)
        os.replace(temporary, PROFILE_STATE)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def previous_profile(profiles):
    try:
        data = json.loads(PROFILE_STATE.read_text()) if PROFILE_STATE.stat().st_size < 1024 else {}
        previous = data.get('previous')
        if previous in profiles and previous != 'power-saver': return previous
    except (OSError, ValueError, AttributeError, TypeError): pass
    if 'balanced' in profiles: return 'balanced'
    raise ValueError('No alternative power mode is available.')


def wait_property(props, interface, name, expected, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if props.Get(interface, name, timeout=2) == expected: return
        time.sleep(.08)
    raise RuntimeError('The system did not confirm the change. Check the current status and try again.')


def set_power(name, value):
    if name == 'batterySaver':
        if type(value) is not bool: raise ValueError('Battery saver needs an on/off value.')
    elif name != 'powerProfile' or not isinstance(value, str) or value not in PROFILE_NAMES:
        raise ValueError('Choose a supported power mode.')
    with POWER_LOCK, connection() as bus:
        interface, props, data = power_service(bus)
        profiles = [str(p['Profile']) for p in data.get('Profiles', []) if p.get('Profile') in PROFILE_NAMES]
        current = str(data.get('ActiveProfile', ''))
        if name == 'batterySaver':
            if (current == 'power-saver') == value: return
            target = 'power-saver' if value else previous_profile(profiles)
        else: target = value
        if target not in profiles: raise ValueError('That power mode is not supported by this device.')
        if target == current: return
        if target == 'performance' and data.get('PerformanceInhibited'):
            raise ValueError('Performance mode is currently unavailable: '+str(data['PerformanceInhibited']))
        if target == 'power-saver' and current in profiles: remember_profile(current)
        props.Set(interface, 'ActiveProfile', dbus.String(target), timeout=5)
        wait_property(props, interface, 'ActiveProfile', target)


def airplane_snapshot():
    try:
        with connection(False) as bus:
            data = dbus.Interface(bus.get_object(RFKILL, RFKILL_PATH), PROPERTIES).GetAll(RFKILL, timeout=2)
        hardware = bool(data.get('HardwareAirplaneMode'))
        return dict(airplane=bool(data.get('AirplaneMode')) or hardware,
                    airplaneAvailable=bool(data.get('HasAirplaneMode')), airplaneBlocked=hardware)
    except (dbus.DBusException, OSError):
        return dict(airplane=False, airplaneAvailable=False, airplaneBlocked=False)


def set_airplane(value):
    if type(value) is not bool: raise ValueError('Airplane mode needs an on/off value.')
    with connection(False) as bus:
        props = dbus.Interface(bus.get_object(RFKILL, RFKILL_PATH), PROPERTIES)
        state = props.GetAll(RFKILL, timeout=2)
        if not state.get('HasAirplaneMode'): raise ValueError('Airplane mode is unavailable on this system.')
        if state.get('HardwareAirplaneMode'): raise ValueError('Turn off the hardware airplane-mode switch first.')
        props.Set(RFKILL, 'AirplaneMode', dbus.Boolean(value), timeout=5)
        wait_property(props, RFKILL, 'AirplaneMode', value)


def bluetooth_snapshot(objects):
    devices = []
    for path, interfaces in objects.items():
        info = interfaces.get('org.bluez.Device1', {})
        if not info.get('Paired'): continue
        adapter = objects.get(info.get('Adapter'), {}).get('org.bluez.Adapter1', {})
        battery = interfaces.get('org.bluez.Battery1', {}).get('Percentage')
        devices.append(dict(id=str(path), name=str(info.get('Alias') or info.get('Name') or 'Bluetooth device'),
                            icon=str(info.get('Icon', 'bluetooth')), connected=bool(info.get('Connected')),
                            available=bool(adapter.get('Powered')) and not bool(info.get('Blocked')),
                            blocked=bool(info.get('Blocked')),
                            battery=int(battery) if battery is not None and 0 <= int(battery) <= 100 else None))
    return sorted(devices, key=lambda item:(not item['connected'], item['name'].casefold()))


def connect_bluetooth(ident, connected):
    if type(connected) is not bool or not isinstance(ident, str): raise ValueError('Choose a paired Bluetooth device.')
    with connection() as bus:
        manager = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager')
        objects = manager.GetManagedObjects(timeout=3)
        device = next((d for d in bluetooth_snapshot(objects) if d['id'] == ident), None)
        if not device: raise ValueError('This device is no longer paired. Pair it in Bluetooth settings.')
        if device['connected'] == connected: return
        if connected and not device['available']: raise ValueError('Turn on Bluetooth and unblock this device first.')
        obj = bus.get_object('org.bluez', ident)
        action = dbus.Interface(obj, 'org.bluez.Device1')
        if connected: action.Connect(timeout=15)
        else: action.Disconnect(timeout=10)
        wait_property(dbus.Interface(obj, PROPERTIES), 'org.bluez.Device1', 'Connected', connected)
