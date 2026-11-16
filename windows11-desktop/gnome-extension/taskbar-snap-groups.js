import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const TASKBAR = 'zorin-taskbar@zorinos.com';
const CARD = 'zorin11-snap-group-card';
const WINDOW_UPDATES = ['_mergeWindows', '_addAndRemoveWindows'];
const HOOKS = [...WINDOW_UPDATES, '_updatePosition'];

function mosaic(members, width, height, scale, tracker) {
    const actor = new St.Widget({style_class: 'zorin11-snap-group-mosaic',
        layout_manager: new Clutter.FixedLayout(), clip_to_allocation: true});
    actor.set_size(width, height);
    const left = Math.min(...members.map(({rect}) => rect.x));
    const top = Math.min(...members.map(({rect}) => rect.y));
    const spanW = Math.max(...members.map(({rect}) => rect.x + rect.width)) - left;
    const spanH = Math.max(...members.map(({rect}) => rect.y + rect.height)) - top;
    const ratio = Math.min(width / spanW, height / spanH);
    for (const {window, rect} of members) {
        const cell = new St.Widget({style_class: 'zorin11-snap-group-cell',
            layout_manager: new Clutter.BinLayout(), clip_to_allocation: true});
        const x = (width - spanW * ratio) / 2 + (rect.x - left) * ratio;
        const y = (height - spanH * ratio) / 2 + (rect.y - top) * ratio;
        const w = Math.max(1, Math.round(rect.width * ratio) - 1);
        const h = Math.max(1, Math.round(rect.height * ratio) - 1);
        cell.set_position(Math.round(x), Math.round(y));
        cell.set_size(w, h);
        const iconSize = Math.min(Math.floor(w / scale), Math.floor(h / scale), 24);
        if (iconSize >= 6) {
            const app = tracker.get_window_app(window);
            const icon = app?.create_icon_texture(iconSize) ??
                new St.Icon({icon_name: 'focus-windows-symbolic', icon_size: iconSize});
            icon.set_x_align(Clutter.ActorAlign.CENTER);
            icon.set_y_align(Clutter.ActorAlign.CENTER);
            cell.add_child(icon);
        }
        const source = window.get_compositor_private();
        if (source?.visible && !window.minimized) {
            cell.add_child(new Clutter.Clone({source,
                x_expand: true, y_expand: true,
                x_align: Clutter.ActorAlign.FILL, y_align: Clutter.ActorAlign.FILL}));
        }
        actor.add_child(cell);
    }
    return actor;
}

export class TaskbarSnapGroups {
    constructor(registry) {
        this._registry = registry;
        this._tracker = Shell.WindowTracker.get_default();
        this._injections = new InjectionManager();
        this._prototypes = new Set();
        this._unsupported = new WeakSet();
        this._states = new Map();
        this._mutating = new WeakSet();
        this._manager = null;
        this._panelsChanged = 0;
        this._pending = 0;
        this._extensionChanged = Main.extensionManager.connect('extension-state-changed', (_, extension) => {
            if (extension.uuid === TASKBAR)
                this.refresh();
        });
        this._sync();
    }

    refresh() {
        if (this._pending)
            return;
        this._pending = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._pending = 0;
            this._sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    _sync() {
        const manager = global.zorinTaskbar;
        if (manager !== this._manager) {
            if (this._panelsChanged)
                this._manager.disconnect(this._panelsChanged);
            this._manager = manager;
            this._panelsChanged = manager?.connect('panels-created', () => this.refresh()) ?? 0;
        }
        for (const panel of manager?.panels ?? []) {
            const menu = panel.taskbar?.previewMenu;
            if (!menu?._box)
                continue;
            const prototype = Object.getPrototypeOf(menu);
            if (!this._prototypes.has(prototype) && !this._unsupported.has(prototype))
                this._patch(prototype);
            if (this._prototypes.has(prototype) && menu.opened && menu.currentAppIcon)
                menu.updatePosition();
        }
    }

    _patch(prototype) {
        const required = [...HOOKS, '_endPeek', 'ensureVisible', 'updatePosition', 'close'];
        if (!required.every(name => typeof prototype[name] === 'function')) {
            this._unsupported.add(prototype);
            return;
        }
        const integration = this;
        // Zorin treats its preview row as a window-only list when it reconciles
        // clients. The extra cards belong in its measurement and focus cycling.
        for (const name of WINDOW_UPDATES) {
            this._injections.overrideMethod(prototype, name, original => function (...args) {
                integration._mutating.add(this);
                try {
                    integration._guard(this, () => integration._clearCards(this));
                    return original.apply(this, args);
                } finally {
                    integration._mutating.delete(this);
                }
            });
        }
        this._injections.overrideMethod(prototype, '_updatePosition', original => function (...args) {
            if (!integration._mutating.has(this))
                integration._guard(this, () => integration._render(this));
            return original.apply(this, args);
        });
        this._prototypes.add(prototype);
    }

    _guard(menu, update) {
        try {
            update();
        } catch (error) {
            const prototype = Object.getPrototypeOf(menu);
            this._unsupported.add(prototype);
            this._prototypes.delete(prototype);
            for (const name of HOOKS)
                this._injections.restoreMethod(prototype, name);
            for (const other of this._states.keys()) {
                if (Object.getPrototypeOf(other) === prototype) {
                    try {
                        this._clearCards(other);
                    } catch {
                        // Dispose remaining owned actors when the menu closes.
                    }
                }
            }
            console.warn(`Snap group cards unavailable: ${error.message}`);
        }
    }

    _state(menu) {
        if (!this._states.has(menu)) {
            const destroyId = menu.connect('destroy', () => this._states.delete(menu));
            this._states.set(menu, {cards: [], destroyId});
        }
        return this._states.get(menu);
    }

    _clearCards(menu) {
        const state = this._states.get(menu);
        if (!state)
            return;
        for (const {actor} of [...state.cards]) {
            if (menu._focusedPreview === actor)
                menu._focusedPreview = null;
            actor.destroy();
        }
    }

    _render(menu) {
        const icon = menu.currentAppIcon;
        if (!icon)
            return;
        const normal = menu._box.get_children().find(actor =>
            !actor.has_style_class_name?.(CARD) && typeof actor.getSize === 'function');
        if (!normal) {
            this._clearCards(menu);
            return;
        }
        const windows = icon.window ? [icon.window] : icon.getAppIconInterestingWindows?.() ?? [];
        const groups = new Map();
        for (const window of windows) {
            const group = this._registry.forWindow(window);
            if (!group || group.members.length < 2)
                continue;
            const members = group.members;
            const key = members.map(({window}) => window.get_stable_sequence()).sort((a, b) => a - b).join(':');
            if (!groups.has(key))
                groups.set(key, {group, preferred: window});
        }
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const [normalW, normalH] = normal.getSize();
        const width = Math.round(Math.min(normalW, 218 * scale));
        const height = Math.round(normalH);
        const desired = Array.from(groups.values(), ({group, preferred}) => ({
            group, preferred,
            signature: JSON.stringify([width, height, scale, preferred.get_stable_sequence(),
                group.members.map(({window, rect}) => [window.get_stable_sequence(), rect.x, rect.y,
                    rect.width, rect.height, !!window.get_compositor_private()?.visible, window.minimized])]),
        }));
        const existing = this._states.get(menu)?.cards ?? [];
        if (existing.length === desired.length &&
            existing.every((record, i) => record.signature === desired[i].signature)) {
            for (const [index, item] of desired.entries())
                existing[index].actor._group = item.group;
            return;
        }
        this._clearCards(menu);
        if (!desired.length)
            return;
        const state = this._state(menu);
        for (const item of desired) {
            const actor = this._card(menu, item, width, height, scale);
            const record = {actor, signature: item.signature};
            actor.connect('destroy', () => {
                state.cards = state.cards.filter(current => current !== record);
            });
            state.cards.push(record);
            menu._box.add_child(actor);
        }
    }

    _card(menu, {group, preferred}, width, height, scale) {
        const count = group.members.length;
        const title = `Snap group · ${count} windows`;
        const appNames = group.members.map(({window}) =>
            this._tracker.get_window_app(window)?.get_name() || window.get_title() || 'Window');
        const actor = new St.Button({style_class: CARD, reactive: true, can_focus: true, track_hover: true,
            accessible_name: `Restore snap group · ${count} windows · ${appNames.join(', ')}`});
        actor.set_size(width, height);
        actor._group = group;
        actor.getSize = () => [width, height];
        actor.setFocus = focused => {
            if (focused) {
                actor.add_style_pseudo_class('focus');
                menu.ensureVisible(actor);
                menu._endPeek();
            } else {
                actor.remove_style_pseudo_class('focus');
            }
        };
        actor.activate = () => {
            const selected = actor._group;
            menu.close(true);
            this._registry.restore(selected, preferred);
        };
        actor.connect('clicked', () => actor.activate());
        actor.connect('notify::hover', () => {
            if (actor.hover)
                menu._endPeek();
        });
        const contents = new St.BoxLayout({vertical: true, style_class: 'zorin11-snap-group-content'});
        contents.add_child(new St.Label({text: title, style_class: 'zorin11-snap-group-title'}));
        contents.add_child(mosaic(group.members, Math.max(1, width - 16 * scale),
            Math.max(1, height - 38 * scale), scale, this._tracker));
        actor.set_child(contents);
        return actor;
    }

    destroy() {
        if (this._pending)
            GLib.source_remove(this._pending);
        if (this._panelsChanged)
            this._manager.disconnect(this._panelsChanged);
        Main.extensionManager.disconnect(this._extensionChanged);
        this._injections.clear();
        this._prototypes.clear();
        for (const [menu, state] of [...this._states]) {
            this._clearCards(menu);
            menu.disconnect(state.destroyId);
            if (menu.opened && menu.currentAppIcon)
                menu.updatePosition();
        }
        this._states.clear();
    }
}
