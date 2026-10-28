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
        for (const panel of global.zorinTaskbar?.panels ?? []) {
            try {
                this._checkPanel(panel);
            } catch (e) {
                // A panel being rebuilt has no allocation yet; check again next tick.
            }
        }
    }

    _checkPanel(panel) {
        if (!panel.monitor || panel.geom?.vertical || panel.geom?.dynamic)
            return;
        const index = panel.monitor.index, now = GLib.get_monotonic_time();
        if (now - (this._changed.get(index) ?? 0) < COOLDOWN)
            return;
        const positions = this._panelSettings.getPanelElementPositions(this._taskbar, index);
        const mode = positions?.find?.(p => p.element === 'taskbar')?.position;
        const groups = panel._elementGroups ?? [];
        const group = groups.find(g => g.expandableIndex >= 0);
        const adjustment = panel.taskbar?._scrollView?.hadjustment;
        if (!group || !Number.isFinite(group.x1) || !adjustment || !panel.panel?.width)
            return;
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
        const actors = new Set(group.elements.map(e => e.actor));
        for (const g of panel._elementGroups ?? [])
            for (const e of g.elements)
                if (e.actor.translation_x && !actors.has(e.actor))
                    e.actor.translation_x = 0;  // the group was rebuilt
        for (const actor of actors)
            if (actor.translation_x !== x)
                actor.translation_x = x;
    }

    _reset() {
        for (const panel of global.zorinTaskbar?.panels ?? [])
            for (const g of panel._elementGroups ?? [])
                for (const e of g.elements)
                    if (e.actor.translation_x)
                        e.actor.translation_x = 0;
    }

    destroy() {
        this._reset();
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
    }
}
