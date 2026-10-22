"""Private, per-user Start preferences and shared filename visibility rules."""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote, unquote, urlparse

EXCLUDED_NAMES = {'node_modules', '__pycache__', 'venv', 'env', 'target', 'build',
                  'dist', '$RECYCLE.BIN', 'System Volume Information'}
# Start menu layouts, in the order Settings lists them. The first is the default.
STYLES = ('windows11', 'windows7')


def paths(values):
    if not isinstance(values, list) or len(values) > 32:
        raise ValueError('Choose up to 32 folders.')
    result = []
    for value in values:
        if not isinstance(value, str) or not value or len(value) > 4096 or '\0' in value:
            raise ValueError('Choose a valid folder path.')
        path = Path(value)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('Choose an absolute folder path.')
        if str(path) not in result:
            result.append(str(path))
    return result


def excluded(path, exclusions):
    return any(path == root or root in path.parents for root in map(Path, exclusions))


def visible(path, roots, exclusions):
    """Recheck suggestions at activation; never follow links or hidden ancestors."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or excluded(path, exclusions):
        return False
    if not any(path == root or root in path.parents for root in map(Path, roots)):
        return False
    try:
        return not any(p.name.startswith('.') or p.name in EXCLUDED_NAMES or p.is_symlink()
                       for p in [path, *path.parents] if p.name)
    except OSError:
        return False


class Preferences:
    def __init__(self, file, defaults):
        self.file = Path(file)
        self.defaults = paths(list(defaults))
        self.state = dict(roots=self.defaults[:], exclusions=[], recentDocuments=True, style=STYLES[0])
        try:
            if self.file.stat().st_size <= 524288:
                data = json.loads(self.file.read_text())
                # Files written before Start styles existed have no style key.
                style = data.get('style', STYLES[0])
                self.state = dict(roots=paths(data['roots']), exclusions=paths(data['exclusions']),
                                  recentDocuments=data['recentDocuments'] is True,
                                  style=style if style in STYLES else STYLES[0])
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def snapshot(self):
        return {k: v[:] if isinstance(v, list) else v for k, v in self.state.items()}

    def change(self, operation, key=None, value=None):
        state = self.snapshot()
        if operation == 'reset':
            state['roots'] = self.defaults[:]
            state['exclusions'] = []
        elif operation == 'recent' and isinstance(value, bool):
            state['recentDocuments'] = value
        elif operation == 'style' and value in STYLES:
            state['style'] = value
        elif operation in ('add', 'remove') and key in ('roots', 'exclusions'):
            path = paths([value])[0]
            if operation == 'add':
                if not Path(path).is_dir() or Path(path).is_symlink():
                    raise ValueError('Choose an available folder, rather than a link.')
                if key == 'roots' and not visible(path, [path], []):
                    raise ValueError('Hidden folders and build folders are excluded from search.')
                state[key] = paths(list(dict.fromkeys([*state[key], path])))
            else:
                state[key] = [p for p in state[key] if p != path]
        else:
            raise ValueError('Unknown Search & Start preference.')
        self.file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.start-', dir=self.file.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, indent=2)
                stream.write('\n')
            os.replace(temporary, self.file)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        self.state = state


def documents(records, preferences, desktop_history=True, limit=6):
    """Filter metadata supplied by Gtk.RecentManager; never build a content index."""
    if not desktop_history or not preferences['recentDocuments']:
        return []
    result, seen = [], set()
    for record in sorted(records, key=lambda item: item['modified'], reverse=True):
        uri = urlparse(record['uri'])
        if record.get('private') or uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
            continue
        path = Path(unquote(uri.path))
        try:
            if path in seen or not visible(path, preferences['roots'], preferences['exclusions']) or not path.is_file():
                continue
        except (OSError, ValueError):
            continue
        seen.add(path)
        result.append(dict(kind='document', id=path.as_uri(), path=str(path), name=path.name,
                           icon='zorin11://icon/'+quote('mime:'+record.get('mime','application/octet-stream'),safe=''),
                           modified=record['modified']))
        if len(result) >= limit: break
    return result
