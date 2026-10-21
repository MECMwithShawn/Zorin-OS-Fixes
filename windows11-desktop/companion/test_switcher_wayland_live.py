"""Opt-in Alt+Tab lifecycle checks with disposable native Wayland windows.

Run with GDK_BACKEND=x11 for the companion chooser. Physical modifier state is
controlled only inside this fixture; no global shortcut or user setting changes.
ZORIN11_TEST_RUNTIME selects an installed companion directory.
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
    colors=[(1.,0.,0.),(0.,0.,1.),(1.,1.,0.)];drawings=[];windows=[]
    for i,title in enumerate(('Alpha','Beta','Gamma')):
        win=Gtk.Window(title='Axentra switcher validation '+title);win.set_default_size(400,260)
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
from switcher import Switcher
from snap_groups import Group,SnapGroups
from windowing import Windows
import gnome_bridge
assert os.environ.get('XDG_SESSION_TYPE')=='wayland','Requires a live GNOME Wayland session'

def wait(fn,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        value=fn()
        if value:return value
        time.sleep(.02)
    raise AssertionError('Timed out')
def pump(seconds):
    start=time.monotonic();wait(lambda:time.monotonic()-start>=seconds,seconds+2)
def color(pix):
    if pix is None:return None
    offset=(pix.get_height()//2)*pix.get_rowstride()+(pix.get_width()//2)*pix.get_n_channels()
    return tuple(pix.get_pixels()[offset:offset+3])

display=Gdk.Display.get_default();manager=Windows();prior=manager.active();child=None;m=None
class Hub:
    surfaces={}
    def __init__(self):self.workers=ThreadPoolExecutor(max_workers=1);self.submitted=0;self.errors=[];self.block=False;self.queued=[]
    def work_area(self,x,y):return display.get_monitor_at_point(x,y).get_workarea()
    def background(self,task,success,failure):
        self.submitted+=1
        if self.block:self.queued.append((task,success,failure));return
        def done(result):
            try:value=result.result()
            except Exception as error:
                self.errors.append(str(error));GLib.idle_add(lambda e=error:(failure(e),False)[1]);return
            GLib.idle_add(lambda:(success(value),False)[1])
        self.workers.submit(task).add_done_callback(done)
hub=Hub()
class FixtureWindows:
    def windows(self):return [w for w in manager.windows() if w.get_pid()==child.pid]
    def get(self,ident):return next((w for w in self.windows() if w.get_xid()==ident),None)
    def active(self):
        active=manager.active()
        return active if active and self.get(active.get_xid()) else next(iter(self.windows()),None)
    def eligible(self,w):return manager.eligible(w) and w.get_pid()==child.pid
    def __getattr__(self,name):return getattr(manager,name)
held=[True]
class FixtureKeys:
    def held(self):return held[0]
    def close(self):pass

def key(value,state=0):
    event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=value;event.state=state
    return m.window.emit('key-press-event',event)
def selected():return m.switcher.items[m.switcher.selected]['key']
def select(ident):
    for _ in range(len(m.switcher.items)+1):
        if selected()==ident:return
        assert key(Gdk.KEY_Tab)
    raise AssertionError('Missing entry')
def active():
    w=manager.screen.get_active_window();return w.get_xid() if w else None

with tempfile.TemporaryFile() as log:
 try:
    child=subprocess.Popen(['/usr/bin/python3',__file__,'--clients'],stdin=subprocess.PIPE,stdout=log,stderr=log,text=True,env=dict(os.environ,GDK_BACKEND='wayland'))
    clients=FixtureWindows();wait(lambda:len(clients.windows())==3)
    ids=[next(w.get_xid() for w in clients.windows() if w.get_name().endswith(name)) for name in ('Alpha','Beta','Gamma')]
    area=display.get_primary_monitor().get_workarea()
    # Leave native clients partly exposed; Mutter can pause fully covered apps.
    for i,ident in enumerate(ids):
        rect=[area.x+8+i*420,area.y+8,400,260]
        gnome_bridge.call('window',id=ident,action='move',rect=rect)
        wait(lambda:tuple(clients.get(ident).get_geometry())==tuple(rect))
    m=Multitasking.__new__(Multitasking)
    m.hub=hub;m.windows=clients;m.window=None;m.overlay=None;m.generation=0;m.origin=None;m.hover_timer=0
    m.preview_cache={};m.groups=[]
    m.desktops=NS(current=lambda:0,on=lambda *_:True,desktop_for=lambda _:0,busy=False)
    m.snap_groups=SnapGroups.__new__(SnapGroups);m.snap_groups.m=m
    def shell(*args,**kwargs):
        win,box=Multitasking.shell(m,*args,**kwargs)
        m.saved_view=NS(alive=lambda:m.window is win,hold_focus=lambda:True)
        return win,box
    m.shell=shell;m.switcher=Switcher(m)
    css=Gtk.CssProvider();css.load_from_path(str(BASE/'multitasking.css'))
    Gtk.StyleContext.add_provider_for_screen(display.get_default_screen(),css,650)
    with patch('switcher.AltKeys',FixtureKeys):
        for ident in ids:manager.activate(clients.get(ident));wait(lambda:active()==ident)
        origin=ids[-1];m.switcher.show();wait(lambda:m.switcher.window is not None)
        first=selected();assert key(Gdk.KEY_Tab);assert selected()!=first
        assert key(Gdk.KEY_ISO_Left_Tab,Gdk.ModifierType.SHIFT_MASK);assert selected()==first
        select(('window',ids[0]));held[0]=False
        wait(lambda:m.window is None);wait(lambda:active()==ids[0])
        held[0]=True;m.switcher.show(True);assert key(Gdk.KEY_Escape)
        wait(lambda:m.window is None);wait(lambda:active()==ids[0])
        assert m.switcher.timer==0 and m.switcher.capture_timer==0 and m.switcher.keys is None
        print('PASS native Wayland forward/reverse selection, release-to-activate, Escape and timer cleanup',flush=True)
        # Group mosaics use the same native IDs as individual cards.
        m.groups=[Group([(ids[0],(0,0,400,260)),(ids[1],(400,0,400,260))])]
        m.switcher.show();wait(lambda:all(i in m.preview_cache for i in ids))
        assert any(e['key'][0]=='group' for e in m.switcher.items)
        child.stdin.write('0 0 255 0\n');child.stdin.flush()
        wait(lambda:color(m.preview_cache.get(ids[0]))==(0,255,0))
        manager.get(ids[0]).minimize();wait(lambda:clients.get(ids[0]).is_minimized())
        wait(lambda:not m.switcher.pending_capture);cached=m.preview_cache[ids[0]];pump(.5)
        assert m.preview_cache[ids[0]] is cached and ids[0] not in m.switcher.preview_targets()
        manager.get(ids[0]).unminimize(0);wait(lambda:not clients.get(ids[0]).is_minimized())
        child.stdin.write('0 255 0 255\n');child.stdin.flush()
        wait(lambda:color(m.preview_cache.get(ids[0]))==(255,0,255))
        print('PASS live native window/group previews, cached minimized preview and resumed refresh',flush=True)
        gnome_bridge.call('window',id=ids[1],action='close')
        wait(lambda:clients.get(ids[1]) is None)
        wait(lambda:all(e['key']!=('window',ids[1]) and e['key'][0]!='group' for e in m.switcher.items))
        assert ids[1] not in m.switcher.preview_targets()
        print('PASS closed native window and incomplete group leave the chooser while it stays open',flush=True)
        # Delay a worker deliberately, then close/reopen before it starts.
        hub.block=True;wait(lambda:hub.queued)
        task,done,_=hub.queued.pop();count=hub.submitted
        assert key(Gdk.KEY_Escape);assert not m.window
        m.switcher.show();pump(.4);assert hub.submitted==count
        assert task()==b'';done(b'');hub.block=False
        wait(lambda:hub.submitted>count);wait(lambda:not m.switcher.pending_capture)
        assert key(Gdk.KEY_Escape);count=hub.submitted;cache=dict(m.preview_cache);pump(.5)
        assert count==hub.submitted and cache==m.preview_cache
        assert not m.switcher.timer and not m.switcher.capture_timer and not m.switcher.keys
        assert not hub.errors,hub.errors
        print('PASS queued capture skips closed chooser; reopen keeps one in flight; closing stops capture/cache updates',flush=True)
 finally:
    held[0]=False
    if m:
        m.close(False)
        if hasattr(m,'switcher'):m.switcher.shutdown()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    if child:
        if child.poll() is None:
            child.stdin.write('quit\n');child.stdin.flush()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
        if child.returncode:log.seek(0);print(log.read().decode()[-3000:])
    if prior and manager.get(prior.get_xid()):manager.activate(manager.get(prior.get_xid()))
    manager.close()
