import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {decide, shift, withMode} from './taskbar-center-state.js';

const SCHEMA = 'org.gnome.shell.extensions.zorin-taskbar';
// Zorin Taskbar's own module instance, so monitor IDs and its cache match.
const PANEL_SETTINGS = 'file:///usr/share/gnome-shell/extensions/zorin-taskbar@zorinos.com/panelSettings.js';
const COOLDOWN = 2000000; // µs after a switch before a monitor is checked again

// Watches each Zorin Taskbar panel once a second and switches its app group
// between the screen centre and the free space beside the tray (see
// taskbar-center-state.js). Reads only allocations; writes only the taskbar's
// panel-element-positions for that monitor, plus a translation on the apps
// group's own actors that nudges it towards the screen centre.
export class TaskbarCentering {
    constructor(settings) {
        this._settings = settings;
        this._changed = new Map();
        this._translations = new Map();
        const source = Gio.SettingsSchemaSource.get_default();
        this._taskbar = source.lookup(SCHEMA, true) ? new Gio.Settings({schema_id: SCHEMA}) : null;
        import(PANEL_SETTINGS).then(module => {
            this._panelSettings = module;
        }).catch(() => {});
        this._timer = GLib.timeout_add(GLib.PRIORITY_LOW, 1000, () => {
            this._check();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _check() {
        if (!this._taskbar || !this._panelSettings)
            return;
        if (!this._settings.get_boolean('adaptive-taskbar-center')) {
            this._reset();
            return;
        }
        const panels = (global.zorinTaskbar?.panels ?? []).filter(panel =>
            panel.monitor && !panel.geom?.vertical && !panel.geom?.dynamic);
        for (const [actor, entry] of this._translations)
            if (!panels.includes(entry.panel)) this._clearTranslation(actor, entry);
        for (const panel of panels) {
            try {
                this._checkPanel(panel);
            } catch (e) {
                // A panel being rebuilt has no allocation yet; check again next tick.
            }
        }
    }

    _checkPanel(panel) {
        const index = panel.monitor.index, now = GLib.get_monotonic_time();
        if (now - (this._changed.get(index) ?? 0) < COOLDOWN)
            return;
        const positions = this._panelSettings.getPanelElementPositions(this._taskbar, index);
        const mode = positions?.find?.(p => p.element === 'taskbar')?.position;
        const groups = panel._elementGroups ?? [];
        const group = groups.find(g => g.expandableIndex >= 0);
        const adjustment = panel.taskbar?._scrollView?.hadjustment;
        if (!group || !Number.isFinite(group.x1) || !adjustment || !panel.panel?.width) {
            this._nudge(panel, null, 0);
            return;
        }
        const state = {
            mode, overflow: adjustment.upper - adjustment.page_size > 1,
            width: panel.panel.width, pad: panel.geom?.varPadding ?? 0,
            groupStart: group.x1, groupEnd: group.x2,
            prevEnd: groups[group.index - 1]?.x2 ?? null, nextStart: groups[group.index + 1]?.x1 ?? null,
        };
        const target = decide(state);
        const next = target && withMode(positions, target);
        this._nudge(panel, group, next ? 0 : shift(state));
        if (!next)
            return;
        this._changed.set(index, now);
        this._panelSettings.setPanelElementPositions(this._taskbar, index, next);
    }

    _nudge(panel, group, x) {
        const actors = new Set(x ? group.elements.map(e => e.actor) : []);
        for (const [actor, entry] of this._translations)
            if (entry.panel === panel && !actors.has(actor)) this._clearTranslation(actor, entry);
        for (const actor of actors) {
            let entry = this._translations.get(actor);
            if (!entry) {
                const destroyId = actor.connect('destroy', () => this._translations.delete(actor));
                entry = {panel, base: actor.translation_x, applied: actor.translation_x, destroyId};
                this._translations.set(actor, entry);
            } else if (actor.translation_x !== entry.applied) {
                // Accept a translation changed by another extension while we were active.
                entry.base = actor.translation_x;
            }
            if (actor.translation_x !== entry.base + x) actor.translation_x = entry.base + x;
            entry.applied = actor.translation_x;
        }
    }

    _clearTranslation(actor, entry) {
        this._translations.delete(actor);
        actor.disconnect(entry.destroyId);
        if (actor.translation_x === entry.applied) actor.translation_x = entry.base;
    }

    _reset() {
        for (const [actor, entry] of this._translations) this._clearTranslation(actor, entry);
    }

    destroy() {
        this._reset();
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
    }
}
