// Run with: gjs -m tests/test_stray_guard.mjs
import GLib from 'gi://GLib';
import {StrayGuard, strayExtensions} from '../gnome-lockscreen-extension/stray-guard.js';

let failed = false;
const check = (ok, message) => { if (!ok) { print(`FAIL ${message}`); failed = true; } };
const ACTIVE = 1, INACTIVE = 2;
const running = state => state === ACTIVE;
const fleet = () => [
    {uuid: 'taskbar', state: ACTIVE},
    {uuid: 'tiling', state: INACTIVE},
    {uuid: 'lockscreen', state: ACTIVE, sessionModes: ['user', 'unlock-dialog']},
    {uuid: 'login', state: ACTIVE, sessionModes: ['gdm']},
    {uuid: 'desktop', state: ACTIVE, sessionModes: ['user']},
];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

check(same(strayExtensions(fleet(), 'unlock-dialog', null, running), ['taskbar', 'login', 'desktop']),
    'On the lock screen, running desktop-only extensions are strays; lock-screen ones and stopped ones are not');
check(same(strayExtensions(fleet(), 'user', null, running), ['login']),
    'On the desktop, desktop extensions are not strays');
check(same(strayExtensions(fleet(), 'unlock-dialog', 'gdm', running), ['taskbar', 'desktop']),
    'An extension allowed in the parent mode is not a stray');

const make = (locked, extensions, extra = {}) => {
    const off = [];
    const guard = new StrayGuard({
        isLocked: () => locked.value, modes: () => ['unlock-dialog', null], extensions: () => extensions,
        isRunning: running, settle: [20, 60],
        disable: async uuid => { off.push(uuid); extensions.find(e => e.uuid === uuid).state = INACTIVE; },
        ...extra});
    return {guard, off};
};
const wait = ms => {
    const loop = new GLib.MainLoop(null, false);
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { loop.quit(); return GLib.SOURCE_REMOVE; });
    loop.run();
};

let locked = {value: true};
let {guard, off} = make(locked, fleet());
guard.check();
check(off.length === 0, 'Nothing is switched off before GNOME has had time to settle');
wait(150);
check(same(off, ['taskbar', 'login', 'desktop']), 'Strays are switched off once, in order, while locked');
guard.destroy();

locked = {value: false};
({guard, off} = make(locked, fleet()));
guard.check();
wait(150);
check(off.length === 0 && guard._timers.size === 0, 'Nothing is touched on the desktop');
guard.destroy();

// The taskbar comes on late, after the first check: the later check catches it.
locked = {value: true};
const late = fleet(); late[0].state = INACTIVE; late[3].state = INACTIVE; late[4].state = INACTIVE;
({guard, off} = make(locked, late));
guard.check();
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 35, () => { late[0].state = ACTIVE; return GLib.SOURCE_REMOVE; });
wait(150);
check(same(off, ['taskbar']), 'An extension switched on after the lock is caught by the later check');
guard.destroy();

// Unlocking part-way stops the sweep, so nothing is switched off on the desktop.
locked = {value: true};
const some = fleet();
const stopped = [];
guard = new StrayGuard({isLocked: () => locked.value, modes: () => ['unlock-dialog', null], extensions: () => some,
    isRunning: running, settle: [20],
    disable: async uuid => { stopped.push(uuid); locked.value = false; }});
guard.check();
wait(100);
check(same(stopped, ['taskbar']), 'Unlocking during a sweep stops it');
guard.destroy();

// A failing extension does not stop later sweeps.
locked = {value: true};
const logs = [];
guard = new StrayGuard({isLocked: () => true, modes: () => ['unlock-dialog', null], extensions: fleet,
    isRunning: running, settle: [20], log: m => logs.push(m),
    disable: async () => { throw new Error('boom'); }});
guard.check();
wait(100);
check(logs.some(m => m.includes('boom')) && guard._sweeping === false, 'A failure is logged and the guard recovers');
guard.destroy();
check(guard._timers.size === 0, 'destroy() cancels pending checks');

if (failed) imports.system.exit(1);
print('PASS stray guard switches off extensions left running on the lock screen');
