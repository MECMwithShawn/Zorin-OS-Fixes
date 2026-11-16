#!/usr/bin/python3
"""Exercise maximize hover with real Brave on a disposable GNOME Wayland session.

Set ZORIN11_TEST_HOVER_SCALE=125 or 150 to hover on one of two mixed-scale outputs.
"""

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from gnome_live import COMPANION, ROOT, UUID, configure_fractional_displays, systemd_fixture, until

FIXTURE = 'hover-pointer@test'
SERVICE = 'local.zorin11.HoverTest'
OBJECT_PATH = '/local/zorin11/HoverTest'
POINTER_EXTENSION = r'''
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const XML = '<node><interface name="local.zorin11.HoverTest">' +
    '<method name="Point"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>' +
    '<method name="Click"/><method name="Escape"/><method name="HideOverview"/>' +
    '<method name="Geometry"><arg type="i" direction="in"/><arg type="s" direction="out"/></method>' +
    '</interface></node>';

export default class extends Extension {
    enable() {
        const seat = Clutter.get_default_backend().get_default_seat();
        this.pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        this.keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.bus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this.bus.export(Gio.DBus.session, '/local/zorin11/HoverTest');
        this.owner = Gio.bus_own_name_on_connection(Gio.DBus.session, 'local.zorin11.HoverTest', 0, null, null);
    }

    Point(x, y) {
        this.pointer.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
    }

    Click() {
        this.pointer.notify_button(GLib.get_monotonic_time(), 1, Clutter.ButtonState.PRESSED);
        this.pointer.notify_button(GLib.get_monotonic_time(), 1, Clutter.ButtonState.RELEASED);
    }

    Escape() {
        this.keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.PRESSED);
        this.keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.RELEASED);
    }

    HideOverview() {
        Main.overview.hide();
    }

    Geometry(id) {
        const window = global.get_window_actors().map(actor => actor.meta_window)
            .find(window => window?.get_stable_sequence() === id);
        if (!window) return '{}';
        const rect = r => [r.x, r.y, r.width, r.height];
        const point = global.get_pointer();
        const detector = Main.extensionManager.lookup('zorin11@zorin-os-fixes').stateObj._maximizeHover;
        return JSON.stringify({
            buffer: rect(window.get_buffer_rect()),
            area: rect(window.get_work_area_current_monitor()),
            pointer: point,
            hovering: detector?._hover?.win?.get_stable_sequence(),
            candidate: detector?._candidate?.(...point)?.get_stable_sequence(),
            fired: detector?._fired,
        });
    }

    disable() {
        this.bus.unexport();
        Gio.bus_unown_name(this.owner);
        this.pointer = null;
        this.keyboard = null;
    }
}
'''


def run_session(temp):
    if (os.environ.get('XDG_RUNTIME_DIR') != str(temp / 'runtime')
            or os.environ.get('XDG_CONFIG_HOME') != str(temp / 'config')
            or os.environ.get('GSETTINGS_BACKEND') != 'keyfile'):
        raise RuntimeError('The hover test must use its private runtime and settings directories')
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi, Gio, GLib

    sys.path.insert(0, str(COMPANION))
    from gnome_bridge import call
    from windowing import zone_rect

    extensions = temp / 'data/gnome-shell/extensions'
    extension = extensions / UUID
    shutil.copytree(ROOT / 'gnome-extension', extension)
    for icon in ('start.svg', 'search.svg', 'taskview.svg'):
        shutil.copy(COMPANION / icon, extension / icon)
    subprocess.run(['glib-compile-schemas', str(extension / 'schemas')], check=True)
    fixture = extensions / FIXTURE
    fixture.mkdir()
    (fixture / 'metadata.json').write_text(json.dumps({
        'uuid': FIXTURE, 'name': 'Private maximize hover pointer', 'description': 'Test only',
        'shell-version': ['46'],
    }))
    (fixture / 'extension.js').write_text(POINTER_EXTENSION)
    (temp / 'hub').mkdir()
    (temp / 'hub/multitasking.json').write_text(json.dumps({'assist': False}))

    shell = Gio.Settings.new('org.gnome.shell')
    shell.set_strv('enabled-extensions', [UUID, FIXTURE])
    shell.set_strv('disabled-extensions',
                  [path.name for path in Path('/usr/share/gnome-shell/extensions').iterdir()
                   if path.is_dir()])
    shell.set_string('welcome-dialog-last-shown-version', '46.0')
    Gio.Settings.new('org.gnome.desktop.wm.preferences').set_string(
        'button-layout', 'appmenu:minimize,maximize,close')
    schema_source = Gio.SettingsSchemaSource.new_from_directory(
        str(extension / 'schemas'), Gio.SettingsSchemaSource.get_default(), False)
    settings = Gio.Settings.new_full(schema_source.lookup('org.gnome.shell.extensions.zorin11', False), None, None)
    settings.set_boolean('maximize-hover', True)
    scale = int(os.environ.get('ZORIN11_TEST_HOVER_SCALE', '100'))
    if scale not in (100, 125, 150):
        raise ValueError('The hover test supports 100%, 125% or 150%')
    fractional = scale != 100
    monitors = ['--virtual-monitor', '1280x800']
    if fractional:
        monitors = ['--virtual-monitor', '1600x1000', '--virtual-monitor', '1920x1080']
        Gio.Settings.new('org.gnome.mutter').set_strv('experimental-features', ['scale-monitor-framebuffer'])
    Gio.Settings.sync()

    children = []
    with (temp / 'shell.log').open('w') as shell_log, (temp / 'app.log').open('w') as app_log:
        def start(args, env=None, log=app_log):
            child = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            children.append(child)
            return child

        try:
            start([sys.executable, __file__, '--systemd-fixture'])
            time.sleep(.3)
            start(['gnome-shell', '--headless', '--wayland', *monitors,
                   '--wayland-display', 'maximize-hover-test'], log=shell_log)
            until(lambda: call('snapshot'))
            if fractional:
                configure_fractional_displays()
            xdisplay = until(lambda: re.search(r'public X11 display (:\d+)', (temp / 'shell.log').read_text()))[1]
            env = dict(os.environ, DISPLAY=xdisplay,
                       XAUTHORITY=str(next((temp / 'runtime').glob('.mutter-Xwaylandauth.*'))))
            subprocess.run(['dbus-update-activation-environment', 'DISPLAY=' + xdisplay,
                            'XAUTHORITY=' + env['XAUTHORITY'],
                            'WAYLAND_DISPLAY=' + env['WAYLAND_DISPLAY']], env=env, check=True)
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

            def invoke(member, arguments=None):
                return bus.call_sync(SERVICE, OBJECT_PATH, SERVICE, member, arguments, None, 0, 3000, None)

            def point(x, y):
                invoke('Point', GLib.Variant('(ii)', (x, y)))

            def geometry(window_id):
                return json.loads(invoke('Geometry', GLib.Variant('(i)', (window_id,))).unpack()[0])

            until(lambda: invoke('HideOverview') is not None)
            app = start([sys.executable, str(COMPANION / 'app.py'), '--background'],
                        dict(env, GDK_BACKEND='x11'))
            other = start([sys.executable, '-c',
                           "import gi;gi.require_version('Gtk','3.0');from gi.repository import Gtk;"
                           "w=Gtk.Window(title='Untouched hover test window');w.set_default_size(450,320);"
                           "w.show_all();Gtk.main()"], dict(env, GDK_BACKEND='wayland'))
            start([shutil.which('brave-browser'), '--ozone-platform=wayland',
                           '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
                           '--password-store=basic', '--force-renderer-accessibility=basic',
                           '--user-data-dir=' + str(temp / 'brave'), '--window-size=900,640', 'about:blank'],
                  dict(env, GDK_BACKEND='wayland', ACCESSIBILITY_ENABLED='1'))

            def snapshot():
                return call('snapshot')['windows']

            def row(pid, title=None):
                return next((w for w in snapshot()
                             if w['pid'] == pid and (title is None or w['title'] == title)), None)

            target = until(lambda: next((w for w in snapshot()
                                        if 'brave' in w['cls'].lower() and w['rect'][2] > 200), None))
            assert target['app'] in ('brave-browser.desktop', 'com.brave.Browser.desktop'), target
            brave_pid = target['pid']
            other_before = until(lambda: row(other.pid))['rect']
            win_id = target['id']
            invoke('HideOverview')
            time.sleep(.4)
            if fractional:
                top = 720 if scale == 125 else 0
                call('window', id=win_id, action='move', rect=[160, top + 45, 860, 590])
                until(lambda: top <= row(brave_pid)['rect'][1] < top + 120)
            call('window', id=win_id, action='activate')
            x, y, width, height = row(brave_pid)['rect']
            point(x + width // 2, y + height * 3 // 4)
            time.sleep(.1)
            invoke('Click')
            until(lambda: row(brave_pid)['focused'])

            Atspi.init()
            Atspi.set_timeout(1000, 1000)

            def find_button(pid, name, coord):
                desktop = Atspi.get_desktop(0)
                applications = (desktop.get_child_at_index(i) for i in range(desktop.get_child_count()))
                application = next((a for a in applications if a and a.get_process_id() == pid), None)
                if not application:
                    return None
                stack = [application]
                for _ in range(350):
                    if not stack:
                        break
                    accessible = stack.pop()
                    role = accessible.get_role()
                    if role == Atspi.Role.PUSH_BUTTON and accessible.get_name() == name:
                        extents = accessible.get_component_iface().get_extents(coord)
                        if extents.width > 0 and extents.height > 0:
                            return extents
                    if role != Atspi.Role.DOCUMENT_WEB:
                        for i in reversed(range(min(accessible.get_child_count(), 160))):
                            child = accessible.get_child_at_index(i)
                            if child:
                                stack.append(child)
                return None

            def brave_button(name):
                button = until(lambda: find_button(brave_pid, name, Atspi.CoordType.WINDOW))
                x, y, _width, _height = geometry(win_id)['buffer']
                return x + button.x + button.width // 2, y + button.y + button.height // 2

            def picker():
                return row(app.pid, 'Snap layouts')

            def wait_for_picker(target_point):
                try:
                    return until(picker, seconds=5)
                except AssertionError as error:
                    actual = geometry(win_id)
                    buffer = actual['buffer']
                    request = {'pid': brave_pid, 'title': row(brave_pid)['title'],
                               'width': buffer[2], 'height': buffer[3],
                               'x': target_point[0] - buffer[0], 'y': target_point[1] - buffer[1]}
                    diagnostic = subprocess.run([sys.executable, str(COMPANION / 'maximize_control.py')],
                                               input=json.dumps(request), text=True, capture_output=True, timeout=2)
                    raise AssertionError((target_point, row(brave_pid), actual, request, diagnostic.stdout)) from error

            minimize = brave_button('Minimize')
            maximize = brave_button('Maximize')
            origin = (maximize[0], maximize[1] + 120)

            point(*minimize)
            time.sleep(1.1)
            assert not picker(), 'Hovering Minimize opened Snap layouts'
            point(*maximize)
            time.sleep(.16)
            point(*origin)
            time.sleep(1)
            assert not picker(), 'The picker opened after leaving Maximize early'

            point(*maximize)
            wait_for_picker(maximize)
            point(x + 30, y + height - 30)
            until(lambda: not picker())
            until(lambda: row(brave_pid)['focused'])
            point(*maximize)
            wait_for_picker(maximize)
            invoke('Escape')
            until(lambda: not picker())
            time.sleep(.9)
            assert not picker(), 'Escape reopened the picker without a fresh hover'
            point(*origin)
            until(lambda: row(brave_pid)['focused'])
            print(f'Brave Maximize hover at {scale}% opened and dismissed correctly; '
                  'Minimize and early leave did not trigger it: passed', flush=True)

            call('window', id=win_id, action='maximize')
            until(lambda: row(brave_pid)['maximized'])
            time.sleep(.65)
            restore = brave_button('Restore')
            point(*restore)
            wait_for_picker(restore)
            zone = until(lambda: find_button(app.pid, 'Halves, zone 1', Atspi.CoordType.SCREEN))
            point(zone.x + zone.width // 2, zone.y + zone.height // 2)
            time.sleep(.2)
            invoke('Click')
            expected = list(zone_rect(geometry(win_id)['area'], (0, 0, .5, 1)))
            until(lambda: row(brave_pid)['rect'] == expected)
            assert row(other.pid)['rect'] == other_before
            assert not picker()
            print('Brave Restore hover and real pointer click snapped only the browser to the selected zone: passed', flush=True)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()


if __name__ == '__main__':
    if '--systemd-fixture' in sys.argv:
        systemd_fixture()
    elif '--session' in sys.argv:
        run_session(Path(sys.argv[-1]))
    else:
        if not shutil.which('brave-browser'):
            raise SystemExit('Install Brave to run this private Wayland test.')
        with tempfile.TemporaryDirectory(prefix='zorin11-maximize-hover-') as directory:
            temp = Path(directory)
            for name in ('home', 'data', 'config', 'cache', 'runtime'):
                (temp / name).mkdir(mode=0o700)
            env = dict(os.environ, HOME=str(temp / 'home'), XDG_DATA_HOME=str(temp / 'data'),
                       XDG_CONFIG_HOME=str(temp / 'config'), XDG_CACHE_HOME=str(temp / 'cache'),
                       XDG_RUNTIME_DIR=str(temp / 'runtime'), GSETTINGS_BACKEND='keyfile',
                       XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland', GTK_USE_PORTAL='0',
                       WAYLAND_DISPLAY='maximize-hover-test', ZORIN11_CONFIG_DIR=str(temp / 'hub'),
                       ZORIN11_RUNTIME_DIR=str(COMPANION), PYTHONPATH=str(COMPANION))
            env.pop('AT_SPI_BUS_ADDRESS', None)
            result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__,
                                     '--session', str(temp)], env=env, capture_output=True, text=True, timeout=90)
            print(result.stdout, end='')
            if result.returncode:
                print(result.stderr[-5000:])
                for name in ('shell.log', 'app.log'):
                    if (temp / name).exists():
                        print(name, (temp / name).read_text()[-6000:])
            raise SystemExit(result.returncode)
