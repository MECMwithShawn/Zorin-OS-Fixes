// Window glass: every app window shows a little of the desktop behind it, blurred,
// like Windows 11's acrylic. A background-blur actor sits under the window's
// surfaces, and the surfaces (not the window actor, which the WM animates) get a
// slightly lowered opacity. Fullscreen windows stay solid.
//
// Settings live in ~/.config/zorin11-hub/glass.json: {"enabled", "active", "inactive", "blur"}.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {DEFAULTS, normalize, wantsGlass, opacityFor} from './model.js';

const BLUR_NAME = 'zorin11-glass-blur';

export default class WindowGlass extends Extension {
    enable() {
        this._cfg = {...DEFAULTS};
        this._tracked = new Map();
        this._waiting = new Map();
        this._file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'zorin11-hub', 'glass.json']));
        this._read();
        try {
            this._monitor = this._file.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._monitorId = this._monitor.connect('changed', () => {
                this._read();
                this._refreshAll();
            });
        } catch (e) {
            logError(e, 'Window glass: cannot watch glass.json');
        }
        this._createdId = global.display.connect('window-created', (_d, win) => this._consider(win));
        this._focusId = global.display.connect('notify::focus-window', () => this._refreshAll());
        for (const actor of global.get_window_actors())
            this._consider(actor.meta_window);
    }

    disable() {
        global.display.disconnect(this._createdId);
        global.display.disconnect(this._focusId);
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        for (const [win, ids] of this._waiting)
            ids.forEach(id => win.disconnect(id));
        this._waiting = null;
        for (const win of [...this._tracked.keys()])
            this._untrack(win);
        this._tracked = null;
    }

    _read() {
        try {
            const [, bytes] = this._file.load_contents(null);
            this._cfg = normalize(JSON.parse(new TextDecoder().decode(bytes)));
        } catch {
            this._cfg = {...DEFAULTS};
        }
    }

    _info(win) {
        return {
            type: win.get_window_type(), skipTaskbar: win.is_skip_taskbar(), wmClass: win.get_wm_class(),
            fullscreen: win.is_fullscreen(), focused: win.has_focus(),
        };
    }

    _consider(win) {
        if (!win || this._tracked.has(win) || this._waiting.has(win))
            return;
        const actor = win.get_compositor_private();
        if (!actor || !win.get_wm_class()) {
            // The class and the first frame can arrive after window-created.
            const retry = () => {
                this._waiting.get(win)?.forEach(id => win.disconnect(id));
                this._waiting.delete(win);
                this._consider(win);
            };
            this._waiting.set(win, [win.connect('shown', retry), win.connect('notify::wm-class', retry), win.connect('unmanaged', () => {
                this._waiting.get(win)?.forEach(id => win.disconnect(id));
                this._waiting.delete(win);
            })]);
            return;
        }
        const effect = new Shell.BlurEffect({mode: Shell.BlurMode.BACKGROUND, radius: this._cfg.blur, brightness: 1.0});
        const blur = new Clutter.Actor({name: BLUR_NAME, reactive: false});
        blur.add_effect_with_name('blur', effect);
        actor.insert_child_below(blur, null);
        const entry = {win, actor, blur, effect, ids: []};
        const on = (obj, signal, fn) => entry.ids.push([obj, obj.connect(signal, fn)]);
        on(win, 'size-changed', () => this._layout(entry));
        on(win, 'position-changed', () => this._layout(entry));
        on(win, 'notify::fullscreen', () => this._apply(entry));
        on(win, 'notify::skip-taskbar', () => this._apply(entry));
        on(win, 'notify::window-type', () => this._apply(entry));
        // Wayland clients can replace their surface actors; restyle new ones.
        on(actor, 'child-added', () => this._apply(entry));
        on(actor, 'destroy', () => this._untrack(win));
        this._tracked.set(win, entry);
        this._layout(entry);
        this._apply(entry);
    }

    _layout(entry) {
        const frame = entry.win.get_frame_rect();
        const buffer = entry.win.get_buffer_rect();
        entry.blur.set_position(frame.x - buffer.x, frame.y - buffer.y);
        entry.blur.set_size(frame.width, frame.height);
    }

    _apply(entry) {
        const info = this._info(entry.win);
        const opacity = wantsGlass(info) ? opacityFor(this._cfg, info) : 255;
        entry.blur.visible = opacity < 255 && this._cfg.blur > 0;
        entry.effect.radius = Math.max(1, this._cfg.blur);
        for (const child of entry.actor.get_children()) {
            if (child !== entry.blur && child.opacity !== opacity)
                child.opacity = opacity;
        }
    }

    _refreshAll() {
        for (const entry of this._tracked.values())
            this._apply(entry);
    }

    _untrack(win) {
        const entry = this._tracked?.get(win);
        if (!entry)
            return;
        this._tracked.delete(win);
        for (const [obj, id] of entry.ids) {
            try {
                obj.disconnect(id);
            } catch {}
        }
        for (const child of entry.actor.get_children()) {
            if (child !== entry.blur)
                child.opacity = 255;
        }
        entry.blur.destroy();
    }
}
