"""Opt-in Wayland caption/WebKit round trip using two disposable app windows.
Run with GDK_BACKEND=x11, matching the installed companion's positioning backend.
No real window is snapped and no user settings or documents are changed.
"""
if __name__ != '__main__':
    import unittest
    raise unittest.SkipTest('Run this GUI fixture directly.')
import json,os,sys,time
from pathlib import Path
from types import SimpleNamespace as NS
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,Gdk,GLib,WebKit2
BASE=Path(os.environ.get('ZORIN11_TEST_RUNTIME',Path(__file__).resolve().parent))
sys.path.insert(0,str(BASE))
from app import Hub
from multitasking import Multitasking
from windowing import Windows,layouts,zone_rect
import gnome_bridge
assert os.environ.get('XDG_SESSION_TYPE')=='wayland','Requires the live Wayland session'

def wait(fn,seconds=5):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        value=fn()
        if value:return value
        time.sleep(.02)
    raise AssertionError('Timed out')
def pump(seconds):
    start=time.monotonic();wait(lambda:time.monotonic()-start>=seconds,seconds+2)
def js(win,code):
    result=[]
    def done(view,res,*_):
        try:result.append(view.evaluate_javascript_finish(res).to_json(0))
        except Exception as error:result.append(error)
    win.web.evaluate_javascript(code,-1,None,None,None,done,None);wait(lambda:result)
    if isinstance(result[0],Exception):raise result[0]
    return json.loads(result[0])

display=Gdk.Display.get_default()
def work_area(x,y):return display.get_monitor_at_point(x,y).get_workarea()
manager=Windows();prior=manager.active();windows=[];errors=[]
m=Multitasking.__new__(Multitasking)
m.windows=manager;m.window=None;m.overlay=None;m.generation=0;m.origin=None;m.hover_timer=0
m.preferences={'assist':False};m.preview_cache={};m.groups=[]
m.snap_groups=NS(remember=lambda *_:None,forget=lambda *_:None)
m.desktops=NS(on=lambda *_:True,current=lambda:0)
hub=NS(multitasking=m,surfaces={},work_area=work_area);m.hub=hub
css=Gtk.CssProvider();css.load_from_path(str(BASE/'multitasking.css'))
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,650)

def fixture(mode,x,y):
    win=Gtk.Window(title='Axentra caption validation');win.mode=mode
    win.set_decorated(False);win.set_default_size(900,620);win.move(x,y)
    content=WebKit2.UserContentManager();content.register_script_message_handler('desktop')
    win.web=WebKit2.WebView.new_with_user_content_manager(content);win.add(win.web);win.ready=False
    data=dict(mode=mode,title='Fixture',path='/fixture',places=[],entries=[],facts={},wallpaper={},apps=[],user='Fixture')
    def receive(_,result):
        msg=json.loads(result.get_js_value().to_string())
        try:
            if msg['action']=='ready':
                win.web.evaluate_javascript('window.receive('+json.dumps(dict(type='state',data=data))+')',-1,None,None,None,None,None)
                win.ready=True
            elif msg['action'] in ('snap-hover','snap-layouts'):Hub.dispatch(hub,win,msg)
        except Exception as e:errors.append(e)
    content.connect('script-message-received::desktop',receive)
    win.web.load_uri((BASE/'dist/index.html').resolve().as_uri());win.show_all()
    windows.append(win);hub.surfaces[mode]=win
    wait(lambda:win.ready);wait(lambda:js(win,'!!document.querySelector(".window-controls button[aria-label=Maximize]")'))
    return win

try:
    area=display.get_primary_monitor().get_workarea()
    first=fixture('explorer',area.x+40,area.y+50)
    second=fixture('settings',area.x+220,area.y+160)
    wait(lambda:manager.for_surface(first) and manager.for_surface(second))
    a=manager.for_surface(first).get_xid();b=manager.for_surface(second).get_xid()
    assert a!=b and a!=first.get_window().get_xid() and b!=second.get_window().get_xid()
    original={i:tuple(manager.get(i).get_geometry()) for i in (a,b)}
    print('PASS duplicate caption titles resolve distinct native GNOME window IDs',flush=True)
    selector="document.querySelector('.window-controls button[aria-label=Maximize]')"
    for target,other,ident,other_id,event in [(first,second,a,b,"new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true})"),
                                              (second,first,b,a,"new MouseEvent('contextmenu',{bubbles:true,cancelable:true,button:2})")]:
        other.present();wait(lambda:other.is_active())
        js(target,selector+'.dispatchEvent('+event+')')
        wait(lambda:m.window and m.window.get_title()=='Snap layouts')
        assert m.origin==ident
        actual=zone_rect(m.area(manager.get(ident)),layouts()[0][1][0])
        m.layout_buttons[0][0].clicked()
        wait(lambda:tuple(manager.get(ident).get_geometry())==actual)
        assert tuple(manager.get(other_id).get_geometry())==original[other_id]
        m.restore(ident);wait(lambda:tuple(manager.get(ident).get_geometry())==original[ident])
        print('PASS',target.mode,'WebKit caption → native picker → snap only requested window → restore',flush=True)
    first.present();wait(lambda:first.is_active())
    Hub.dispatch(hub,first,{'action':'snap-hover','enter':True})
    Hub.dispatch(hub,first,{'action':'snap-hover','enter':False})
    pump(.8);assert m.window is None
    Hub.dispatch(hub,first,{'action':'snap-hover','enter':True})
    wait(lambda:m.window is not None);assert m.origin==a
    event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=Gdk.KEY_Escape
    assert m.key(m.window,event);wait(lambda:m.window is None)
    assert tuple(manager.get(a).get_geometry())==original[a]
    print('PASS delayed maximize hover, leave cancellation and Escape preserve geometry',flush=True)
    first.hide();assert manager.for_surface(first) is None
    assert not errors,errors
finally:
    if m.hover_timer:GLib.source_remove(m.hover_timer)
    m.close(False)
    for win in windows:win.destroy()
    if prior and manager.get(prior.get_xid()):manager.activate(prior)
    manager.close()
