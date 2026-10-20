imports.gi.versions.Gtk = '3.0';
const {Gtk, Gdk, GLib, Gio} = imports.gi;
Gtk.init(null);
imports.searchPath.unshift(`${ARGV[0]}/app`);
const Prefs = imports.preferences;
Prefs.init(`${ARGV[0]}/app`);
const Manager = imports.desktopManager.DesktopManager;
const m = Object.create(Manager.prototype);
m._codePath = `${ARGV[0]}/app`;
let refreshes = 0, pastes = 0, folders = 0, sorts = 0;
m._updateDesktop = async () => {refreshes++;};
m.unselectAll = () => {};
m._doPaste = () => {pastes++;};
m.doNewFolder = () => {folders++;};
m.doSorts = () => {sorts++;};
m._createDesktopBackgroundMenu();
function check(value, message) {if (!value) throw Error(message);}
function row(menu, name) {
    return menu.get_children().find(r => r.get_accessible().accessible_name === name || r.get_label?.() === name);
}
function activate(menu, name) {
    const found = row(menu, name);
    check(found, `Missing ${name}`);
    found.activate();
    while (GLib.MainContext.default().pending()) GLib.MainContext.default().iteration(false);
    return found;
}
const names = m._menu.get_children().filter(r => !(r instanceof Gtk.SeparatorMenuItem)).map(r => r.get_accessible().accessible_name);
check(JSON.stringify(names) === JSON.stringify(['View','Sort by','Refresh','Paste','New','Display settings','Personalize','Next desktop background','Show more options']), names);
activate(m._menu, 'Refresh'); check(refreshes === 1, 'Refresh did not reload');
const view = row(m._menu, 'View').get_submenu();
activate(view, 'Small icons'); check(Prefs.desktopSettings.get_string('icon-size') === 'small', 'Icon size did not change');
activate(view, 'Auto arrange icons'); check(Prefs.desktopSettings.get_boolean('keep-arranged'), 'Auto arrange did not persist');
activate(view, 'Show desktop icons'); check(!m._axentraSettings.get_boolean('show-icons') && refreshes === 2, 'Hide icons did not refresh');
activate(view, 'Show desktop icons'); check(m._axentraSettings.get_boolean('show-icons'), 'Show icons did not persist');
activate(row(m._menu, 'Sort by').get_submenu(), 'Size');
check(Prefs.desktopSettings.get_string('arrangeorder') === 'SIZE' && sorts === 1, 'Sorting did not use Zorin');
m._pasteMenuItem.set_sensitive(false);check(!row(m._menu, 'Paste').get_sensitive(), 'Empty clipboard must disable Paste');
m._pasteMenuItem.set_sensitive(true);activate(m._menu, 'Paste');check(pastes === 1, 'Paste did not delegate');
activate(row(m._menu, 'New').get_submenu(), 'Folder');check(folders === 1, 'New folder did not delegate');
check(row(m._menu, 'Show more options').get_submenu().get_children().includes(m._undoMenuItem), 'Original operations missing');
for (const name of ['Display settings','Personalize','Next desktop background']) {
    activate(m._menu, name);
    GLib.usleep(150000);
}
if (ARGV[1]) {
    const window = new Gtk.Window({title:'Desktop menu preview', default_width:420, default_height:600});
    const box = new Gtk.EventBox();
    window.add(box);window.show_all();
    m._menu.popup_at_widget(box, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.NORTH_WEST, null);
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
        const display = Gdk.get_default_root_window();
        const image = Gdk.pixbuf_get_from_window(display,0,0,420,600);
        image.savev(`${ARGV[1]}/desktop-menu.png`,'png',[],[]);
        Gtk.main_quit();return GLib.SOURCE_REMOVE;
    });
    Gtk.main();
}
print('PASS real GTK menu routing, icon preferences, refresh, clipboard sensitivity, native file action delegation');
