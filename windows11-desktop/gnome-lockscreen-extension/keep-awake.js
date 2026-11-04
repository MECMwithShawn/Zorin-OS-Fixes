import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const KEEP_ON_MINUTES = 10;
const RECENT_INPUT = 5000; // ms; an idle timeout locks long after the last key press
const IDLE = 8; // GSM_INHIBITOR_FLAG_IDLE

// GNOME turns the displays off about 30 seconds into a lock. After a lock the
// user asked for, this holds an idle inhibitor for a while so the lock screen
// stays visible. The hold ends on unlock, so nothing changes while signed in.
export class KeepAwake {
    constructor(shield, idleTime, bus = Gio.DBus.session, minutes = KEEP_ON_MINUTES) {
        this._shield = shield;
        this._idleTime = idleTime;
        this._bus = bus;
        this._minutes = minutes;
        this._holding = false;
        this._cookie = 0;
        this._timer = 0;
        this._changed = shield.connect('locked-changed', () => this._sync());
    }

    _sync() {
        if (!this._shield.locked)
            this._release();
        else if (this._idleTime() < RECENT_INPUT)
            this._hold();
    }

    _call(method, parameters, type, callback = null) {
        this._bus.call('org.gnome.SessionManager', '/org/gnome/SessionManager', 'org.gnome.SessionManager',
            method, parameters, type, Gio.DBusCallFlags.NONE, -1, null, callback);
    }

    _hold() {
        if (this._holding)
            return;
        this._holding = true;
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, this._minutes * 60, () => {
            this._timer = 0;
            this._release();
            return GLib.SOURCE_REMOVE;
        });
        const reason = new GLib.Variant('(susu)', ['zorin11-lockscreen', 0, 'Keeping the lock screen visible', IDLE]);
        this._call('Inhibit', reason, new GLib.VariantType('(u)'), (bus, result) => {
            try {
                const [cookie] = bus.call_finish(result).deepUnpack();
                this._cookie = cookie;
                if (!this._holding)
                    this._release();
            } catch (e) {
                console.error(`Axentra lock screen: ${e.message}`);
                this._holding = false;
            }
        });
    }

    _release() {
        this._holding = false;
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        if (this._cookie)
            this._call('Uninhibit', new GLib.Variant('(u)', [this._cookie]), null);
        this._cookie = 0;
    }

    destroy() {
        this._shield.disconnect(this._changed);
        this._release();
    }
}
