import Gio from 'gi://Gio';
import {ExtensionState} from 'resource:///org/gnome/shell/misc/extensionUtils.js';
import {InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const TILING_UUID = 'zorin-tiling-shell@zorinos.com';
const TILING_SCHEMA = 'org.gnome.shell.extensions.zorin-tiling-shell';
const SUGGESTIONS_KEY = 'enable-snap-assistant-windows-suggestions';
const FADE_PROPERTIES = ['opacity', 'scale-x', 'scale-y'];

function tryPreviewRepair(action) {
    try {
        return action();
    } catch (error) {
        console.error('Snap Suggestions compatibility:', error);
        return undefined;
    }
}

export class SnapSuggestions {
    constructor() {
        this._injections = new InjectionManager();
        this._fades = new Map();
        this._prototype = null;
        this._extensionSignal = Main.extensionManager.connect('extension-state-changed', (_, extension) => {
            if (extension.uuid === TILING_UUID)
                this._sync();
        });
        this._startupSignal = Main.layoutManager.connect_after('startup-complete', () => this._sync());
        this._sync();
    }

    get ready() {
        return this._prototype !== null && this._nativePrototype() === this._prototype;
    }

    _nativePrototype() {
        const extension = Main.extensionManager.lookup(TILING_UUID);
        if (extension?.state !== ExtensionState.ACTIVE)
            return null;
        const layout = extension.stateObj?._tilingManagers?.[0]?._tilingSuggestionsLayout;
        return layout ? Object.getPrototypeOf(layout) : null;
    }

    _sync() {
        const prototype = this._nativePrototype();
        if (!prototype || prototype === this._prototype ||
            !['_recursivelyShowPopup', 'close', 'destroy'].every(name => typeof prototype[name] === 'function'))
            return;

        this._clearInjections();
        const guard = this;
        this._injections.overrideMethod(prototype, '_recursivelyShowPopup', original => function (windows, monitor) {
            const before = tryPreviewRepair(() => guard._visibleCandidates(this, windows));
            const result = original.call(this, windows, monitor);
            if (before)
                tryPreviewRepair(() => guard._recordFades(this, before));
            return result;
        });
        for (const method of ['close', 'destroy']) {
            this._injections.overrideMethod(prototype, method, original => function (...args) {
                tryPreviewRepair(() => guard._cancelFades(this));
                return original.apply(this, args);
            });
        }
        this._prototype = prototype;

        const schema = Gio.SettingsSchemaSource.get_default()?.lookup(TILING_SCHEMA, true);
        if (schema?.has_key(SUGGESTIONS_KEY)) {
            const settings = new Gio.Settings({settings_schema: schema});
            if (settings.is_writable(SUGGESTIONS_KEY) && settings.get_user_value(SUGGESTIONS_KEY) === null)
                settings.set_boolean(SUGGESTIONS_KEY, true);
        }
    }

    _visibleCandidates(layout, windows) {
        if (!layout._previews?.length)
            return [];
        const fades = this._fades.get(layout);
        const candidates = [];
        for (const window of windows) {
            const actor = window.get_compositor_private();
            if (window.minimized || !actor?.visible)
                continue;
            const [pivotX, pivotY] = actor.get_pivot_point();
            candidates.push({
                window, actor,
                previousTransitions: FADE_PROPERTIES.map(name => actor.get_transition(name)),
                appearance: fades?.get(actor)?.appearance ?? {
                    opacity: actor.opacity, scaleX: actor.scale_x, scaleY: actor.scale_y,
                    pivotX, pivotY,
                },
            });
        }
        return candidates;
    }

    _recordFades(layout, candidates) {
        for (const candidate of candidates) {
            const {actor, previousTransitions} = candidate;
            const opacity = actor.get_transition('opacity');
            if (!opacity || opacity === previousTransitions[0] ||
                opacity.get_interval()?.peek_final_value() !== 0)
                continue;
            const transitions = FADE_PROPERTIES.map((name, index) => {
                const current = actor.get_transition(name);
                return [name, current === previousTransitions[index] ? null : current];
            });
            if (!this._fades.has(layout))
                this._fades.set(layout, new Map());
            this._fades.get(layout).set(actor, {...candidate, transitions});
        }
    }

    _cancelFades(layout) {
        const fades = this._fades.get(layout);
        this._fades.delete(layout);
        for (const {window, actor, appearance, transitions} of fades?.values() ?? []) {
            if (window.minimized || window.get_compositor_private() !== actor || !actor.visible ||
                actor.get_transition('opacity') !== transitions[0][1])
                continue;

            // Only cancel this popup's still-running transitions. Normally
            // the vendor hides the real window before its preview is removed.
            // If the popup closes sooner, that pending fade must not hide it.
            for (const [name, transition] of transitions) {
                if (transition && actor.get_transition(name) === transition)
                    actor.remove_transition(name);
            }
            if (window === layout._lastTiledWindow && window.assignedTile)
                continue;
            actor.opacity = appearance.opacity;
            if (!actor.get_transition('scale-x'))
                actor.scale_x = appearance.scaleX;
            if (!actor.get_transition('scale-y'))
                actor.scale_y = appearance.scaleY;
            actor.set_pivot_point(appearance.pivotX, appearance.pivotY);
        }
    }

    _clearInjections() {
        for (const layout of this._fades.keys())
            tryPreviewRepair(() => this._cancelFades(layout));
        this._injections.clear();
        this._prototype = null;
    }

    destroy() {
        Main.extensionManager.disconnect(this._extensionSignal);
        Main.layoutManager.disconnect(this._startupSignal);
        this._clearInjections();
    }
}
