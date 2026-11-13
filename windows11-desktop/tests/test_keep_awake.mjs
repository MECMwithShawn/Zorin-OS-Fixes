// Run with: gjs -m tests/test_keep_awake.mjs
import GLib from 'gi://GLib';
import {KeepAwake} from '../gnome-lockscreen-extension/keep-awake.js';

let failed = false;
const check = (ok, message) => { if (!ok) { print(`FAIL ${message}`); failed = true; } };

let sent = 0;
const send = () => sent++;
let keep = new KeepAwake(() => 100);
check(keep.holdBack(true, send) === true && sent === 0, 'A manual lock holds the signal back');
check(keep.holdBack(true, send) === false, 'A repeated signal passes through');
check(keep.holdBack(false, send) === false && sent === 0, 'Unlocking passes through and drops the held signal');
check(keep.holdBack(true, send) === true, 'The next lock is held back again');
keep.destroy();
check(sent === 1, 'Disabling sends the held signal so the power service is not left waiting');

check(new KeepAwake(() => 60000).holdBack(true, send) === false, 'An idle lock lets the displays sleep');

sent = 0;
const timed = new KeepAwake(() => 0, 1 / 60);
check(timed.holdBack(true, send) === true, 'Timed hold starts');
const loop = new GLib.MainLoop(null, false);
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2500, () => { loop.quit(); return GLib.SOURCE_REMOVE; });
loop.run();
check(sent === 1, 'The signal goes out after the time limit so a forgotten laptop can sleep');

if (failed) imports.system.exit(1);
print('PASS keep-awake holds, releases and times out');
