"""Exercise a real Gio desktop-file launch, without opening a user application."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from gi.repository import Gio
from app import Hub
from gnome_bridge import active as is_gnome
from model import Store
import settings_backend


class NativeTests(unittest.TestCase):
    @unittest.skipUnless(is_gnome() and os.environ.get('XDG_SESSION_TYPE') == 'wayland'
                         and os.environ.get('GDK_BACKEND') == 'x11',
                         'Needs the companion’s XWayland environment inside GNOME Wayland')
    def test_gio_child_selects_its_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'backend.json'
            probe = root / 'backend.py'
            probe.write_text("""\
import json, os, sys
from pathlib import Path
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk
result = [Gdk.Display.get_default().__gtype__.name, os.environ.get('GDK_BACKEND')]
marker = Path(sys.argv[1])
temporary = marker.with_suffix('.tmp')
temporary.write_text(json.dumps(result))
temporary.replace(marker)
""")
            hub = Hub()
            hub.apps = {}
            for name, prefix in (('auto', ''), ('force-x11', '/usr/bin/env GDK_BACKEND=x11 ')):
                desktop = root / f'{name}.desktop'
                command = f'{prefix}/usr/bin/python3 "{probe}" "{marker}"'
                desktop.write_text('[Desktop Entry]\nType=Application\nName=Backend probe\n'
                                   f'Exec={command}\nActions=inspect;\n\n'
                                   f'[Desktop Action inspect]\nName=Inspect\nExec={command}\n')
                hub.apps[desktop.name] = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            hub.store = Store(root / 'state.json', hub.apps, root)
            hub.start = Mock()
            hub.broadcast = Mock()

            def backend():
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not marker.exists():
                    time.sleep(.03)
                result = json.loads(marker.read_text())
                marker.unlink()
                return result

            hub.launch('auto.desktop')
            self.assertEqual(backend(), ['GdkWaylandDisplay', None])
            hub.launch_app_action('auto.desktop', 'inspect')
            self.assertEqual(backend(), ['GdkWaylandDisplay', None])
            hub.launch('force-x11.desktop')
            self.assertEqual(backend(), ['GdkX11Display', 'x11'])
            start_process = settings_backend.subprocess.Popen
            children = []

            def start_and_track(*args, **kwargs):
                child = start_process(*args, **kwargs)
                children.append(child)
                return child

            try:
                with patch.dict(settings_backend.TOOLS, {'display': ['/usr/bin/python3', str(probe), str(marker)]}), \
                     patch.object(settings_backend.subprocess, 'Popen', side_effect=start_and_track):
                    settings_backend.launch('display')
                    self.assertEqual(backend(), ['GdkWaylandDisplay', None])
            finally:
                for child in children:
                    child.wait(timeout=3)
            self.assertEqual(os.environ.get('GDK_BACKEND'), 'x11')

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
