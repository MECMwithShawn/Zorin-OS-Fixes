import assert from 'node:assert/strict';
import {decide, shift, withMode, MARGIN, GAP} from '../gnome-extension/taskbar-center-state.js';
// A 1280 px panel (1920 px at 150%) with an 8 px end padding and a 400 px tray.
const panel = {width: 1280, pad: 8, prevEnd: null, nextStart: 880};
// Screen-centred apps that are clipped move into the free space.
assert.equal(decide({...panel, mode: 'centerMonitor', overflow: true, groupStart: 400, groupEnd: 880}), 'centered');
assert.equal(decide({...panel, mode: 'centerMonitor', overflow: false, groupStart: 540, groupEnd: 740}), null);
// Back on the centre line only when the apps fit there with room to spare.
const fits = 2 * (880 - 640 - MARGIN);  // largest group that fits with margin
assert.equal(decide({...panel, mode: 'centered', overflow: false, groupStart: 100, groupEnd: 100 + fits}), 'centerMonitor');
assert.equal(decide({...panel, mode: 'centered', overflow: false, groupStart: 100, groupEnd: 100 + fits + 2}), null);
assert.equal(decide({...panel, mode: 'centered', overflow: true, groupStart: 8, groupEnd: 880}), null);
// A group before the apps limits the left side too.
assert.equal(decide({...panel, prevEnd: 600, mode: 'centered', overflow: false, groupStart: 600, groupEnd: 700}), null);
// Other taskbar layouts are left alone.
assert.equal(decide({...panel, mode: 'stackedTL', overflow: true, groupStart: 8, groupEnd: 880}), null);
// In the free space the apps move towards the screen centre, up to the tray.
const near = {...panel, mode: 'centered', overflow: false};
assert.equal(shift({...near, groupStart: 8, groupEnd: 808}), 880 - GAP - 808, 'stops short of the tray');
assert.equal(shift({...near, groupStart: 8, groupEnd: 108}), 640 - 58, 'a small group reaches the centre');
assert.equal(shift({...near, groupStart: 8, groupEnd: 880}), 0, 'a full group stays put');
assert.equal(shift({...near, overflow: true, groupStart: 8, groupEnd: 700}), 0);
assert.equal(shift({...near, mode: 'centerMonitor', groupStart: 540, groupEnd: 740}), 0);
assert.equal(shift({...near, nextStart: 1272, groupStart: 700, groupEnd: 900}), -160, 'and leftwards');
const positions = [
    {element: 'leftBox', visible: true, position: 'centerMonitor'},
    {element: 'showAppsButton', visible: false, position: 'centerMonitor'},
    {element: 'taskbar', visible: true, position: 'centerMonitor'},
    {element: 'rightBox', visible: true, position: 'stackedBR'},
];
const moved = withMode(positions, 'centered');
assert.deepEqual(moved.map(p => p.position), ['centered', 'centered', 'centered', 'stackedBR']);
assert.equal(positions[0].position, 'centerMonitor', 'input is not mutated');
assert.equal(withMode(moved, 'centered'), null);
assert.equal(withMode([{element: 'taskbar', position: 'stackedTL'}], 'centered'), null);
assert.equal(withMode(null, 'centered'), null);
console.log('taskbar centering decisions passed');
