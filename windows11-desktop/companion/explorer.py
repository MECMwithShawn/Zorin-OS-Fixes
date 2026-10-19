"""File Explorer operations backed by real local files and Gio applications."""
import datetime
import json
import tempfile
import threading
import os
from pathlib import Path
import shutil
from urllib.parse import urlparse, unquote
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gio, GLib, Gtk

HOME = Path.home()
DRIVE_LETTERS = Path(os.environ.get('ZORIN11_CONFIG_DIR', str(HOME/'.config/zorin11-hub')))/'drive-letters.json'
DRIVE_NAMES = DRIVE_LETTERS.with_name('drive-names.json')
DRIVE_LOCK = threading.Lock()
PLACES = [('Desktop', 'desktop'), ('Downloads', 'download'), ('Documents', 'document'),
          ('Pictures', 'image'), ('Music', 'music'), ('Videos', 'video')]


def place_paths():
    values = [GLib.UserDirectory.DIRECTORY_DESKTOP, GLib.UserDirectory.DIRECTORY_DOWNLOAD,
              GLib.UserDirectory.DIRECTORY_DOCUMENTS, GLib.UserDirectory.DIRECTORY_PICTURES,
              GLib.UserDirectory.DIRECTORY_MUSIC, GLib.UserDirectory.DIRECTORY_VIDEOS]
    return [dict(name=name, path=GLib.get_user_special_dir(kind) or str(HOME/name), symbol=symbol)
            for (name, symbol), kind in zip(PLACES, values)]


def entry(path):
    p = Path(path)
    folder = p.is_dir()
    try:
        stat = p.stat()
        size, modified = stat.st_size, stat.st_mtime
    except OSError:
        size, modified = 0, 0
    return {'path': str(p), 'name': p.name or str(p), 'folder': folder,
            'size': size if not folder else None, 'modified': modified,
            'date': datetime.datetime.fromtimestamp(modified).strftime('%m/%d/%Y %I:%M %p') if modified else '',
            'type': 'File folder' if folder else (p.suffix[1:].upper()+' file' if p.suffix else 'File'),
            'symbol': 'folder' if folder else 'image' if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif','.svg') else 'document'}


def read_drive_names(path):
    try:values=json.loads(path.read_text())
    except (OSError,ValueError):return {}
    return {key:value for key,value in values.items() if isinstance(value,str)} if isinstance(values,dict) else {}


def save_drive_names(values,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
        json.dump(values,stream);temp=Path(stream.name)
    try:temp.replace(path)
    finally:temp.unlink(missing_ok=True)


def rename_drive(path,name):
    if not isinstance(name,str) or not name.strip() or len(name.strip())>64 or any(ord(c)<32 for c in name) or any(c in name for c in '/\\'):
        raise ValueError('Enter a drive label of 1–64 characters without slashes or control characters.')
    drive=next((item for item in listing('::computer')['entries'] if item['path']==path),None)
    if not drive:raise ValueError('This drive is no longer mounted.')
    with DRIVE_LOCK:
        names=read_drive_names(DRIVE_NAMES);names[drive['driveId']]=name.strip()
        save_drive_names(names,DRIVE_NAMES)


def label_drives(entries, registry=None, names_path=None):
    """Windows-style aliases only; file operations still use the real paths."""
    registry = registry or DRIVE_LETTERS
    entries = sorted(entries, key=lambda item: (item['path'] != '/', item.get('removable', False),
                                                item['name'].casefold(), item['path']))
    with DRIVE_LOCK:
        names=read_drive_names(names_path or (registry.with_name('drive-names.json') if registry!=DRIVE_LETTERS else DRIVE_NAMES))
        try:
            saved = json.loads(registry.read_text())
        except (OSError, ValueError):
            saved = {}
        letters = {}
        for ident, letter in (saved.items() if isinstance(saved, dict) else []):
            if isinstance(letter, str) and len(letter) == 1 and 'D' <= letter <= 'Z' and letter not in letters.values():
                letters[ident] = letter
        for item in entries:
            item['driveId']=item.get('driveId') or 'path:'+item['path']
            if item['path'] == '/':
                item.update(name='Local Disk', driveLetter='C')
            else:
                ident = item.get('driveId') or 'path:'+item['path']
                if ident not in letters:
                    available = next((chr(n) for n in range(ord('D'), ord('Z')+1) if chr(n) not in letters.values()), None)
                    if available:
                        letters[ident] = available
                item['driveLetter'] = letters.get(ident, '')
            item['label']=names.get(item['driveId'],item['name'])
            item['name']=item['label']
            if item['driveLetter']:
                item['name'] += ' ('+item['driveLetter']+':)'
        if letters != saved:
            registry.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=registry.parent, delete=False) as stream:
                json.dump(letters, stream)
                temp = Path(stream.name)
            try:
                temp.replace(registry)
            finally:
                temp.unlink(missing_ok=True)
    return sorted(entries, key=lambda item: (item['driveLetter'] or '~', item['name'].casefold()))


def listing(location, hidden=False):
    places = place_paths()
    if location == '::home':
        return {'path': location, 'title': 'Home', 'entries': [entry(p['path']) for p in places if Path(p['path']).exists()], 'places': places}
    if location == '::computer':
        roots = [Path('/')]
        mounts={}
        if HOME.stat().st_dev != roots[0].stat().st_dev:
            roots.append(HOME)
        for mount in Gio.VolumeMonitor.get().get_mounts():
            p = mount.get_root().get_path()
            if p and Path(p) not in roots:
                roots.append(Path(p))
                mounts[Path(p)]=mount
        entries = []
        for root in roots:
            item = entry(root)
            mount=mounts.get(root)
            item['name'] = 'System' if str(root)=='/' else 'Home' if root==HOME else mount.get_name() if mount else root.name
            item['icon'] = 'drive-harddisk'
            if str(root)=='/':item['icon']='drive-harddisk-root'
            elif mount and 'usb' in mount.get_icon().to_string():item['icon']='drive-harddisk-usb'
            volume=mount.get_volume() if mount else None
            drive=mount.get_drive() if mount else None
            uuid=(volume.get_uuid() if volume else None) or (mount.get_uuid() if mount else None)
            item['driveId']='uuid:'+uuid if uuid else 'path:'+str(root)
            item['removable']=bool((drive and drive.is_removable()) or item['icon']=='drive-harddisk-usb')
            item['type']='Local disk' if item['icon']!='drive-harddisk-usb' else 'USB drive'
            try:
                usage = shutil.disk_usage(root)
                item.update(total=usage.total, free=usage.free)
                info=Gio.File.new_for_path(str(root)).query_filesystem_info('filesystem::type',None)
                item['filesystem']=info.get_attribute_string('filesystem::type') or ''
            except (OSError,GLib.Error):
                pass
            item['symbol'] = 'drive'
            entries.append(item)
        return {'path': location, 'title': 'This PC', 'entries': label_drives(entries), 'places': places}
    folder = Path(location).expanduser().absolute()
    if not folder.is_dir():
        raise ValueError('This folder is unavailable.')
    # Listing is executed on a worker. No UI-thread filesystem traversal.
    with os.scandir(folder) as iterator:
        entries = [entry(item.path) for item in iterator if hidden or not item.name.startswith('.')]
    return {'path': str(folder), 'title': 'Home folder' if folder==HOME else folder.name or 'Local Disk (C:)',
            'entries': sorted(entries, key=lambda e: (not e['folder'], e['name'].casefold())), 'places': places}


def child_path(parent, name):
    if not isinstance(name,str) or not name.strip() or name in ('.','..') or '/' in name or '\x00' in name:
        raise ValueError('Enter a filename without a slash.')
    directory = Path(parent)
    if not directory.is_dir():
        raise ValueError('Choose a folder first.')
    return directory/name


def create_folder(parent, name):
    destination = child_path(parent, name)
    destination.mkdir()  # Never overwrite an existing item.
    return str(destination)


def rename(path, name):
    source = Path(path)
    destination = child_path(source.parent, name)
    if os.path.lexists(destination):
        raise FileExistsError('An item with that name already exists.')
    # Gio.move with NONE refuses an existing destination, even if it appears
    # after the existence check; Path.rename would silently overwrite it.
    Gio.File.new_for_path(str(source)).move(Gio.File.new_for_path(str(destination)), Gio.FileCopyFlags.NONE, None, None, None)
    return str(destination)


def paste(sources, destination, cut=False):
    root = Path(destination)
    if not root.is_dir():
        raise ValueError('Choose a destination folder first.')
    results = []
    for value in sources:
        source = Path(value)
        target = root/source.name
        if root.resolve() == source.resolve() or source.resolve() in root.resolve().parents:
            raise ValueError('A folder cannot be pasted inside itself.')
        if os.path.lexists(target):
            if cut and source.absolute()==target.absolute():
                continue
            stem, suffix = (source.name, '') if source.is_dir() else (source.stem, source.suffix)
            index = 1
            while os.path.lexists(target):
                tail = ' - Copy' if index==1 else f' - Copy ({index})'
                target = root/(stem+tail+suffix)
                index += 1
        if cut:
            Gio.File.new_for_path(str(source)).move(Gio.File.new_for_path(str(target)), Gio.FileCopyFlags.NONE, None, None, None)
        elif source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target, symlinks=True)
        else:
            Gio.File.new_for_path(str(source)).copy(Gio.File.new_for_path(str(target)), Gio.FileCopyFlags.NOFOLLOW_SYMLINKS, None, None, None)
        results.append(str(target))
    return results


def trash(paths):
    for path in paths:
        Gio.File.new_for_path(path).trash(None)


def clipboard_read(clipboard):
    atom = __import__('gi.repository', fromlist=['Gdk']).Gdk.Atom.intern('x-special/gnome-copied-files', False)
    data = clipboard.wait_for_contents(atom)
    if data and data.get_data():
        lines = bytes(data.get_data()).decode().splitlines()
        cut = lines.pop(0)=='cut'
    else:
        lines = clipboard.wait_for_uris() or []
        cut = False
    paths = [unquote(urlparse(uri).path) for uri in lines if uri.startswith('file://') and urlparse(uri).netloc in ('','localhost')]
    return paths, cut
