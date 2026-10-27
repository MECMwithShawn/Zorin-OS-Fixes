import Gtk from 'gi://Gtk?version=4.0';
import Gdk from 'gi://Gdk?version=4.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {PRESETS, normalize} from './model.js';
import {paint} from './renderer.js';

const HERE = Gio.File.new_for_uri(import.meta.url).get_parent().get_path();
const source = Gio.SettingsSchemaSource.new_from_directory(`${HERE}/schemas`, Gio.SettingsSchemaSource.get_default(), false);
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
export function buildMotionControls(win) {
    const settings = new Gio.Settings({settings_schema: source.lookup('org.gnome.shell.extensions.zorin11-motion', false)});
    settings.delay();
    let refreshing = false;
    const desktop = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
    const root = new Gtk.Box({orientation: Gtk.Orientation.VERTICAL, spacing: 14,
        margin_top: 22, margin_bottom: 18, margin_start: 24, margin_end: 24});
    root.append(label('Taskbar motion', 'motion-title'));
    root.append(label('Preview your changes, then Apply to taskbar to use them.', 'motion-muted'));
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
        b.update_property([Gtk.AccessibleProperty.LABEL], [name]);
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
        scale.connect('value-changed', () => {if (!refreshing) settings.set_int(key, Math.round(scale.get_value()));});
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
    for (const [key, text] of [['apply-at-startup','Apply at startup'],['pause-on-battery','Pause on battery power'],['pause-fullscreen','Pause for fullscreen apps']]) {
        const row = new Gtk.Box({spacing: 12}); const textLabel = label(text); textLabel.hexpand = true; row.append(textLabel);
        const toggle = new Gtk.Switch({valign: Gtk.Align.CENTER}); row.append(toggle);
        toggle.update_property([Gtk.AccessibleProperty.LABEL], [text]);
        settings.bind(key, toggle, 'active', Gio.SettingsBindFlags.DEFAULT); controls.append(row);
        if (key === 'apply-at-startup') controls.append(label('Restore your selected effect when you sign in. Off keeps it manual; Apply still starts it for this session.', 'motion-muted'));
    }
    const status = label('', 'motion-muted'); root.append(status);
    const footer = new Gtk.Box({spacing: 8, halign: Gtk.Align.END});
    const defaults = new Gtk.Button({label: 'Restore defaults'});
    defaults.connect('clicked', () => {for (const key of settings.settings_schema.list_keys()) if (key !== 'activation-request') settings.reset(key);});
    const revert = new Gtk.Button({label: 'Revert changes'});
    revert.connect('clicked', () => settings.revert());
    const apply = new Gtk.Button({label: 'Apply to taskbar'}); apply.add_css_class('suggested-action');
    apply.connect('clicked', () => applyToTaskbar());
    footer.append(defaults); footer.append(revert); footer.append(apply); root.append(footer);
    let timer = 0, config, closed = false, busy = false, request = 0;
    let activation = 'Checking taskbar…';
    const cancellable = new Gio.Cancellable();
    drawing.set_draw_func((_area, cr, width, height) => {
        cr.setSourceRGB(.09,.13,.15); cr.paint();
        paint(cr, width, height, config, timer ? GLib.get_monotonic_time()/1e6 : 0,
            {x: width/2 - 135 + selectedApp*46, width: 40}, false);
    });
    function refresh() {
        if (closed) return;
        refreshing = true;
        config = normalize({preset: settings.get_string('preset'), intensity: settings.get_int('intensity'),
            period: settings.get_int('period'), accent: settings.get_string('accent')});
        for (const [id, b] of presets) b.set_active(id === config.preset);
        for (const r of ranges) {r.scale.set_value(settings.get_int(r.key)); r.value.label = settings.get_int(r.key) + r.unit;}
        const c = new Gdk.RGBA(); c.parse(config.accent); color.set_rgba(c);
        refreshing = false;
        const reduced = !desktop.get_boolean('enable-animations');
        const dirty = settings.get_has_unapplied();
        status.label = dirty ? 'Preview changes · Apply to update your taskbar.' : activation;
        if (!dirty) status.label += settings.get_boolean('apply-at-startup') ? ' Restores at sign-in.' : ' Startup is off; Apply starts motion for this session.';
        if (reduced) status.label += ' Motion is paused by Reduced motion.';
        revert.sensitive = dirty && !busy; apply.sensitive = !busy;
        apply.label = busy ? 'Applying…' : 'Apply to taskbar';
        const moving = !preview.active && !reduced && config.preset !== 'off' && win.is_active && root.get_mapped();
        preview.label = preview.active ? 'Play preview' : 'Pause preview';
        if (moving && !timer) timer = GLib.timeout_add(GLib.PRIORITY_LOW, 50, () => {drawing.queue_draw(); return GLib.SOURCE_CONTINUE;});
        if (!moving && timer) {GLib.source_remove(timer); timer = 0;}
        drawing.queue_draw();
    }

    function shellCall(method) {
        return new Promise((resolve, reject) => Gio.DBus.session.call(
            'org.gnome.Shell', '/org/gnome/Shell', 'org.gnome.Shell.Extensions', method,
            new GLib.Variant('(s)', ['zorin11-motion@zorin-os-fixes']), null,
            Gio.DBusCallFlags.NONE, 2000, cancellable, (bus, result) => {
                try { resolve(bus.call_finish(result).deep_unpack()[0]); }
                catch (e) { reject(e); }
            }));
    }
    async function checkActivation(enable = false) {
        const serial = ++request;
        try {
            const shell = new Gio.Settings({schema_id: 'org.gnome.shell'});
            let info = await shellCall('GetExtensionInfo');
            if (closed) return;
            if (enable && !shell.get_boolean('disable-user-extensions')) {
                if (info.state?.unpack() === 2) {
                    await shellCall('EnableExtension');
                    info = await shellCall('GetExtensionInfo');
                } else if (!info.uuid) {
                    // GNOME discovers newly installed extensions on the next login.
                    const uuid = 'zorin11-motion@zorin-os-fixes';
                    shell.set_strv('enabled-extensions', [...new Set([...shell.get_strv('enabled-extensions'), uuid])]);
                    shell.set_strv('disabled-extensions', shell.get_strv('disabled-extensions').filter(id => id !== uuid));
                    Gio.Settings.sync();
                }
            }
            if (closed || serial !== request) return;
            const state = info.state?.unpack();
            activation = shell.get_boolean('disable-user-extensions')
                ? 'Saved · Enable extensions in GNOME Extensions to activate taskbar motion.'
                : state === 1 ? (enable ? 'Applied to your taskbar' : 'Taskbar motion is ready') + ' · Battery and fullscreen pauses still apply.'
                : !info.uuid ? 'Saved · First activation needs your next sign-in. The preview works now.'
                : state === 2 ? 'Saved · Taskbar motion is disabled. Apply to activate it.'
                : 'Saved · Taskbar motion could not start. Check GNOME Extensions for details.';
        } catch (_) {
            if (!closed && serial === request)
                activation = 'Saved · Unable to reach GNOME Shell. Apply again when the desktop is ready.';
        }
        if (!closed) refresh();
    }
    async function applyToTaskbar() {
        if (busy || closed) return;
        busy = true;
        settings.apply(); Gio.Settings.sync(); refresh();
        await checkActivation(true);
        if (!closed) {
            // An explicit request also starts an unchanged preset when startup
            // is off, including when Apply just enabled the extension.
            settings.set_string('activation-request', GLib.uuid_string_random());
            settings.apply(); Gio.Settings.sync(); busy = false; refresh();
        }
    }
    const signals = [settings.connect('changed', refresh),
        settings.connect('notify::has-unapplied', refresh),
        desktop.connect('changed::enable-animations', refresh)];
    const focusSignal = win.connect('notify::is-active', refresh);
    root.connect('map', refresh); root.connect('unmap', refresh);
    const subscription = Gio.DBus.session.signal_subscribe('org.gnome.Shell',
        'org.gnome.Shell.Extensions', 'ExtensionStateChanged', '/org/gnome/Shell',
        'zorin11-motion@zorin-os-fixes', Gio.DBusSignalFlags.NONE, () => {
            if (!busy && !closed) checkActivation();
        });
    win.connect('close-request', () => {
        closed = true; cancellable.cancel();
        if (timer) GLib.source_remove(timer); timer = 0;
        settings.disconnect(signals[0]); settings.disconnect(signals[1]);
        desktop.disconnect(signals[2]); win.disconnect(focusSignal);
        Gio.DBus.session.signal_unsubscribe(subscription);
        settings.revert();
        return false;
    });
    refresh(); checkActivation();
    return root;
}
