"""Opt-in live Wayland previews; only disposable native windows are captured.

Run GDK_BACKEND=x11 /usr/bin/python3 test_card_previews_live.py. The companion
chooser uses XWayland positioning while its child clients use native Wayland.
ZORIN11_TEST_RUNTIME can select the installed companion runtime.
"""
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this GUI fixture directly.')
import os,sys,time,subprocess,tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib

if '--clients' in sys.argv:
    colors=[(1.,0.,0.),(0.,0.,1.)];drawings=[];windows=[]
    for i,title in enumerate(('Alpha','Beta')):
        win=Gtk.Window(title='Axentra preview validation '+title);win.set_default_size(640,420)
        drawing=Gtk.DrawingArea()
        def draw(_,cr,index=i):cr.set_source_rgb(*colors[index]);cr.paint();return False
        drawing.connect('draw',draw);win.add(drawing);win.show_all();windows.append(win);drawings.append(drawing)
    def command(*_):
        line=sys.stdin.readline().strip()
        if not line or line=='quit':Gtk.main_quit();return False
        index,r,g,b=map(int,line.split());colors[index]=(r/255,g/255,b/255);drawings[index].queue_draw();return True
    GLib.io_add_watch(sys.stdin,GLib.IO_IN|GLib.IO_HUP,command)
    Gtk.main();raise SystemExit

BASE=Path(os.environ.get('ZORIN11_TEST_RUNTIME',Path(__file__).resolve().parent))
sys.path.insert(0,str(BASE))
from multitasking import Multitasking
from taskview import TaskView
from windowing import Windows
import gnome_bridge
assert os.environ.get('XDG_SESSION_TYPE')=='wayland','Requires the running GNOME Wayland session'

def wait(fn,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        value=fn()
        if value:return value
        time.sleep(.02)
    
    if globals().get('m'):
        print('DEBUG panel',m.window.get_title() if m.window else None,'capture pending',m.card_previews.pending,'timer',m.card_previews.timer,'cache',{k:color(v) for k,v in m.preview_cache.items()},'targets',[c.xid for c in m.card_previews.targets()],flush=True)
    raise AssertionError('Timed out')
def pump(seconds):
    start=time.monotonic();wait(lambda:time.monotonic()-start>=seconds,seconds+2)
def color(pix):
    if pix is None:return None
    offset=(pix.get_height()//2)*pix.get_rowstride()+(pix.get_width()//2)*pix.get_n_channels()
    return tuple(pix.get_pixels()[offset:offset+3])

manager=Windows();prior=manager.active();display=Gdk.Display.get_default();child=None;m=None
class Hub:
    surfaces={}
    def __init__(self):self.workers=ThreadPoolExecutor(max_workers=1);self.submitted=0;self.errors=[]
    def work_area(self,x,y):return display.get_monitor_at_point(x,y).get_workarea()
    def background(self,task,success,failure=None):
        self.submitted+=1;future=self.workers.submit(task)
        def done(result):
            try:
                value=result.result();GLib.idle_add(lambda:(success(value),False)[1])
            except Exception as error:
                self.errors.append(str(error))
                if failure:GLib.idle_add(lambda message=str(error):(failure(message),False)[1])
        future.add_done_callback(done)
hub=Hub()
class FixtureWindows:
    def windows(self):return [w for w in manager.windows() if w.get_pid()==child.pid]
    def get(self,ident):return next((w for w in self.windows() if w.get_xid()==ident),None)
    def active(self):return next(iter(self.windows()),None)
    def __getattr__(self,name):return getattr(manager,name)

with tempfile.TemporaryFile() as log:
 try:
    child=subprocess.Popen(['/usr/bin/python3',__file__,'--clients'],stdin=subprocess.PIPE,stdout=log,stderr=log,text=True,env=dict(os.environ,GDK_BACKEND='wayland'))
    clients=FixtureWindows();wait(lambda:len(clients.windows())==2)
    alpha=next(w.get_xid() for w in clients.windows() if w.get_name().endswith('Alpha'))
    beta=next(w.get_xid() for w in clients.windows() if w.get_name().endswith('Beta'))
    # Keep a small part of each native client visible outside the centered
    # chooser. Mutter may stop frame callbacks for fully occluded clients.
    work=display.get_primary_monitor().get_workarea()
    for ident,x in ((alpha,work.x+8),(beta,work.x+work.width-408)):
        rect=[x,work.y+8,400,260]
        gnome_bridge.call('window',id=ident,action='move',rect=rect)
        wait(lambda:tuple(clients.get(ident).get_geometry())==tuple(rect))
    def paint(index,r,g,b):child.stdin.write(f'{index} {r} {g} {b}\n');child.stdin.flush()
    m=Multitasking.__new__(Multitasking)
    m.hub=hub;m.windows=clients;m.window=None;m.overlay=None;m.generation=0;m.origin=None;m.hover_timer=0
    m.preferences={'assist':True};m.preview_cache={};m.groups=[]
    # Keep only these disposable test panels open if the real user changes
    # focus during validation. Production focus-loss dismissal is unchanged.
    def shell(*args,**kwargs):
        win,box=Multitasking.shell(m,*args,**kwargs)
        m.saved_view=NS(alive=lambda:m.window is win,hold_focus=lambda:True)
        return win,box
    m.shell=shell
    m.snap_groups=NS(prune=lambda:None,remember=lambda *_:None,forget=lambda *_:None)
    desktop_name=['Validation'];renames=[]
    def rename(index,name):desktop_name[0]=name;renames.append(name)
    m.desktops=NS(rename=rename,current=lambda:0,items=lambda:[dict(id=0,uid='preview-fixture',name=desktop_name[0],current=True)],
                  desktop_for=lambda _:0,on=lambda *_:True,busy=False,compiz=False,shared=lambda _:False,
                  dimensions=lambda:(manager.screen.get_width(),manager.screen.get_height(),1,1))
    css=Gtk.CssProvider();css.load_from_path(str(BASE/'multitasking.css'))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,650)
    with patch.object(TaskView,'load_wallpapers',lambda _:None):
        m.show_tasks();wait(lambda:color(m.preview_cache.get(alpha))==(255,0,0))
        flow=m.flow;view=m.task_view
        assert view.search.get_accessible().get_name()=='Search windows across your desktops'
        def key(value,state=0):
            event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=value;event.state=state
            return m.window.emit('key-press-event',event)
        entry=view.rename_entries[0][0];entry.grab_focus();entry.set_text('Do not save')
        assert key(Gdk.KEY_Escape)
        assert view.alive() and entry.get_text()=='Validation' and not renames
        assert m.window.get_focus() is view.search
        entry.grab_focus();entry.set_text('Work');entry.emit('activate')
        assert renames==['Work'] and desktop_name[0]=='Work'
        # The fake workspace backend keeps all real desktop names unchanged.
        wait(lambda:view.revision==view.fingerprint())
        flow=m.flow
        view.search.set_text('Beta');view.desktop_buttons[0].grab_focus()
        assert key(Gdk.KEY_f,Gdk.ModifierType.CONTROL_MASK)
        assert m.window.get_focus() is view.search and view.search.get_selection_bounds()==(0,4)
        assert key(Gdk.KEY_Escape);assert not view.search.get_text() and view.alive()
        print('PASS native GTK Escape cancels desktop draft, Enter saves, Ctrl+F selects search and Escape clears it',flush=True)
        paint(0,0,255,0)
        wait(lambda:color(m.preview_cache.get(alpha))==(0,255,0))
        assert m.flow is flow,'Content update must not rebuild the chooser'
        image=next(c.preview_image for c in m.flow.get_children() if c.xid==alpha)
        assert color(image.get_pixbuf())==(0,255,0)
        assert color(view.pixbufs[alpha])==(0,255,0)
        print('PASS native Wayland content changes refresh Task View card and workspace preview without rebuilding',flush=True)
        view.search.set_text('Beta');wait(lambda:all(c.xid!=alpha for c in m.card_previews.targets()))
        paint(0,0,0,255);pump(1.3)
        assert color(m.preview_cache[alpha])==(0,255,0),'Filtered card was recaptured'
        view.search.set_text('');wait(lambda:color(m.preview_cache.get(alpha))==(0,0,255))
        print('PASS search filtering pauses hidden previews; clearing search resumes capture',flush=True)
        clients.get(alpha).minimize()
        wait(lambda:clients.get(alpha).is_minimized());wait(lambda:all(c.xid!=alpha for c in m.card_previews.targets()))
        paint(0,255,255,0);pump(1.3)
        assert color(m.preview_cache[alpha])==(0,0,255)
        assert m.task_view.alive()
        print('PASS minimized windows retain cached previews without new capture',flush=True)
        # Force a rebuild while a capture is pending; the replacement panel
        # must survive completion of the old generation's asynchronous job.
        if m.card_previews.pending:wait(lambda:not m.card_previews.pending)
        m.card_previews.tick();assert m.card_previews.pending
        view.render();wait(lambda:not m.card_previews.pending)
        paint(1,255,0,255);wait(lambda:color(m.preview_cache.get(beta))==(255,0,255))
        print('PASS rebuilding Task View during capture rejects obsolete results and resumes live previews',flush=True)
        assert key(Gdk.KEY_Escape);assert m.window is None
        count=hub.submitted;cache=dict(m.preview_cache)
        pump(1.2)
        assert m.card_previews.timer==0 and m.card_previews.flow is None
        assert hub.submitted==count and cache==m.preview_cache
        print('PASS closing Task View stops new captures and late cache updates',flush=True)
    area=hub.work_area(0,0);bounds=(area.x,area.y,area.width,area.height)
    m.assist([(alpha,bounds)],[bounds],bounds)
    wait(lambda:m.window and m.window.get_title()=='Snap assist')
    paint(1,0,255,255);wait(lambda:color(m.preview_cache.get(beta))==(0,255,255))
    card=next(c for c in m.flow.get_children() if c.xid==beta)
    assert color(card.preview_image.get_pixbuf())==(0,255,255)
    print('PASS Snap Assist also refreshes live native Wayland previews',flush=True)
    m.close(False);count=hub.submitted;pump(.7);assert hub.submitted==count
    assert not hub.errors,hub.errors
 finally:
    if m:m.close(False)
    if child:
        child.terminate();child.wait(timeout=5)
    hub.workers.shutdown(wait=True,cancel_futures=True)
    if prior and manager.get(prior.get_xid()):manager.activate(prior)
    manager.close()
