import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
import thumbnail_cache as library
import file_thumbnails as thumbnails


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photos = self.root/'OneDrive/Photos'
        self.photos.mkdir(parents=True)
        self.image = self.photos/'Photo.jpg'
        Image.new('RGB', (400, 250), 'red').save(self.image)
        self.disk = thumbnails.DiskCache(self.root/'cache')
        self.stop = threading.Event()

    def test_recursion_deduplication_links_and_cancellation(self):
        (self.photos/'link.jpg').symlink_to(self.image)
        (self.photos/'cycle').symlink_to(self.photos)
        for name in ('.private', 'node_modules'):
            folder = self.photos/name
            folder.mkdir()
            Image.new('RGB', (20, 20)).save(folder/'ignored.jpg')
        self.assertEqual(list(library.photos([self.photos.parent, self.photos], self.stop)), [self.image])
        self.stop.set()
        self.assertEqual(list(library.photos([self.photos], self.stop)), [])

    def test_library_build_reuse_changes_and_cloud_policy(self):
        original = self.image.read_bytes()
        reports = []
        with patch.object(library, 'locally_available', return_value=False):
            first = library.warm([self.photos], self.disk, self.stop, report=reports.append)
            self.assertEqual(first['onlineSkipped'], 1)
            result = library.warm([self.photos], self.disk, self.stop, include_online=True)
        self.assertEqual(result['created'], 1)
        self.assertEqual(self.image.read_bytes(), original)
        with patch.object(thumbnails, 'read', side_effect=AssertionError('Warm library must not decode again')):
            again = library.warm([self.photos], thumbnails.DiskCache(self.disk.root), self.stop, include_online=True)
        self.assertEqual(again['cached'], 1)
        Image.new('RGB', (400, 250), 'blue').save(self.image)
        changed = library.warm([self.photos], self.disk, self.stop, include_online=True)
        self.assertEqual(changed['created'], 1)
        self.assertFalse(reports[-1]['running'])


if __name__ == '__main__':
    unittest.main()
