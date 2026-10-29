"""Isolated native Save current layout dialog and persistence."""
import os,sys,subprocess,tempfile
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this GTK fixture directly.')
if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private'],env=dict(os.environ,GDK_BACKEND='x11'),timeout=20).returncode)
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
from types import SimpleNamespace as NS
from unittest.mock import patch
from saved_groups import SavedGroups
from saved_groups_view import SavedGroupsView
from test_window_layouts import member
with tempfile.TemporaryDirectory() as folder:
    m=NS(config=Path(folder),groups=[],windows=NS(active=lambda:None),area=lambda *_:(0,0,1200,850))
    def shell(*_):
        m.window=Gtk.Window();box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);m.window.add(box);return m.window,box
    m.shell=shell;m.close=lambda *args:m.window.destroy()
    m.saved_groups=SavedGroups(m)
    snapshot=([dict(member(),_window=1)],'desktop')
    with patch.object(m.saved_groups,'current_layout',return_value=snapshot):
        view=SavedGroupsView(m);view.capture_button.clicked()
        dialog=next(w for w in Gtk.Window.list_toplevels() if isinstance(w,Gtk.Dialog))
        entry=next(c for c in dialog.get_content_area().get_children() if isinstance(c,Gtk.Entry))
        entry.set_text('');dialog.response(Gtk.ResponseType.OK)
        assert not m.saved_groups.store.groups and view.modal
        entry.set_text('Both displays');dialog.response(Gtk.ResponseType.OK)
        assert m.saved_groups.store.groups[0]['name']=='Both displays'
        assert m.saved_groups.store.groups[0]['kind']=='layout' and not view.modal
        view.capture_button.clicked()
        dialog=next(w for w in Gtk.Window.list_toplevels() if isinstance(w,Gtk.Dialog))
        dialog.response(Gtk.ResponseType.CANCEL);assert len(m.saved_groups.store.groups)==1
        def descendants(widget):
            yield widget
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():yield from descendants(child)
        toggle=next(w for w in descendants(view.win) if isinstance(w,Gtk.CheckButton))
        toggle.set_active(True)
        assert m.saved_groups.store.data['startup_layout']==m.saved_groups.store.groups[0]['id']
        toggle=next(w for w in descendants(view.win) if isinstance(w,Gtk.CheckButton))
        toggle.set_active(False);assert not m.saved_groups.store.data['startup_layout']
        view.win.destroy()
print('PASS: named Save current layout dialog, blank-name validation, persistence, cancel')
