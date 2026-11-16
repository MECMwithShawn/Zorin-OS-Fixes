#!/usr/bin/python3
"""Drive real GTK titlebar drags and pick suggested windows in private Wayland.

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
    '<method name="EscapeWhenSuggestionsOpen"/>' +
    '<method name="State"><arg type="i" direction="in"/><arg type="s" direction="out"/></method>' +
    '</interface></node>';

export default class extends Extension {
    enable() {
        const seat = Clutter.get_default_backend().get_default_seat();
        this.pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        this.keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.grab = null;
        this.escapeSource = 0;
        this.escapedDuringFade = null;
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

    EscapeWhenSuggestionsOpen() {
        const deadline = GLib.get_monotonic_time() + 2_000_000;
        this.escapedDuringFade = null;
        this.escapeSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5, () => {
            const tiling = Main.extensionManager.lookup('zorin-tiling-shell@zorinos.com').stateObj;
            const layout = tiling._tilingManagers.find(manager => manager._tilingSuggestionsLayout?._showing)
                ?._tilingSuggestionsLayout;
            if (!layout && GLib.get_monotonic_time() < deadline)
                return GLib.SOURCE_CONTINUE;
            this.escapeSource = 0;
            if (layout) {
                this.escapedDuringFade = layout._previews.some(tile => tile._container.get_children().some(row =>
                    row.get_children().some(card => card._windowActor?.visible && card._windowActor.get_transition('opacity'))
                ));
                this.Escape();
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    HideOverview() {
        Main.overview.hide();
    }

    State(id) {
        const window = global.get_window_actors().map(actor => actor.meta_window)
            .find(window => window?.get_stable_sequence() === id);
        const rect = r => [r.x, r.y, r.width, r.height];
        const innerRect = actor => [actor.innerX, actor.innerY, actor.innerWidth, actor.innerHeight];
        const suggestedCards = tile => tile._container.get_children().flatMap(row =>
            row.get_children().filter(card => card._metaWindow && card.mapped && card.opacity === 255).map(card => {
                const clone = card.get_window_clone();
                return {
                    id: card._metaWindow.get_stable_sequence(),
                    rect: [...clone.get_transformed_position(), ...clone.get_transformed_size()],
                    color: color(card._previewContainer),
                };
            })
        );
        const color = actor => {
            const {red, green, blue} = actor.get_theme_node().get_background_color();
            return [red, green, blue];
        };
        const tiling = Main.extensionManager.lookup('zorin-tiling-shell@zorinos.com').stateObj;
        const monitors = Main.layoutManager.monitors.map(monitor => {
            const manager = tiling?._tilingManagers?.find(manager => manager._monitor.index === monitor.index);
            const content = manager?._snapAssist?._content;
            const selection = manager?._selectedTilesPreview;
            const suggestions = manager?._tilingSuggestionsLayout;
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
                preview: selection?.showing ? innerRect(selection) : null,
                selectedLayout: manager?._snapAssistingInfo.layoutId,
                suggestions: suggestions?._showing ? suggestions._previews.map(tile => ({
                    rect: innerRect(tile),
                    cards: suggestedCards(tile),
                })) : null,
            };
        });
        return JSON.stringify({
            grab: this.grab,
            escapedDuringFade: this.escapedDuringFade,
            enabled: this.tilingSettings.get_boolean('enable-snap-assist'),
            suggestionsEnabled: this.tilingSettings.get_boolean('enable-snap-assistant-windows-suggestions'),
            monitors,
            pointer: global.get_pointer().slice(0, 2),
            window: window ? {
                rect: rect(window.get_frame_rect()),
                monitor: window.get_monitor(),
                focused: window === global.display.focusWindow,
                visible: window.get_compositor_private()?.visible,
                opacity: window.get_compositor_private()?.opacity,
                scale: window.get_compositor_private()?.get_scale(),
            } : null,
        });
    }

    disable() {
        if (this.escapeSource)
            GLib.source_remove(this.escapeSource);
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

    # Keep the nested Shell from monitoring the physical desktop's logind session.
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS']
    os.environ['XDG_SESSION_ID'] = 'zorin11-snap-test'

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
    Gio.Settings.new('org.gnome.desktop.session').set_uint('idle-delay', 0)
    Gio.Settings.new('org.gnome.desktop.interface').set_boolean('enable-animations', True)
    fractional = os.environ.get('ZORIN11_TEST_FRACTIONAL') == '1'
    monitor_args = ['--virtual-monitor', '1280x800']
    if fractional:
        monitor_args = ['--virtual-monitor', '1600x1000', '--virtual-monitor', '1920x1080']
        mutter = Gio.Settings.new('org.gnome.mutter')
        mutter.set_strv('experimental-features', ['scale-monitor-framebuffer'])
        mutter.set_boolean('workspaces-only-on-primary', False)
    tiling_settings = Gio.Settings.new('org.gnome.shell.extensions.zorin-tiling-shell')
    tiling_settings.set_boolean('enable-snap-assist', True)
    suggestions_key = 'enable-snap-assistant-windows-suggestions'
    if fractional:
        assert tiling_settings.get_user_value(suggestions_key) is None
    else:
        tiling_settings.set_boolean(suggestions_key, False)
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
            until(lambda: all(row['strip'] is not None for row in state(0)['monitors']), seconds=15)
            if fractional:
                configure_fractional_displays()
            app = start([sys.executable, '-c', WINDOW, 'Snap drag test window'])
            win_id = until(lambda: window(app.pid))['id']
            invoke('HideOverview')
            time.sleep(.65)

            def begin_drag(area):
                ax, ay, _aw, _ah = area
                initial = [ax + 180, ay + 190, 520, 350]
                call('window', id=win_id, action='move', rect=initial)
                call('window', id=win_id, action='activate')
                try:
                    until(lambda: (row := state(win_id)['window']) and row['focused']
                          and row['rect'] == initial, seconds=4)
                except AssertionError as error:
                    raise AssertionError(f'Could not place {window(app.pid)} at {initial}: {state(win_id)}') from error
                x = initial[0] + initial[2] // 2
                y = initial[1] + 23
                point(x, y)
                until(lambda: state(win_id)['pointer'] == [x, y], seconds=4)
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
            step(lambda: call('snap-suggestions-ready') is True, 'Native suggestions recovery guard is not ready')
            if fractional:
                step(lambda: state(win_id)['suggestionsEnabled'],
                     'Unset suggestions preference did not turn on when the guard became ready')
                apply_setting('snapSuggestions', False)
                step(lambda: not state(win_id)['suggestionsEnabled'], 'Could not turn suggestions off')
                print('The guard enables the unset suggestions preference at startup: passed', flush=True)
            else:
                assert not state(win_id)['suggestionsEnabled'], 'The guard overrode an explicit opt-out'
                print('The guard preserves an explicit opt-out at startup: passed', flush=True)
            for monitor in monitors:
                index = monitor['index']
                area = monitor['area']
                ax, ay, aw, ah = area
                edge = (ax + aw // 2, ay + 18)
                candidates = {}
                for offset, name in enumerate(('First', 'Second')):
                    candidate = start([sys.executable, '-c', WINDOW, f'{name} suggested window'])
                    ident = until(lambda: window(candidate.pid))['id']
                    rect = [ax + aw // 2 + 25 * offset, ay + 150 + 25 * offset, 520, 350]
                    step(lambda: state(ident)['window']['rect'][2:] == rect[2:], 'Candidate size did not settle')
                    call('window', id=ident, action='move', rect=rect)
                    step(lambda: state(ident)['window']['rect'] == rect,
                         f'Candidate {ident} placement did not settle after aiming for {rect}')
                    candidates[ident] = rect

                def candidate_frames():
                    return {ident: state(ident)['window']['rect'] for ident in candidates}

                def reveal():
                    point(*edge)
                    strip = step(lambda: (current := monitor_state(index)['strip'])['enlarged']
                                 and current, 'Drag did not reveal the strip')
                    assert [layout['id'] for layout in strip['tiles']] == [
                        f'Layout {n}' for n in range(1, 7)], strip
                    assert not any(row['strip']['enlarged'] for row in state(win_id)['monitors']
                                   if row['index'] != index)
                    assert strip['color'] == [34, 41, 48], strip

                def select_left_zone(layout_number, fraction):
                    def placed_zone():
                        zone = monitor_state(index)['strip']['tiles'][layout_number - 1]['zones'][0]
                        rect = zone['rect']
                        return zone if None not in rect and rect[1] >= ay else None

                    zone = step(placed_zone, 'Tile did not enter the monitor work area')
                    assert zone['color'] == [54, 66, 76], zone
                    zx, zy, zw, zh = zone['rect']
                    point(round(zx + zw / 2), round(zy + zh / 2))
                    current = step(lambda: (row := monitor_state(index))['preview'] and row,
                                   'Tile hover did not show a preview')
                    assert current['selectedLayout'] == f'Layout {layout_number}', current
                    assert current['strip']['tiles'][layout_number - 1]['zones'][0]['color'] == [21, 83, 117], current
                    x, y, w, h = current['preview']
                    assert abs(x - ax) <= 8 and abs(y - ay) <= 8, current
                    assert abs(w - aw * fraction) <= 12 and abs(h - ah) <= 16, current
                    return current['preview']

                initial = begin_drag(area)
                reveal()
                select_left_zone(1, .5)
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
                expected = select_left_zone(1, .5)
                release()
                step(lambda: window(app.pid)['rect'] == expected, 'Drop did not place the dragged window')
                assert state(win_id)['window']['monitor'] == index
                assert candidate_frames() == candidates
                step(lambda: not monitor_state(index)['strip']['visible'], 'Strip stayed visible after drop')
                assert monitor_state(index)['suggestions'] is None
                print(f'Top-edge strip, six layouts, retreat, Escape and left-half drop on '
                      f'logical monitor {monitor["bounds"]}: passed', flush=True)

                def drag_into_thirds(before_release=None):
                    begin_drag(area)
                    reveal()
                    expected = select_left_zone(4, 1 / 3)
                    if before_release:
                        before_release()
                    release()
                    step(lambda: window(app.pid)['rect'] == expected, 'Third-width drop did not place the dragged window')
                    assert state(win_id)['window']['monitor'] == index
                    return expected

                def suggestions(expected_ids):
                    def ready():
                        zones = monitor_state(index)['suggestions']
                        if zones is None:
                            return None
                        for zone in zones:
                            cards = {card['id']: card for card in zone['cards']}
                            if set(cards) == expected_ids and all(
                                    card['rect'][2] > 0 and card['rect'][3] > 0 for card in cards.values()):
                                return zone['rect'], cards
                        return None
                    zone, cards = step(ready, 'Unexpected candidate windows or no suggestion cards')
                    assert all(card['color'] == [34, 41, 48] for card in cards.values()), cards
                    assert not any(row['suggestions'] for row in state(win_id)['monitors']
                                   if row['index'] != index)
                    return zone, cards

                apply_setting('snapSuggestions', True)
                step(lambda: state(win_id)['suggestionsEnabled'], 'Shell did not observe the suggestions toggle')
                initial_zone = drag_into_thirds()
                suggestions(set(candidates))
                invoke('Escape')
                step(lambda: monitor_state(index)['suggestions'] is None, 'Escape did not dismiss suggestions')
                step(lambda: all(state(ident)['window']['visible'] for ident in candidates),
                     'Escape did not reveal the unselected windows again')
                assert candidate_frames() == candidates
                assert window(app.pid)['rect'] == initial_zone

                initial_zone = drag_into_thirds(lambda: invoke('EscapeWhenSuggestionsOpen'))
                step(lambda: state(win_id)['escapedDuringFade'], 'Escape was not sent during the candidate fade')
                step(lambda: monitor_state(index)['suggestions'] is None, 'Early Escape did not dismiss suggestions')
                time.sleep(.55)
                for ident in candidates:
                    restored = state(ident)['window']
                    assert restored['visible'] and restored['opacity'] == 255 and restored['scale'] == [1, 1], restored
                assert candidate_frames() == candidates
                assert window(app.pid)['rect'] == initial_zone

                initial_zone = drag_into_thirds()
                remaining = set(candidates)
                for position, ident in enumerate(candidates, start=1):
                    zone, cards = suggestions(remaining)
                    assert abs(zone[0] - (ax + aw * position / 3)) <= 8, zone
                    assert abs(zone[1] - ay) <= 8 and abs(zone[2] - aw / 3) <= 12, zone
                    assert abs(zone[3] - ah) <= 16, zone
                    x, y, width, height = cards[ident]['rect']
                    point(round(x + width / 2), round(y + height / 2))
                    button(True)
                    button(False)
                    step(lambda: state(ident)['window']['rect'] == zone,
                         'The suggestion click did not fill the vacant zone')
                    assert state(ident)['window']['monitor'] == index
                    remaining.remove(ident)
                    assert all(state(other)['window']['rect'] == candidates[other] for other in remaining)
                step(lambda: monitor_state(index)['suggestions'] is None, 'Suggestions stayed open after the last zone')
                assert window(app.pid)['rect'] == initial_zone
                print(f'Open-window suggestions, early/normal Escape and two real preview clicks fill adjacent thirds on '
                      f'logical monitor {monitor["bounds"]}: passed', flush=True)
                apply_setting('snapSuggestions', False)
                step(lambda: not state(win_id)['suggestionsEnabled'], 'Shell did not observe suggestions turning off')
                for ident in candidates:
                    call('window', id=ident, action='close')
                    step(lambda: state(ident)['window'] is None, 'Test candidate did not close')

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
