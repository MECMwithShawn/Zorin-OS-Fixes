"""Local raster thumbnails, decoded outside the UI with bounded resources."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, unquote

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff'}
BYTE_LIMIT = 32 * 1024 * 1024
PIXEL_LIMIT = 64_000_000
CACHE_LIMIT = 16 * 1024 * 1024


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
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='image-thumbnail')
        self.slots = threading.BoundedSemaphore(32)
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.closed = False

    def request(self, request, path, version, valid):
        from gi.repository import GLib
        if self.closed or not valid():
            finish(request)
            return
        key = (path, *version)
        if key in self.cache:
            content = self.cache.pop(key)
            self.cache[key] = content
            finish(request, content)
            return
        if not self.slots.acquire(blocking=False):
            finish(request)
            return

        def deliver(future):
            self.slots.release()
            try:
                content = future.result() if not self.closed and valid() else b''
            except Exception:
                content = b''
            if content:
                self.cache_bytes -= len(self.cache.pop(key, b''))
                self.cache[key] = content
                self.cache_bytes += len(content)
                while self.cache_bytes > CACHE_LIMIT or len(self.cache) > 256:
                    self.cache_bytes -= len(self.cache.popitem(last=False)[1])
            finish(request, content)
            return False

        future = self.pool.submit(read, path, version, lambda: not self.closed and valid())
        future.add_done_callback(lambda result: GLib.idle_add(deliver, result))

    def close(self):
        self.closed = True
        self.cache.clear()
        self.cache_bytes = 0
        self.pool.shutdown(wait=False, cancel_futures=True)


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
    if not getattr(hub, 'thumbnails', None):
        hub.thumbnails = Service()
        hub.connect('shutdown', lambda *_: hub.thumbnails.close())
    hub.thumbnails.request(request, path, version, valid)


if __name__ == '__main__':
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        sys.stdout.buffer.write(generate(sys.argv[1], json.loads(sys.argv[2])))
    except Exception:
        sys.exit(1)
