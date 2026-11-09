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
check(JSON.stringify(names) === JSON.stringify(['View','Sort by','Refresh','New fence here','Paste','New','Display settings','Personalize','Next desktop background','Show more options']), names);
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
// Trusted launchers now expose Rename, while special icons retain restrictions.
const fileProto = imports.fileItem.FileItem.prototype;
const shortcut = Object.create(fileProto);
Object.defineProperties(shortcut, {trustedDesktopFile:{value:true},isSpecial:{value:false}});
check(shortcut.canRename, 'Trusted shortcut is missing Rename');
const special = Object.create(fileProto);
special._fileExtra = imports.enums.FileType.USER_DIRECTORY_HOME;
Object.defineProperties(special, {trustedDesktopFile:{value:false},isSpecial:{value:true}});
check(!special.canRename, 'Special icon unexpectedly renamable');
const fileMenu = Object.create(imports.fileItemMenu.FileItemMenu.prototype);
fileMenu._menu = new Gtk.Menu();
fileMenu._menuSignals = new imports.signalManager.SignalManager();
let renameActivated=false;
const renameRow=fileMenu._addElementToMenu('Rename…',()=>renameActivated=true);
check(fileMenu._menu.get_style_context().has_class('axentra-desktop-menu'),'Icon menu is not styled');
renameRow.activate();check(renameActivated,'Rename action did not route');
fileMenu._menuSignals.disconnectAllSignals();fileMenu._menu.destroy();
const path = `${ARGV[0]}/shortcut-test.desktop`;
const file = Gio.File.new_for_path(path);
GLib.file_set_contents(path, '[Desktop Entry]\nType=Application\nName=Before\nName[en_US]=Before localized\nExec=/usr/bin/true --example\nIcon=test-icon\n');
file.set_attribute_uint32('unix::mode', 0o755, Gio.FileQueryInfoFlags.NONE, null);
const rename = imports.shortcutRename;
rename.renameShortcut(file,'After rename');
const key = new GLib.KeyFile();key.load_from_file(path,GLib.KeyFileFlags.KEEP_TRANSLATIONS);
check(key.get_string('Desktop Entry','Name') === 'After rename','Label not saved');
check(key.get_string('Desktop Entry','Name[en_US]') === 'After rename','Localized label not updated');
check(key.get_string('Desktop Entry','Exec') === '/usr/bin/true --example','Launch command changed');
check(key.get_string('Desktop Entry','Icon') === 'test-icon','Icon changed');
check((file.query_info('unix::mode',0,null).get_attribute_uint32('unix::mode') & 0o777) === 0o755,'Execute permission lost');
for (const invalid of ['', 'bad/name', 'bad\nname']) {
    let rejected=false;try {rename.renameShortcut(file,invalid);} catch(e) {rejected=true;}
    check(rejected,'Invalid shortcut name accepted');
}
let popupCount=0;
const dialog = rename.ask({showPopup:()=>popupCount++,hidePopup:()=>popupCount--}, {file,fileName:'shortcut-test.desktop'});
const entry = dialog.get_content_area().get_children().find(c=>c instanceof Gtk.Entry);
entry.text='Dialog renamed';dialog.response(Gtk.ResponseType.OK);
check(popupCount===0,'Rename popup was not released');
key.load_from_file(path,GLib.KeyFileFlags.KEEP_TRANSLATIONS);
check(key.get_string('Desktop Entry','Name') === 'Dialog renamed','Dialog did not rename');
file.delete(null);
print('PASS trusted shortcut Rename, dialog, locale labels, validation, executable and icon preservation');
print('PASS real GTK menu routing, icon preferences, refresh, clipboard sensitivity, native file action delegation');
