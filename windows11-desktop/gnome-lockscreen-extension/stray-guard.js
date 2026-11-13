import GLib from 'gi://GLib';

// Checks run this long after the session mode changes, in case GNOME is still
// part-way through switching extensions on.
const SETTLE_MS = [300, 2000, 6000];

// The running extensions that GNOME should have switched off for this session
// mode (a missing "session-modes" list means desktop only).
export function strayExtensions(extensions, mode, parentMode, isRunning) {
    return extensions
        .filter(e => isRunning(e.state) &&
            !(e.sessionModes ?? ['user']).some(m => m === mode || m === parentMode))
        .map(e => e.uuid);
}

// GNOME switches extensions on one at a time and waits for each. If the screen
// locks while it is still working through that list after an unlock (closing
// the lid a moment after unlocking does it), the rest of the list is switched
// on anyway, and desktop-only extensions such as the taskbar end up drawn on
// top of the lock screen. While the screen is locked, this switches them off
// again. It never switches anything on: GNOME does that at the next unlock.
export class StrayGuard {
    constructor({isLocked, modes, extensions, isRunning, disable, log = () => {}, settle = SETTLE_MS}) {
        Object.assign(this, {_isLocked: isLocked, _modes: modes, _extensions: extensions,
            _isRunning: isRunning, _disable: disable, _log: log, _settle: settle});
        this._timers = new Set();
        this._sweeping = false;
    }

    // Call when the session mode changes, and when an extension changes state.
    check() {
        if (!this._isLocked() || this._timers.size)
            return;
        for (const ms of this._settle) {
            const id = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
                this._timers.delete(id);
                this.sweep();
                return GLib.SOURCE_REMOVE;
            });
            this._timers.add(id);
        }
    }

    async sweep() {
        if (this._sweeping || !this._isLocked())
            return 0;
        this._sweeping = true;
        let count = 0;
        try {
            const [mode, parentMode] = this._modes();
            for (const uuid of strayExtensions(this._extensions(), mode, parentMode, this._isRunning)) {
                if (!this._isLocked())
                    break;
                this._log(`switching off ${uuid}, which was left running on the lock screen`);
                // eslint-disable-next-line no-await-in-loop
                await this._disable(uuid);
                count++;
            }
        } catch (e) {
            this._log(`could not switch off a stray extension: ${e.message}`);
        } finally {
            this._sweeping = false;
        }
        return count;
    }

    destroy() {
        for (const id of this._timers)
            GLib.source_remove(id);
        this._timers.clear();
    }
}
