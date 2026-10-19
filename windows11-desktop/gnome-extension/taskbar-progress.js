import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Atk from 'gi://Atk';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {ProgressState} from './progress-state.js';

// Attach only our actors; the installed Zorin Taskbar continues owning icons,
// notification badges, menus, focus, previews and window activation.
export class TaskbarProgress {
    constructor() {
        this.state = new ProgressState(); this.icons = new Map(); this.signals = [];
        this.panelSignals = []; this.pending = 0;
        this.settings = new Gio.Settings({schema_id: 'org.gnome.shell.extensions.zorin-taskbar'});
        this.connect(this.settings, 'changed::progress-show-bar', () => this.refresh(), this.signals);
        this.connect(Main.extensionManager, 'extension-state-changed', () => this.schedule(), this.signals);
        this.updateSignal = Gio.DBus.session.signal_subscribe(null, 'com.canonical.Unity.LauncherEntry',
            'Update', null, null, Gio.DBusSignalFlags.NONE, (_bus, sender, _path, _iface, _member, params) => {
                if (params.get_type_string() !== '(sa{sv})') return;
                const [uri, values] = params.deep_unpack();
                if (typeof uri !== 'string' || !/^application:\/\/[^/\s]{1,240}\.desktop$/.test(uri)) return;
                if (!Gio.DesktopAppInfo.new(uri.slice(14))) return;
                const props = {};
                for (const key of ['progress', 'progress-visible']) if (values[key]) props[key] = values[key].unpack();
                if (this.state.update(sender, uri, props)) this.refresh();
            });
        this.ownerSignal = Gio.DBus.session.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus',
            'NameOwnerChanged', '/org/freedesktop/DBus', null, Gio.DBusSignalFlags.NONE,
            (_bus, _sender, _path, _iface, _member, params) => {
                const [name, _old, owner] = params.deep_unpack();
                if (!owner && this.state.removeSender(name)) this.refresh();
            });
        this.sync();
    }
    connect(object, signal, callback, list) {
        const record = {object, id: object.connect(signal, callback), death: 0};
        // Panel rebuilds destroy actors before the deferred rescan runs.
        if (object instanceof Clutter.Actor) record.death = object.connect('destroy', () => { record.object = null; });
        list.push(record);
    }
    disconnect(list) {
        for (const r of list) if (r.object) {
            r.object.disconnect(r.id);
            if (r.death) r.object.disconnect(r.death);
        }
        list.length = 0;
    }
    schedule() {
        if (this.pending) return;
        this.pending = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this.pending = 0; this.sync(); return GLib.SOURCE_REMOVE;
        });
    }
    sync() {
        this.disconnect(this.panelSignals);
        const manager = global.zorinTaskbar;
        if (manager) this.connect(manager, 'panels-created', () => this.schedule(), this.panelSignals);
        const live = new Set();
        for (const panel of manager?.panels || []) {
            const taskbar = panel.taskbar;
            if (!taskbar?._box || !taskbar._getAppIcons) continue;
            this.connect(taskbar._box, 'child-added', () => this.schedule(), this.panelSignals);
            this.connect(taskbar._box, 'child-removed', () => this.schedule(), this.panelSignals);
            for (const icon of taskbar._getAppIcons()) {
                if (!icon._dtpIconContainer || !icon.app) continue;
                live.add(icon);
                if (!this.icons.has(icon)) this.attach(icon);
            }
        }
        for (const icon of this.icons.keys()) if (!live.has(icon)) this.detach(icon);
        this.refresh();
    }
    attach(icon) {
        const actor = new St.DrawingArea({reactive: false, x_expand: true, y_expand: true,
            x_align: Clutter.ActorAlign.FILL, y_align: Clutter.ActorAlign.FILL,
            accessible_role: Atk.Role.PROGRESS_BAR, visible: false});
        const row = {actor, value: 0, signals: []};
        this.icons.set(icon, row);
        actor.connect('repaint', () => {
            const cr = actor.get_context(), [width, height] = actor.get_surface_size();
            const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
            const pad = 4 * scale, bar = 4 * scale, w = Math.max(0, width - pad * 2), y = height - bar - 2 * scale;
            cr.setSourceRGBA(0.08, 0.10, 0.12, 0.95); cr.rectangle(pad, y, w, bar); cr.fill();
            cr.setSourceRGBA(0.22, 0.76, 1, 1); cr.rectangle(pad, y, w * row.value, bar); cr.fill();
            cr.$dispose();
        });
        this.connect(icon, 'destroy', () => { this.disconnect(row.signals); this.icons.delete(icon); }, row.signals);
        icon._dtpIconContainer.add_child(actor);
    }
    detach(icon) {
        const row = this.icons.get(icon);
        if (!row) return;
        this.disconnect(row.signals); row.actor.destroy(); this.icons.delete(icon);
    }
    refresh() {
        const enabled = this.settings.get_boolean('progress-show-bar');
        for (const [icon, row] of this.icons) {
            const progress = this.state.get(icon.app.get_id());
            row.actor.visible = enabled && !!progress;
            if (progress) {
                row.value = progress.value;
                row.actor.accessible_name = `${icon.app.get_name()}: ${Math.round(row.value * 100)}%`;
                row.actor.queue_repaint();
            }
        }
    }
    snapshot() {
        return [...this.icons].map(([icon, row]) => ({app: icon.app.get_id(),
            progress: row.actor.visible ? row.value : null, progressVisible: row.actor.visible,
            badge: String(icon._notificationsCount || ''), badgeVisible: !!icon._numberOverlayBin?.visible,
            label: row.actor.accessible_name || '', monitor: icon.dtpPanel.monitor.index,
            rect: [...row.actor.get_transformed_position(), ...row.actor.get_transformed_size()]}));
    }
    destroy() {
        if (this.pending) GLib.source_remove(this.pending);
        this.pending = 0;
        Gio.DBus.session.signal_unsubscribe(this.updateSignal);
        Gio.DBus.session.signal_unsubscribe(this.ownerSignal);
        this.disconnect(this.signals); this.disconnect(this.panelSignals);
        for (const icon of [...this.icons.keys()]) this.detach(icon);
        this.state.entries.clear();
    }
}
