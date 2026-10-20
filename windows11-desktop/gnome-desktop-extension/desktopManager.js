// SPDX-License-Identifier: GPL-3.0-or-later
// Adapter for Zorin's installed GPL Desktop Icons manager, without modifying it.
/* exported DesktopManager */
const Gtk = imports.gi.Gtk;
const Gdk = imports.gi.Gdk;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Prefs = imports.preferences;
const Upstream = imports.zorinOriginal.desktopManager;

function menu() {
    const result = new Gtk.Menu();
    result.get_style_context().add_class('axentra-desktop-menu');
    return result;
}
function item(label, icon, action) {
    const row = new Gtk.MenuItem();
    const box = new Gtk.Box({orientation: Gtk.Orientation.HORIZONTAL, spacing: 12});
    const image = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU);
    image.set_pixel_size(18);
    box.pack_start(image, false, false, 0);
    box.pack_start(new Gtk.Label({label, xalign: 0, hexpand: true}), true, true, 0);
    row.add(box);
    row.get_accessible().set_name(label);
    if (action) row.connect('activate', action);
    return row;
}
function launch(page) {
    // No shell interpolation and no file-manager or OneDrive routing changes.
    const runtime = GLib.getenv('ZORIN11_RUNTIME_DIR') ||
        GLib.build_filenamev([GLib.get_home_dir(), '.local/share/zorin11-hub']);
    const launcher = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.NONE});
    launcher.setenv('GDK_BACKEND', 'x11', true);
    launcher.spawnv(['/usr/bin/python3', `${runtime}/app.py`, '--settings', page]);
}

var DesktopManager = class extends Upstream.DesktopManager {
    _createDesktopBackgroundMenu() {
        super._createDesktopBackgroundMenu();
        const original = this._menu;
        const css = new Gtk.CssProvider();
        css.load_from_path(GLib.build_filenamev([this._codePath, 'menu.css']));
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        const schema = Gio.SettingsSchemaSource.new_from_directory(
            GLib.build_filenamev([this._codePath, '..', 'schemas']),
            Gio.SettingsSchemaSource.get_default(), false);
        this._axentraSettings = new Gio.Settings({
            settings_schema: schema.lookup('org.gnome.shell.extensions.zorin11-desktop', false)});
        this._axentraSettings.connect('changed::show-icons', () => {
            this.unselectAll();
            this._updateDesktop().catch(logError);
        });
        const main = menu();
        const view = item('View', 'view-grid-symbolic');
        const viewMenu = menu();
        view.set_submenu(viewMenu);
        let group = null;
        for (const [label, size] of [['Large icons', 'large'], ['Medium icons', 'standard'], ['Small icons', 'small']]) {
            const row = new Gtk.RadioMenuItem({label});
            if (group) row.join_group(group);
            else group = row;
            row.set_active(Prefs.desktopSettings.get_string('icon-size') === size);
            row.connect('activate', () => {
                if (row.active) Prefs.desktopSettings.set_string('icon-size', size);
            });
            viewMenu.append(row);
        }
        viewMenu.append(new Gtk.SeparatorMenuItem());
        const arrange = new Gtk.CheckMenuItem({label: 'Auto arrange icons'});
        Prefs.desktopSettings.bind('keep-arranged', arrange, 'active', Gio.SettingsBindFlags.DEFAULT);
        viewMenu.append(arrange);
        const show = new Gtk.CheckMenuItem({label: 'Show desktop icons'});
        this._axentraSettings.bind('show-icons', show, 'active', Gio.SettingsBindFlags.DEFAULT);
        viewMenu.append(show);
        main.append(view);

        const sort = item('Sort by', 'view-sort-ascending-symbolic');
        const sorts = menu();
        for (const [label, value] of [['Name', 'NAME'], ['Date modified', 'MODIFIEDTIME'], ['Item type', 'KIND'], ['Size', 'SIZE']]) {
            const row = new Gtk.MenuItem({label});
            row.connect('activate', () => {
                Prefs.desktopSettings.set_string('arrangeorder', value);
                this.doSorts();
            });
            sorts.append(row);
        }
        sort.set_submenu(sorts);
        main.append(sort);
        main.append(item('Refresh', 'view-refresh-symbolic', () => this._updateDesktop().catch(logError)));
        main.append(new Gtk.SeparatorMenuItem());
        const paste = item('Paste', 'edit-paste-symbolic', () => this._doPaste());
        this._pasteMenuItem.bind_property('sensitive', paste, 'sensitive', 2);
        main.append(paste);
        const create = item('New', 'list-add-symbolic');
        const createMenu = menu();
        createMenu.append(item('Folder', 'folder-new-symbolic', () => this.doNewFolder()));
        // Preserve Zorin's template monitor and the original template actions.
        original.remove(this._newDocumentItem);
        this._newDocumentItem.set_label('Document from template');
        createMenu.append(this._newDocumentItem);
        create.set_submenu(createMenu);
        main.append(create);
        main.append(new Gtk.SeparatorMenuItem());
        main.append(item('Display settings', 'video-display-symbolic', () => launch('display')));
        main.append(item('Personalize', 'preferences-desktop-wallpaper-symbolic', () => launch('personalization')));
        main.append(item('Next desktop background', 'media-skip-forward-symbolic', () => {
            const runtime = GLib.getenv('ZORIN11_RUNTIME_DIR') ||
                GLib.build_filenamev([GLib.get_home_dir(), '.local/share/zorin11-hub']);
            const launcher = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.NONE});
            launcher.setenv('GDK_BACKEND', 'x11', true);
            launcher.spawnv(['/usr/bin/python3', `${runtime}/wallpaper_action.py`]);
        }));
        main.append(new Gtk.SeparatorMenuItem());
        const more = item('Show more options', 'view-more-symbolic');
        more.set_submenu(original);
        main.append(more);
        this._menu = main;
        main.show_all();
    }
    _drawDesktop(files) {
        if (this._axentraSettings && !this._axentraSettings.get_boolean('show-icons')) {
            for (const file of files) file._onDestroy();
            files = [];
        }
        super._drawDesktop(files);
    }
};
