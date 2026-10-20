#!/usr/bin/python3
"""Native GTK controls against a disposable sysfs fixture; private display/bus."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def session(output):
    import device_manager as d
    from gi.repository import Gtk, Gdk
    from unittest.mock import patch
    from test_hardware_inventory import fixture
    def until(check):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            if check():
                return
            time.sleep(.02)
        raise AssertionError('GTK state did not arrive')

    def paint():
        deadline = time.monotonic() + .25
        until(lambda: time.monotonic() >= deadline)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        fixture(root)
        collect = d.inventory.collect
        fail = False
        def sample():
            if fail:
                raise RuntimeError('Fixture unavailable')
            return collect(root, {'0000:01:00.0': 'Fixture GPU'})
        with patch.object(d.inventory, 'collect', side_effect=sample):
            app = d.Application()
            app.register(None)
            app.activate()
            window = app.get_active_window()
            until(lambda: not window.pending)
            assert len(window.data) == 6
            assert not window.properties_button.get_sensitive()
            assert all(not window.tree.row_expanded(row.path) for row in window.store)
            window.tree.expand_all()
            assert all(window.tree.row_expanded(row.path) for row in window.store)
            window.tree.collapse_all()
            window.search.set_text('testgpu 1234')
            until(lambda: len(window.store) == 1)
            parent = window.store.get_iter_first()
            child = window.store.iter_children(parent)
            assert window.store[child][1] == 'Fixture GPU'
            assert window.tree.row_expanded(window.store.get_path(parent))
            window.tree.get_selection().select_iter(child)
            assert window.properties_button.get_sensitive()
            window.properties_button.clicked()
            dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, d.Properties))
            assert 'PCI 0x1234:0x5678' in dialog.details
            dialog.response(1)
            assert Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() == dialog.details
            dialog.response(Gtk.ResponseType.CLOSE)
            window.refresh_button.clicked()
            until(lambda: not window.pending)
            assert window.selected()['id'] == 'pci:0000:01:00.0'
            # Keyboard context menu uses the same actionable Properties item.
            assert window.popup()
            menu = Gtk.Menu.get_for_attach_widget(window.tree)[0]
            menu.get_children()[0].activate()
            menu.destroy()
            dialog = next(w for w in Gtk.Window.list_toplevels() if isinstance(w, d.Properties))
            dialog.response(Gtk.ResponseType.CLOSE)
            # Refresh after removal clears selection and cannot show stale properties.
            (root / 'bus/pci/devices/0000:01:00.0/vendor').unlink()
            window.refresh_button.clicked()
            until(lambda: not window.pending)
            assert len(window.store) == 0 and window.selected() is None
            assert not window.properties_button.get_sensitive()
            window.search.set_text('nonexistent')
            paint()
            assert '0 of 5 devices' in window.status.get_text()
            fail = True
            window.refresh()
            until(lambda: not window.pending)
            assert 'unavailable' in window.status.get_text() and not window.data
            fail = False
            window.search.set_text('')
            window.refresh()
            until(lambda: not window.pending)
            assert len(window.data) == 5
            window.tree.expand_all()
            paint()
            surface = window.get_window()
            Gdk.pixbuf_get_from_window(surface, 0, 0, surface.get_width(), surface.get_height()).savev(str(output / 'device-manager.png'), 'png', [], [])
            window.close()
            until(lambda: window.closed)
            assert window.closed and window.received(None) is False
    print('Native Device Manager passed: grouped tree, search, Properties, clipboard, context menu, refresh retention, unplug, failure/retry and cleanup.')


if __name__ == '__main__':
    if '--session' in sys.argv:
        session(Path(sys.argv[-1]))
    else:
        output = Path(os.environ.get('ZORIN11_TEST_OUTPUT', '/tmp/zorin11-device-test'))
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, XDG_CONFIG_HOME=temp, XDG_CACHE_HOME=temp,
                       GTK_USE_PORTAL='0', GIO_USE_VFS='local', NO_AT_BRIDGE='1',
                       GSETTINGS_BACKEND='memory', XDG_CURRENT_DESKTOP='GNOME')
            result = subprocess.run(['dbus-run-session', '--', 'xvfb-run', '-a', '/usr/bin/python3',
                                     __file__, '--session', str(output)], env=env,
                                    capture_output=True, text=True, timeout=45)
            print(result.stdout)
            if result.returncode:
                print(result.stderr)
            raise SystemExit(result.returncode)
