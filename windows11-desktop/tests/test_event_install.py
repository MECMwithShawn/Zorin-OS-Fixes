"""Standalone launcher installation and compare-safe recovery."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'companion')]
import gnome_install
import gnome_setup
import task_manager
import wallpaper


class EventInstallTests(unittest.TestCase):
    def test_launcher_runs_only_the_standalone_app(self):
        from gi.repository import Gio
        with tempfile.TemporaryDirectory(prefix='event launcher ') as temp:
            root = Path(temp)
            with patch.object(gnome_install, 'DEST', root):
                entry = root/'event-viewer.desktop'
                entry.write_bytes(gnome_install.event_viewer_entry())
            app = Gio.DesktopAppInfo.new_from_filename(str(entry))
            self.assertIsNotNone(app)
            self.assertEqual(app.get_name(), 'Event Viewer')
            self.assertEqual(app.get_executable(), '/usr/bin/python3')
            self.assertIn(f'"{root}/event_viewer.py"', app.get_commandline())
            self.assertEqual(app.get_startup_wm_class(), 'Zorin11-event-viewer')
            self.assertFalse(app.get_boolean('Terminal'))
            self.assertNotIn('app.py', app.get_commandline())

    def test_fresh_install_upgrade_restore_and_later_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root/'backup.json'
            helper = root/'runtime/event_viewer.py'
            launcher = root/'applications/event-viewer.desktop'
            launcher.parent.mkdir()
            launcher.write_bytes(b'Original launcher')
            original_record = dict(path=str(root/'unrelated'), before=None,
                                   after=base64.b64encode(b'Keep this record').decode())
            manifest.write_text(json.dumps([original_record]))
            with patch.object(gnome_install, 'FILES', manifest), \
                 patch.object(gnome_install, 'DEST', root/'runtime'), \
                 patch.object(gnome_install.os, 'geteuid', return_value=1000), \
                 patch.object(gnome_install.subprocess, 'run'), \
                 patch.object(gnome_setup, 'restore'), \
                 patch.object(task_manager, 'restore'), patch.object(wallpaper, 'restore'):
                files = {helper: b'First helper', launcher: b'First launcher'}
                gnome_install.write_files(files)
                files = {helper: b'Updated helper', launcher: b'Updated launcher'}
                gnome_install.write_files(files)
                records = {r['path']: r for r in json.loads(manifest.read_text())}
                self.assertEqual(records[str(root/'unrelated')], original_record)
                self.assertIsNone(records[str(helper)]['before'])
                self.assertEqual(base64.b64decode(records[str(launcher)]['before']), b'Original launcher')
                gnome_install.restore()
                self.assertFalse(helper.exists())
                self.assertEqual(launcher.read_bytes(), b'Original launcher')
                gnome_install.write_files(files)
                helper.write_bytes(b'User edited helper')
                gnome_install.restore()
                self.assertEqual(helper.read_bytes(), b'User edited helper')
                self.assertEqual(launcher.read_bytes(), b'Original launcher')


if __name__ == '__main__':
    unittest.main()
