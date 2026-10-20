"""Standalone Windows-style Event Viewer; no shared frontend dependencies."""
from concurrent.futures import ThreadPoolExecutor, CancelledError
from threading import Event
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import event_logs as logs


STYLE = b"""
#zorin11-events, #zorin11-events headerbar { background: #202020; color: #f2f2f2; }
#zorin11-events headerbar { border-bottom: 1px solid #383838; box-shadow: none; }
#zorin11-events label { color: inherit; }
#zorin11-events button, #zorin11-events entry {
    background: #2d2d2d; color: #f2f2f2; border: 1px solid #414141;
    border-radius: 5px; box-shadow: none;
}
#zorin11-events button:hover { background: #393939; }
#zorin11-events button:disabled { color: #909090; background: #252525; }
#zorin11-events entry:focus { border-color: #60cdff; }
#zorin11-events button.titlebutton { border: none; border-radius: 3px; }
#zorin11-events button.titlebutton.close:hover { background: #c42b1c; color: white; }
#zorin11-events list { background: #202020; }
#zorin11-events row { border-radius: 5px; margin: 2px 0; }
#zorin11-events row:selected { background: #383838; color: #ffffff; }
#zorin11-events row:hover { background: #303030; }
#zorin11-events treeview, #zorin11-events textview text { background: #272727; color: #f2f2f2; }
#zorin11-events treeview:selected { background: #34464f; color: #ffffff; }
#zorin11-events treeview header button { border-radius: 0; border-width: 0 1px 1px 0; }
#zorin11-events paned separator { background: #202020; min-height: 6px; }
"""


class EventWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Event Viewer')
        self.set_name('zorin11-events')
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        self.set_wmclass('Zorin11-event-viewer', 'Zorin11-event-viewer')
        self.set_icon_name('utilities-system-monitor')
        self.set_default_size(1100, 760)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancel = Event()
        self.closed = self.pending = self.again = False
        self.generation = 0
        self.timer = 0
        self.rows = []
        self.warning = self.error = ''
        header = Gtk.HeaderBar(title='Event Viewer', show_close_button=True)
        self.set_titlebar(header)
        self.refresh_button = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        self.refresh_button.set_tooltip_text('Refresh events (F5)')
        self.refresh_button.get_accessible().set_name('Refresh events')
        self.refresh_button.connect('clicked', lambda *_: self.request())
        header.pack_end(self.refresh_button)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=20)
        self.add(outer)
        controls = Gtk.Box(spacing=10)
        outer.pack_start(controls, False, False, 0)
        self.period = self.combo([('boot', 'Current boot'), ('previous', 'Previous boot'),
                                  ('hour', 'Last hour'), ('day', 'Last 24 hours')], 'Time range')
        self.level = self.combo([('all', 'All levels'), ('errors', 'Errors and critical'),
                                ('warnings', 'Warnings and errors'), ('information', 'Information and notices')], 'Event level')
        controls.pack_start(self.period, False, False, 0)
        controls.pack_start(self.level, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text='Search loaded events')
        self.search.get_accessible().set_name('Search loaded events')
        self.search.connect('search-changed', lambda *_: self.populate())
        controls.pack_start(self.search, True, True, 0)
        self.auto = Gtk.CheckButton(label='Auto-refresh')
        self.auto.set_tooltip_text('Read the latest events every five seconds')
        self.auto.connect('toggled', self.toggle_auto)
        controls.pack_end(self.auto, False, False, 0)
        body = Gtk.Box(spacing=16)
        outer.pack_start(body, True, True, 0)
        self.scopes = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.scopes.set_size_request(155, -1)
        for key, label, icon in [('application', 'Application', 'view-grid-symbolic'),
                                  ('system', 'System', 'computer-symbolic'), ('kernel', 'Kernel', 'utilities-terminal-symbolic')]:
            row = Gtk.ListBoxRow()
            row.scope = key
            box = Gtk.Box(spacing=10, margin=12)
            box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
            box.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
            row.add(box)
            self.scopes.add(row)
        self.scopes.select_row(self.scopes.get_row_at_index(1))
        body.pack_start(self.scopes, False, False, 0)
        panes = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        panes.set_position(340)
        body.pack_start(panes, True, True, 0)
        self.store = Gtk.ListStore(str, str, str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_enable_search(False)
        self.tree.get_accessible().set_name('Events')
        level = Gtk.TreeViewColumn('Level')
        icon = Gtk.CellRendererPixbuf()
        level.pack_start(icon, False)
        level.add_attribute(icon, 'icon-name', 0)
        text = Gtk.CellRendererText()
        level.pack_start(text, True)
        level.add_attribute(text, 'text', 1)
        self.tree.append_column(level)
        for title, index, width in [('Date and time', 2, 185), ('Source', 3, 150), ('Message', 4, 260)]:
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            column.set_resizable(True)
            column.set_expand(title == 'Message')
            self.tree.append_column(column)
        self.tree.get_selection().connect('changed', lambda *_: self.show_details())
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        panes.pack1(scroll, True, False)
        self.detail = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.detail.set_top_margin(12)
        self.detail.set_bottom_margin(12)
        self.detail.set_left_margin(12)
        self.detail.set_right_margin(12)
        self.detail.get_accessible().set_name('Selected event details')
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.add(self.detail)
        panes.pack2(detail_scroll, True, False)
        footer = Gtk.Box(spacing=12)
        outer.pack_end(footer, False, False, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(100)
        footer.pack_start(self.status, True, True, 0)
        self.copy = Gtk.Button(label='Copy event')
        self.copy.set_sensitive(False)
        self.copy.connect('clicked', self.copy_event)
        footer.pack_end(self.copy, False, False, 0)
        self.period.connect('changed', lambda *_: self.request(True))
        self.level.connect('changed', lambda *_: self.request(True))
        self.scopes.connect('row-selected', lambda *_: self.request(True))
        self.connect('key-press-event', self.key)
        self.connect('destroy', self.cleanup)
        self.show_details()
        self.show_all()
        self.request()

    @staticmethod
    def combo(items, name):
        widget = Gtk.ComboBoxText()
        for key, label in items:
            widget.append(key, label)
        widget.set_active(0)
        widget.get_accessible().set_name(name)
        return widget

    def selected(self):
        model, iterator = self.tree.get_selection().get_selected()
        ident = model[iterator][5] if iterator else ''
        return next((r for r in self.rows if r['id'] == ident), None)

    def show_details(self):
        row = self.selected()
        self.detail.get_buffer().set_text(logs.details(row) if row else 'Select an event to view its details.')
        self.copy.set_sensitive(row is not None)

    def copy_event(self, *_):
        row = self.selected()
        if row:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(logs.details(row), -1)

    def populate(self, keep=None):
        if self.closed:
            return
        selected = self.selected()
        keep = keep or (selected['id'] if selected else None)
        self.store.clear()
        count = 0
        for row in self.rows:
            if not logs.matches(row, self.search.get_text()):
                continue
            priority = row['priority']
            icon = ('dialog-error' if 0 <= priority <= 3 else 'dialog-warning' if priority == 4 else 'dialog-information')
            item = self.store.append([icon, row['level'], row['time'], row['source'],
                                      ' '.join(row['message'].split())[:300], row['id']])
            count += 1
            if row['id'] == keep:
                self.tree.get_selection().select_iter(item)
        self.show_details()
        self.status.set_text(self.error or f'{count} of {len(self.rows)} loaded events · Latest {logs.LIMIT} maximum · Local times'
                             + ('\n' + self.warning if self.warning else ''))

    def request(self, reset=False):
        if self.closed:
            return
        self.generation += 1
        if reset:
            self.rows = []
            self.error = self.warning = ''
            self.populate()
        self.status.set_text('Reading events…')
        if self.pending:
            self.again = True
            self.cancel.set()
        else:
            self.start_query()

    def start_query(self):
        self.pending = True
        self.cancel = Event()
        self.refresh_button.set_sensitive(False)
        token = self.generation
        scope = self.scopes.get_selected_row().scope
        future = self.pool.submit(logs.load, scope, self.period.get_active_id(), self.level.get_active_id(), self.cancel)
        future.add_done_callback(lambda result: GLib.idle_add(self.received, result, token))

    def received(self, future, token):
        if self.closed:
            return False
        self.pending = False
        self.refresh_button.set_sensitive(True)
        if token == self.generation:
            try:
                result = future.result()
                selected = self.selected()
                self.rows, self.warning = result['rows'], result['warning']
                self.error = ''
                self.populate(selected['id'] if selected else None)
            except CancelledError:
                pass
            except Exception as error:
                self.rows = []
                self.error = 'Events unavailable. Choose Refresh to retry.\n' + str(error)[:1000]
                self.populate()
        if self.again:
            self.again = False
            self.start_query()
        return False

    def toggle_auto(self, *_):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if self.auto.get_active():
            self.timer = GLib.timeout_add_seconds(5, self.tick)

    def tick(self):
        if self.closed:
            return False
        if not self.pending:
            self.request()
        return True

    def key(self, _window, event):
        if event.keyval == Gdk.KEY_F5:
            self.request()
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

    def cleanup(self, *_):
        self.closed = True
        self.cancel.set()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        self.pool.shutdown(wait=False, cancel_futures=True)


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.zorin11.EventViewer')

    def do_activate(self):
        (self.get_active_window() or EventWindow(self)).present()


if __name__ == '__main__':
    Application().run()
