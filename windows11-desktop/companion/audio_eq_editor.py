"""Editor for the persistent system-wide Custom EQ preset."""
import threading
import uuid
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk
import audio_effects as eq


class Equalizer(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.zorin11.CustomEqualizer', flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.preview_timer = 0
        self.preview_pending = 0
        self.preview_token = str(uuid.uuid4())
        self.preview_started = False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Custom System EQ')
        self.window.set_default_size(540, 480)
        self.window.connect('destroy', self._closed)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24)
        self.window.add(box)
        title = Gtk.Label(xalign=0)
        title.set_markup('<b>Custom system equalizer</b>')
        box.pack_start(title, False, False, 0)
        box.pack_start(Gtk.Label(label='Hear changes as you adjust each band. Save to keep them.\nClosing without saving restores your saved preset.', xalign=0), False, False, 0)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.pack_start(self.controls, True, True, 0)
        self.base = Gtk.ComboBoxText()
        for p in eq.PRESETS:
            self.base.append(p['id'], 'Start from: ' + ('Flat' if p['id'] == 'off' else p['name']))
        self.base.set_active_id('custom')
        self.controls.pack_start(self.base, False, False, 0)
        grid = Gtk.Grid(column_spacing=18, row_spacing=12)
        self.controls.pack_start(grid, True, True, 0)
        self.adjustments = []
        for i, (frequency, gain) in enumerate(zip(eq.FREQUENCIES, eq.custom_gains())):
            label = f'{frequency / 1000:g} kHz' if frequency >= 1000 else f'{frequency} Hz'
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            adjustment = Gtk.Adjustment(value=gain, lower=-12, upper=12, step_increment=.5, page_increment=1)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment, hexpand=True, draw_value=False)
            scale.add_mark(0, Gtk.PositionType.BOTTOM, None)
            scale.get_accessible().set_name(label + ' gain')
            spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=.5, digits=1)
            spin.get_accessible().set_name(label + ' gain in dB')
            grid.attach(scale, 1, i, 1, 1)
            grid.attach(spin, 2, i, 1, 1)
            grid.attach(Gtk.Label(label='dB'), 3, i, 1, 1)
            self.adjustments.append(adjustment)
        for adjustment in self.adjustments:
            adjustment.connect('value-changed', self._changed)
        self.base.connect('changed', self._base_changed)
        box.pack_start(Gtk.Label(label='Range: −12 to +12 dB. Automatic headroom helps prevent clipping.', wrap=True, xalign=0), False, False, 0)
        self.status = Gtk.Label(label='', wrap=True, xalign=0)
        self.status.set_selectable(True)
        box.pack_start(self.status, False, False, 0)
        self.save_button = Gtk.Button(label='Save as system default')
        self.save_button.get_style_context().add_class('suggested-action')
        self.save_button.connect('clicked', self._save)
        box.pack_start(self.save_button, False, False, 0)
        self.window.show_all()

    def _closed(self, *_):
        self._stop_preview()
        self.window = None

    def _stop_preview(self):
        for timer in (self.preview_timer, self.preview_pending):
            if timer:
                GLib.source_remove(timer)
        self.preview_timer = self.preview_pending = 0
        eq.clear_preview(self.preview_token)

    def _changed(self, *_):
        if not self.preview_pending:
            self.preview_pending = GLib.timeout_add(60, self._preview)

    def _preview(self):
        self.preview_pending = 0
        try:
            eq.write_preview([a.get_value() for a in self.adjustments], self.preview_token)
            self.status.set_text('Live preview · Not saved. Close to restore your saved preset.')
            if not self.preview_timer:
                self.preview_timer = GLib.timeout_add(500, self._refresh_preview)
            if not self.preview_started:
                self.preview_started = True
                self.hold()
                def start():
                    error = None
                    try:
                        eq.run(['systemctl', '--user', 'start', eq.UNIT], timeout=12)
                    except Exception as exc:
                        error = str(exc)
                    GLib.idle_add(self._preview_ready, error)
                threading.Thread(target=start).start()
        except Exception as exc:
            self.status.set_text('Could not preview: ' + str(exc))
        return GLib.SOURCE_REMOVE

    def _refresh_preview(self):
        try:
            eq.write_preview([a.get_value() for a in self.adjustments], self.preview_token)
            status = eq.read_json(eq.STATUS, {})
            if status.get('error'):
                self.status.set_text('Could not preview: ' + status['error'])
        except Exception as exc:
            self.status.set_text('Could not preview: ' + str(exc))
        return GLib.SOURCE_CONTINUE

    def _preview_ready(self, error):
        if error and self.window:
            self.preview_started = False
            self._stop_preview()
            self.status.set_text('Could not preview: ' + error)
        self.release()
        return GLib.SOURCE_REMOVE

    def _base_changed(self, combo):
        for adjustment, gain in zip(self.adjustments, eq.preset(combo.get_active_id())['gains']):
            adjustment.set_value(gain)

    def _save(self, *_):
        gains = [a.get_value() for a in self.adjustments]
        self._stop_preview()
        self.controls.set_sensitive(False)
        self.save_button.set_sensitive(False)
        self.status.set_text('Saving and applying…')
        self.hold()
        def apply():
            error = None
            try:
                eq.configure('custom', gains)
            except Exception as exc:
                error = str(exc)
            GLib.idle_add(self._finished, error)
        threading.Thread(target=apply).start()

    def _finished(self, error):
        if self.window:
            self.controls.set_sensitive(True)
            self.save_button.set_sensitive(True)
            self.status.set_text('Could not save: ' + error if error else 'Custom is now your system default and will be restored after login.')
        self.release()
        return GLib.SOURCE_REMOVE


if __name__ == '__main__':
    Equalizer().run(None)
