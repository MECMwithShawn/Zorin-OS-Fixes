"""Local raster thumbnails, decoded outside the UI with bounded resources."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import io
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import tempfile
import time
from urllib.parse import parse_qs, unquote

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff'}
BYTE_LIMIT = 32 * 1024 * 1024
PIXEL_LIMIT = 64_000_000
CACHE_LIMIT = 16 * 1024 * 1024
DISK_LIMIT = 2 * 1024 * 1024 * 1024
DISK_ENTRIES = 32768
PREFETCH_LIMIT = 512


def locally_available(path):
    """Do not hydrate online-only OneDrive files during background preparation."""
    try:
        return os.getxattr(path, 'user.axentra.onedrive.status') in (b'local', b'pinned')
    except OSError as error:
        return error.errno in (errno.ENODATA, errno.ENOTSUP)


class DiskCache:
    """Private, bounded, disposable cache outside the source/sync folders."""
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(
            os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache')))/'zorin11-hub/thumbnails-v1'
        self.lock = threading.Lock()
        self.writes = 0

    def key(self, path, version):
        info = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or [info.st_mtime, info.st_size] != version
                or not 0 < info.st_size <= BYTE_LIMIT):
            return None
        # FUSE device/inode IDs can change on remount; source timestamps do not.
        identity = [path, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()

    def get(self, key, touch=True):
        if not key:
            return b''
        try:
            with self.lock:
                fd = os.open(self.root/(key+'.png'), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 300000:
                        return b''
                    data = stream.read(300001)
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    return b''
                if touch:
                    os.utime(self.root/(key+'.png'), None, follow_symlinks=False)
                return data
        except OSError:
            return b''

    def put(self, key, data):
        if not key or not data:
            return
        temp = None
        try:
            with self.lock:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                if self.root.is_symlink():
                    return
                self.root.chmod(0o700)
                with tempfile.NamedTemporaryFile(dir=self.root, prefix='.tmp-', delete=False) as stream:
                    temp = Path(stream.name)
                    stream.write(data)
                temp.replace(self.root/(key+'.png'))
                self.writes += 1
            if self.writes % 32 == 1:
                self.prune()
        except OSError:
            pass  # Read-only/full cache storage must not prevent viewing a photo.
        finally:
            if temp:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass

    def prune(self):
        try:
            with self.lock, open(self.root/'.prune.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                entries = []
                for path in self.root.glob('*.png'):
                    info = path.lstat()
                    entries.append((info.st_mtime_ns, path, info.st_size))
                total = sum(item[2] for item in entries)
                count = len(entries)
                for _, path, size in sorted(entries):
                    if total <= DISK_LIMIT and count <= DISK_ENTRIES:
                        break
                    path.unlink(missing_ok=True)
                    total -= size
                    count -= 1
        except OSError:
            pass

    def load(self, path, version, valid, background=False, timeout=3):
        try:
            key = self.key(path, version)
            if not key or not valid():
                return b''
            content = self.get(key, touch=not background)
            if content:
                return content
            if background and not locally_available(path):
                return b''
            content = read(path, version, valid, timeout=timeout)
            if content and valid() and key == self.key(path, version):
                self.put(key, content)
            return content
        except OSError:
            return b''


def generate(path, version):
    """Read only a regular local file; normalize orientation and discard metadata."""
    if Path(path).suffix.lower() not in EXTENSIONS:
        return b''
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= BYTE_LIMIT:
            return b''
        if [before.st_mtime, before.st_size] != version:
            return b''
        content = stream.read(BYTE_LIMIT + 1)
        after = os.fstat(stream.fileno())
        if len(content) > BYTE_LIMIT or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            return b''
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(content)) as source:
        if source.format not in ('JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'):
            return b''
        if source.width * source.height > PIXEL_LIMIT:
            return b''
        # Resize before transposing to keep large JPEG decode memory low.
        source.thumbnail((256, 256), Image.Resampling.LANCZOS)
        picture = ImageOps.exif_transpose(source).convert('RGBA')
        picture.info.clear()
        output = io.BytesIO()
        picture.save(output, format='PNG')
        return output.getvalue()


def read(path, version, valid=lambda: True, timeout=3):
    """A corrupt/slow decoder cannot occupy the UI or a worker indefinitely."""
    if not valid():
        return b''
    process = subprocess.Popen(['/usr/bin/python3', __file__, path, json.dumps(version)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    try:
        while valid() and time.monotonic() < deadline:
            try:
                output = process.communicate(timeout=.1)[0]
                return output if process.returncode == 0 and len(output) <= 300000 else b''
            except subprocess.TimeoutExpired:
                continue
        return b''
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def finish(request, content=b''):
    from gi.repository import Gio, GLib
    request.finish(Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(content)), len(content),
                   'image/png' if content else 'text/plain')


class Service:
    def __init__(self, cache_root=None):
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='image-thumbnail')
        self.disk = DiskCache(cache_root)
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.closed = False
        self.jobs = {}
        self.warming = OrderedDict()
        self.running = 0
        self.background_running = 0

    def request(self, request, path, version, valid):
        if self.closed or not valid():
            finish(request)
            return
        key = (path, *version)
        if key in self.cache:
            content = self.cache.pop(key)
            self.cache[key] = content
            finish(request, content)
            return
        if key in self.jobs:
            self.jobs[key]['waiters'].append((request, valid))
            return
        if len(self.jobs) >= 32:
            finish(request)
            return
        self.jobs[key] = dict(path=path, version=version, waiters=[(request, valid)],
                              valid=lambda: False, started=False, background=False)
        self.pump()

    def prefetch(self, owner, entries, valid):
        """One folder per window, capped work; visible requests always go first."""
        if self.closed:
            return
        queue = []
        for entry in entries:
            if not entry['folder'] and Path(entry['path']).suffix.lower() in EXTENSIONS:
                path, version = entry['path'], [entry.get('modified'), entry.get('size')]
                queue.append((path, version))
                if len(queue) == PREFETCH_LIMIT:
                    break
        self.warming.pop(owner, None)
        self.warming[owner] = (iter(queue), valid)
        while len(self.warming) > 4:
            self.warming.popitem(last=False)
        self.pump()

    def pump(self):
        from gi.repository import GLib
        if self.closed:
            return
        while self.running < 2:
            selected = next(((key, job) for key, job in self.jobs.items() if not job['started']), None)
            if selected is None and not self.background_running:
                while self.warming and selected is None:
                    owner, (queue, valid) = next(iter(self.warming.items()))
                    item = next(queue, None) if valid() else None
                    if item is None:
                        self.warming.pop(owner)
                        continue
                    path, version = item
                    key = (path, *version)
                    if key in self.cache or key in self.jobs:
                        continue
                    job = dict(path=path, version=version, waiters=[], valid=valid,
                               started=False, background=True)
                    self.jobs[key] = job
                    selected = key, job
            if selected is None:
                break
            key, job = selected
            job['started'] = True
            self.running += 1
            self.background_running += job['background']

            def alive(job=job):
                return not self.closed and (job['valid']() or any(v() for _, v in job['waiters']))

            future = self.pool.submit(self.disk.load, job['path'], job['version'], alive, job['background'])
            future.add_done_callback(lambda result, key=key, job=job: GLib.idle_add(self.deliver, key, job, result))

    def deliver(self, key, job, future):
        self.jobs.pop(key, None)
        self.running -= 1
        self.background_running -= job['background']
        try:
            content = future.result() if not self.closed else b''
        except Exception:
            content = b''
        if not content and job['background'] and job['waiters'] and not self.closed:
            # A visible request may have joined a skipped online-only background job.
            job.update(background=False, started=False, valid=lambda: False)
            self.jobs[key] = job
            self.pump()
            return False
        if content:
            self.cache_bytes -= len(self.cache.pop(key, b''))
            self.cache[key] = content
            self.cache_bytes += len(content)
            while self.cache_bytes > CACHE_LIMIT or len(self.cache) > 256:
                self.cache_bytes -= len(self.cache.popitem(last=False)[1])
        for request, valid in job['waiters']:
            finish(request, content if valid() else b'')
        self.pump()
        return False

    def close(self):
        self.closed = True
        self.cache.clear()
        self.cache_bytes = 0
        self.warming.clear()
        for key, job in list(self.jobs.items()):
            if not job['started']:
                for request, _ in job['waiters']:
                    finish(request)
                del self.jobs[key]
        self.pool.shutdown(wait=False, cancel_futures=True)


def service(hub):
    if not getattr(hub, 'thumbnails', None):
        hub.thumbnails = Service()
        hub.connect('shutdown', lambda *_: hub.thumbnails.close())
    return hub.thumbnails


def prefetch(hub, surface):
    from gi.repository import GLib
    state = surface.file_state
    def valid():
        return hub.surfaces.get(str(id(surface))) is surface and surface.file_state is state
    def begin():
        if valid():
            service(hub).prefetch(str(id(surface)), state.get('entries', []), valid)
        return False
    # Give the initial visible requests a head start.
    GLib.timeout_add(700, begin)


def serve(hub, request, uri):
    """Only the requesting Explorer's currently listed files are eligible."""
    path = unquote(uri.path.lstrip('/'))
    try:
        version = json.loads(parse_qs(uri.query)['v'][0])
    except (ValueError, KeyError, IndexError):
        finish(request)
        return
    surface = next((s for s in hub.surfaces.values()
                    if s.mode == 'explorer' and s.web == request.get_web_view()), None)
    if surface is None or Path(path).suffix.lower() not in EXTENSIONS:
        finish(request)
        return
    location = surface.location

    def valid():
        return (hub.surfaces.get(str(id(surface))) is surface and surface.location == location
                and any(e['path'] == path and not e['folder']
                        and [e.get('modified'), e.get('size')] == version
                        for e in (surface.file_state or {}).get('entries', [])))

    if not valid():
        finish(request)
        return
    service(hub).request(request, path, version, valid)


if __name__ == '__main__':
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        sys.stdout.buffer.write(generate(sys.argv[1], json.loads(sys.argv[2])))
    except Exception:
        sys.exit(1)
