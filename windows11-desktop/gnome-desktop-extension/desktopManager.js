// SPDX-License-Identifier: GPL-3.0-or-later
// Adapter for Zorin's installed GPL Desktop Icons manager, without modifying it.
/* exported DesktopManager */
const Gtk = imports.gi.Gtk;
const Gdk = imports.gi.Gdk;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Prefs = imports.preferences;
const DesktopIconsUtil = imports.desktopIconsUtil;
const Enums = imports.enums;
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
function runtimeDir() {
    return GLib.getenv('ZORIN11_RUNTIME_DIR') ||
        GLib.build_filenamev([GLib.get_home_dir(), '.local/share/zorin11-hub']);
}
function companion(args) {
    const launcher = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.NONE});
    launcher.setenv('GDK_BACKEND', 'x11', true);
    launcher.spawnv(['/usr/bin/python3', `${runtimeDir()}/app.py`, ...args]);
}
// Desktop files shown inside a fence. The companion publishes the list with
// its PID; a stale list (companion not running) hides nothing.
function fencedFile() {
    const config = GLib.getenv('ZORIN11_CONFIG_DIR') ||
        GLib.build_filenamev([GLib.get_user_config_dir(), 'zorin11-hub']);
    return Gio.File.new_for_path(GLib.build_filenamev([config, 'fenced.json']));
}
// The PID must still be the same process: same boot and kernel start time.
function companionAlive(data) {
    try {
        const read = path => new TextDecoder().decode(GLib.file_get_contents(path)[1]);
        const stat = read(`/proc/${data.pid}/stat`);
        const start = stat.slice(stat.lastIndexOf(')') + 2).split(' ')[19];
        return read('/proc/sys/kernel/random/boot_id').trim() === data.boot && start === data.start;
    } catch (e) {
        return false;
    }
}
function readFenced() {
    try {
        const [ok, bytes] = fencedFile().load_contents(null);
        const data = JSON.parse(new TextDecoder().decode(bytes));
        if (!ok || data.version !== 1 || !Number.isInteger(data.pid) || !Array.isArray(data.paths))
            return new Set();
        if (!companionAlive(data))
            return new Set();
        return new Set(data.paths.filter(path => typeof path === 'string'));
    } catch (e) {
        return new Set();
    }
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
        main.append(item('New fence here', 'view-app-grid-symbolic',
            () => companion(['--new-fence', `${this._clickX}`, `${this._clickY}`])));
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
        if (!this._fencedMonitor) {
            this._fencedMonitor = fencedFile().monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._fencedMonitor.connect('changed', (monitor, file, other, event) => {
                if (event === Gio.FileMonitorEvent.CHANGES_DONE_HINT || event === Gio.FileMonitorEvent.CREATED ||
                    event === Gio.FileMonitorEvent.DELETED || event === Gio.FileMonitorEvent.MOVED_IN ||
                    event === Gio.FileMonitorEvent.RENAMED)
                    this._updateDesktop().catch(logError);
            });
        }
        const fenced = readFenced();
        // While icons are fenced, notice if the companion goes away (crash,
        // kill) and bring them back, since then nothing rewrites the list.
        if (fenced.size && !this._fencedWatch) {
            this._fencedWatch = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 5, () => {
                if (readFenced().size)
                    return GLib.SOURCE_CONTINUE;
                this._fencedWatch = 0;
                this._updateDesktop().catch(logError);
                return GLib.SOURCE_REMOVE;
            });
        }
        if (fenced.size) {
            files = files.filter(file => {
                if (!fenced.has(file.path))
                    return true;
                file._onDestroy();
                return false;
            });
        }
        super._drawDesktop(files);
    }

    onDragDataReceived(context, x, y, selection, info, forceLocal, forceCopy) {
        // A desktop file dragged out of a fence is already in ~/Desktop: place
        // it at the drop point instead of asking Files to move it onto itself.
        if (!forceLocal && (info === Enums.DndTargetInfo.URI_LIST || info === Enums.DndTargetInfo.GNOME_ICON_LIST)) {
            const files = DesktopIconsUtil.getFilesFromNautilusDnD(selection, info);
            const desktop = this._desktopDir.get_uri();
            if (files.length && files.every(uri => Gio.File.new_for_uri(uri).get_parent()?.get_uri() === desktop)) {
                this.onDragLeave();
                this.clearFileCoordinates(files, [x, y]);
                Gtk.drag_finish(context, true, false, Gtk.get_current_event_time());
                return;
            }
        }
        super.onDragDataReceived(context, x, y, selection, info, forceLocal, forceCopy);
    }

    onPressButton(x, y, event, grid) {
        // Double-click empty desktop: quick-hide or show all fences.
        if (event.get_event_type() === Gdk.EventType.DOUBLE_BUTTON_PRESS && event.get_button()[1] === 1)
            companion(['--toggle-fences']);
        super.onPressButton(x, y, event, grid);
    }
};
