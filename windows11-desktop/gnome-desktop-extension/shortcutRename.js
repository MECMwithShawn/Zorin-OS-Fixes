// SPDX-License-Identifier: GPL-3.0-or-later
/* exported renameShortcut, ask */
const {Gio, GLib, Gtk} = imports.gi;
function renameShortcut(file, name) {
    name = name.trim();
    if (!name || name.length > 200 || /[\r\n\x00/]/.test(name))
        throw new Error('Enter a name without slashes or line breaks (up to 200 characters).');
    const info = file.query_info('standard::type,standard::is-symlink,unix::mode,metadata::trusted', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
    if (info.get_is_symlink() || info.get_file_type() !== Gio.FileType.REGULAR)
        throw new Error('This shortcut cannot be renamed here.');
    const [ok, bytes, etag] = file.load_contents(null);
    if (!ok) throw new Error('Could not read the shortcut.');
    const key = new GLib.KeyFile();
    key.load_from_data(new TextDecoder().decode(bytes), bytes.length, GLib.KeyFileFlags.KEEP_COMMENTS | GLib.KeyFileFlags.KEEP_TRANSLATIONS);
    if (key.get_string('Desktop Entry', 'Type') !== 'Application') throw new Error('This is not an application shortcut.');
    // Localized Name entries otherwise override the edited label in GNOME.
    for (const k of key.get_keys('Desktop Entry')[0])
        if (k.startsWith('Name[')) key.set_string('Desktop Entry', k, name);
    key.set_string('Desktop Entry', 'Name', name);
    file.replace_contents(key.to_data()[0], etag, false, Gio.FileCreateFlags.NONE, null);
    if (info.has_attribute('unix::mode')) file.set_attribute_uint32('unix::mode', info.get_attribute_uint32('unix::mode'), Gio.FileQueryInfoFlags.NONE, null);
    const trust = info.get_attribute_string('metadata::trusted');
    if (trust) file.set_attribute_string('metadata::trusted', trust, Gio.FileQueryInfoFlags.NONE, null);
}
function ask(manager, fileItem) {
    const dialog = new Gtk.Dialog({title:'Rename shortcut', modal:true});
    dialog.add_button('Cancel', Gtk.ResponseType.CANCEL);
    dialog.add_button('Rename', Gtk.ResponseType.OK);
    dialog.set_default_response(Gtk.ResponseType.OK);
    const box = dialog.get_content_area();box.set_border_width(20);box.set_spacing(12);
    const entry = new Gtk.Entry({text:fileItem._desktopFile?.get_display_name() || fileItem.fileName.replace(/\.desktop$/, ''), activates_default:true, max_length:200});
    entry.get_accessible().set_name('Shortcut name');box.add(entry);
    const error = new Gtk.Label({wrap:true});box.add(error);
    manager.showPopup();
    dialog.connect('destroy', () => manager.hidePopup());
    dialog.connect('response', (_, response) => {
        if (response === Gtk.ResponseType.OK) {
            try {renameShortcut(fileItem.file, entry.text);}
            catch (e) {error.set_text(e.message);return;}
        }
        dialog.destroy();
    });
    dialog.show_all();entry.grab_focus();entry.select_region(0,-1);
    return dialog;
}
