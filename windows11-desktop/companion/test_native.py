"""Exercise a real Gio desktop-file launch, without opening a user application."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from gi.repository import Gio
from app import Hub
from model import Store


class NativeTests(unittest.TestCase):
    def test_gio_launch_and_recent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root/'launched'
            probe = root/'probe.py'
            probe.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("launched")\n')
            desktop = root/'probe.desktop'
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Launch probe\nExec=/usr/bin/python3 ' + str(probe) + '\nTerminal=false\n')
            hub = Hub()
            hub.apps = {'probe.desktop': Gio.DesktopAppInfo.new_from_filename(str(desktop))}
            hub.store = Store(root/'state.json', hub.apps, root)
            hub.start = Mock()
            hub.broadcast = Mock()
            hub.launch('probe.desktop')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not marker.exists():
                time.sleep(.03)
            self.assertEqual(marker.read_text(), 'launched')
            self.assertEqual(hub.store.state['recent'], ['probe.desktop'])
            hub.start.hide.assert_called_once()
            with self.assertRaises(ValueError):
                hub.launch('not-installed.desktop')


if __name__ == '__main__':
    unittest.main()
