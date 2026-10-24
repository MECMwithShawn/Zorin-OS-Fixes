"""Package details for an installed desktop app, shown in Start search.

Only package metadata is read. Launch command lines are never inspected
because some contain credentials.
"""
import os
import re
import subprocess
from pathlib import Path

TIMEOUT = 3


def _run(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT,
                                env=dict(os.environ, LC_ALL='C'))
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout if result.returncode == 0 else ''


def _publisher(maintainer):
    return re.sub(r'\s*<[^>]*>\s*', '', maintainer or '').strip()


def _size(kib):
    try:
        value = int(kib) * 1024
    except (TypeError, ValueError):
        return ''
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.0f} {unit}' if unit == 'bytes' else f'{value:.1f} {unit}'
        value /= 1024


def _fields(text):
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition(':')
        if sep and key.strip() and value.strip():
            fields.setdefault(key.strip().lower(), value.strip())
    return fields


def _flatpak(app_id):
    info = _fields(_run('flatpak', 'info', app_id))
    return {'source': 'Flatpak', 'package': app_id, 'version': info.get('version', ''),
            'publisher': info.get('origin', ''), 'size': info.get('installed', '').replace('\xa0', ' ')}


def _snap(name):
    info = _fields(_run('snap', 'info', name))
    version = info.get('installed', '').split()
    return {'source': 'Snap', 'package': name, 'version': version[0] if version else '',
            'publisher': info.get('publisher', '').rstrip('*✓ ')}


def _deb(path):
    owner = _run('dpkg-query', '-S', str(path)).splitlines()
    package = owner[0].split(':', 1)[0].split(',')[0].strip() if owner else ''
    if not package:
        return None
    version, maintainer, size, homepage = (_run(
        'dpkg-query', '-W', '-f=${Version}\t${Maintainer}\t${Installed-Size}\t${Homepage}', package
    ).split('\t') + ['', '', '', ''])[:4]
    return {'source': 'Debian package', 'package': package, 'version': version,
            'publisher': _publisher(maintainer), 'size': _size(size), 'homepage': homepage}


def details(desktop_file):
    """Return source, package, version, publisher and size for a .desktop file."""
    if not desktop_file:
        return {'source': 'Built in'}
    path = Path(desktop_file)
    text = str(path)
    if '/flatpak/exports/' in text:
        return _flatpak(path.stem)
    if '/snapd/desktop/' in text:
        return _snap(path.stem.split('_', 1)[0])
    found = _deb(path)
    if found:
        return found
    if Path.home() in path.parents:
        return {'source': 'Installed for this user'}
    return {'source': 'Installed locally'}
