import GLib from 'gi://GLib';

const SYSFS = '/sys/class/power_supply';

const read = path => {
    try {
        return new TextDecoder().decode(GLib.file_get_contents(path)[1]).trim();
    } catch (_) {
        return null;
    }
};

// The kernel reports voltage in microvolts.
export function formatVolts(text) {
    const microvolts = Number(text);
    return text && microvolts > 0 ? `${(microvolts / 1e6).toFixed(2)} V` : '';
}

export function batteryVoltage(root = SYSFS) {
    let names = [];
    try {
        const entries = GLib.Dir.open(root, 0);
        for (let name; (name = entries.read_name());)
            names.push(name);
        entries.close();
    } catch (_) {
        return '';
    }
    const battery = names.sort().find(name => read(`${root}/${name}/type`) === 'Battery');
    return battery ? formatVolts(read(`${root}/${battery}/voltage_now`)) : '';
}

// Adds the battery voltage to the percentage on the Quick Settings battery
// button. The Shell rewrites that title whenever UPower reports a change, so
// the addition lives in its _sync, which also runs each time the menu opens to
// keep the reading fresh.
export class BatteryVoltage {
    constructor(panels, read = batteryVoltage) {
        this._panels = panels;
        this._read = read;
        this._menus = new Map();
        this._proto = null;
        this._original = null;
        this._timer = GLib.timeout_add(GLib.PRIORITY_LOW, 2000, () => {
            this._attach();
            return GLib.SOURCE_CONTINUE;
        });
        this._attach();
    }

    _inject(toggle) {
        if (this._proto)
            return;
        const volts = this._read;
        const original = this._original = Object.getPrototypeOf(toggle)._sync;
        this._proto = Object.getPrototypeOf(toggle);
        this._proto._sync = function () {
            original.call(this);
            const reading = this.visible ? volts() : '';
            if (reading)
                this.title = `${this.title} · ${reading}`;
        };
    }

    _attach() {
        const seen = new Set();
        for (const panel of this._panels()) {
            const quick = panel?.statusArea?.quickSettings;
            const toggle = quick?._system?._systemItem?._powerToggle;
            if (!toggle || !quick.menu)
                continue;
            seen.add(quick.menu);
            this._inject(toggle);
            if (this._menus.has(quick.menu))
                continue;
            const id = quick.menu.connect('open-state-changed', (_menu, open) => {
                if (open)
                    toggle._sync();
            });
            this._menus.set(quick.menu, {id, toggle});
            toggle._sync();
        }
        for (const [menu, {id}] of this._menus) {
            if (!seen.has(menu)) {
                menu.disconnect(id);
                this._menus.delete(menu);
            }
        }
    }

    destroy() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        if (this._proto)
            this._proto._sync = this._original;
        for (const [menu, {id, toggle}] of this._menus) {
            menu.disconnect(id);
            toggle._sync();
        }
        this._menus.clear();
        this._proto = this._original = null;
    }
}
