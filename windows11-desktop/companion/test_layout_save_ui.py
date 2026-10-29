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
from gi.repository import Gtk,Gdk
sys.path.insert(0,os.environ.get("ZORIN11_TEST_RUNTIME",str(Path(__file__).parent)))
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
        m.saved_view=view
        from multitasking import Multitasking
        event=lambda key,state=0:NS(keyval=key,state=state)
        assert Multitasking.key(m,view.win,event(Gdk.KEY_f,Gdk.ModifierType.CONTROL_MASK))
        assert view.win.get_focus() is view.search
        view.search.set_text('no such layout');assert view.no_matches.get_visible()
        assert not view.rows[0][0].get_visible()
        assert Multitasking.key(m,view.win,event(Gdk.KEY_Escape))
        assert view.rows[0][0].get_visible() and not view.no_matches.get_visible()
        name=next(w for w in descendants(view.win) if getattr(w,'recipe_id',None))
        view.win.set_focus(name);name.set_text('Unwanted partial edit')
        assert Multitasking.key(m,view.win,event(Gdk.KEY_Escape))
        assert name.get_text()=='Both displays'
        name.emit('focus-out-event',Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE))
        assert m.saved_groups.store.groups[0]['name']=='Both displays'
        name.set_text('Office');name.emit('activate')
        view.search.set_text('office');assert view.rows[0][0].get_visible()
        view.search.set_text('Both displays');assert not view.rows[0][0].get_visible()
        provider=Gtk.CssProvider();provider.load_from_path(str(Path(os.environ.get('ZORIN11_TEST_RUNTIME',Path(__file__).parent))/'multitasking.css'))
        if os.environ.get('ZORIN11_LAYOUT_PREVIEW'):
            view.search.set_text('');view.win.get_style_context().add_class('z11-multitask')
            Gtk.StyleContext.add_provider_for_screen(view.win.get_screen(),provider,650)
            view.box.set_border_width(24);view.box.set_spacing(16)
            view.win.resize(920,520)
            while Gtk.events_pending():Gtk.main_iteration_do(False)
            w,h=view.win.get_size()
            image=Gdk.pixbuf_get_from_window(view.win.get_window(),0,0,w,h)
            image.savev(os.environ['ZORIN11_LAYOUT_PREVIEW'],'png',[],[])
        view.win.destroy()
print('PASS: Save layout, startup toggle, search, Ctrl+F, Escape rename cancellation, search updates after rename, CSS')
