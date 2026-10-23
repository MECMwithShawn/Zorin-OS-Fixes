#!/usr/bin/gjs -m
// Host the installed Zorin preferences and our Motion page without changing vendor files.
import Adw from 'gi://Adw?version=1';
import Gtk from 'gi://Gtk?version=4.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import GIRepository from 'gi://GIRepository?version=2.0';
import {buildMotionControls} from './controls.js';

const vendor = 'zorin-taskbar@zorinos.com';
async function loadVendor() {
    for (const lib of ['/usr/lib/gnome-shell', '/usr/lib64/gnome-shell']) {
        GIRepository.Repository.prepend_search_path(`${lib}/girepository-1.0`);
        GIRepository.Repository.prepend_library_path(lib);
    }
    const resource = GLib.get_system_data_dirs().map(dir => `${dir}/gnome-shell/org.gnome.Shell.Extensions.src.gresource`)
        .find(path => GLib.file_test(path, GLib.FileTest.IS_REGULAR));
    if (!resource) throw new Error('GNOME preferences resources are unavailable');
    Gio.Resource.load(resource)._register();
    imports.package.initFormat();
    GObject.gtypeNameBasedOnJSPath = true;
    const {extensionManager} = await import('resource:///org/gnome/Shell/Extensions/js/extensionsService.js');
    const {ExtensionPrefsDialog} = await import('resource:///org/gnome/Shell/Extensions/js/extensionPrefsDialog.js');
    const info = Gio.DBus.session.call_sync('org.gnome.Shell', '/org/gnome/Shell', 'org.gnome.Shell.Extensions',
        'GetExtensionInfo', new GLib.Variant('(s)', [vendor]), null, Gio.DBusCallFlags.NONE, 2000, null).deep_unpack()[0];
    if (!info.uuid) throw new Error('Zorin taskbar is not available in this session');
    return new ExtensionPrefsDialog(extensionManager.createExtensionObject(info));
}
const App = GObject.registerClass(class extends Adw.Application {
    _init() { super._init({application_id: 'local.zorin11.TaskbarSettings', flags: Gio.ApplicationFlags.HANDLES_COMMAND_LINE}); }
    vfunc_command_line(commandLine) {
        this.showMotion = commandLine.get_arguments().includes('--motion');
        this.activate();
        commandLine.set_exit_status(0);
        commandLine.done();
        return 0;
    }
    vfunc_activate() {
        if (this.window) {
            if (this.showMotion) this.window.set_visible_page_name('motion');
            this.window.present(); return;
        }
        if (this.opening) return;
        this.opening = true; this.hold();
        this.open().finally(() => { this.opening = false; this.release(); });
    }
    async open() {
        let win;
        try {
            win = await loadVendor();
            await new Promise(resolve => win.connect('loaded', resolve));
        } catch (e) {
            // Keep Motion usable if a future GNOME version changes its preferences loader.
            log(`Taskbar preferences: ${e.message}`);
            win = new Adw.PreferencesWindow();
            const page = new Adw.PreferencesPage({title: 'Taskbar', icon_name: 'preferences-desktop-display-symbolic'});
            const group = new Adw.PreferencesGroup({description: 'Open the installed taskbar controls for position, style and behavior.'});
            const button = new Gtk.Button({label: 'Open taskbar controls', margin_top: 12, margin_bottom: 12});
            button.connect('clicked', () => Gio.Subprocess.new(['gnome-extensions', 'prefs', vendor], Gio.SubprocessFlags.NONE));
            group.add(button); page.add(group); win.add(page);
        }
        this.window = win; this.add_window(win);
        win.title = 'Taskbar settings'; win.set_default_size(820, 830);
        const motionPage = new Adw.PreferencesPage({title: 'Motion', name: 'motion', icon_name: 'preferences-desktop-effects-symbolic'});
        const group = new Adw.PreferencesGroup();
        group.add(buildMotionControls(win)); motionPage.add(group); win.add(motionPage);
        if (this.showMotion) win.visible_page = motionPage;
        win.connect('close-request', () => { this.window = null; return false; });
        win.present();
    }
});
new App().run(['taskbar-settings', ...ARGV]);
