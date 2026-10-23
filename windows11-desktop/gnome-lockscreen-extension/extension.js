import Clutter from 'gi://Clutter';
import GDesktopEnums from 'gi://GDesktopEnums';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Layout from 'resource:///org/gnome/shell/ui/layout.js';
import {UnlockDialog} from 'resource:///org/gnome/shell/ui/unlockDialog.js';

// Presentation only: no verifier, password entry, key handler or unlock method is replaced.
export default class LockScreen extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._desktop = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
        this._interface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._dialogs = new Map(); this._signals = [];
        const watch = (obj, signal, callback) => this._signals.push([obj, obj.connect(signal, callback)]);
        watch(this._settings, 'changed', () => this._refresh());
        watch(this._desktop, 'changed', () => {if (this._settings.get_string('source') === 'desktop') this._refresh();});
        watch(this._interface, 'changed::color-scheme', () => this._refresh());
        watch(Main.layoutManager, 'monitors-changed', () => this._refresh());
        watch(St.ThemeContext.get_for_stage(global.stage), 'notify::scale-factor', () => this._refresh());
        this._injections = new InjectionManager();
        const owner = this;
        this._injections.overrideMethod(UnlockDialog.prototype, '_init', original => function (...args) {
            original.call(this, ...args);
            try { owner._attach(this); } catch (e) { console.error(`Axentra lock screen: ${e.message}`); }
        });
        if (Main.screenShield?._dialog instanceof UnlockDialog) this._attach(Main.screenShield._dialog);
    }
    _attach(dialog) {
        if (this._dialogs.has(dialog)) return;
        const row = {dialog, group: null, credit: null, backgrounds: [], image: null, loadedId: 0, dead: false,
            originalOpacity: dialog._backgroundGroup.opacity};
        row.destroyId = dialog.connect('destroy', () => {
            row.dead = true; dialog._adjustment.disconnect(row.progressId); this._cancelImage(row); this._dialogs.delete(dialog);
        });
        row.progressId = dialog._adjustment.connect('notify::value', () => this._effects(row));
        this._dialogs.set(dialog, row);
        this._render(row);
    }
    _cancelImage(row) {
        if (row.loadedId && row.image) row.image.disconnect(row.loadedId);
        row.loadedId = 0; row.image = null;
    }
    _clear(row) {
        this._cancelImage(row);
        row.group?.destroy(); row.group = null;
        row.credit?.destroy(); row.credit = null;
        row.backgrounds = [];
        if (!row.dead) {
            row.dialog._backgroundGroup.opacity = row.originalOpacity;
            row.dialog.remove_style_class_name('zorin11-lockscreen');
        }
    }
    _picture() {
        const desktop = this._settings.get_string('source') === 'desktop';
        const uri = desktop ? this._desktop.get_string(this._interface.get_string('color-scheme') === 'prefer-dark'
            ? 'picture-uri-dark' : 'picture-uri') : this._settings.get_string('picture-uri');
        const file = Gio.File.new_for_uri(uri);
        return file.is_native() && file.query_exists(null) ? file : null;
    }
    _render(row) {
        this._clear(row);
        if (!this._settings.get_boolean('enabled') || row.dead) return;
        const dialog = row.dialog;
        dialog.add_style_class_name('zorin11-lockscreen');
        const file = this._picture();
        if (!file) return; // Keep GNOME's working background if a selected picture disappears.
        row.group = new Clutter.Actor({reactive: false});
        dialog.insert_child_at_index(row.group, 0);
        for (const monitor of Main.layoutManager.monitors) {
            const widget = new St.Widget({x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height,
                reactive: false, effect: new Shell.BlurEffect({name: 'zorin11-lock-blur'})});
            const background = new Meta.Background({meta_display: global.display});
            background.set_file(file, GDesktopEnums.BackgroundStyle.ZOOM);
            const actor = new Meta.BackgroundActor({meta_display: global.display, monitor: monitor.index,
                request_mode: Clutter.RequestMode.CONTENT_SIZE});
            actor.content.background = background;
            widget.add_child(actor); row.group.add_child(widget);
            row.backgrounds.push(widget);
        }
        // Do not cover the native fallback until Mutter has loaded the image.
        row.image = Meta.BackgroundImageCache.get_default().load(file);
        const ready = () => {
            if (row.dead || !row.group) return;
            row.dialog._backgroundGroup.opacity = 0;
            this._effects(row);
        };
        if (row.image.is_loaded()) ready();
        else row.loadedId = row.image.connect('loaded', () => {this._cancelImage(row); ready();});
        const title = this._settings.get_string('source') === 'desktop' ? 'Your desktop background' : this._settings.get_string('picture-title');
        if (this._settings.get_boolean('show-credit') && title) {
            row.credit = new St.Widget({layout_manager: new Clutter.BinLayout(), reactive: false});
            row.credit.add_constraint(new Layout.MonitorConstraint({primary: true}));
            const box = new St.BoxLayout({vertical: true, style_class: 'zorin11-lock-credit',
                x_expand: true, y_expand: true, x_align: Clutter.ActorAlign.START, y_align: Clutter.ActorAlign.END});
            box.add_child(new St.Label({text: title.slice(0, 160), style_class: 'zorin11-lock-title'}));
            const credit = this._settings.get_string('source') === 'desktop' ? '' : this._settings.get_string('picture-credit');
            if (credit) box.add_child(new St.Label({text: credit.slice(0, 220), style_class: 'zorin11-lock-attribution'}));
            row.credit.add_child(box); dialog.add_child(row.credit);
        }
        this._effects(row);
    }
    _effects(row) {
        if (row.dead) return;
        const progress = Math.max(0, Math.min(1, row.dialog._adjustment.value));
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        for (const widget of row.backgrounds) widget.get_effect('zorin11-lock-blur')?.set({
            brightness: (1 - this._settings.get_int('dimming') / 100) * (1 - .25 * progress),
            radius: 30 * scale * progress,
        });
        if (row.credit) row.credit.opacity = Math.round(255 * (1 - progress));
    }
    _refresh() { for (const row of this._dialogs.values()) this._render(row); }
    disable() {
        this._injections.clear();
        for (const [obj, id] of this._signals) obj.disconnect(id);
        for (const row of this._dialogs.values()) {
            row.dialog.disconnect(row.destroyId); row.dialog._adjustment.disconnect(row.progressId);
            this._clear(row);
        }
        this._dialogs.clear(); this._signals = [];
    }
}
