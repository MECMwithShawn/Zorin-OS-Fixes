import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const IDLE = 3000; // ms the pointer may stay away before an open drawer folds again

// Folds the tray icons in each taskbar's right box (everything left of the
// network/volume/battery button) behind one arrow, like Windows' hidden-icons
// chevron but expanding in place so each icon's own menu still opens from it.
// Icons stay where Zorin Taskbar put them; only their visibility changes, and
// an icon that hides or shows itself while folded is remembered for later.
export class TrayDrawer {
    constructor(settings) {
        this._settings = settings;
        this._boxes = new Map();
        this._open = false;
        this._changed = settings.connect('changed::tray-drawer', () => this._sync());
        this._timer = GLib.timeout_add(GLib.PRIORITY_LOW, 2000, () => {
            this._sync();
            return GLib.SOURCE_CONTINUE;
        });
        this._sync();
    }

    get enabled() {
        return this._settings.get_boolean('tray-drawer');
    }

    _panelBoxes() {
        const panels = global.zorinTaskbar?.panels?.map(p => p.panel) ?? [Main.panel];
        return panels.filter(p => p?._rightBox);
    }

    // Attaches to new taskbars and lets go of rebuilt ones.
    _sync() {
        const panels = this.enabled ? this._panelBoxes() : [];
        const boxes = new Set(panels.map(p => p._rightBox));
        for (const box of [...this._boxes.keys()])
            if (!boxes.has(box))
                this._release(box);
        for (const panel of panels)
            if (!this._boxes.has(panel._rightBox))
                this._attach(panel._rightBox, panel);
        if (!boxes.size)
            this._open = false;
    }

    _attach(box, panel) {
        const arrow = new St.Button({
            style_class: 'panel-button zorin11-tray-drawer',
            can_focus: true, track_hover: true, reactive: true,
            accessible_name: 'Show hidden icons',
            child: new St.Icon({icon_name: 'pan-start-symbolic', style_class: 'system-status-icon'}),
        });
        arrow.connect('clicked', () => this.toggle());
        // Without Zorin Taskbar the system button and clock share GNOME's box.
        const keep = new Set(['quickSettings', 'dateMenu'].map(k => panel.statusArea?.[k]?.container));
        const state = {arrow, panel, keep, items: new Map(), ids: []};
        this._boxes.set(box, state);
        box.add_child(arrow);
        for (const child of box.get_children())
            this._track(state, child);
        state.ids.push(box.connect('child-added', (_, child) => {
            this._track(state, child);
            if (child !== arrow)
                box.set_child_above_sibling(arrow, null);
        }));
        state.ids.push(box.connect('child-removed', (_, child) => this._untrack(state, child)));
        state.ids.push(box.connect('destroy', () => this._boxes.delete(box)));
        this._apply(state);
    }

    _track(state, child) {
        if (child === state.arrow || state.keep.has(child) || state.items.has(child))
            return;
        const item = {want: child.visible, guard: false};
        item.id = child.connect('notify::visible', () => {
            if (item.guard)
                return;
            item.want = child.visible;
            if (!this._open && child.visible)
                this._set(item, child, false);
            this._syncArrow(state);
        });
        state.items.set(child, item);
        if (!this._open)
            this._set(item, child, false);
        this._syncArrow(state);
    }

    _untrack(state, child) {
        const item = state.items.get(child);
        if (!item)
            return;
        child.disconnect(item.id);
        state.items.delete(child);
        this._syncArrow(state);
    }

    _set(item, child, visible) {
        item.guard = true;
        child.visible = visible;
        item.guard = false;
    }

    // With nothing to fold the arrow would expand to nothing, so it hides.
    _syncArrow(state) {
        state.arrow.visible = [...state.items.values()].some(i => i.want);
        state.arrow.child.icon_name = this._open ? 'pan-end-symbolic' : 'pan-start-symbolic';
        state.arrow.accessible_name = this._open ? 'Hide icons' : 'Show hidden icons';
    }

    _apply(state) {
        for (const [child, item] of state.items) {
            const show = this._open && item.want;
            if (show && !child.visible) {
                child.opacity = 0;
                this._set(item, child, true);
                child.ease({opacity: 255, duration: 150, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
            } else if (!show && child.visible) {
                this._set(item, child, false);
            }
        }
        this._syncArrow(state);
    }

    toggle(open = !this._open) {
        this._open = open;
        for (const state of this._boxes.values())
            this._apply(state);
        if (this._idle)
            GLib.source_remove(this._idle);
        this._idle = 0;
        if (open) {
            this._away = 0;
            this._idle = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => this._watch());
        }
    }

    // Folds the drawer once the pointer has left every tray for a while and no
    // tray menu is open.
    _watch() {
        const [x, y] = global.get_pointer();
        const near = [...this._boxes.keys()].some(box => {
            const [bx, by] = box.get_transformed_position(), [w, h] = box.get_transformed_size();
            return x >= bx && x < bx + w && y >= by - 8 && y < by + h;
        });
        // An open tray menu holds a grab; with none the stage is the grab actor.
        const grab = global.stage.get_grab_actor?.();
        const menu = (grab && grab !== global.stage) ||
            [...this._boxes.values()].some(s => s.panel.menuManager?.activeMenu);
        this._away = near || menu ? 0 : this._away + 250;
        if (this._away < IDLE)
            return GLib.SOURCE_CONTINUE;
        this._idle = 0;
        this.toggle(false);
        return GLib.SOURCE_REMOVE;
    }

    _release(box) {
        const state = this._boxes.get(box);
        this._boxes.delete(box);
        for (const id of state.ids)
            box.disconnect(id);
        for (const [child, item] of state.items) {
            child.disconnect(item.id);
            child.remove_transition('opacity');
            child.opacity = 255;
            if (child.visible !== item.want)
                this._set(item, child, item.want);
        }
        state.arrow.destroy();
    }

    destroy() {
        this._settings.disconnect(this._changed);
        for (const id of [this._timer, this._idle])
            if (id)
                GLib.source_remove(id);
        this._timer = this._idle = 0;
        for (const box of [...this._boxes.keys()])
            this._release(box);
    }
}
