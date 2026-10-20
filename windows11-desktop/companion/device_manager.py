"""Standalone Windows-inspired hardware tree; shared Explorer is not imported."""
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import hardware_inventory as inventory


class Properties(Gtk.Dialog):
    def __init__(self, parent, row):
        super().__init__(title=row['name'] + ' Properties', transient_for=parent,
                         modal=True, destroy_with_parent=True)
        self.set_default_size(620, 420)
        self.add_button('Copy details', 1)
        self.add_button('Close', Gtk.ResponseType.CLOSE)
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.details = inventory.report(row)
        area = self.get_content_area()
        area.set_border_width(20)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        area.pack_start(scroll, True, True, 0)
        text = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.get_buffer().set_text(self.details)
        text.get_accessible().set_name('Device properties')
        scroll.add(text)
        self.connect('response', self.respond)
        self.show_all()

    def respond(self, _dialog, response):
        if response == 1:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.details, -1)
        else:
            self.destroy()


class DeviceWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Device Manager')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        self.set_wmclass('Zorin11-device-manager', 'Zorin11-device-manager')
        self.set_icon_name('computer')
        self.set_default_size(860, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.closed = self.pending = self.again = False
        self.data = []
        self.error = ''
        self.expanded = set()
        self.query_active = False
        header = Gtk.HeaderBar(title='Device Manager', show_close_button=True)
        self.set_titlebar(header)
        self.refresh_button = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        self.refresh_button.set_tooltip_text('Refresh hardware inventory (F5)')
        self.refresh_button.get_accessible().set_name('Refresh hardware inventory')
        self.refresh_button.connect('clicked', lambda *_: self.refresh())
        header.pack_end(self.refresh_button)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=20)
        self.add(outer)
        self.search = Gtk.SearchEntry(placeholder_text='Search devices, drivers or hardware IDs')
        self.search.get_accessible().set_name('Search devices')
        self.search.connect('search-changed', lambda *_: self.populate())
        outer.pack_start(self.search, False, False, 0)
        self.store = Gtk.TreeStore(str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.get_accessible().set_name('Hardware devices')
        self.tree.set_enable_search(False)
        column = Gtk.TreeViewColumn('Device')
        icon = Gtk.CellRendererPixbuf()
        column.pack_start(icon, False)
        column.add_attribute(icon, 'icon-name', 0)
        title = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        column.pack_start(title, True)
        column.add_attribute(title, 'text', 1)
        column.set_expand(True)
        column.set_min_width(360)
        self.tree.append_column(column)
        self.tree.append_column(Gtk.TreeViewColumn('Driver', Gtk.CellRendererText(), text=2))
        self.tree.connect('row-activated', self.activated)
        self.tree.get_selection().connect('changed', lambda *_: self.properties_button.set_sensitive(self.selected() is not None))
        self.tree.connect('popup-menu', self.popup)
        self.tree.connect('button-press-event', self.mouse)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        outer.pack_start(scroll, True, True, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        outer.pack_start(self.status, False, False, 0)
        footer = Gtk.Box(spacing=10)
        outer.pack_start(footer, False, False, 0)
        for text, action in [('Expand all', self.tree.expand_all), ('Collapse all', self.tree.collapse_all)]:
            button = Gtk.Button(label=text)
            button.connect('clicked', lambda _, action=action: action())
            footer.pack_start(button, False, False, 0)
        self.properties_button = Gtk.Button(label='Properties')
        self.properties_button.set_sensitive(False)
        self.properties_button.connect('clicked', lambda *_: self.properties())
        footer.pack_end(self.properties_button, False, False, 0)
        self.connect('key-press-event', self.key)
        self.connect('destroy', self.cleanup)
        self.show_all()
        self.refresh()

    def selected(self):
        model, iterator = self.tree.get_selection().get_selected()
        ident = model[iterator][3] if iterator else ''
        return next((r for r in self.data if r['id'] == ident), None)

    def properties(self):
        row = self.selected()
        if row:
            return Properties(self, row)

    def activated(self, _tree, path, _column):
        if self.store[path][3]:
            self.properties()
        elif self.tree.row_expanded(path):
            self.tree.collapse_row(path)
        else:
            self.tree.expand_row(path, False)

    def popup(self, _tree=None, event=None):
        if not self.selected():
            return False
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label='Properties')
        item.connect('activate', lambda *_: self.properties())
        menu.append(item)
        menu.connect('selection-done', lambda menu: menu.destroy())
        menu.show_all()
        menu.attach_to_widget(self.tree, None)
        if event:
            menu.popup_at_pointer(event)
        else:
            model, iterator = self.tree.get_selection().get_selected()
            rect = self.tree.get_cell_area(model.get_path(iterator), self.tree.get_column(0))
            menu.popup_at_rect(self.tree.get_bin_window(), rect, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
        return True

    def mouse(self, _tree, event):
        if event.button != 3:
            return False
        hit = self.tree.get_path_at_pos(int(event.x), int(event.y))
        if not hit:
            return False
        self.tree.get_selection().select_path(hit[0])
        return self.popup(event=event)

    def key(self, _window, event):
        if event.keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        if event.keyval in (Gdk.KEY_f, Gdk.KEY_F) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        if event.keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text('')
            else:
                self.close()
            return True
        return False

    def refresh(self):
        if self.closed:
            return
        if self.pending:
            self.again = True
            return
        self.pending = True
        self.refresh_button.set_sensitive(False)
        self.status.set_text('Reading hardware inventory…')
        self.pool.submit(inventory.collect).add_done_callback(lambda f: GLib.idle_add(self.received, f))

    def received(self, future):
        if self.closed:
            return False
        self.pending = False
        self.refresh_button.set_sensitive(True)
        try:
            result = future.result()
            self.error = ''
            selected = self.selected()
            self.data = result['devices']
            self.warnings = result['warnings']
            self.populate(selected['id'] if selected else None)
        except Exception as error:
            self.data = []
            self.store.clear()
            self.error = 'Hardware inventory unavailable. Choose Refresh to retry.\n' + str(error)[:200]
            self.status.set_text(self.error)
        if self.again:
            self.again = False
            self.refresh()
        return False

    def populate(self, keep=None):
        if self.closed:
            return
        selected = self.selected()
        keep = keep or (selected['id'] if selected else None)
        if not self.query_active:
            self.expanded = {row[1].rsplit(' (', 1)[0] for row in self.store
                             if self.tree.row_expanded(row.path)}
        query = self.search.get_text().strip()
        self.query_active = bool(query)
        self.store.clear()
        groups = {}
        count = 0
        for row in self.data:
            if not inventory.matches(row, query):
                continue
            category = row['category']
            if category not in groups:
                groups[category] = (self.store.append(None, [row['icon'], category, '', '']), 0)
            parent, total = groups[category]
            groups[category] = (parent, total + 1)
            child = self.store.append(parent, [row['icon'], row['name'], row['driver'], row['id']])
            count += 1
            if row['id'] == keep:
                self.tree.expand_to_path(self.store.get_path(child))
                self.tree.get_selection().select_iter(child)
        for category, (parent, total) in groups.items():
            self.store[parent][1] = f'{category} ({total})'
            if query or category in self.expanded:
                self.tree.expand_row(self.store.get_path(parent), False)
        self.status.set_text(self.error or f'{count} of {len(self.data)} devices · Read-only inventory · F5 to refresh'
                             + ('\n' + '; '.join(getattr(self, 'warnings', [])) if getattr(self, 'warnings', []) else ''))

    def cleanup(self, *_):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.zorin11.DeviceManager')

    def do_activate(self):
        window = self.get_active_window() or DeviceWindow(self)
        window.present()


if __name__ == '__main__':
    Application().run()
