"""Low-priority user service for the Pictures and OneDrive thumbnail libraries."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import threading
import time

from file_thumbnails import DiskCache, EXTENSIONS, BYTE_LIMIT, locally_available


def library_roots():
    from gi.repository import GLib
    from explorer import _onedrive_folder
    pictures = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
                    or Path.home()/'Pictures')
    cloud = _onedrive_folder()
    return [pictures, *([cloud] if cloud else [])]


def photos(roots, stopped):
    """Traverse source folders read-only; never follow directory or file links."""
    roots = list(dict.fromkeys(Path(p).absolute() for p in roots))
    roots = [p for p in roots if not any(other != p and other in p.parents for other in roots)]
    for root in roots:
        if root.is_symlink():
            continue
        for directory, folders, files in os.walk(root, followlinks=False):
            if stopped.is_set():
                return
            folders[:] = sorted((name for name in folders if not name.startswith('.')
                                 and name not in ('node_modules', '__pycache__', 'target', 'vendor')),
                                key=lambda name: (name.casefold() not in ('photos', 'pictures'), name.casefold()))
            for name in sorted(files):
                if stopped.is_set():
                    return
                path = Path(directory)/name
                if not name.startswith('.') and path.suffix.lower() in EXTENSIONS and not path.is_symlink():
                    yield path


def warm(roots, disk, stopped, include_online=False, report=lambda _: None):
    counts = dict(examined=0, cached=0, created=0, unavailable=0, onlineSkipped=0)
    for path in photos(roots, stopped):
        counts['examined'] += 1
        try:
            info = path.stat()
            version = [info.st_mtime, info.st_size]
            key = disk.key(str(path), version)
            if key and disk.get(key, touch=False):
                counts['cached'] += 1
            elif not 0 < info.st_size <= BYTE_LIMIT:
                counts['unavailable'] += 1
            elif not include_online and not locally_available(path):
                counts['onlineSkipped'] += 1
            elif disk.load(str(path), version, lambda: not stopped.is_set(), timeout=15):
                counts['created'] += 1
            else:
                counts['unavailable'] += 1
        except OSError:
            counts['unavailable'] += 1
        if counts['examined'] % 25 == 0:
            report(dict(counts, running=True, updated=time.time()))
    disk.prune()
    report(dict(counts, running=False, interrupted=stopped.is_set(), updated=time.time()))
    return counts


def units(destination):
    # systemd specifiers/quotes must survive installation under paths with spaces.
    script = str(Path(destination)/'thumbnail_cache.py').replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"')
    return {
        'zorin11-thumbnail-cache.service': f'''[Unit]
Description=Prepare photo thumbnails for Windows 11 Explorer
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 "{script}"
Nice=15
IOSchedulingClass=idle
CPUQuota=25%
MemoryMax=768M
TimeoutStartSec=infinity
TimeoutStopSec=20
UMask=0077
''',
        'zorin11-thumbnail-cache.timer': '''[Unit]
Description=Keep Explorer photo thumbnails ready after sign-in

[Timer]
OnStartupSec=90
OnUnitInactiveSec=15min
RandomizedDelaySec=30
Unit=zorin11-thumbnail-cache.service

[Install]
WantedBy=timers.target
'''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', help='Photo folder; repeat for multiple roots')
    parser.add_argument('--include-online', action='store_true', help='Read online-only photos through OneDrive')
    args = parser.parse_args()
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'zorin11-hub/thumbnail-cache.json'
    try:
        include_online = json.loads(config.read_text()).get('includeOnline', False) is True
    except (OSError, ValueError, AttributeError):
        include_online = False
    disk = DiskCache()
    disk.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if disk.root.is_symlink():
        raise RuntimeError('Thumbnail cache directory cannot be a symbolic link')
    disk.root.chmod(0o700)
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    # Multiple manual launches/timer firings cannot scan the library together.
    with open(disk.root/'.library.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        def report(value):
            status = disk.root.parent/'thumbnail-status.json'
            temp = status.with_suffix('.tmp')
            temp.write_text(json.dumps(value))
            temp.chmod(0o600)
            temp.replace(status)
        report(dict(running=True, examined=0, updated=time.time()))
        result = warm(args.root or library_roots(), disk, stopped, args.include_online or include_online, report)
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
