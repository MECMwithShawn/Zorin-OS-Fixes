import assert from 'node:assert/strict';
import {DEFAULTS, normalize, wantsGlass, opacityFor} from '../gnome-glass-extension/model.js';

assert.deepEqual(normalize(null), DEFAULTS);
assert.deepEqual(normalize({active: 5, inactive: 300, blur: -4, enabled: 0}), {enabled: false, active: 60, inactive: 100, blur: 0});
assert.deepEqual(normalize({active: 'x', blur: 'y'}), DEFAULTS);

const app = {type: 0, skipTaskbar: false, wmClass: 'brave-browser', fullscreen: false, focused: true};
assert.equal(wantsGlass(app), true);
assert.equal(wantsGlass({...app, type: 3}), true);
assert.equal(wantsGlass({...app, skipTaskbar: true}), false, 'companion surfaces and popups stay as drawn');
assert.equal(wantsGlass({...app, type: 1}), false, 'desktop');
assert.equal(wantsGlass({...app, wmClass: 'axentra-terminal'}), false, 'terminal has its own acrylic');

assert.equal(opacityFor(DEFAULTS, app), Math.round(90 * 255 / 100));
assert.equal(opacityFor(DEFAULTS, {...app, focused: false}), Math.round(85 * 255 / 100));
assert.equal(opacityFor(DEFAULTS, {...app, fullscreen: true}), 255);
assert.equal(opacityFor({...DEFAULTS, enabled: false}, app), 255);
console.log('glass model: ok');
