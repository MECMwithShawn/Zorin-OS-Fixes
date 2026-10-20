"""Verified, dated backups of the installed desktop; no automatic restore."""
import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid

HOME = Path.home()
SETTINGS = HOME/'.config/zorin11-gnome/backup-settings.json'
EXCLUDED = {'__pycache__', 'node_modules', '.git', 'target', '.pytest_cache'}
GUIDE = """Axentra Windows 11 desktop snapshot

This archive records the installed desktop, not a generic installer release.
Verify SHA256SUMS before use. manifest.json lists every archived file and its hash.
home/ contains selected user configuration, launchers, installed theme code/icons,
SnippingTool and wallpapers. profile/ contains current GNOME settings and the
account photo when readable. reference/ contains OS and vendor-version evidence.

Restore into a staging directory first. Compare the manifest, installed GNOME
version, and current files before restoring selected components. Never extract
the entire archive over your home directory: Explorer, OneDrive integration,
account settings and other apps may have received newer changes.

gnome-settings.json describes the CURRENT Windows-style settings. The original
integration/files recovery journals undo theme installation; they are not the
same as restoring this snapshot. Monitor configuration is reference-only.
Symlinks are recorded without following them. Vendor files are reference copies,
not instructions to overwrite OS-managed files. No OneDrive credentials, browser
profiles, personal document trees or thumbnail cache are collected.

These backups may contain personal pins, paths, wallpaper and your account photo.
Keep them private. A successful local write does not confirm cloud upload.
"""


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def configured_destination(settings=SETTINGS):
    data = json.loads(settings.read_text())
    destination = Path(data['destination']).expanduser()
    # A missing OneDrive mount must not silently turn into a local-only backup.
    mount = data.get('required_mount')
    if mount and not Path(mount).is_mount():
        raise RuntimeError('Backup mount is unavailable: '+mount)
    return destination


def remember_destination(destination, settings=SETTINGS):
    destination = Path(destination).absolute()
    mount = next((p for p in [destination, *destination.parents]
                  if p.is_mount() and p != Path('/')), None)
    settings.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.with_suffix('.tmp')
    temporary.write_text(json.dumps({'destination':str(destination),
                                    'required_mount':str(mount) if mount else None}, indent=2)+'\n')
    temporary.chmod(0o600)
    temporary.replace(settings)


def collect(home=HOME):
    """Explicit desktop-owned roots; never recurse through OneDrive or links."""
    result = {}
    roots = ['.local/share/zorin11-hub', '.config/zorin11-hub',
             '.config/zorin11-gnome', '.config/zorin11-snipping-tool',
             '.local/share/icons/Win11', '.local/share/icons/Win11-dark',
             '.local/bin/zorin11-snipping-tool', '.config/gtk-3.0/gtk.css',
             '.config/wezterm/wezterm.lua', '.config/zorin-mimeapps.list']
    roots += [str(p.relative_to(home)) for pattern in (
        '.local/share/gnome-shell/extensions/zorin11*',
        '.local/share/applications/zorin11*.desktop',
        '.config/autostart/zorin11*.desktop',
        '.config/systemd/user/zorin11*.service',
        '.config/systemd/user/zorin11*.timer',
    ) for p in home.glob(pattern)]
    roots += ['.local/share/applications/'+name+'.desktop' for name in
              ('gnome-background-panel', 'gnome-display-panel', 'org.gnome.Settings',
               'gnome-sound-panel', 'gnome-bluetooth-panel', 'org.gnome.Nautilus',
               'org.gnome.SystemMonitor', 'io.missioncenter.MissionCenter')]

    def walk(path, name):
        try: mode = path.lstat().st_mode
        except FileNotFoundError: return
        if path.name in EXCLUDED or path.suffix in ('.pyc', '.lock', '.tmp'):
            return
        if stat.S_ISLNK(mode) or stat.S_ISREG(mode):
            result[name] = path
        elif stat.S_ISDIR(mode):
            for child in sorted(path.iterdir()):
                walk(child, name+'/'+child.name)

    for relative in roots:
        walk(home/relative, 'home/'+relative)
    vendor = Path('/usr/share/gnome-shell/extensions')
    for name in ('zorin-desktop-icons@zorinos.com', 'zorin-taskbar@zorinos.com'):
        walk(vendor/name, 'reference/vendor/'+name)
    for path, name in [(Path('/etc/os-release'), 'reference/os-release'),
                       (home/'.config/monitors.xml', 'reference/monitors.xml')]:
        if path.is_file():
            result[name] = path
    return result


def current_settings(home=HOME):
    from gi.repository import Gio
    source = Gio.SettingsSchemaSource.get_default()
    for schema_dir in (home/'.local/share/gnome-shell/extensions').glob('zorin11*/schemas'):
        if (schema_dir/'gschemas.compiled').is_file():
            source = Gio.SettingsSchemaSource.new_from_directory(str(schema_dir), source, False)
    requests = {}
    journal = home/'.config/zorin11-gnome/integration-backup.json'
    for record in json.loads(journal.read_text()) if journal.exists() else []:
        requests.setdefault(record['schema'], set()).add(record['key'])
    for schema in ('org.gnome.desktop.background', 'org.gnome.desktop.wm.preferences',
                   'org.gnome.desktop.interface', 'org.gnome.shell.extensions.zorin-taskbar',
                   'org.gnome.desktop.session', 'org.gnome.desktop.screensaver',
                   'org.gnome.settings-daemon.plugins.power',
                   'org.gnome.settings-daemon.plugins.media-keys',
                   'org.gnome.shell.extensions.zorin-menu', 'org.gnome.shell.extensions.user-theme',
                   'org.gnome.shell.extensions.zorin-desktop-icons',
                   'org.gnome.shell.extensions.zorin11-desktop'):
        spec = source.lookup(schema, True)
        if spec:
            requests.setdefault(schema, set()).update(spec.list_keys())
    records = []
    for schema, keys in sorted(requests.items()):
        spec = source.lookup(schema, True)
        if not spec or not spec.get_path():
            continue
        settings = Gio.Settings.new_full(spec, None, None)
        for key in sorted(keys):
            if spec.has_key(key):
                value = settings.get_value(key)
                records.append({'schema':schema, 'key':key, 'type':value.get_type_string(),
                                'value':value.print_(True)})
    media = source.lookup('org.gnome.settings-daemon.plugins.media-keys', True)
    custom_id = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
    custom = source.lookup(custom_id, True)
    if media and custom:
        settings = Gio.Settings.new_full(media, None, None)
        for path in settings.get_strv('custom-keybindings'):
            binding = Gio.Settings.new_full(custom, None, path)
            for key in custom.list_keys():
                value = binding.get_value(key)
                records.append({'schema':custom_id, 'path':path, 'key':key,
                                'type':value.get_type_string(), 'value':value.print_(True)})
    return records


def account_photo():
    from gi.repository import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        user = bus.call_sync('org.freedesktop.Accounts', '/org/freedesktop/Accounts',
            'org.freedesktop.Accounts', 'FindUserById', GLib.Variant('(x)', (os.getuid(),)),
            None, Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]
        icon = bus.call_sync('org.freedesktop.Accounts', user, 'org.freedesktop.DBus.Properties',
            'Get', GLib.Variant('(ss)', ('org.freedesktop.Accounts.User', 'IconFile')),
            None, Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]
        if icon and Path(icon).is_file():
            return Path(icon)
    except GLib.Error:
        pass
    return next((p for p in (HOME/'.face', HOME/'.face.icon') if p.is_file()), None)


def build_archive(target, sources, generated, metadata):
    entries = []
    with tarfile.open(target, 'w:gz', compresslevel=3, dereference=False) as archive:
        for name, path in sorted(sources.items()):
            archive.inodes.clear()  # Record hard-linked files independently.
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            if info.issym():
                archive.addfile(info)
                entries.append({'path':name, 'kind':'symlink', 'target':info.linkname})
            elif info.isfile():
                # Snapshot once; hash exactly the bytes written, even if the live
                # component changes later in the backup operation.
                content = path.read_bytes()
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
                entries.append({'path':name, 'kind':'file', 'size':len(content),
                                'sha256':hashlib.sha256(content).hexdigest()})
            else:
                raise RuntimeError('Unsupported backup source: '+str(path))
        for name, content in sorted(generated.items()):
            info = tarfile.TarInfo(name);info.size = len(content);info.mode = 0o600
            archive.addfile(info, io.BytesIO(content))
            entries.append({'path':name, 'kind':'file', 'size':len(content),
                            'sha256':hashlib.sha256(content).hexdigest()})
        manifest = {**metadata, 'format':1, 'entries':entries}
        content = (json.dumps(manifest, indent=2)+'\n').encode()
        info = tarfile.TarInfo('manifest.json');info.size = len(content);info.mode = 0o600
        archive.addfile(info, io.BytesIO(content))
    verify_archive(target)
    return manifest


def verify_archive(path):
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        manifest = json.load(archive.extractfile('manifest.json'))
        expected = {x['path']:x for x in manifest['entries']}
        if len(members) != len(expected)+1 or set(x.name for x in members) != set(expected)|{'manifest.json'}:
            raise RuntimeError('Backup inventory mismatch')
        for member in members:
            if member.name == 'manifest.json':
                continue
            record = expected[member.name]
            if record['kind'] == 'symlink':
                if not member.issym() or member.linkname != record['target']:
                    raise RuntimeError('Backup symlink mismatch: '+member.name)
            elif not member.isfile() or hashlib.file_digest(archive.extractfile(member), 'sha256').hexdigest() != record['sha256']:
                raise RuntimeError('Backup checksum mismatch: '+member.name)
    return manifest


def publish(destination, archive, manifest):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    ident = datetime.datetime.now().astimezone().strftime('%Y-%m-%d_%H-%M-%S')+'_'+uuid.uuid4().hex[:8]
    pending = destination/('.partial-'+ident)
    final = destination/ident
    pending.mkdir()
    try:
        target = pending/'desktop-snapshot.tar.gz'
        shutil.copyfile(archive, target)
        checksum = digest(archive)
        if digest(target) != checksum:
            raise RuntimeError('Destination checksum mismatch; backup not published')
        (pending/'SHA256SUMS').write_text(checksum+'  desktop-snapshot.tar.gz\n')
        (pending/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        (pending/'RESTORE-README.txt').write_text(GUIDE)
        pending.rename(final)
    except BaseException:
        # Only remove our own incomplete folder, never previous snapshots.
        shutil.rmtree(pending, ignore_errors=True)
        raise
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, help='New backup destination; remembered after success')
    parser.add_argument('--verify', type=Path, help='Verify an existing desktop-snapshot.tar.gz')
    args = parser.parse_args()
    if args.verify:
        manifest = verify_archive(args.verify)
        print('Verified', len(manifest['entries']), 'snapshot entries')
        return
    destination = args.destination or configured_destination()
    sources = collect()
    photo = account_photo()
    if photo:
        sources['profile/account-photo.original'] = photo
    generated = {'profile/gnome-settings.json':(json.dumps(current_settings(), indent=2)+'\n').encode(),
                 'RESTORE-README.txt':GUIDE.encode()}
    metadata = {'created':datetime.datetime.now().astimezone().isoformat(),
                'scope':'Installed Windows-style desktop; selective restore only',
                'gnome':subprocess.check_output(['gnome-shell', '--version'], text=True).strip()}
    with tempfile.TemporaryDirectory(prefix='axentra-desktop-backup-') as folder:
        archive = Path(folder)/'desktop-snapshot.tar.gz'
        manifest = build_archive(archive, sources, generated, metadata)
        final = publish(destination, archive, manifest)
    if args.destination:
        remember_destination(destination)
    print('Verified backup:', final)
    print('Entries:', len(manifest['entries']))


if __name__ == '__main__':
    main()
