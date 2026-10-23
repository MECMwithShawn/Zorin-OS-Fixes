"""User-side pre-update snapshots and conservative post-update layout repair."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time

import desktop_backup as backup

HOME = Path.home()
ROOT = HOME/'.local/state/zorin11-update-guard'
STATE = ROOT/'state.json'
MANAGED_EXTENSIONS = {
    'zorin11@zorin-os-fixes', 'zorin11-audio@zorin-os-fixes', 'zorin11-motion@zorin-os-fixes',
    'zorin11-desktop@zorin-os-fixes', 'zorin-taskbar@zorinos.com',
    'zorin-menu@zorinos.com', 'user-theme@gnome-shell-extensions.gcampax.github.com',
    'zorin-window-move-effect@zorinos.com',
}
SCALARS = {
    'org.gnome.desktop.interface': {'gtk-theme', 'icon-theme', 'color-scheme'},
    'org.gnome.desktop.wm.preferences': {'button-layout'},
    'org.gnome.shell.extensions.user-theme': {'name'},
    'com.zorin.desktop.auto-theme': {'enabled'},
    'org.gnome.shell': {'favorite-apps'},
    'org.gnome.mutter': {'dynamic-workspaces'},
    'org.gnome.shell.extensions.zorin-menu': {'super-hotkey'},
    'org.gnome.shell.keybindings': {'toggle-application-view', 'focus-active-notification'},
    'org.gnome.desktop.wm.keybindings': {'switch-applications', 'switch-applications-backward',
                                       'switch-windows', 'switch-windows-backward'},
}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.guard-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def package_busy():
    """Read kernel POSIX lock inventory without opening root-only dpkg locks."""
    try:
        identities = set()
        for path in ('/var/lib/dpkg/lock', '/var/lib/dpkg/lock-frontend'):
            info = Path(path).stat()
            identities.add((os.major(info.st_dev), os.minor(info.st_dev), info.st_ino))
        for line in Path('/proc/locks').read_text().splitlines():
            for major, minor, inode in re.findall(r'\b([0-9a-f]+):([0-9a-f]+):(\d+)\b', line):
                if (int(major, 16), int(minor, 16), int(inode)) in identities:
                    return True
        return False
    except OSError:
        return True


def compatible():
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    version = subprocess.check_output(['gnome-shell', '--version'], text=True).strip()
    if release.get('ID', '').strip('"') != 'zorin' or release.get('VERSION_ID', '').strip('"') != '18':
        return 'OS version changed; review layout compatibility.'
    if not re.search(r'\b46(?:\.|$)', version):
        return 'GNOME major version changed; automatic layout repair paused.'
    for theme in ('/usr/share/themes/ZorinBlue-Dark', '/usr/share/gnome-shell/theme/ZorinBlue-Dark'):
        if not Path(theme).is_dir():
            return 'The required Zorin theme is unavailable; review appearance compatibility.'
    vendor = Path('/usr/share/gnome-shell/extensions/zorin-desktop-icons@zorinos.com/app')
    try:
        text = (vendor/'desktopManager.js').read_text()
        if not all(token in text for token in ('_createDesktopBackgroundMenu()', '_drawDesktop(', '_prepareMenu()', '_updateDesktop()', 'doNewFolder(', 'doSorts(')):
            return 'Zorin Desktop Icons API changed; review the desktop adapter.'
    except OSError:
        return 'Zorin Desktop Icons is unavailable.'
    return None


def session_active():
    from gi.repository import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', ('org.gnome.Shell',)),
            None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
    except GLib.Error:
        return False


def protected_file(name):
    """Never restore Explorer, OneDrive code, personal state or vendor files."""
    if not name.startswith('home/'):
        return False
    relative = Path(name[5:])
    if relative.is_absolute() or '..' in relative.parts:
        return False
    value = relative.as_posix()
    if value.startswith('.local/share/gnome-shell/extensions/zorin11'):
        return len(relative.parts) >= 6 and relative.parts[4] in MANAGED_EXTENSIONS
    if value.startswith(('.local/share/icons/Win11/', '.local/share/icons/Win11-dark/')):
        return True
    if value == '.config/gtk-3.0/gtk.css':
        return True
    if relative.parent == Path('.local/share/applications'):
        return relative.name.startswith('zorin11') and relative.suffix == '.desktop' or relative.name in {
            'gnome-background-panel.desktop', 'gnome-display-panel.desktop', 'gnome-sound-panel.desktop'}
    return False


def capture_profile():
    from gi.repository import Gio
    journal = HOME/'.config/zorin11-gnome/integration-backup.json'
    owned = json.loads(journal.read_text()) if journal.exists() else []
    result = []
    for record in owned:
        schema, key = record['schema'], record['key']
        if schema == 'org.gnome.shell.extensions.zorin-taskbar' or key in SCALARS.get(schema, set()):
            settings = Gio.Settings.new(schema)
            result.append({'schema':schema, 'key':key,
                'wanted':settings.get_value(key).print_(True), 'original':record['old']})
    shell = Gio.Settings.new('org.gnome.shell')
    return {'settings':result,
        'enabled':[x for x in shell.get_strv('enabled-extensions') if x in MANAGED_EXTENSIONS],
        'disabled':[x for x in shell.get_strv('disabled-extensions') if x in MANAGED_EXTENSIONS],
        'extensions_paused':shell.get_boolean('disable-user-extensions'),
        'wallpaper':{key:Gio.Settings.new('org.gnome.desktop.background').get_string(key)
            for key in ('picture-uri', 'picture-uri-dark', 'picture-options')}}


def before(transaction=None):
    state = load()
    # APT may invoke dpkg repeatedly in one update. Retain the first pre-update
    # baseline until the package locks are gone and the repair pass completes.
    if transaction and state.get('transaction') == transaction and state.get('pending') and time.time()-state.get('created', 0) < 3600:
        if Path(state.get('archive', '')).is_file() and (Path(state.get('destination', ''))/'desktop-snapshot.tar.gz').is_file():
            backup.configured_destination()  # also enforce the required mount
            state['last_event'] = time.time()
            save(STATE, state)
            print('Reusing verified pre-update snapshot:', state['destination'])
            return
    destination = backup.configured_destination()
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.capture-', dir=ROOT) as directory:
        staged = Path(directory)
        profile = capture_profile()
        archive = staged/'snapshot.tar.gz'
        published = backup.create_snapshot(destination, retain=archive,
            extra={'purpose':'automatic-before-apt-update'})
        # Save the pre-update profile together with the exact local repair copy.
        name = 'baseline-'+str(time.time_ns())
        baseline = ROOT/name
        staged.rename(baseline)
        state = {'pending':True, 'created':time.time(), 'last_event':time.time(),
                 'transaction':transaction,
                 'destination':str(published), 'archive':str(baseline/'snapshot.tar.gz'),
                 'archive_sha256':backup.digest(baseline/'snapshot.tar.gz'),
                 'profile':profile, 'status':'backed-up'}
        save(STATE, state)
    # Keep two local repair copies. Never prune the OneDrive snapshots.
    previous = sorted(ROOT.glob('baseline-*'), key=lambda p:p.name, reverse=True)
    for old in previous[2:]:
        if old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)
    print('Verified pre-update backup:', published)


def restore_missing(archive, home=HOME):
    repaired, skipped = [], []
    manifest = backup.verify_archive(archive)
    with tarfile.open(archive, 'r:gz') as bundle:
        members = {member.name:member for member in bundle.getmembers()}
        for record in manifest['entries']:
            name = record['path']
            if not protected_file(name):
                continue
            path = home/name[5:]
            # Do not follow a substituted parent into OneDrive or another tree.
            if any(p.is_symlink() for p in [path.parent, *path.parents] if p != home and p.is_relative_to(home)):
                skipped.append(name+': parent is a symlink')
                continue
            if path.exists() or path.is_symlink():
                continue  # preserve edited files, even if different from backup
            path.parent.mkdir(parents=True, exist_ok=True)
            member = members[name]
            if record['kind'] == 'symlink':
                path.symlink_to(record['target'])
            else:
                fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.guard-')
                try:
                    with os.fdopen(fd, 'wb') as output:
                        shutil.copyfileobj(bundle.extractfile(member), output)
                        output.flush(); os.fsync(output.fileno())
                    os.chmod(temp, member.mode & 0o777)
                    # No replacement if another editor created the file meanwhile.
                    os.link(temp, path)
                except FileExistsError:
                    continue
                finally:
                    os.unlink(temp)
            repaired.append(name)
    return repaired, skipped


def settings_repair(profile):
    from gi.repository import Gio, GLib
    source = Gio.SettingsSchemaSource.get_default()
    repaired, skipped = [], []
    for record in profile['settings']:
        schema, key = record['schema'], record['key']
        label = schema+' '+key
        spec = source.lookup(schema, True)
        if not spec or not spec.has_key(key):
            skipped.append(label+': missing schema/key'); continue
        settings = Gio.Settings.new(schema)
        actual = settings.get_value(key).print_(True)
        if actual == record['wanted']:
            continue
        default = settings.get_default_value(key).print_(True)
        if actual not in (default, record['original']):
            skipped.append(label+': preserving later customization'); continue
        wanted = GLib.Variant.parse(None, record['wanted'], None, None)
        if not settings.is_writable(key) or not spec.get_key(key).range_check(wanted):
            skipped.append(label+': incompatible or locked'); continue
        if settings.set_value(key, wanted):
            repaired.append(label)
    shell = Gio.Settings.new('org.gnome.shell')
    if not profile['extensions_paused'] and not shell.get_boolean('disable-user-extensions'):
        for key in ('enabled', 'disabled'):
            setting = key+'-extensions'
            actual = shell.get_strv(setting)
            opposite = ('disabled' if key == 'enabled' else 'enabled')+'-extensions'
            conflicts = shell.get_strv(opposite)
            missing = [x for x in profile[key] if x not in actual or x in conflicts]
            accepted = []
            for ident in missing:
                roots = (HOME/'.local/share/gnome-shell/extensions', Path('/usr/share/gnome-shell/extensions'))
                metadata = next((r/ident/'metadata.json' for r in roots if (r/ident/'metadata.json').is_file()), None)
                if key == 'enabled' and (not metadata or '46' not in json.loads(metadata.read_text()).get('shell-version', [])):
                    skipped.append(ident+': missing or incompatible extension'); continue
                accepted.append(ident)
            # Membership-only repair preserves every unrelated extension.
            if accepted:
                shell.set_strv(setting, list(dict.fromkeys(actual+accepted)))
                shell.set_strv(opposite, [x for x in conflicts if x not in accepted])
                repaired.append(setting)
    elif not profile['extensions_paused']:
        skipped.append('User extensions globally paused; preserving pause')
    wallpaper = Gio.Settings.new('org.gnome.desktop.background')
    prefs = HOME/'.config/zorin11-hub/wallpapers.json'
    data = json.loads(prefs.read_text()) if prefs.exists() else {}
    current_picture = Path(data.get('appliedPath') or '/nonexistent')
    for key in ('picture-uri', 'picture-uri-dark'):
        actual = wallpaper.get_string(key)
        from urllib.parse import urlparse, unquote
        uri = urlparse(actual)
        missing = uri.scheme == 'file' and not Path(unquote(uri.path)).is_file()
        if actual == wallpaper.get_default_value(key).unpack() or missing:
            desired = current_picture.as_uri() if current_picture.is_file() else profile['wallpaper'][key]
            parsed = urlparse(desired)
            if parsed.scheme == 'file' and Path(unquote(parsed.path)).is_file() and actual != desired:
                wallpaper.set_string(key, desired); repaired.append(key)
    Gio.Settings.sync()
    return repaired, skipped


def repair():
    state = load()
    if not state.get('pending'):
        return
    if time.time()-state['last_event'] < 60 or package_busy() or not session_active():
        return
    reason = compatible()
    if reason:
        state.update(pending=False, status='needs-review', details=[reason])
    else:
        archive = Path(state['archive'])
        if backup.digest(archive) != state['archive_sha256']:
            raise RuntimeError('Repair archive changed; refusing restoration.')
        files, skipped = restore_missing(archive)
        settings, notes = settings_repair(state['profile'])
        state.update(pending=False, status='needs-review' if skipped+notes else 'checked',
                     repaired=files+settings, details=skipped+notes, checked=time.time())
        if files:
            subprocess.run(['update-desktop-database', str(HOME/'.local/share/applications')], check=True)
    save(STATE, state)
    if state['status'] == 'needs-review' and shutil.which('notify-send'):
        subprocess.run(['notify-send', 'Windows 11 desktop protection',
            'Your desktop needs a compatibility check after this update. Automatic repair has been paused.'], check=False)
    print(json.dumps({key:state.get(key) for key in ('status','repaired','details')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('before','after','repair','status'))
    parser.add_argument('--transaction')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Desktop guard must run as the desktop user.')
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT/'guard.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'before':
            before(args.transaction)
        elif args.action == 'after':
            state = load()
            if state.get('pending'):
                state['last_event'] = time.time()
                save(STATE, state)
        elif args.action == 'repair':
            try:
                repair()
            except Exception as error:
                state = load()
                state.update(pending=False, status='needs-review', details=[str(error)])
                save(STATE, state)
                if shutil.which('notify-send'):
                    subprocess.run(['notify-send', 'Windows 11 desktop protection',
                                    'Automatic repair stopped safely: '+str(error)], check=False)
                raise
        else:
            print(json.dumps(load(), indent=2))


if __name__ == '__main__':
    main()
