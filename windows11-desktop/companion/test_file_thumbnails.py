import io
from pathlib import Path
import os
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlparse, quote
import json
import unittest
from unittest.mock import patch
from PIL import Image
import file_thumbnails as t


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'photo.JPG'
        Image.new('RGB', (800, 400), 'red').save(self.path)

    def version(self, path=None):
        value = (path or self.path).stat()
        return [value.st_mtime, value.st_size]

    def test_real_decoder_size_orientation_and_metadata(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'Private description'
        Image.new('RGB', (800, 400), 'red').save(self.path, exif=exif)
        raw = t.read(str(self.path), self.version())
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.size, (128, 256))
            self.assertEqual(image.format, 'PNG')
            self.assertFalse(image.getexif())
            self.assertNotIn('exif', image.info)
        self.assertEqual(t.read(str(self.path), [0, 1]), b'')

    def test_alpha_formats_and_limits(self):
        for extension in ('.png', '.webp', '.gif', '.bmp', '.tiff'):
            path = self.root/('photo'+extension)
            Image.new('RGBA', (128, 64), (10, 20, 30, 0)).save(path)
            self.assertTrue(t.read(str(path), self.version(path)), extension)
        with patch.object(t, 'BYTE_LIMIT', 10):
            self.assertEqual(t.generate(self.path, self.version()), b'')
        with patch.object(t, 'PIXEL_LIMIT', 10):
            self.assertEqual(t.generate(self.path, self.version()), b'')

    def test_missing_corrupt_links_and_special_files(self):
        for filename in ('bad.jpg', 'vector.svg'):
            path = self.root/filename
            path.write_text('<script>not an image</script>')
            self.assertEqual(t.read(str(path), self.version(path)), b'')
        link = self.root/'link.jpg'
        link.symlink_to(self.path)
        self.assertEqual(t.read(str(link), self.version()), b'')
        fifo = self.root/'pipe.jpg'
        os.mkfifo(fifo)
        self.assertEqual(t.read(str(fifo), [0, 0]), b'')
        self.assertEqual(t.read(str(self.root/'missing.jpg'), [0, 0]), b'')

    def test_decoder_cancellation_and_timeout(self):
        actual = t.subprocess.Popen
        children = []
        def slow(*_args, **kwargs):
            child = actual(['/usr/bin/python3', '-c', 'import time;time.sleep(20)'], **kwargs)
            children.append(child)
            return child
        with patch.object(t.subprocess, 'Popen', side_effect=slow):
            start = time.monotonic()
            self.assertEqual(t.read(str(self.path), self.version(), lambda: time.monotonic()-start < .2), b'')
            self.assertEqual(t.read(str(self.path), self.version(), timeout=.2), b'')
        self.assertTrue(all(p.poll() is not None for p in children))
        self.assertLess(time.monotonic()-start, 2)

    def test_service_cache_and_stale_delivery(self):
        from gi.repository import GLib
        service = t.Service()
        results = []
        def wait():
            end = time.monotonic()+4
            while not results and time.monotonic() < end:
                GLib.MainContext.default().iteration(False)
                time.sleep(.01)
            self.assertTrue(results)
        try:
            with patch.object(t, 'finish', side_effect=lambda _, data=b'': results.append(data)):
                service.request(None, str(self.path), self.version(), lambda: True)
                wait()
                self.assertTrue(results.pop())
                with patch.object(t, 'read', side_effect=AssertionError('Cache should avoid decoding')):
                    service.request(None, str(self.path), self.version(), lambda: True)
                    self.assertTrue(results.pop())
                alive = [True]
                # Different metadata bypasses the cache; navigation invalidates delivery.
                service.request(None, str(self.path), [0, 1], lambda: alive[0])
                alive[0] = False
                wait()
                self.assertEqual(results.pop(), b'')
                with patch.object(t, 'CACHE_LIMIT', 1):
                    Image.new('RGB', (100, 100), 'blue').save(self.path)
                    service.request(None, str(self.path), self.version(), lambda: True)
                    wait()
                self.assertLessEqual(service.cache_bytes, 1)
        finally:
            service.close()
            service.pool.shutdown(wait=True)

    def test_request_requires_own_current_listing_and_version(self):
        from unittest.mock import Mock
        web = object()
        surface = SimpleNamespace(mode='explorer', web=web, location=str(self.root),
                                  file_state={'entries':[dict(path=str(self.path), folder=False,
                                                             modified=self.version()[0], size=self.version()[1])]})
        service = Mock()
        hub = SimpleNamespace(surfaces={str(id(surface)):surface}, thumbnails=service)
        request = SimpleNamespace(get_web_view=lambda: web)
        uri = urlparse('zorin11://thumbnail/'+quote(str(self.path), safe='')+'?v='+quote(json.dumps(self.version())))
        t.serve(hub, request, uri)
        self.assertEqual(service.request.call_count, 1)
        valid = service.request.call_args.args[-1]
        self.assertTrue(valid())
        surface.location = '/another-folder'
        self.assertFalse(valid())
        surface.location = str(self.root)
        with patch.object(t, 'finish') as denied:
            t.serve(hub, SimpleNamespace(get_web_view=lambda: object()), uri)
            self.assertTrue(denied.called)
            t.serve(hub, request, urlparse('zorin11://thumbnail/'+quote(str(self.path), safe='')+'?v=[0,0]'))
            self.assertEqual(denied.call_count, 2)
            surface.file_state['entries'] = []
            t.serve(hub, request, uri)
            self.assertEqual(denied.call_count, 3)
        self.assertEqual(service.request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
