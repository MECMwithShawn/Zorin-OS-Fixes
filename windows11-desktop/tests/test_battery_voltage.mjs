import GLib from 'gi://GLib';
import {BatteryVoltage, batteryVoltage, formatVolts} from '../gnome-extension/battery-voltage.js';

const assert = (ok, message) => {
    if (!ok)
        throw new Error(message);
};

assert(formatVolts('12034000') === '12.03 V', 'microvolts become volts');
assert(formatVolts('0') === '' && formatVolts('') === '' && formatVolts(null) === '' && formatVolts('n/a') === '', 'bad readings are hidden');

const root = GLib.dir_make_tmp('zorin11-power-XXXXXX');
const write = (name, file, text) => {
    GLib.mkdir_with_parents(`${root}/${name}`, 0o700);
    GLib.file_set_contents(`${root}/${name}/${file}`, text);
};
write('AC', 'type', 'Mains\n');
assert(batteryVoltage(root) === '', 'no battery shows nothing');
write('ucsi', 'type', 'USB\n');
write('ucsi', 'voltage_now', '5000000\n');
write('BAT0', 'type', 'Battery\n');
write('BAT0', 'voltage_now', '12034000\n');
assert(batteryVoltage(root) === '12.03 V', 'only the battery is read');
assert(batteryVoltage(`${root}/missing`) === '', 'a missing folder shows nothing');

class Toggle {
    constructor() {
        this.visible = true;
        this.title = '';
        this.percent = 100;
    }

    _sync() {
        if (this.visible)
            this.title = `${this.percent}%`;
    }
}
class Menu {
    constructor() {
        this.handlers = new Map();
        this.next = 1;
    }

    connect(_signal, handler) {
        this.handlers.set(this.next, handler);
        return this.next++;
    }

    disconnect(id) {
        this.handlers.delete(id);
    }

    open() {
        for (const handler of this.handlers.values())
            handler(this, true);
    }
}
const panel = () => {
    const toggle = new Toggle(), menu = new Menu();
    return {toggle, menu, statusArea: {quickSettings: {menu, _system: {_systemItem: {_powerToggle: toggle}}}}};
};
const original = Toggle.prototype._sync;
const main = panel(), second = panel();
let panels = [main, second, {statusArea: {}}, null], volts = '12.03 V';
const feature = new BatteryVoltage(() => panels, () => volts);

assert(main.toggle.title === '100% · 12.03 V', 'voltage joins the percentage');
assert(second.toggle.title === '100% · 12.03 V', 'every taskbar gets it');
main.toggle.percent = 90;
main.toggle._sync();
assert(main.toggle.title === '90% · 12.03 V', 'a UPower update keeps it, without repeating');
volts = '12.50 V';
main.menu.open();
assert(main.toggle.title === '90% · 12.50 V', 'opening the menu refreshes it');
volts = '';
main.menu.open();
assert(main.toggle.title === '90%', 'an unreadable voltage leaves the plain percentage');
volts = '12.03 V';
main.toggle.visible = false;
main.toggle.title = 'unchanged';
main.toggle._sync();
assert(main.toggle.title === 'unchanged', 'a hidden button is left alone');
main.toggle.visible = true;
panels = [main];
feature._attach();
assert(second.menu.handlers.size === 0 && main.menu.handlers.size === 1, 'a rebuilt taskbar is let go, once');
feature._attach();
assert(main.menu.handlers.size === 1, 'a menu is only connected once');
feature.destroy();
assert(Toggle.prototype._sync === original, 'disable restores the Shell code');
assert(main.toggle.title === '90%', 'disable restores the title');
assert(main.menu.handlers.size === 0, 'disable disconnects the menu');
GLib.spawn_command_line_sync(`rm -rf ${root}`);
print('PASS');
