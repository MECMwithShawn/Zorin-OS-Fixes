// Keeps browser picture-in-picture videos above other windows, as Windows does.
//
// Each video window is pinned once, when it is first recognised (browsers can
// set the title just after the window appears). After that it is left alone,
// so Win+Ctrl+T or Alt+Space → Always on Top still unpins it, and it stays
// unpinned when the extension restarts after the lock screen. Disabling the
// extension leaves open videos as they are.
import {isPictureInPicture} from './pip-state.js';

// Lives with the module, so it outlasts disable/enable in one Shell session.
const pinned = new WeakSet();

export class PipOnTop {
    constructor() {
        this._watched = new Map();
        this._created = global.display.connect('window-created', (_display, win) => this._watch(win));
        for (const actor of global.get_window_actors())
            this._pinIfVideo(actor.meta_window);
    }

    _matches(win) {
        return isPictureInPicture({
            title: win.get_title(),
            wmClass: win.get_wm_class(),
            appId: win.get_sandboxed_app_id?.() || win.get_gtk_application_id?.() || null,
        });
    }

    _watch(win) {
        if (!win || this._watched.has(win) || this._pinIfVideo(win))
            return;
        const check = () => {
            if (this._pinIfVideo(win))
                this._unwatch(win);
        };
        this._watched.set(win, [
            win.connect('notify::title', check),
            win.connect('notify::wm-class', check),
            win.connect('unmanaged', () => this._unwatch(win)),
        ]);
    }

    _pinIfVideo(win) {
        if (!win || !this._matches(win))
            return false;
        if (!pinned.has(win)) {
            pinned.add(win);
            if (!win.is_above())
                win.make_above();
        }
        return true;
    }

    _unwatch(win) {
        for (const id of this._watched.get(win) ?? []) {
            try {
                win.disconnect(id);
            } catch (e) {}
        }
        this._watched.delete(win);
    }

    destroy() {
        if (this._created)
            global.display.disconnect(this._created);
        this._created = 0;
        for (const win of [...this._watched.keys()])
            this._unwatch(win);
    }
}
