import assert from 'node:assert/strict';
import {isPictureInPicture} from '../gnome-extension/pip-state.js';

const pip = (title, wmClass, appId = null) => isPictureInPicture({title, wmClass, appId});
// Chromium browsers and Firefox, native Wayland app IDs and X11 classes.
assert.ok(pip('Picture in picture', 'brave-browser'));
assert.ok(pip('Picture in picture', 'Brave-browser'));
assert.ok(pip('Picture in picture', 'google-chrome'));
assert.ok(pip('Picture in picture', 'chromium'));
assert.ok(pip('Picture in picture', 'microsoft-edge'));
assert.ok(pip('Picture-in-Picture', 'firefox'));
assert.ok(pip('Picture-in-Picture', 'org.mozilla.firefox'));
assert.ok(pip(' picture-in-picture ', 'firefox'), 'case and spacing do not matter');
// A Brave web app (YouTube installed as an app) keeps Brave in its app ID.
assert.ok(pip('Picture in picture', 'brave-agimnkijcaahngcdmfeangaknmldooml-Default'));
// Flatpak browsers report their app ID separately.
assert.ok(pip('Picture in picture', null, 'com.brave.Browser'));
// Normal browser windows carry the browser name in the title.
assert.ok(!pip('Picture in picture - YouTube - Brave', 'brave-browser'));
assert.ok(!pip('YouTube - Brave', 'brave-browser'));
// Other apps are left alone, whatever the title.
assert.ok(!pip('Picture in picture', 'org.gnome.TextEditor'));
assert.ok(!pip('Picture in picture', null, null));
assert.ok(!pip(null, 'brave-browser'));
assert.ok(!pip('', 'brave-browser'));
console.log('picture-in-picture decisions passed');
