"""Private, per-user Start preferences and shared filename visibility rules."""
import copy
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote, unquote, urlparse

EXCLUDED_NAMES = {'node_modules', '__pycache__', 'venv', 'env', 'target', 'build',
                  'dist', '$RECYCLE.BIN', 'System Volume Information'}
# Start menu layouts, in the order Settings lists them. The first is the default.
STYLES = ('windows11', 'windows10', 'modern', 'windows7', 'tabbed', 'launcher', 'fullscreen')
# Windows 10 tile sizes; medium is the default and is not stored.
TILE_SIZES = ('small', 'medium', 'wide', 'large')


# Windows 11 Start layout names: rows of pins per page and how many recommendations show.
LAYOUTS = {'default': (3, 6), 'more-pins': (4, 2), 'more-recommendations': (2, 8)}
COLUMNS = (6, 7, 8)
MAX_TABS = 8
# Shared appearance: tint transparency (percent), corner shape and taskbar Start button image.
TRANSPARENCY = (0, 20, 40, 60)
CORNERS = ('style', 'rounded', 'square')
BUTTONS = ('windows11', 'windows10', 'orb', 'custom')


def start_tabs(value):
    """Named pin tabs shown beside Pinned in the Windows 11 layout."""
    if not isinstance(value, list) or len(value) > MAX_TABS:
        raise ValueError('Choose up to 8 tabs.')
    result, seen = [], set()
    for tab in value:
        if not isinstance(tab, dict) or not isinstance(tab.get('id'), str) or not tab['id'] or len(tab['id']) > 40 \
                or tab['id'] in seen or tab['id'] == 'pinned':
            raise ValueError('Tab is invalid.')
        name, apps = tab.get('name'), tab.get('apps')
        if not isinstance(name, str) or not name.strip() or len(name) > 40:
            raise ValueError('Name the tab in 40 characters or fewer.')
        if not isinstance(apps, list) or len(apps) > 200 or not all(isinstance(a, str) and a and len(a) <= 512 for a in apps):
            raise ValueError('A tab holds up to 200 apps.')
        seen.add(tab['id'])
        result.append(dict(id=tab['id'], name=name.strip(), apps=list(dict.fromkeys(apps))))
    return result


def tiles(value):
    if not isinstance(value, dict) or len(value) > 512:
        raise ValueError('Too many tile sizes.')
    for ident, size in value.items():
        if not isinstance(ident, str) or not ident or len(ident) > 512 or size not in TILE_SIZES[:1] + TILE_SIZES[2:]:
            raise ValueError('Choose a valid tile size.')
    return dict(value)


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
        self.state = dict(roots=self.defaults[:], exclusions=[], recentDocuments=True, style=STYLES[0], tiles={},
                          layout='default', columns=COLUMNS[0], showRecommended=True, tabs=[],
                          transparency=0, corners='style', button='windows11')
        try:
            if self.file.stat().st_size <= 524288:
                data = json.loads(self.file.read_text())
                # Files written before Start styles existed have no style key.
                style = data.get('style', STYLES[0])
                self.state = dict(roots=paths(data['roots']), exclusions=paths(data['exclusions']),
                                  recentDocuments=data['recentDocuments'] is True,
                                  style=style if style in STYLES else STYLES[0])
                # Each optional Start setting falls back on its own, so one bad value keeps the rest.
                for key, check, default in (('tiles', tiles, {}), ('tabs', start_tabs, []),
                        ('layout', lambda v: v if v in LAYOUTS else None, 'default'),
                        ('columns', lambda v: v if v in COLUMNS else None, COLUMNS[0]),
                        ('showRecommended', lambda v: v if isinstance(v, bool) else None, True),
                        ('transparency', lambda v: v if v in TRANSPARENCY and not isinstance(v, bool) else None, 0),
                        ('corners', lambda v: v if v in CORNERS else None, 'style'),
                        ('button', lambda v: v if v in BUTTONS else None, 'windows11')):
                    try:
                        value = check(data.get(key, default))
                    except ValueError:
                        value = None
                    self.state[key] = default if value is None else value
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def snapshot(self):
        return copy.deepcopy(self.state)

    def change(self, operation, key=None, value=None):
        state = self.snapshot()
        if operation == 'reset':
            state['roots'] = self.defaults[:]
            state['exclusions'] = []
        elif operation == 'recent' and isinstance(value, bool):
            state['recentDocuments'] = value
        elif operation == 'style' and value in STYLES:
            state['style'] = value
        elif operation == 'tile' and isinstance(key, str) and value in TILE_SIZES:
            state['tiles'].pop(key, None)
            if value != 'medium':
                state['tiles'] = tiles({**state['tiles'], key: value})
        elif operation == 'layout' and value in LAYOUTS:
            state['layout'] = value
        elif operation == 'columns' and value in COLUMNS and not isinstance(value, bool):
            state['columns'] = value
        elif operation == 'show-recommended' and isinstance(value, bool):
            state['showRecommended'] = value
        elif operation == 'transparency' and value in TRANSPARENCY and not isinstance(value, bool):
            state['transparency'] = value
        elif operation == 'corners' and value in CORNERS:
            state['corners'] = value
        elif operation == 'button' and value in BUTTONS:
            state['button'] = value
        elif operation.startswith('tab-'):
            state['tabs'] = self.tab_change(state['tabs'], operation[4:], key, value)
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


    @staticmethod
    def tab_change(tabs, operation, key, value):
        tab = next((t for t in tabs if t['id'] == key), None)
        if operation == 'create':
            used = {t['id'] for t in tabs}
            ident = next(f'tab{n}' for n in range(1, MAX_TABS + 2) if f'tab{n}' not in used)
            return start_tabs([*tabs, dict(id=ident, name=value, apps=[])])
        if tab is None:
            raise ValueError('That tab no longer exists.')
        if operation == 'rename':
            tab['name'] = value
        elif operation == 'delete':
            tabs = [t for t in tabs if t is not tab]
        elif operation == 'add' and isinstance(value, str):
            tab['apps'] = [*tab['apps'], value]
        elif operation == 'remove':
            tab['apps'] = [a for a in tab['apps'] if a != value]
        elif operation == 'move' and isinstance(value, dict) and value.get('id') in tab['apps'] and value.get('target') in tab['apps']:
            apps = [a for a in tab['apps'] if a != value['id']]
            apps.insert(apps.index(value['target']), value['id'])
            tab['apps'] = apps
        else:
            raise ValueError('Unknown tab change.')
        return start_tabs(tabs)


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
