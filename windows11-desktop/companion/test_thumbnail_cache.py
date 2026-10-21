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

    def test_fuse_root_is_skipped_before_any_filesystem_access(self):
        with patch.object(library, 'unsafe_mounts', return_value=[self.photos.parent]), \
             patch.object(Path, 'is_symlink', side_effect=AssertionError('must not stat FUSE')), \
             patch.object(os, 'walk', side_effect=AssertionError('must not scan FUSE')):
            self.assertEqual(list(library.photos([self.photos], self.stop)), [])

    def test_nested_mount_skipped_but_local_photos_remain(self):
        cloud = self.photos/'Cloud'
        cloud.mkdir()
        Image.new('RGB', (20, 20)).save(cloud/'remote.jpg')
        with patch.object(library, 'unsafe_mounts', return_value=[cloud]):
            self.assertEqual(list(library.photos([self.photos], self.stop)), [self.image])

    def test_mount_names_are_decoded_without_resolving_them(self):
        text = '1 0 0:1 / /home/a/My\\040Drive rw - fuse.axentra-onedrive source rw\n'
        text += '2 0 0:2 / /local rw - ext4 source rw\n'
        with patch.object(Path, 'read_text', return_value=text):
            self.assertEqual(library.unsafe_mounts(), [Path('/home/a/My Drive')])

    def test_online_opt_in_does_not_bypass_fuse_exclusion(self):
        with patch.object(library, 'unsafe_mounts', return_value=[self.photos.parent]), \
             patch.object(self.disk, 'load', side_effect=AssertionError('must not decode FUSE')):
            result = library.warm([self.photos], self.disk, self.stop, include_online=True)
            self.assertEqual(result['examined'], 0)

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
