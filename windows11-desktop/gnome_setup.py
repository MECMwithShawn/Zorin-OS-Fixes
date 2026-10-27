"""Windows 11-inspired appearance using Zorin's existing GNOME extensions."""
import json
import os
from pathlib import Path
import tempfile

BACKUP = Path.home() / '.config/zorin11-gnome/integration-backup.json'
TASKBAR = 'org.gnome.shell.extensions.zorin-taskbar'
REQUIRED_EXTENSIONS = (
    'zorin-taskbar@zorinos.com',
    'zorin-menu@zorinos.com',
    'user-theme@gnome-shell-extensions.gcampax.github.com',
)


def bindings():
    from gi.repository import Gio, GLib
    return Gio, GLib


def monitor_ids():
    """Use connector/serial identities understood by Zorin Taskbar."""
    Gio, GLib = bindings()
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    result = bus.call_sync(
        'org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
        'org.gnome.Mutter.DisplayConfig', 'GetCurrentState', None, None,
        Gio.DBusCallFlags.NONE, 5000, None).unpack()
    ids=[]
    for index,logical in enumerate(result[2]):
        connector,vendor,product,serial=logical[5][0]
        ident=f'{vendor}-{serial}' if vendor and serial else str(index)
        if ident in ids:ident=connector if connector not in ids else str(index)
        ids.append(ident)
    return ids


def appearance(monitors):
    center = ['leftBox', 'showAppsButton', 'activitiesButton', 'taskbar']
    right = ['centerBox', 'rightBox', 'systemMenu', 'dateMenu', 'desktopButton']
    positions = [dict(element=name, visible=name not in ('showAppsButton','activitiesButton'),
                      position='centerMonitor' if name in center else 'stackedBR')
                 for name in center + right]
    return {
        'org.gnome.desktop.interface': {
            'gtk-theme': 'ZorinBlue-Dark', 'color-scheme': 'prefer-dark',
            'icon-theme': 'Win11-dark'},
        'org.gnome.desktop.wm.preferences': {
            'button-layout': 'appmenu:minimize,maximize,close'},
        'org.gnome.shell.extensions.user-theme': {'name': 'ZorinBlue-Dark'},
        'com.zorin.desktop.auto-theme': {'enabled': False},
        TASKBAR: {
            'panel-position': 'BOTTOM', 'panel-size': 48, 'panel-margin': 0,
            'panel-positions': json.dumps({m: 'BOTTOM' for m in monitors}),
            'panel-sizes': json.dumps({m: 48 for m in monitors}),
            'panel-element-positions': json.dumps({m: positions for m in monitors}),
            'group-apps': True, 'dot-style-focused': 'METRO',
            'dot-style-unfocused': 'DOTS', 'global-border-radius': 6,
            'progress-show-count': True, 'progress-show-bar': True,
            'show-showdesktop-icon': False, 'showdesktop-button-width': 8,
            'show-showdesktop-hover': True,
            'trans-use-custom-opacity': True, 'trans-panel-opacity': 0.95},
        'org.gnome.shell.extensions.zorin-menu': {'super-hotkey': True},
    }


def plan(changes):
    """Validate every setting before writing any desktop configuration."""
    Gio, GLib = bindings()
    source = Gio.SettingsSchemaSource.get_default()
    records = []
    for schema, values in changes.items():
        spec = source.lookup(schema, True)
        if spec is None:
            raise RuntimeError(f'Missing Zorin GNOME settings schema: {schema}')
        settings = Gio.Settings.new(schema)
        for key, value in values.items():
            if not spec.has_key(key) or not settings.is_writable(key):
                raise RuntimeError(f'Missing or locked setting: {schema} {key}')
            old = settings.get_value(key)
            new = GLib.Variant(old.get_type_string(), value)
            if not spec.get_key(key).range_check(new):
                raise RuntimeError(f'Unsupported setting value: {schema} {key}')
            records.append(dict(schema=schema, key=key, old=old.print_(True),
                                new=new.print_(True)))
    return records


def check():
    if os.geteuid() == 0:
        raise RuntimeError('Run as your desktop user, without sudo.')
    if 'GNOME' not in os.environ.get('XDG_CURRENT_DESKTOP', '').upper().split(':'):
        raise RuntimeError('Run inside your Zorin GNOME desktop session.')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'zorin' or release.get('VERSION_ID', '').strip('"') != '18':
        raise RuntimeError('The GNOME adaptation supports Zorin OS 18.')
    Gio, GLib = bindings()
    shell = Gio.Settings.new('org.gnome.shell')
    enabled = shell.get_strv('enabled-extensions')
    disabled = shell.get_strv('disabled-extensions')
    missing = [name for name in REQUIRED_EXTENSIONS if name not in enabled or name in disabled]
    if shell.get_boolean('disable-user-extensions') or missing:
        raise RuntimeError('Enable Zorin Taskbar, Zorin Menu and User Themes in Extensions before installing.')
    for path in ('/usr/share/themes/ZorinBlue-Dark', '/usr/share/gnome-shell/theme/ZorinBlue-Dark'):
        if not Path(path).is_dir():
            raise RuntimeError(f'Missing standard Zorin theme: {path}')
    import gi,importlib.util,shutil
    for name,version in [('Gtk','3.0'),('WebKit2','4.1'),('Wnck','3.0'),('Atspi','2.0'),('Gdm','1.0')]:gi.require_version(name,version)
    missing=[name for name in ('dbus','cairo','PIL') if importlib.util.find_spec(name) is None]
    missing += [name for name in ('gjs','glib-compile-schemas','update-desktop-database','git','flatpak','pactl','nmcli','Xwayland') if not shutil.which(name)]
    import subprocess
    if shutil.which('flatpak') and subprocess.run(['flatpak','info','io.missioncenter.MissionCenter'],capture_output=True).returncode:
        missing.append('Mission Center (Flatpak)')
    if missing:raise RuntimeError('Missing dependencies: '+', '.join(missing)+'. Run ./install-system-deps.sh')
    changes=appearance(monitor_ids())
    # Preserve settings for disconnected monitors, while overriding connected ones.
    for key in ('panel-positions','panel-sizes','panel-element-positions'):
        old=json.loads(Gio.Settings.new(TASKBAR).get_string(key))
        old.update(json.loads(changes[TASKBAR][key]));changes[TASKBAR][key]=json.dumps(old)
    records = plan(changes)
    print('Ready: Zorin 18 GNOME, existing taskbar/menu, dark theme; X11 or Wayland.')
    return records


def save(records, path=BACKUP):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.backup-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(records, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def merge_original(records, previous):
    original = {(r['schema'], r['key']): r for r in previous}
    merged = dict(original)
    for item in records:
        identity = item['schema'], item['key']
        merged[identity] = dict(item, old=original.get(identity, item)['old'])
    return list(merged.values())


def install(records, path=BACKUP):
    Gio, GLib = bindings()
    previous = json.loads(path.read_text()) if path.exists() else []
    save(merge_original(records, previous), path)
    for item in records:
        settings = Gio.Settings.new(item['schema'])
        if not settings.set_value(item['key'], GLib.Variant.parse(None, item['new'], None, None)):
            raise RuntimeError(f"Could not apply {item['key']}; recovery record: {path}")
    Gio.Settings.sync()
    for item in records:
        actual = Gio.Settings.new(item['schema']).get_value(item['key']).print_(True)
        if actual != item['new']:
            raise RuntimeError(f"Setting did not persist: {item['key']}")
    print(f'Applied and verified {len(records)} settings. Recovery record: {path}')
    print('GNOME appearance settings applied.')


def restore(path=BACKUP):
    if os.geteuid() == 0:
        raise RuntimeError('Run as your desktop user, without sudo.')
    if not path.exists():
        print('No GNOME recovery record found; nothing to restore.')
        return
    Gio, GLib = bindings()
    remaining = []
    for item in json.loads(path.read_text()):
        try:
            source = Gio.SettingsSchemaSource.get_default()
            spec = source.lookup(item['schema'], True)
            if spec is None or not spec.has_key(item['key']):
                raise RuntimeError('Schema/key unavailable in this session')
            settings = Gio.Settings.new(item['schema'])
            if settings.get_value(item['key']).print_(True) != item['new']:
                print('Preserving later change:', item['key'])
                continue
            if not settings.set_value(item['key'], GLib.Variant.parse(None, item['old'], None, None)):
                raise RuntimeError('Setting is not writable')
        except Exception as error:
            print('Could not restore', item['key'], ':', error)
            remaining.append(item)
    Gio.Settings.sync()
    if remaining:
        save(remaining, path)
        raise RuntimeError('Some settings could not be restored; their recovery records were retained.')
    path.unlink()
    print('Previous GNOME settings restored. Downloaded icon themes remain available.')
