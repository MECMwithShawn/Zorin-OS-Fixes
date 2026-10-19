"""Alt+Tab keyboard, group restore and lifecycle checks in isolated X sessions."""
import os, subprocess, sys, tempfile, time, shutil
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv and '--next' not in sys.argv and '--previous' not in sys.argv:
    for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
        with tempfile.TemporaryDirectory(prefix='z11-switcher-') as temp:
            root=Path(temp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
            with (root/'log').open('w') as log:
                server=subprocess.Popen(['Xephyr',display,'-screen',os.environ.get('ZORIN11_TEST_SCREEN','1600x1000'),'-noreset','-nolisten','tcp'],stdout=log,stderr=log)
                try:
                    time.sleep(.7)
                    env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0',LIBGL_ALWAYS_SOFTWARE='1')
                    shutil.copytree(BASE/'window-theme',root/'data/themes/Zorin11-Dark')
                    subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',wm],env=env,stdout=log,stderr=log,check=True,timeout=100)
                finally:
                    server.terminate();server.wait();log.flush();print((root/'log').read_text()[-10000:])
    sys.exit()

import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,Gio,GLib
# Xfce invokes a separate process just as it does the installed app.py. Relay
# that command to this session's real Multitasking object over GApplication.
class ShortcutApp(Gio.Application):
    def __init__(self):super().__init__(application_id='local.zorin11.SwitcherTest',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    def do_command_line(self,command):
        m.switcher.show('--previous' in command.get_arguments());return 0
app=ShortcutApp()
if '--next' in sys.argv or '--previous' in sys.argv:sys.exit(app.run(sys.argv))
app.register(None);app.hold()

import ctypes as C
import dbus
from concurrent.futures import ThreadPoolExecutor
from multitasking import Multitasking
from windowing import layouts,zone_rect
import effects
xf=dbus.Interface(dbus.SessionBus().get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
for binding,arg in [('<Alt>Tab','--switch-next'),('<Alt><Shift>Tab','--switch-previous')]:
    xf.SetProperty('xfce4-keyboard-shortcuts','/xfwm4/custom/'+binding,dbus.String(''))
    xf.SetProperty('xfce4-keyboard-shortcuts','/commands/custom/'+binding,dbus.String(f'/usr/bin/python3 "{BASE}/app.py" {arg}'))
xf.SetProperty('xfce4-keyboard-shortcuts','/xfwm4/custom/override',dbus.Boolean(True))
xf.SetProperty('xfce4-keyboard-shortcuts','/commands/custom/override',dbus.Boolean(True))
wm_name=sys.argv[-1]
if wm_name=='compiz':
    subprocess.run(['/usr/bin/python3',str(BASE/'effects.py'),'--configure'],env=effects.environment(),check=True)
    wm=subprocess.Popen(['compiz','--replace','ccp'],env=effects.environment())
else:wm=subprocess.Popen(['xfwm4','--replace'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
for binding,arg in [('<Alt>Tab','--next'),('<Alt><Shift>Tab','--previous')]:
    command_binding=binding.replace('Tab','ISO_Left_Tab') if 'Shift' in binding else binding
    if command_binding!=binding:xf.ResetProperty('xfce4-keyboard-shortcuts','/commands/custom/'+binding,False)
    xf.SetProperty('xfce4-keyboard-shortcuts','/commands/custom/'+command_binding,dbus.String(f'/usr/bin/python3 "{Path(__file__).resolve()}" {arg}'))
daemon=subprocess.Popen(['xfsettingsd','--replace','--no-daemon'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def pump(seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.004)
def until(fn,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if fn():return
        pump(.04)
    raise AssertionError('Timed out: '+str(fn))
def near(actual,wanted):return all(abs(a-b)<=4 for a,b in zip(actual,wanted))
x=C.CDLL('libX11.so.6');xt=C.CDLL('libXtst.so.6')
x.XOpenDisplay.restype=C.c_void_p;x.XOpenDisplay.argtypes=[C.c_char_p];display=x.XOpenDisplay(None)
x.XStringToKeysym.restype=C.c_ulong;x.XStringToKeysym.argtypes=[C.c_char_p]
x.XKeysymToKeycode.restype=C.c_uint;x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong]
xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong];x.XFlush.argtypes=[C.c_void_p]
def key(name,down):
    xt.XTestFakeKeyEvent(display,x.XKeysymToKeycode(display,x.XStringToKeysym(name.encode())),down,0);x.XFlush(display)
def tap(name):key(name,1);pump(.045);key(name,0);pump(.06)
def begin(reverse=False):
    key('Alt_L',1)
    if reverse:key('Shift_L',1)
    tap('Tab');until(lambda:m.switcher.window and m.switcher.grabbed)
    if reverse:key('Shift_L',0)
def release():key('Alt_L',0);until(lambda:not m.switcher.window);pump(.25)
def selected():return m.switcher.items[m.switcher.selected]['key']
def select(key_id):
    for _ in range(len(m.switcher.items)+1):
        if selected()==key_id:return
        tap('Tab')
    raise AssertionError(('Missing selection',key_id))
def active():
    w=m.windows.screen.get_active_window();return w.get_xid() if w else 0
class Hub:
    surfaces={}
    def __init__(self):self.workers=ThreadPoolExecutor(max_workers=3)
    def work_area(self,x,y):return Gdk.Display.get_default().get_monitor_at_point(x,y).get_workarea()
    def monitor_geometry(self):return self.work_area(100,100)
    def background(self,task,success,failure):
        def done(future):
            try:value=future.result()
            except Exception as error:GLib.idle_add(lambda e=error:(failure(e),False)[1]);return
            GLib.idle_add(lambda:(success(value),False)[1])
        self.workers.submit(task).add_done_callback(done)
hub=Hub();m=Multitasking(hub,Path(os.environ['ZORIN11_CONFIG_DIR']));windows=[]
try:
    pump(2)
    for i in range(3):
        w=Gtk.Window(title=['Research notes','Project files','Terminal session'][i]);windows.append(w)
        w.set_default_size(560,380);w.move(100+i*80,100+i*70);w.set_icon_name('applications-system')
        drawing=Gtk.DrawingArea();w.add(drawing)
        drawing.connect('draw',lambda widget,cr,i=i:(cr.set_source_rgb(*[(.14,.42,.64),(.30,.53,.24),(.51,.28,.54)][i]),cr.paint(),False)[-1]);w.show_all()
    until(lambda:len(m.windows.windows())==3);ids=[w.get_window().get_xid() for w in windows];pump(.5)
    for xid in (ids[2],ids[0],ids[1]):m.windows.activate(m.windows.get(xid));pump(.15)
    begin();assert selected()==('window',ids[0]),selected();release();until(lambda:active()==ids[0])
    for xid in (ids[2],ids[0],ids[1]):m.windows.activate(m.windows.get(xid));pump(.15)
    begin(True);assert selected()==('window',ids[2]);tap('Escape');key('Alt_L',0);until(lambda:not m.switcher.window);until(lambda:active()==ids[1])
    # A rapid press/release still selects the previous window without a popup.
    key('Alt_L',1);key('Tab',1);key('Tab',0);key('Alt_L',0)
    until(lambda:active()==ids[0]);assert not m.switcher.window
    if wm_name=='compiz':
        previous=active();key('Control_L',1);key('Alt_L',1);tap('Tab');pump(.2)
        assert not m.switcher.window
        key('Alt_L',0);key('Control_L',0);until(lambda:active()!=previous)
    print('PASS native Xfce dispatch, forward/reverse, release, cancel, rapid tap and Compiz fallback',flush=True)
    placements=[(xid,zone_rect(m.area(),zone)) for xid,zone in zip(ids[:2],layouts()[0][1])]
    for xid,rect in placements:m.windows.place(xid,rect)
    pump(.7);placements=[(xid,tuple(m.windows.get(xid).get_geometry())) for xid,_ in placements]
    m.remember_group(placements);token=m.groups[0].token
    # Compiz/NVIDIA can emit a Wnck close while remapping a live resource.
    native=next(w for w in m.windows.screen.get_windows() if w.get_xid()==ids[0])
    m.windows.screen.emit('window-closed',native);del native;pump(.2)
    assert m.groups and m.groups[0].token==token
    m.windows.activate(m.windows.get(ids[2]));pump(.2);begin();select(('group',token))
    until(lambda:all(xid in m.preview_cache for xid in ids[:2]))
    out=os.environ.get('ZORIN11_TEST_SCREENSHOTS')
    if out:
        Path(out).mkdir(parents=True,exist_ok=True)
        pix=Gdk.pixbuf_get_from_window(m.switcher.window.get_window(),0,0,m.switcher.window.get_allocated_width(),m.switcher.window.get_allocated_height())
        pix.savev(str(Path(out)/(wm_name+'-alt-tab-groups.png')),'png',[],[])
    tap('Escape');key('Alt_L',0);pump(.2)
    for xid in ids[:2]:m.windows.place(xid,(200,160,600,400))
    pump(.6)
    for xid in ids[:2]:m.windows.get(xid).minimize()
    until(lambda:all(m.windows.get(xid).is_minimized() for xid in ids[:2]))
    m.windows.activate(m.windows.get(ids[2]));pump(.2);begin();select(('group',token));release()
    until(lambda:all(not m.windows.get(xid).is_minimized() and near(m.windows.get(xid).get_geometry(),rect) for xid,rect in placements))
    # Group MRU: switching to the unrelated app then quick Alt+Tab returns the
    # whole group, not just one of its individual members.
    m.windows.activate(m.windows.get(ids[2]));pump(.3);begin();assert selected()==('group',token),selected();release()
    until(lambda:active() in ids[:2]);pump(.4)
    print('PASS false Wnck close retained, mosaic capture, minimized/moved group restore, combined MRU',flush=True)
    # Losing the lifetime watcher drops tokens safely and can recover.
    m.snap_groups.watch.process.kill();until(lambda:not m.groups)
    m.remember_group(placements);token=m.groups[0].token;pump(.2)
    assert m.snap_groups.watch.process.poll() is None
    # A closed member invalidates the group while the chooser is on screen.
    begin();select(('group',token));windows[1].destroy();until(lambda:all(e['key']!=('group',token) for e in m.switcher.items))
    assert all(e['key']!=('window',ids[1]) for e in m.switcher.items)
    tap('Escape');key('Alt_L',0);pump(.2)
    # Ending the view from another command must release the grab immediately.
    begin();m.close(False);key('Alt_L',0);pump(.2)
    begin();tap('Escape');key('Alt_L',0);pump(.2)
    # Many entries stay keyboard reachable and selected cards scroll into view.
    for i in range(12):
        w=Gtk.Window(title=f'Extra window {i}');w.set_default_size(320,200);w.show_all();windows.append(w)
    pump(.7);begin()
    for _ in range(len(m.switcher.items)+2):tap('Tab')
    assert m.switcher.window
    tap('Escape');key('Alt_L',0);pump(.2)
    begin()
    for _ in range(len(m.switcher.items)):
        if m.switcher.selected==len(m.switcher.items)-1:break
        tap('Tab')
    pump(.3)
    bounds=m.switcher.cards[-1].get_parent().get_allocation();adj=m.switcher.scroll.get_vadjustment()
    assert bounds.y>=adj.get_value()-2 and bounds.y+bounds.height<=adj.get_value()+adj.get_page_size()+2,(bounds.y,bounds.height,adj.get_value(),adj.get_page_size())
    tap('Escape');key('Alt_L',0);pump(.2)
    # Another client's grab must time out cleanly without a stranded chooser.
    x.XDefaultRootWindow.argtypes=[C.c_void_p];x.XDefaultRootWindow.restype=C.c_ulong
    x.XGrabKeyboard.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_int,C.c_ulong]
    x.XUngrabKeyboard.argtypes=[C.c_void_p,C.c_ulong]
    key('Alt_L',1);pump(.05)
    assert x.XGrabKeyboard(display,x.XDefaultRootWindow(display),0,1,1,0)==0
    m.switcher.show();until(lambda:not m.switcher.window,2)
    assert not m.switcher.keys and not m.switcher.timer and not m.switcher.capture_timer
    x.XUngrabKeyboard(display,0);key('Alt_L',0);pump(.2)
    begin();tap('Escape');key('Alt_L',0);pump(.2)
    print('PASS closed-member invalidation, cleanup/reopen, scrolling to final card, conflicting keyboard grab',flush=True)
finally:
    for name in ('Alt_L','Alt_R','Shift_L','Control_L','Tab','Escape'):key(name,0)
    m.shutdown()
    for w in windows:w.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    daemon.terminate();wm.terminate();pump(.2)
