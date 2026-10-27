import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {PRESETS, normalize, pauseReason} from './model.js';
import {paint} from './renderer.js';

// This survives extension disable/enable (including a lock cycle), but a new
// GNOME Shell process starts a fresh login session. The saved preset is retained.
const session = {active: undefined, request: null};
const SCHEMA = 'org.gnome.shell.extensions.zorin11-motion';
export default class TaskbarMotion extends Extension {
    enable() {
        this._settings = this.getSettings(SCHEMA); this._interface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._signals = []; this._panelSignals = []; this._panels = []; this._menus = []; this._timer = 0; this._pending = 0; this._alive = true;
        const request = this._settings.get_string('activation-request');
        if (session.active === undefined) session.active = this._settings.get_boolean('apply-at-startup');
        else if (session.request !== request) session.active = true;
        session.request = request;
        this._connect(this._settings, 'changed', (_settings, key) => {
            if (key === 'activation-request') {session.active = true; session.request = this._settings.get_string(key);}
            this._refresh();
        });
        this._connect(this._interface, 'changed::enable-animations', () => this._refresh());
        this._connect(Main.extensionManager, 'extension-state-changed', (_manager, extension) => {
            if (extension.uuid === 'zorin-taskbar@zorinos.com') this._schedule();
        });
        this._connect(Main.layoutManager, 'monitors-changed', () => this._schedule());
        this._connect(Main.layoutManager, 'startup-complete', () => this._schedule());
        this._connect(Main.overview, 'showing', () => this._refresh());
        this._connect(Main.overview, 'hidden', () => this._refresh());
        this._connect(Main.sessionMode, 'updated', () => this._refresh());
        this._connect(global.display, 'in-fullscreen-changed', () => this._refresh());
        this._connect(global.display, 'notify::focus-window', () => this._refresh());
        this._powerCancel = new Gio.Cancellable();
        Gio.DBusProxy.new_for_bus(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, null, 'org.freedesktop.UPower',
            '/org/freedesktop/UPower', 'org.freedesktop.UPower', this._powerCancel, (_source, result) => {
                try {
                    const proxy = Gio.DBusProxy.new_for_bus_finish(result);
                    if (!this._alive) return;
                    this._power = proxy;
                    this._connect(proxy, 'g-properties-changed', () => this._refresh());
                    this._refresh();
                } catch (_) { /* Desktops without UPower keep manual controls. */ }
            });
        this._sync();
    }
    _connect(object, signal, callback, list = this._signals) {
        const r = {object, id: object.connect(signal, callback), death: 0};
        if (object instanceof Clutter.Actor) r.death = object.connect('destroy', () => {r.object = null;});
        list.push(r);
    }
    _disconnect(list) {
        for (const r of list) if (r.object) {r.object.disconnect(r.id); if (r.death) r.object.disconnect(r.death);}
        list.length = 0;
    }
    _schedule() {
        if (this._pending) return;
        this._pending = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {this._pending = 0; this._sync(); return GLib.SOURCE_REMOVE;});
    }
    _destroyMenus() {
        for (const row of this._menus) {
            if (!row.tileDead) row.tile.destroy();
            if (!row.indicatorDead) row.indicator.destroy();
        }
        this._menus = [];
    }
    _sync() {
        const manager = global.zorinTaskbar;
        const panels = manager?.panels || [{panel: Main.panel, monitor: {index: Main.layoutManager.primaryIndex}}];
        if (this._manager === manager && this._panels.length === panels.length && this._panels.every((r, i) => !r.dead && r.entry === panels[i])) {
            this._refresh(); return;
        }
        this._disconnect(this._panelSignals);
        this._manager = manager;
        for (const r of this._panels) if (!r.dead) r.actor.destroy();
        this._destroyMenus();
        this._panels = []; this._menus = [];
        if (manager) this._connect(manager, 'panels-created', () => this._schedule(), this._panelSignals);
        for (const entry of panels) {
            const panel = entry.panel;
            const actor = new St.DrawingArea({name: 'zorin11-motion-layer', reactive: false, can_focus: false, opacity: 0});
            const row = {panel, entry, actor, dead: false};
            actor.connect('destroy', () => {row.dead = true;});
            actor.connect('repaint', () => {
                const cr = actor.get_context(), [w, h] = actor.get_surface_size();
                paint(cr, w, h, this._config, GLib.get_monotonic_time() / 1e6, this._focus(row, w)); cr.$dispose();
            });
            panel.insert_child_at_index(actor, 0);
            // Zorin's panel allocates only its own known children. Allocate our
            // decorative layer explicitly, without altering its layout method.
            const size = () => {if (!row.dead && panel.has_allocation()) {
                actor.allocate(new Clutter.ActorBox({x1: 0, y1: 0, x2: panel.width, y2: panel.height}));
            }};
            row.allocate = size;
            this._connect(panel, 'notify::allocation', size, this._panelSignals);
            this._connect(panel, 'notify::mapped', () => this._refresh(), this._panelSignals);
            size(); this._panels.push(row);
            const settings = panel.statusArea?.quickSettings;
            if (settings?.addExternalIndicator) {
                const indicator = new QuickSettings.SystemIndicator();
                const tile = new QuickSettings.QuickMenuToggle({title: 'Taskbar motion', iconName: 'preferences-desktop-effects-symbolic', toggleMode: true});
                tile.menu.setHeader('preferences-desktop-effects-symbolic', 'Taskbar motion', 'Subtle light, at your pace');
                const options = new Map();
                for (const [id, name] of PRESETS) {
                    const item = new PopupMenu.PopupMenuItem(name);
                    item.connect('activate', () => this._activate(id));
                    tile.menu.addMenuItem(item); options.set(id, item);
                }
                tile.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                const startup = new PopupMenu.PopupSwitchMenuItem('Apply at startup', this._settings.get_boolean('apply-at-startup'));
                startup.connect('toggled', (_item, state) => this._settings.set_boolean('apply-at-startup', state));
                tile.menu.addMenuItem(startup);
                tile.menu.addAction('Customize motion…', () => {settings.menu.close(); this._preferences();});
                tile.connect('clicked', () => this._activate(!session.active && this._config.preset !== 'off' ? this._config.preset : this._config.preset === 'off' ? this._lastPreset || 'aurora' : 'off'));
                indicator.quickSettingsItems.push(tile); settings.addExternalIndicator(indicator);
                const menu = {tile, indicator, options, startup, panel: row, tileDead: false, indicatorDead: false};
                tile.connect('destroy', () => {menu.tileDead = true;});
                indicator.connect('destroy', () => {menu.indicatorDead = true;});
                this._menus.push(menu);
            }
        }
        this._refresh();
    }
    _activate(preset) {
        session.active = true; this._settings.set_string('preset', preset); this._refresh();
    }
    _preferences() {
        Gio.Subprocess.new(['/usr/bin/gjs', '-m', `${this.path}/taskbar-settings.js`, '--motion'], Gio.SubprocessFlags.NONE);
    }
    _focus(row, width) {
        if (this._config.preset !== 'halo') return null;
        const app = global.display.focus_window;
        for (const icon of row.entry.taskbar?._getAppIcons?.() || []) {
            if (!app || !icon.app?.get_windows().includes(app)) continue;
            const [px] = row.panel.get_transformed_position(), [pw] = row.panel.get_transformed_size();
            const [x] = icon.get_transformed_position(), [w] = icon.get_transformed_size();
            return pw > 0 ? {x: (x - px) * width / pw, width: w * width / pw} : null;
        }
        return null;
    }
    _refresh() {
        this._config = normalize({preset: this._settings.get_string('preset'), intensity: this._settings.get_int('intensity'),
            period: this._settings.get_int('period'), accent: this._settings.get_string('accent'),
            pauseBattery: this._settings.get_boolean('pause-on-battery'), pauseFullscreen: this._settings.get_boolean('pause-fullscreen')});
        if (this._config.preset !== 'off') this._lastPreset = this._config.preset;
        const battery = this._power?.get_cached_property('OnBattery')?.unpack() || false;
        let moving = false;
        for (const row of this._panels) {
            if (row.dead) continue;
            row.reason = !session.active && this._config.preset !== 'off' ? 'Not started · Choose a preset or Apply' : pauseReason(this._config, {animations: this._interface.get_boolean('enable-animations'), battery,
                locked: Main.sessionMode.isLocked, overview: Main.overview.visible,
                fullscreen: global.display.get_monitor_in_fullscreen(row.entry.monitor.index)});
            row.moving = !row.reason && row.panel.mapped;
            row.actor.opacity = row.moving ? 255 : 0;
            if (row.moving) {moving = true; row.allocate(); row.actor.queue_repaint();}
        }
        for (const {tile, options, startup, panel, tileDead} of this._menus) {
            if (tileDead) continue;
            tile.checked = session.active && this._config.preset !== 'off';
            startup.setToggleState(this._settings.get_boolean('apply-at-startup'));
            tile.subtitle = panel.reason || PRESETS.find(p => p[0] === this._config.preset)[1];
            for (const [id, item] of options) item.setOrnament(id === this._config.preset ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
        }
        if (moving && !this._timer) this._timer = GLib.timeout_add(GLib.PRIORITY_LOW, 50, () => {
            for (const row of this._panels) if (!row.dead && row.moving && row.actor.mapped) {
                if (!row.actor.has_allocation()) row.allocate();
                row.actor.queue_repaint();
            }
            return GLib.SOURCE_CONTINUE;
        });
        if (!moving && this._timer) {GLib.source_remove(this._timer); this._timer = 0;}
    }
    disable() {
        this._alive = false; this._powerCancel.cancel();
        for (const id of [this._timer, this._pending]) if (id) GLib.source_remove(id);
        this._timer = 0; this._pending = 0; this._disconnect(this._signals); this._disconnect(this._panelSignals);
        for (const row of this._panels) if (!row.dead) row.actor.destroy();
        this._destroyMenus();
        this._panels = []; this._menus = []; this._power = null; this._manager = undefined;
    }
}
