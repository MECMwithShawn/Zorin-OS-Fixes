import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const BRAVE = new Set(['brave-browser.desktop', 'com.brave.Browser.desktop', 'zorin11-brave-snap.desktop']);
const BUTTONS = Clutter.ModifierType.BUTTON1_MASK | Clutter.ModifierType.BUTTON2_MASK
    | Clutter.ModifierType.BUTTON3_MASK;
const contains = (rect, x, y) =>
    x >= rect[0] && y >= rect[1] && x < rect[0] + rect[2] && y < rect[1] + rect[3];

export class MaximizeHover {
    constructor(settings) {
        this._settings = settings;
        this._tracker = Shell.WindowTracker.get_default();
        this._settingId = settings.connect('changed::maximize-hover', () => this._configure());
        this._configure();
    }

    _configure() {
        this._stop();
        if (Meta.is_wayland_compositor() && this._settings.get_boolean('maximize-hover')) {
            this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
                this._check();
                return GLib.SOURCE_CONTINUE;
            });
        }
    }

    _candidate(x, y, modifiers) {
        if (modifiers & BUTTONS || Main.sessionMode.isLocked || Main.overview.visible || Main.modalCount)
            return null;
        const win = global.display.focus_window;
        if (!win || win.is_fullscreen() || win.minimized || (!win.allows_resize() && !win.get_maximized())
            || !BRAVE.has(this._tracker.get_window_app(win)?.get_id()))
            return null;
        const frame = win.get_frame_rect();
        // Limit accessibility inspection to the top chrome and outer edges.
        // The accessibility control, rather than this filter, selects the button.
        if (y < frame.y || y >= frame.y + 64 || x < frame.x || x >= frame.x + frame.width
            || (x >= frame.x + 180 && x < frame.x + frame.width - 180))
            return null;
        const actor = win.get_compositor_private();
        let picked = global.stage.get_actor_at_pos(Clutter.PickMode.ALL, x, y);
        while (picked && picked !== actor)
            picked = picked.get_parent();
        return picked ? win : null;
    }

    _check() {
        const [x, y, modifiers] = global.get_pointer();
        if (this._fired && contains(this._fired, x, y))
            return;
        this._fired = null;
        const win = this._candidate(x, y, modifiers);
        const now = GLib.get_monotonic_time();
        const hover = this._hover;
        if (!win || hover?.win !== win || Math.hypot(hover.x - x, hover.y - y) > 3) {
            this._hover = win ? {win, x, y, since: now, queried: false} : null;
            return;
        }
        if (!hover.queried && !this._probe && now - hover.since >= 650_000) {
            hover.queried = true;
            this._resolve(hover);
        }
    }

    _resolve(hover) {
        const {win, x, y} = hover;
        const buffer = win.get_buffer_rect();
        const box = [buffer.x, buffer.y, buffer.width, buffer.height];
        const runtime = GLib.getenv('ZORIN11_RUNTIME_DIR')
            || GLib.build_filenamev([GLib.get_home_dir(), '.local/share/zorin11-hub']);
        const request = {pid: win.get_pid(), title: win.get_title(),
            width: buffer.width, height: buffer.height, x: x - buffer.x, y: y - buffer.y};
        let process;
        try {
            process = Gio.Subprocess.new(
                ['/usr/bin/python3', `${runtime}/maximize_control.py`],
                Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (_) {
            return;
        }
        this._probe = process;
        this._deadline = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1100, () => {
            this._deadline = 0;
            this._probe = null;
            process.force_exit();
            return GLib.SOURCE_REMOVE;
        });
        process.communicate_utf8_async(JSON.stringify(request), null, (child, result) => {
            try {
                const [, output] = child.communicate_utf8_finish(result);
                if (this._probe !== process)
                    return;
                const rect = JSON.parse(output);
                if (!Array.isArray(rect) || rect.length !== 4 || !rect.every(Number.isFinite)
                    || rect[2] <= 0 || rect[3] <= 0 || this._hover !== hover)
                    return;
                const [px, py, state] = global.get_pointer();
                if (this._candidate(px, py, state) !== win)
                    return;
                const current = win.get_buffer_rect();
                if ([current.x, current.y, current.width, current.height].some((v, i) => v !== box[i]))
                    return;
                const anchor = [box[0] + rect[0], box[1] + rect[1], rect[2], rect[3]];
                if (!contains(anchor, px, py))
                    return;
                this._fired = anchor;
                Gio.Subprocess.new(['/usr/bin/env', 'GDK_BACKEND=x11', '/usr/bin/python3',
                    `${runtime}/app.py`, '--hover-snap', String(win.get_stable_sequence()),
                    ...anchor.map(value => String(Math.round(value)))], Gio.SubprocessFlags.NONE);
            } catch (_) {
                // Unsupported or unavailable accessibility metadata is normal.
            } finally {
                if (this._probe === process) {
                    this._probe = null;
                    if (this._deadline) GLib.Source.remove(this._deadline);
                    this._deadline = 0;
                }
            }
        });
    }

    _stop() {
        if (this._timer) GLib.Source.remove(this._timer);
        if (this._deadline) GLib.Source.remove(this._deadline);
        this._timer = this._deadline = 0;
        this._probe?.force_exit();
        this._probe = this._hover = this._fired = null;
    }

    destroy() {
        this._stop();
        this._settings.disconnect(this._settingId);
    }
}
