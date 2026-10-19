import assert from 'node:assert/strict';
import {ProgressState} from '../gnome-extension/progress-state.js';
const state = new ProgressState(), uri = 'application://org.test.App.desktop';
const app = 'org.test.App.desktop';
assert.equal(state.update(':1.1', uri, {progress: .25, 'progress-visible': true}), true);
assert.equal(state.get(app).value, .25);
state.update(':1.1', uri, {progress: .75});
assert.equal(state.get(app).value, .75);
state.update(':1.1', uri, {'progress-visible': false});
assert.equal(state.get(app), null);
state.update(':1.1', uri, {'progress-visible': true});
assert.equal(state.get(app).value, .75);
state.update(':1.2', uri, {progress: .3, 'progress-visible': true});
assert.equal(state.get(app).value, .3);
state.removeSender(':1.2');
assert.equal(state.get(app).value, .75);
for (const value of [NaN, Infinity, '0.5', null]) {
    assert.equal(state.update(':1.1', uri, {progress: value}), false);
    assert.equal(state.get(app).value, .75);
}
assert.equal(state.update(':1.1', uri, {'progress-visible': 'false'}), false);
state.update(':1.1', uri, {progress: 12}); assert.equal(state.get(app).value, 1);
state.update(':1.1', uri, {progress: -5}); assert.equal(state.get(app).value, 0);
for (const bad of ['file:///tmp/app.desktop', 'application://../app.desktop', 'application://bad app.desktop', 'app.desktop'])
    assert.equal(state.update(':1.1', bad, {progress: 1}), false);
state.removeSender(':1.1'); assert.equal(state.entries.size, 0);
for (let i = 0; i < 300; i++) state.update(`:1.${i}`, uri, {progress: .5});
assert.equal(state.entries.size, 256);
assert.equal(state.update(':1.0', uri, {progress: .6}), true);
console.log('Launcher progress: partial updates, visibility, multiple senders, disconnects, invalid input, bounds and capacity passed');
