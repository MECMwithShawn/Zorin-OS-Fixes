"""Independent lock-screen photos. Never writes desktop, login or sync settings."""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gio, GdkPixbuf
import gnome_wallpaper

UUID = 'zorin11-lockscreen@zorin-os-fixes'
SCHEMA = 'org.gnome.shell.extensions.zorin11-lockscreen'
ROOT = Path(os.environ.get('ZORIN11_LOCKSCREEN_DIR', str(Path.home()/'.config/zorin11-hub/lockscreen')))
SOURCES = ('spotlight', 'bing', 'zorin', 'desktop', 'picture')

def settings():
    directory = Path(os.environ.get('ZORIN11_LOCKSCREEN_SCHEMA', str(Path.home()/'.local/share/gnome-shell/extensions'/UUID/'schemas')))
    source = Gio.SettingsSchemaSource.new_from_directory(str(directory), Gio.SettingsSchemaSource.get_default(), False)
    schema = source.lookup(SCHEMA, False)
    if not schema: raise RuntimeError('Install the lock-screen extension first.')
    return Gio.Settings.new_full(schema, None, None)

def defaults():
    return dict(source='spotlight', daily=True, enabled=True, showCredit=True, dimming=14,
                path='/usr/share/backgrounds/Zorin.jpg', title='Zorin wallpaper', credit='', revision='', lastDay='', error='')

def load():
    try: return dict(defaults(), **json.loads((ROOT/'state.json').read_text()))
    except (OSError, ValueError, TypeError): return defaults()

@contextlib.contextmanager
def locked():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT/'state.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield

def save(state):
    with tempfile.NamedTemporaryFile(mode='w', dir=ROOT, delete=False) as handle:
        json.dump(state, handle, indent=2); handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    os.replace(handle.name, ROOT/'state.json')

def validate_image(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file(): raise ValueError('Choose an available picture.')
    if path.stat().st_size > 30*1024*1024: raise ValueError('Choose a picture smaller than 30 MB.')
    info, width, height = GdkPixbuf.Pixbuf.get_file_info(str(path))
    if not info or width <= 0 or height <= 0 or width*height > 80000000:
        raise ValueError('This picture cannot be used as a lock-screen background.')
    GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 32, 32, True)
    return path

def sync(state):
    s = settings(); s.delay()
    values = {'enabled': state['enabled'], 'show-credit': state['showCredit'], 'dimming': state['dimming'],
              'source': state['source'], 'picture-uri': Path(state['path']).as_uri(),
              'picture-title': state['title'], 'picture-credit': state['credit']}
    for key, value in values.items():
        setter = s.set_boolean if type(value) is bool else s.set_int if type(value) is int else s.set_string
        if not setter(key, value): s.revert(); raise RuntimeError('GNOME rejected '+key)
    s.apply(); Gio.Settings.sync()

def prune(selected):
    assets = ROOT/'pictures'
    files = sorted(assets.glob('*.jpg'), key=lambda p:p.stat().st_mtime, reverse=True)
    for path in files[30:]:
        if str(path) != selected: path.unlink(missing_ok=True)

def apply(options):
    with locked():
        state = load()
        for key in ('source', 'daily', 'enabled', 'showCredit', 'dimming', 'path', 'title', 'credit', 'assetSource', 'lastDay', 'url'):
            if key in options: state[key] = options[key]
        if state['source'] not in SOURCES: raise ValueError('Choose a supported background.')
        if any(type(state[k]) is not bool for k in ('daily', 'enabled', 'showCredit')): raise ValueError('Expected an on/off value.')
        if type(state['dimming']) is not int or not 0 <= state['dimming'] <= 45: raise ValueError('Dimming must be between 0 and 45.')
        selected = validate_image(state['path'])
        if state['source'] == 'picture' and selected.parent != ROOT/'pictures':
            # Copy one explicitly selected image so unlocking never depends on
            # a cloud/FUSE mount, removable drive or connection being available.
            data = selected.read_bytes()
            directory = ROOT/'pictures'; directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, delete=False, suffix='.download') as handle:
                handle.write(data); temp = Path(handle.name)
            try:
                validate_image(temp)
                cached = directory/(hashlib.sha256(data).hexdigest()[:32]+'.jpg')
                temp.replace(cached); selected = cached
            finally: temp.unlink(missing_ok=True)
        state['path'] = str(selected)
        for key in ('title', 'credit'): state[key] = str(state[key])[:220]
        state.update(revision=uuid.uuid4().hex, error='')
        sync(state); save(state); prune(state['path'])
        return state

def prepare(source):
    """Fetch to our cache only; Apply decides when it becomes the background."""
    import wallpaper
    options = wallpaper.candidates(source, prefer_uhd=True)
    if not options: raise ValueError('No picture is available from this service right now.')
    previous = load().get('url')
    entry = next((i for i in options if i['url'] != previous), options[0])
    try: data = wallpaper.fetch(entry['url'], 30*1024*1024)
    except (OSError, ValueError):
        if not entry.get('fallback'): raise
        data = wallpaper.fetch(entry['fallback'], 30*1024*1024)
    if not data.startswith((b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n')): raise ValueError('The service did not return a photo.')
    directory = ROOT/'pictures'; directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, delete=False, suffix='.download') as handle:
        handle.write(data); temp = Path(handle.name)
    try:
        validate_image(temp)
        path = directory/(hashlib.sha256(data).hexdigest()[:32]+'.jpg')
        temp.replace(path)
    finally: temp.unlink(missing_ok=True)
    with locked(): prune(load()['path'])
    return dict(path=str(path), title=entry.get('title') or 'Windows Spotlight', credit=entry.get('credit', ''),
                assetSource=source, url=entry['url'], lastDay=datetime.date.today().isoformat())

def refresh(force=False):
    state = load(); source = state['source']
    if not state['enabled'] or not state['daily'] or source not in ('spotlight', 'bing'): return False
    if not force and state['lastDay'] == datetime.date.today().isoformat() and state.get('assetSource') == source: return False
    try:
        photo = prepare(source)
        with locked():
            current = load()
            if current['revision'] != state['revision']: return False
            current.update(photo, revision=uuid.uuid4().hex, error='')
            sync(current); save(current); prune(current['path'])
        return True
    except Exception as error:
        with locked():
            current = load()
            if current['revision'] == state['revision']:
                current['error'] = str(error)[:240]; save(current)
        raise

if __name__ == '__main__':
    import sys
    if '--initialize' in sys.argv: apply(load())
    elif '--refresh' in sys.argv:
        try: refresh(force='--force' in sys.argv)
        except Exception as error: print('Keeping the cached lock-screen photo:', error, file=sys.stderr); sys.exit(1)
    else: print(json.dumps(load(), indent=2))
