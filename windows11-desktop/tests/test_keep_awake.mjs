// Run with: gjs -m tests/test_keep_awake.mjs
import GLib from 'gi://GLib';
import {KeepAwake} from '../gnome-lockscreen-extension/keep-awake.js';

let failed = false;
const check = (ok, message) => { if (!ok) { print(`FAIL ${message}`); failed = true; } };

class Bus {
    constructor() { this.held = new Set(); this.next = 1; this.pending = null; this.calls = []; }
    call(name, path, iface, method, parameters, type, flags, timeout, cancel, callback) {
        this.calls.push(method);
        if (method === 'Uninhibit') this.held.delete(parameters.deepUnpack()[0]);
        if (method !== 'Inhibit') return;
        check(parameters.deepUnpack()[3] === 8, 'Only idle may be inhibited, never suspend or logout');
        const cookie = this.next++;
        this.held.add(cookie);
        this.pending = () => callback(this, cookie);
    }
    call_finish(cookie) { return {deepUnpack: () => [cookie]}; }
    answer() { this.pending?.(); this.pending = null; }
}
class Shield {
    constructor() { this.locked = false; this.handler = null; }
    connect(signal, handler) { this.handler = handler; return 1; }
    disconnect() { this.handler = null; }
    set(locked) { this.locked = locked; this.handler(); }
}
const make = idle => { const bus = new Bus(), shield = new Shield(); return [bus, shield, new KeepAwake(shield, () => idle, bus)]; };

let [bus, shield, keep] = make(100);
shield.set(true); bus.answer();
check(bus.held.size === 1, 'A manual lock takes one hold');
shield.handler(); check(bus.held.size === 1, 'A repeated signal must not take a second hold');
shield.set(false);
check(bus.held.size === 0, 'Unlocking releases the hold');
keep.destroy();

[bus, shield, keep] = make(60000);
shield.set(true);
check(!bus.calls.includes('Inhibit'), 'An idle lock lets the displays sleep');
keep.destroy();

[bus, shield, keep] = make(100);
shield.set(true); shield.set(false); bus.answer();
check(bus.held.size === 0, 'Unlocking before the hold arrives still releases it');
keep.destroy();

[bus, shield, keep] = make(100);
shield.set(true); bus.answer(); keep.destroy();
check(bus.held.size === 0 && shield.handler === null, 'Disabling releases the hold');

const bus2 = new Bus(), shield2 = new Shield();
const timed = new KeepAwake(shield2, () => 0, bus2, 1 / 60);
shield2.set(true); bus2.answer();
const loop = new GLib.MainLoop(null, false);
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1400, () => { loop.quit(); return GLib.SOURCE_REMOVE; });
loop.run();
check(bus2.held.size === 0, 'The hold ends by itself so a forgotten laptop can sleep');
shield2.set(false); timed.destroy();

if (failed) imports.system.exit(1);
print('PASS keep-awake holds, releases and times out');
