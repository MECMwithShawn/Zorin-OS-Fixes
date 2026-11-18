import GLib from 'gi://GLib';

const KEEP_ON_MINUTES = 10;
const RECENT_INPUT = 5000; // ms; an idle timeout locks long after the last key press

// gsd-power switches the displays off the moment it hears the screen saver's
// ActiveChanged signal, ignoring idle inhibitors. After a lock the user asked
// for, this holds that one signal back for a while so the lock screen stays
// visible. Locking itself is unaffected: only the power service's cue is late.
export class KeepAwake {
    constructor(idleTime, minutes = KEEP_ON_MINUTES) {
        this._idleTime = idleTime;
        this._minutes = minutes;
        this._timer = 0;
        this._emit = null;
    }

    recentInput() {
        return this._idleTime() < RECENT_INPUT;
    }

    // Returns true when the caller must not send this ActiveChanged yet.
    holdBack(active, emit) {
        if (!active) {
            this._clear();
            return false;
        }
        if (this._emit || !this.recentInput())
            return false;
        this._emit = emit;
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, this._minutes * 60, () => {
            this._timer = 0;
            this._send();
            return GLib.SOURCE_REMOVE;
        });
        return true;
    }

    _send() {
        const emit = this._emit;
        this._clear();
        emit?.();
    }

    _clear() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        this._emit = null;
    }

    destroy() {
        this._send();
    }
}
