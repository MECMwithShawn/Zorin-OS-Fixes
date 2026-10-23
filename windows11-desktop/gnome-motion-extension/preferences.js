#!/usr/bin/gjs -m
import Gtk from 'gi://Gtk?version=4.0';
import Gdk from 'gi://Gdk?version=4.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import {PRESETS, normalize} from './model.js';
import {paint} from './renderer.js';

const HERE = Gio.File.new_for_uri(import.meta.url).get_parent().get_path();
const source = Gio.SettingsSchemaSource.new_from_directory(`${HERE}/schemas`, Gio.SettingsSchemaSource.get_default(), false);
const settings = new Gio.Settings({settings_schema: source.lookup('org.gnome.shell.extensions.zorin11-motion', false)});
const desktop = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
const css = new Gtk.CssProvider();
css.load_from_data(`
.motion-window { background: #202124; color: #f3f3f3; }
.motion-title { font-size: 23px; font-weight: 600; }
.motion-muted { color: #b6b9c0; font-size: 12px; }
.motion-card { background: #2b2d31; border: 1px solid #41444a; border-radius: 10px; padding: 12px; }
.motion-card:hover { background: #34373d; }
.motion-card:checked { background: #273b49; border-color: #60cdff; }
.motion-card label { color: #f3f3f3; }
.motion-card .motion-muted { color: #c3cbd2; }
.motion-preview { border: 1px solid #41444a; border-radius: 10px; }
.motion-app { color: #e7efff; min-width: 28px; min-height: 30px; padding: 4px; background: transparent; border: 0; box-shadow: none; border-radius: 5px; }
.motion-app:checked { background: rgba(255,255,255,.08); border-bottom: 2px solid #60cdff; }
.motion-control { background: #2b2d31; border-radius: 10px; padding: 12px; }
`, -1);
function label(text, cls = null) {
    const w = new Gtk.Label({label: text, xalign: 0, wrap: true});
    if (cls) w.add_css_class(cls); return w;
}
const App = GObject.registerClass(class extends Gtk.Application {
    _init() {super._init({application_id: 'local.zorin11.TaskbarMotion', flags: Gio.ApplicationFlags.DEFAULT_FLAGS});}
    vfunc_activate() {
        if (this.window) {this.window.present(); return;}
        Gtk.Settings.get_default().gtk_application_prefer_dark_theme = true;
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        const win = new Gtk.ApplicationWindow({application: this, title: 'Taskbar motion', default_width: 760, default_height: 800});
        this.window = win; win.add_css_class('motion-window');
        const root = new Gtk.Box({orientation: Gtk.Orientation.VERTICAL, spacing: 14,
            margin_top: 22, margin_bottom: 18, margin_start: 24, margin_end: 24});
        const scroll = new Gtk.ScrolledWindow({hscrollbar_policy: Gtk.PolicyType.NEVER});
        scroll.set_child(root); win.set_child(scroll);
        root.append(label('Taskbar motion', 'motion-title'));
        root.append(label('Soft light. Slow movement. Your accent.', 'motion-muted'));
        const overlay = new Gtk.Overlay({height_request: 86}); overlay.add_css_class('motion-preview');
        const drawing = new Gtk.DrawingArea({content_height: 86, hexpand: true}); overlay.set_child(drawing);
        root.append(overlay);
        let selectedApp = 2;
        const apps = new Gtk.Box({spacing: 6, halign: Gtk.Align.CENTER, valign: Gtk.Align.CENTER});
        const names = [['view-app-grid-symbolic','Start'],['system-search-symbolic','Search'],['folder','Files'],
            ['web-browser','Browser'],['utilities-terminal','Terminal'],['preferences-system','Settings']];
        const appButtons = [];
        for (const [i, [icon, name]] of names.entries()) {
            const b = new Gtk.ToggleButton({tooltip_text: name, width_request: 40, active: i === selectedApp});
            b.add_css_class('motion-app'); b.set_child(new Gtk.Image({icon_name: icon, pixel_size: 24}));
            b.update_property([Gtk.AccessibleProperty.LABEL], [name + ' preview']);
            b.connect('clicked', () => {selectedApp = i; appButtons.forEach((item, n) => item.set_active(n === i)); drawing.queue_draw();});
            apps.append(b); appButtons.push(b);
        }
        overlay.add_overlay(apps);
        const grid = new Gtk.Grid({row_spacing: 8, column_spacing: 8, column_homogeneous: true});
        const presets = new Map();
        for (const [i, [id, name, description]] of PRESETS.entries()) {
            const b = new Gtk.ToggleButton({hexpand: true}); b.add_css_class('motion-card');
            const box = new Gtk.Box({orientation: Gtk.Orientation.VERTICAL, spacing: 5});
            box.append(label(name)); box.append(label(description, 'motion-muted')); b.set_child(box);
            b.connect('clicked', () => settings.set_string('preset', id));
            grid.attach(b, i % 2, Math.floor(i / 2), 1, 1); presets.set(id, b);
        }
        root.append(grid);
        const controls = new Gtk.Box({orientation: Gtk.Orientation.VERTICAL, spacing: 12}); controls.add_css_class('motion-control'); root.append(controls);
        const range = (key, title, min, max, unit) => {
            const box = new Gtk.Box({spacing: 16}), caption = label(title), value = label('');
            caption.set_size_request(80, -1);
            const scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min, max, 1);
            scale.hexpand = true; scale.draw_value = false; scale.set_value(settings.get_int(key));
            scale.update_property([Gtk.AccessibleProperty.LABEL], [title]);
            value.set_size_request(58, -1);
            scale.connect('value-changed', () => settings.set_int(key, Math.round(scale.get_value())));
            box.append(caption); box.append(scale); box.append(value); controls.append(box);
            return {scale, value, key, unit};
        };
        const ranges = [range('intensity', 'Intensity', 5, 50, '%'), range('period', 'Cycle time', 8, 40, ' sec')];
        const accentRow = new Gtk.Box({spacing: 10}); accentRow.append(label('Accent'));
        const color = new Gtk.ColorButton({use_alpha: false, title: 'Taskbar accent'});
        color.update_property([Gtk.AccessibleProperty.LABEL], ['Accent color']);
        color.connect('color-set', () => {
            const c = color.get_rgba();
            settings.set_string('accent', '#' + [c.red, c.green, c.blue].map(v => Math.round(v * 255).toString(16).padStart(2,'0')).join(''));
        });
        accentRow.append(color);
        const preview = new Gtk.ToggleButton({label: 'Pause preview', active: false, margin_start: 12});
        preview.connect('toggled', () => refresh()); accentRow.append(preview); controls.append(accentRow);
        for (const [key, text] of [['pause-on-battery','Pause on battery power'],['pause-fullscreen','Pause for fullscreen apps']]) {
            const row = new Gtk.Box({spacing: 12}); const textLabel = label(text); textLabel.hexpand = true; row.append(textLabel);
            const toggle = new Gtk.Switch({valign: Gtk.Align.CENTER}); row.append(toggle);
            toggle.update_property([Gtk.AccessibleProperty.LABEL], [text]);
            settings.bind(key, toggle, 'active', Gio.SettingsBindFlags.DEFAULT); controls.append(row);
        }
        const status = label('', 'motion-muted'); root.append(status);
        const footer = new Gtk.Box({spacing: 8, halign: Gtk.Align.END});
        const defaults = new Gtk.Button({label: 'Restore defaults'});
        defaults.connect('clicked', () => {for (const key of settings.settings_schema.list_keys()) settings.reset(key);});
        const close = new Gtk.Button({label: 'Done'}); close.connect('clicked', () => win.close());
        footer.append(defaults); footer.append(close); root.append(footer);
        let timer = 0, active = false, config;
        drawing.set_draw_func((_area, cr, width, height) => {
            cr.setSourceRGB(.09,.13,.15); cr.paint();
            paint(cr, width, height, config, timer ? GLib.get_monotonic_time()/1e6 : 0,
                {x: width/2 - 135 + selectedApp*46, width: 40}, false);
        });
        function refresh() {
            config = normalize({preset: settings.get_string('preset'), intensity: settings.get_int('intensity'),
                period: settings.get_int('period'), accent: settings.get_string('accent')});
            for (const [id, b] of presets) b.set_active(id === config.preset);
            for (const r of ranges) {r.scale.set_value(settings.get_int(r.key)); r.value.label = settings.get_int(r.key) + r.unit;}
            const c = new Gdk.RGBA(); c.parse(config.accent); color.set_rgba(c);
            const reduced = !desktop.get_boolean('enable-animations');
            status.label = reduced ? 'Motion paused by your Reduced motion setting.' :
                active ? 'Saved · Applied to your taskbar. Preview ignores battery and fullscreen pauses.' :
                'Saved · Taskbar motion starts at your next sign-in. Preview is available now.';
            const moving = !preview.active && !reduced && config.preset !== 'off' && win.is_active;
            preview.label = preview.active ? 'Play preview' : 'Pause preview';
            if (moving && !timer) timer = GLib.timeout_add(GLib.PRIORITY_LOW, 50, () => {drawing.queue_draw(); return GLib.SOURCE_CONTINUE;});
            if (!moving && timer) {GLib.source_remove(timer); timer = 0;}
            drawing.queue_draw();
        }
        const signals = [settings.connect('changed', refresh), desktop.connect('changed::enable-animations', refresh)];
        win.connect('notify::is-active', refresh);
        win.connect('close-request', () => {if (timer) GLib.source_remove(timer); timer = 0;
            settings.disconnect(signals[0]); desktop.disconnect(signals[1]); this.window = null; return false;});
        refresh(); win.present();
        Gio.DBus.session.call('org.gnome.Shell','/org/gnome/Shell','org.gnome.Shell.Extensions','GetExtensionInfo',
            new GLib.Variant('(s)', ['zorin11-motion@zorin-os-fixes']), null, Gio.DBusCallFlags.NONE, 1500, null, (bus,result) => {
                try {active = bus.call_finish(result).deep_unpack()[0].state?.unpack() === 1;} catch (_) {}
                if (this.window) refresh();
            });
    }
});
new App().run([]);
