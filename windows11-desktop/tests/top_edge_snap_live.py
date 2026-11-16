#!/usr/bin/python3
"""Drive real GTK titlebar drags in a private GNOME Wayland session.

Requires GNOME Shell 46, Zorin Tiling Shell, and GTK4. Set
ZORIN11_TEST_FRACTIONAL=1 to test both 125% and 150% virtual displays.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from gnome_live import COMPANION, ROOT, UUID, configure_fractional_displays, systemd_fixture, until

FIXTURE = 'snap-drag-pointer@test'
TILING_UUID = 'zorin-tiling-shell@zorinos.com'
SERVICE = 'local.zorin11.SnapDragTest'
OBJECT_PATH = '/local/zorin11/SnapDragTest'
DISPLAY = 'zorin11-snap-drag-test'

WINDOW = '''
import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

app = Gtk.Application()

def activate(app):
    window = Gtk.ApplicationWindow(application=app, title=sys.argv[1])
    window.set_default_size(520, 350)
    titlebar = Gtk.HeaderBar()
    titlebar.set_show_title_buttons(True)
    window.set_titlebar(titlebar)
    window.set_child(Gtk.Label(label='Private Wayland drag test'))
    window.present()

app.connect('activate', activate)
app.run(None)
'''

POINTER_EXTENSION = r'''
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const XML = '<node><interface name="local.zorin11.SnapDragTest">' +
    '<method name="Point"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>' +
    '<method name="Button"><arg type="b" direction="in"/></method>' +
    '<method name="Escape"/><method name="HideOverview"/>' +
    '<method name="State"><arg type="i" direction="in"/><arg type="s" direction="out"/></method>' +
    '</interface></node>';

export default class extends Extension {
    enable() {
        const seat = Clutter.get_default_backend().get_default_seat();
        this.pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        this.keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.grab = null;
        this.tilingSettings = new Gio.Settings({schema_id: 'org.gnome.shell.extensions.zorin-tiling-shell'});
        this.signals = [
            global.display.connect('grab-op-begin', (_display, window, op) => {
                this.grab = {id: window?.get_stable_sequence(), op};
            }),
            global.display.connect('grab-op-end', () => { this.grab = null; }),
        ];
        this.bus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this.bus.export(Gio.DBus.session, '/local/zorin11/SnapDragTest');
        this.owner = Gio.bus_own_name_on_connection(Gio.DBus.session, 'local.zorin11.SnapDragTest', 0, null, null);
    }

    Point(x, y) {
        this.pointer.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
    }

    Button(pressed) {
        this.pointer.notify_button(GLib.get_monotonic_time(), 1,
            pressed ? Clutter.ButtonState.PRESSED : Clutter.ButtonState.RELEASED);
    }

    Escape() {
        this.keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.PRESSED);
        this.keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.RELEASED);
    }

    HideOverview() {
        Main.overview.hide();
    }

    State(id) {
        const window = global.get_window_actors().map(actor => actor.meta_window)
            .find(window => window?.get_stable_sequence() === id);
        const rect = r => [r.x, r.y, r.width, r.height];
        const color = actor => {
            const {red, green, blue} = actor.get_theme_node().get_background_color();
            return [red, green, blue];
        };
        const tiling = Main.extensionManager.lookup('zorin-tiling-shell@zorinos.com').stateObj;
        const monitors = Main.layoutManager.monitors.map(monitor => {
            const manager = tiling?._tilingManagers?.find(manager => manager._monitor.index === monitor.index);
            const content = manager?._snapAssist?._content;
            const selection = manager?._selectedTilesPreview;
            return {
                index: monitor.index,
                bounds: rect(monitor),
                area: rect(Main.layoutManager.getWorkAreaForMonitor(monitor.index)),
                strip: content ? {
                    visible: content.visible,
                    enlarged: content._isEnlarged,
                    color: content.visible ? color(content) : null,
                    tiles: content._snapAssistLayouts.map(layout => {
                        const [x, y] = layout.get_transformed_position();
                        return {
                            id: layout.layout.id,
                            zones: layout._previews.map(tile => {
                                const r = tile.rect;
                                return {
                                    rect: [x + r.x, y + r.y, r.width, r.height],
                                    color: content.visible ? color(tile) : null,
                                };
                            }),
                        };
                    }),
                } : null,
                preview: selection?.showing
                    ? [selection.innerX, selection.innerY, selection.innerWidth, selection.innerHeight] : null,
                selectedLayout: manager?._snapAssistingInfo.layoutId,
            };
        });
        return JSON.stringify({
            grab: this.grab,
            enabled: this.tilingSettings.get_boolean('enable-snap-assist'),
            monitors,
            window: window ? {rect: rect(window.get_frame_rect()), monitor: window.get_monitor()} : null,
        });
    }

    disable() {
        for (const signal of this.signals)
            global.display.disconnect(signal);
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
        raise RuntimeError('This test requires private runtime and settings directories')

    from gi.repository import Gio, GLib

    sys.path.insert(0, str(COMPANION))
    from gnome_bridge import call
    from settings_backend import apply as apply_setting

    extensions = temp / 'data/gnome-shell/extensions'
    extension = extensions / UUID
    shutil.copytree(ROOT / 'gnome-extension', extension)
    for icon in ('start.svg', 'search.svg', 'taskview.svg'):
        shutil.copy(COMPANION / icon, extension / icon)
    subprocess.run(['glib-compile-schemas', str(extension / 'schemas')], check=True)
    fixture = extensions / FIXTURE
    fixture.mkdir()
    (fixture / 'metadata.json').write_text(json.dumps({
        'uuid': FIXTURE, 'name': 'Private Snap drag pointer', 'description': 'Test only',
        'shell-version': ['46'],
    }))
    (fixture / 'extension.js').write_text(POINTER_EXTENSION)
    (temp / 'hub').mkdir()
    (temp / 'hub/multitasking.json').write_text(json.dumps({'assist': False}))

    shell_settings = Gio.Settings.new('org.gnome.shell')
    shell_settings.set_strv('enabled-extensions', [TILING_UUID, UUID, FIXTURE])
    shell_settings.set_strv('disabled-extensions',
                            [path.name for path in Path('/usr/share/gnome-shell/extensions').iterdir()
                             if path.is_dir() and path.name != TILING_UUID])
    shell_settings.set_string('welcome-dialog-last-shown-version', '46.0')
    fractional = os.environ.get('ZORIN11_TEST_FRACTIONAL') == '1'
    monitor_args = ['--virtual-monitor', '1280x800']
    if fractional:
        monitor_args = ['--virtual-monitor', '1600x1000', '--virtual-monitor', '1920x1080']
        mutter = Gio.Settings.new('org.gnome.mutter')
        mutter.set_strv('experimental-features', ['scale-monitor-framebuffer'])
        mutter.set_boolean('workspaces-only-on-primary', False)
    tiling_settings = Gio.Settings.new('org.gnome.shell.extensions.zorin-tiling-shell')
    tiling_settings.set_boolean('enable-snap-assist', True)
    tiling_settings.set_boolean('top-edge-maximize', False)
    Gio.Settings.sync()

    children = []
    with (temp / 'shell.log').open('w') as shell_log, (temp / 'app.log').open('w') as app_log:
        def start(args, log=app_log):
            child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            children.append(child)
            return child

        try:
            start([sys.executable, __file__, '--systemd-fixture'])
            time.sleep(.3)
            start(['gnome-shell', '--headless', '--wayland', *monitor_args, '--wayland-display', DISPLAY],
                  log=shell_log)
            until(lambda: call('snapshot'))
            if fractional:
                configure_fractional_displays()
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

            def invoke(member, arguments=None):
                return bus.call_sync(SERVICE, OBJECT_PATH, SERVICE, member, arguments, None,
                                     Gio.DBusCallFlags.NONE, 3000, None)

            def point(x, y):
                invoke('Point', GLib.Variant('(ii)', (x, y)))

            def button(pressed):
                invoke('Button', GLib.Variant('(b)', (pressed,)))

            def state(window_id):
                return json.loads(invoke('State', GLib.Variant('(i)', (window_id,))).unpack()[0])

            def window(pid):
                return next((row for row in call('snapshot')['windows'] if row['pid'] == pid), None)

            until(lambda: invoke('HideOverview') is not None)
            other = start([sys.executable, '-c', WINDOW, 'Untouched snap test window'])
            until(lambda: window(other.pid))
            app = start([sys.executable, '-c', WINDOW, 'Snap drag test window'])
            win_id = until(lambda: window(app.pid))['id']
            invoke('HideOverview')
            time.sleep(.65)
            other_before = window(other.pid)['rect']

            def begin_drag(area):
                ax, ay, _aw, _ah = area
                initial = [ax + 180, ay + 190, 520, 350]
                call('window', id=win_id, action='move', rect=initial)
                call('window', id=win_id, action='activate')
                try:
                    until(lambda: window(app.pid)['rect'] == initial, seconds=4)
                except AssertionError as error:
                    raise AssertionError(f'Could not place {window(app.pid)} at {initial}: {state(win_id)}') from error
                x = initial[0] + initial[2] // 2
                y = initial[1] + 23
                point(x, y)
                time.sleep(.12)
                try:
                    button(True)
                    time.sleep(.12)
                    point(x, y - 19)
                    def moving():
                        grab = state(win_id)['grab']
                        return grab and grab['id'] == win_id and grab['op'] & ~1024 == 1
                    until(moving, seconds=4)
                    return initial
                except AssertionError as error:
                    button(False)
                    raise AssertionError(f'Titlebar drag failed: {state(win_id)}') from error

            def monitor_state(index):
                return next(row for row in state(win_id)['monitors'] if row['index'] == index)

            def release():
                button(False)
                until(lambda: not state(win_id)['grab'])

            def step(check, description):
                try:
                    return until(check, seconds=5)
                except AssertionError as error:
                    raise AssertionError(f'{description}: {state(win_id)}') from error

            monitors = state(win_id)['monitors']
            for monitor in monitors:
                index = monitor['index']
                area = monitor['area']
                ax, ay, aw, ah = area
                edge = (ax + aw // 2, ay + 18)

                def reveal():
                    point(*edge)
                    strip = step(lambda: (current := monitor_state(index)['strip'])['enlarged']
                                 and current, 'Drag did not reveal the strip')
                    assert [layout['id'] for layout in strip['tiles']] == [
                        f'Layout {n}' for n in range(1, 7)], strip
                    assert not any(row['strip']['enlarged'] for row in state(win_id)['monitors']
                                   if row['index'] != index)
                    assert strip['color'] == [34, 41, 48], strip

                def select_left_half():
                    def placed_zone():
                        zone = monitor_state(index)['strip']['tiles'][0]['zones'][0]
                        rect = zone['rect']
                        return zone if None not in rect and rect[1] >= ay else None

                    zone = step(placed_zone, 'Tile did not enter the monitor work area')
                    assert zone['color'] == [54, 66, 76], zone
                    zx, zy, zw, zh = zone['rect']
                    point(round(zx + zw / 2), round(zy + zh / 2))
                    current = step(lambda: (row := monitor_state(index))['preview'] and row,
                                   'Tile hover did not show a preview')
                    assert current['selectedLayout'] == 'Layout 1', current
                    assert current['strip']['tiles'][0]['zones'][0]['color'] == [21, 83, 117], current
                    x, y, w, h = current['preview']
                    assert abs(x - ax) <= 8 and abs(y - ay) <= 8, current
                    assert abs(w - aw / 2) <= 12 and abs(h - ah) <= 16, current
                    return current['preview']

                initial = begin_drag(area)
                reveal()
                select_left_half()
                point(ax + aw // 2, ay + 170)
                step(lambda: not (row := monitor_state(index))['strip']['enlarged'] and not row['preview'],
                     'Leaving the strip retained the selected zone')
                release()
                assert window(app.pid)['rect'][2:] == initial[2:]
                step(lambda: not monitor_state(index)['strip']['visible'], 'Strip stayed visible after release')

                initial = begin_drag(area)
                reveal()
                invoke('Escape')
                release()
                step(lambda: not monitor_state(index)['strip']['visible'], 'Escape did not dismiss the strip')
                step(lambda: window(app.pid)['rect'] == initial, 'Escape did not restore the original frame')

                begin_drag(area)
                reveal()
                expected = select_left_half()
                release()
                step(lambda: window(app.pid)['rect'] == expected, 'Drop did not place the dragged window')
                assert state(win_id)['window']['monitor'] == index
                assert window(other.pid)['rect'] == other_before
                step(lambda: not monitor_state(index)['strip']['visible'], 'Strip stayed visible after drop')
                print(f'Top-edge strip, six layouts, retreat, Escape and left-half drop on '
                      f'logical monitor {monitor["bounds"]}: passed', flush=True)

            apply_setting('topEdgeSnap', False)
            step(lambda: not state(win_id)['enabled'], 'Shell did not observe the Settings toggle')
            initial = begin_drag(monitors[0]['area'])
            ax, ay, aw, _ah = monitors[0]['area']
            point(ax + aw // 2, ay + 18)
            time.sleep(.45)
            assert not monitor_state(monitors[0]['index'])['strip']['visible']
            release()
            assert window(app.pid)['rect'][2:] == initial[2:]
            print('Disabling top-edge Snap Layouts suppresses the strip and preserves ordinary dragging: passed',
                  flush=True)
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
        if not (Path('/usr/share/gnome-shell/extensions') / TILING_UUID / 'metadata.json').is_file():
            raise SystemExit('Install Zorin Tiling Shell to run this private Wayland test.')
        with tempfile.TemporaryDirectory(prefix='zorin11-snap-drag-') as directory:
            temp = Path(directory)
            for name in ('home', 'data', 'config', 'cache', 'runtime'):
                (temp / name).mkdir(mode=0o700)
            env = dict(os.environ, HOME=str(temp / 'home'), XDG_DATA_HOME=str(temp / 'data'),
                       XDG_CONFIG_HOME=str(temp / 'config'), XDG_CACHE_HOME=str(temp / 'cache'),
                       XDG_RUNTIME_DIR=str(temp / 'runtime'), GSETTINGS_BACKEND='keyfile',
                       XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland', GTK_USE_PORTAL='0',
                       GDK_BACKEND='wayland', WAYLAND_DISPLAY=DISPLAY, LC_ALL='C.UTF-8',
                       LANGUAGE='C.UTF-8', ZORIN11_CONFIG_DIR=str(temp / 'hub'),
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
