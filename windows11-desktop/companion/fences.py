"""Fences-style behaviour for Desktop Groups.

Desktop files dragged into a fence stay in ~/Desktop. The companion lists them
in ``fenced.json`` and the desktop-icons overlay skips drawing them, so they
appear only inside their fence. Files are never moved, hidden in other apps or
deleted. The list names the companion's PID; when that process is gone the
overlay ignores the list and every icon returns to the desktop.
"""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlparse

TINTS = {
    'slate': '#20242a', 'graphite': '#2b2b2b', 'midnight': '#14213d', 'ocean': '#0e4c75',
    'teal': '#0f5e5a', 'forest': '#1f4d2b', 'plum': '#4a2552', 'rose': '#6b2340',
    'amber': '#6b4a10', 'frost': '#c9d6e3',
}
ICON_SIZES = ('small', 'medium', 'large')
SORTS = ('manual', 'name', 'type', 'modified')
DEFAULT_STYLE = {'tint': 'slate', 'opacity': 0.55, 'iconSize': 'medium', 'sort': 'manual',
                 'autoRoll': False}
SNAP = 14


def clean_style(style):
    """Merge user changes onto the defaults, dropping anything unknown."""
    result = dict(DEFAULT_STYLE)
    if not isinstance(style, dict):
        return result
    if style.get('tint') in TINTS:
        result['tint'] = style['tint']
    try:
        result['opacity'] = round(min(1.0, max(0.1, float(style.get('opacity', result['opacity'])))), 2)
    except (TypeError, ValueError):
        pass
    if style.get('iconSize') in ICON_SIZES:
        result['iconSize'] = style['iconSize']
    if style.get('sort') in SORTS:
        result['sort'] = style['sort']
    if 'autoRoll' in style:
        result['autoRoll'] = bool(style['autoRoll'])
    return result


def desktop_dir():
    from gi.repository import GLib
    folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
    return Path(folder) if folder else Path.home()/'Desktop'


def uri_paths(uris):
    """Local, existing paths from a drop; other schemes are ignored."""
    paths = []
    for uri in uris or []:
        parsed = urlparse(uri.strip())
        if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost'):
            continue
        path = Path(unquote(parsed.path))
        if path.is_absolute() and (path.exists() or path.is_symlink()) and str(path) not in paths:
            paths.append(str(path))
    return paths


def fenced_paths(state, desktop):
    """Desktop files shown in a fence instead of on the desktop."""
    if not state.get('groups_visible'):
        return []
    desktop = Path(desktop)
    found = []
    for group in state.get('groups', []):
        if group.get('folder'):
            continue
        for item in group.get('items', []):
            path = item.get('path')
            if item.get('kind') == 'path' and path and Path(path).parent == desktop and path not in found:
                found.append(path)
    return sorted(found)


def process_identity(pid):
    """Boot ID and kernel start time, so a reused PID never matches a stale list."""
    try:
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        stat = Path(f'/proc/{pid}/stat').read_text()
        return boot, stat[stat.rindex(')')+2:].split()[19]
    except (OSError, ValueError, IndexError):
        return '', ''


def write_fenced(target, paths, pid):
    """Atomically publish the fenced list; returns False when unchanged."""
    target = Path(target)
    boot, start = process_identity(pid)
    content = json.dumps({'version': 1, 'pid': pid, 'boot': boot, 'start': start, 'paths': list(paths)},
                         ensure_ascii=False, indent=1) + '\n'
    try:
        if target.read_text() == content:
            return False
    except OSError:
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.fenced-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def launcher_trusted(path):
    """Zorin's desktop rule for running a .desktop file: executable, marked
    trusted with Allow Launching, and not writable by other users."""
    import stat
    from gi.repository import Gio
    try:
        info = Gio.File.new_for_path(str(path)).query_info(
            'unix::mode,access::can-execute,metadata::trusted', Gio.FileQueryInfoFlags.NONE, None)
        folder = Path(path).parent.stat().st_mode
    except Exception:
        return False
    return (info.get_attribute_boolean('access::can-execute')
            and info.get_attribute_as_string('metadata::trusted') == 'true'
            and not info.get_attribute_uint32('unix::mode') & stat.S_IWOTH
            and not folder & stat.S_IWOTH)


def sort_items(items, mode):
    if mode == 'name':
        return sorted(items, key=lambda i: str(i.get('name', '')).casefold())
    if mode == 'type':
        def kind(item):
            if item.get('kind') == 'app':
                return (0, '')
            if item.get('isDir'):
                return (1, '')
            return (2, Path(item.get('path', '')).suffix.casefold())
        return sorted(items, key=lambda i: (kind(i), str(i.get('name', '')).casefold()))
    if mode == 'modified':
        return sorted(items, key=lambda i: -float(i.get('modified') or 0))
    return items


def snap(x, y, width, height, area, others, threshold=SNAP):
    """Snap a fence rectangle to work-area edges and neighbouring fences."""
    ax, ay, aw, ah = area
    xs = [(ax, 0), (ax+aw, width)]
    ys = [(ay, 0), (ay+ah, height)]
    for ox, oy, ow, oh in others:
        xs += [(ox, 0), (ox+ow, 0), (ox, width), (ox+ow, width)]
        ys += [(oy, 0), (oy+oh, 0), (oy, height), (oy+oh, height)]
    def best(value, edges):
        choice, distance = value, threshold+1
        for edge, offset in edges:
            if abs(edge - offset - value) < distance:
                choice, distance = edge - offset, abs(edge - offset - value)
        return choice
    return best(x, xs), best(y, ys)
