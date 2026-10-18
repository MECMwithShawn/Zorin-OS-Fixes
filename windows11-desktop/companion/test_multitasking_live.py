"""Exercise only disposable windows in a private Xephyr and D-Bus session."""
import os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv:
  for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
    with tempfile.TemporaryDirectory(prefix='z11-snap-test-') as temp:
        root=Path(temp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
        with (root/'log').open('w') as log:
            server=subprocess.Popen(['Xephyr',display,'-screen','1600x1000','-noreset','-nolisten','tcp'],stdout=log,stderr=log)
            try:
                time.sleep(.7)
                env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0',LIBGL_ALWAYS_SOFTWARE='1')
                shutil.copytree(BASE/'window-theme',root/'data/themes/Zorin11-Dark')
                subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',wm],env=env,stdout=log,stderr=log,check=True,timeout=75)
            finally:
                server.terminate();server.wait();log.flush();print((root/'log').read_text()[-6500:])
  sys.exit()

import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
from concurrent.futures import ThreadPoolExecutor
from multitasking import Multitasking
from windowing import layouts,zone_rect
wm_name=sys.argv[-1]
if wm_name=='compiz':
    import effects
    subprocess.run(['/usr/bin/python3',str(BASE/'effects.py'),'--configure'],env=effects.environment(),check=True)
    wm=subprocess.Popen(['compiz','--replace','ccp'],env=effects.environment())
else:wm=subprocess.Popen(['xfwm4','--replace'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def pump(seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)
def until(fn,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if fn():return
        pump(.05)
    raise AssertionError('Timed out: '+str(fn))
def near(actual,wanted):return all(abs(a-b)<=3 for a,b in zip(actual,wanted))
def keys(*names):
    import ctypes as C
    x=C.CDLL('libX11.so.6');xt=C.CDLL('libXtst.so.6')
    x.XOpenDisplay.restype=C.c_void_p;x.XOpenDisplay.argtypes=[C.c_char_p];display=x.XOpenDisplay(None)
    x.XStringToKeysym.restype=C.c_ulong;x.XStringToKeysym.argtypes=[C.c_char_p]
    x.XKeysymToKeycode.restype=C.c_uint;x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong]
    xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
    x.XFlush.argtypes=[C.c_void_p];x.XCloseDisplay.argtypes=[C.c_void_p]
    codes=[x.XKeysymToKeycode(display,x.XStringToKeysym(n.encode())) for n in names]
    for code in codes:xt.XTestFakeKeyEvent(display,code,1,0)
    x.XFlush(display);pump(.4)
    for code in reversed(codes):xt.XTestFakeKeyEvent(display,code,0,0)
    x.XFlush(display);x.XCloseDisplay(display);pump(.3)
class Hub:
    surfaces={}
    def __init__(self):self.workers=ThreadPoolExecutor(max_workers=3)
    def work_area(self,x,y):
        area=Gdk.Display.get_default().get_monitor_at_point(x,y).get_workarea()
        return area
    def monitor_geometry(self):return self.work_area(100,100)
    def background(self,task,success,failure):
        def done(future):
            try:value=future.result()
            except Exception as error:GLib.idle_add(lambda e=error:(failure(e),False)[1]);return
            GLib.idle_add(lambda:(success(value),False)[1])
        self.workers.submit(task).add_done_callback(done)
    def open_settings(self,*_):pass
hub=Hub();m=Multitasking(hub,Path(os.environ['ZORIN11_CONFIG_DIR']))
windows=[]
try:
    pump(2)
    print('WM:',m.windows.screen.get_window_manager_name(),'composited:',Gdk.Screen.get_default().is_composited(),flush=True)
    for index in range(3):
        w=Gtk.Window(title=['Research notes','Project files','Terminal session'][index]);windows.append(w)
        w.set_default_size(560,380);w.move(100+index*80,100+index*70)
        w.set_icon_name('applications-system');box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20);box.set_border_width(30)
        title=Gtk.Label(label=w.get_title());title.set_line_wrap(True);box.pack_start(title,False,False,0)
        text=Gtk.DrawingArea()
        def draw(widget,cr):
            cr.set_source_rgb(.16,.19,.23);cr.paint();cr.set_source_rgb(.38,.81,1);cr.rectangle(20,20,90,5);cr.fill();return True
        text.connect('draw',draw)
        box.pack_start(text,True,True,0);w.add(box);w.show_all()
    until(lambda:len(m.windows.windows())==3);pump(.3)
    for widget in (windows[2],windows[0],windows[1]):
        m.windows.activate(m.windows.get(widget.get_window().get_xid()));pump(.2)
    keys('Alt_L','Tab');until(lambda:m.windows.screen.get_active_window().get_xid()==windows[0].get_window().get_xid())
    for widget in (windows[2],windows[0],windows[1]):
        m.windows.activate(m.windows.get(widget.get_window().get_xid()));pump(.2)
    keys('Alt_L','Shift_L','Tab');until(lambda:m.windows.screen.get_active_window().get_xid()==windows[2].get_window().get_xid())
    xid=windows[0].get_window().get_xid();client=m.windows.get(xid);original=tuple(client.get_geometry())
    area=m.area();m.preferences['assist']=False
    for name,zones in layouts():
        for zone in zones:
            expected=zone_rect(area,zone);m.windows.place(xid,expected)
            try:until(lambda:near(m.windows.get(xid).get_geometry(),expected),3)
            except AssertionError:raise AssertionError((wm_name,name,expected,tuple(m.windows.get(xid).get_geometry())))
    m.windows.restore(xid);until(lambda:near(m.windows.get(xid).get_geometry(),original))
    client.maximize();until(lambda:m.windows.get(xid).is_maximized())
    m.windows.place(xid,zone_rect(area,layouts()[0][1][0]));until(lambda:not m.windows.get(xid).is_maximized())
    m.windows.restore(xid);until(lambda:m.windows.get(xid).is_maximized())
    client.unmaximize();pump(.3)
    # Real composite thumbnail, not a desktop crop of whatever covers it.
    m.show_tasks();pump(.6)
    preview=subprocess.run(['/usr/bin/python3',str(BASE/'window_preview.py'),str(xid)],capture_output=True,timeout=3).stdout
    assert preview.startswith(b'\x89PNG'),('No real preview',wm_name)
    m.close(False)
    windows[0].set_size_request(900,200);pump(.2);m.show_snap(xid);pump(.1)
    assert not m.layout_buttons[0][0].get_sensitive()
    assert m.layout_buttons[1][0].get_sensitive()
    m.close(False);windows[0].set_size_request(-1,-1);pump(.2)
    m.show_snap(xid);pump(.3)
    assert len(m.layout_buttons)==6
    out=os.environ.get('ZORIN11_TEST_OUTPUT')
    def capture(name):
        if not out:return
        path=Path(out);path.mkdir(parents=True,exist_ok=True);w=m.window
        pix=Gdk.pixbuf_get_from_window(w.get_window(),0,0,w.get_size().width,w.get_size().height)
        pix.savev(str(path/(wm_name+'-'+name+'.png')),'png',[],[])
    capture('snap-layouts')
    m.preferences['assist']=True;m.layout_buttons[0][0].clicked()
    until(lambda:m.window and m.window.get_title()=='Snap assist');pump(.3)
    assert len(m.flow.get_children())==2
    m.flow.get_children()[0].get_child().clicked()
    until(lambda:len(m.groups)==1);assert len(m.groups[0])==2
    m.show_tasks();pump(1.5)
    assert len(m.flow.get_children())==3
    capture('task-view')
    entry=next(c for c in m.window.get_child().get_children() if isinstance(c,Gtk.SearchEntry))
    entry.set_text('Project files');entry.emit('search-changed');pump(.2)
    visible=[c for c in m.flow.get_children() if c.get_child_visible()];assert len(visible)==1
    chosen=windows[1].get_window().get_xid();visible[0].get_child().clicked()
    until(lambda:m.windows.screen.get_active_window().get_xid()==chosen)
    windows[2].iconify();until(lambda:m.windows.get(windows[2].get_window().get_xid()).is_minimized())
    m.windows.activate(m.windows.get(windows[2].get_window().get_xid()));until(lambda:not m.windows.get(windows[2].get_window().get_xid()).is_minimized())
    # Keep a card/reference alive across closing its app, then force GC before
    # the WM exits. libwnck 43 crashes here if callbacks retain raw WnckWindow.
    import gc
    m.show_tasks();pump(.3)
    doomed=windows[2].get_window().get_xid();retained=m.windows.get(doomed)
    windows[2].destroy();pump(.2);m.close(False);del retained;gc.collect()
    assert m.windows.get(doomed) is None
    try:m.windows.place(doomed,(0,0,500,300));raise AssertionError('Closed window was accepted')
    except ValueError:pass
    print('PASSED',wm_name,': Alt+Tab/reverse/release; all zones; minimum-size disabling; outer frame geometry; restore/maximized restore; real thumbnails; Snap Assist/group; Task View search/activation; minimized and closed windows.',flush=True)
finally:
    m.shutdown()
    for w in windows:w.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    wm.terminate();wm.wait(timeout=10)
