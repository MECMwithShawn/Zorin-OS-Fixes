"""Exercise only disposable windows in a private Xephyr and D-Bus session."""
import os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv:
  for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
    with tempfile.TemporaryDirectory(prefix='z11-desktops-test-') as temp:
        root=Path(temp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
        with (root/'log').open('w') as log:
            server=subprocess.Popen(['Xephyr',display,'-screen','1600x1000','-noreset','-nolisten','tcp'],stdout=log,stderr=log)
            try:
                time.sleep(.7)
                env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0',LIBGL_ALWAYS_SOFTWARE='1')
                shutil.copytree(BASE/'window-theme',root/'data/themes/Zorin11-Dark')
                subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',wm],env=env,stdout=log,stderr=log,check=True,timeout=130)
            finally:
                server.terminate();server.wait();log.flush();print((root/'log').read_text()[-10000:])
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
def operation(fn):
    result=[];fn(lambda *args:result.append(args));until(lambda:bool(result),12)
    assert not result[0][0],result
    return result[0][1]
def visible():return [c for c in m.flow.get_children() if c.get_child_visible()]
def drag(source,target):
    import ctypes as C
    x=C.CDLL('libX11.so.6');xt=C.CDLL('libXtst.so.6')
    x.XOpenDisplay.restype=C.c_void_p;x.XOpenDisplay.argtypes=[C.c_char_p];display=x.XOpenDisplay(None)
    x.XFlush.argtypes=[C.c_void_p];x.XCloseDisplay.argtypes=[C.c_void_p]
    xt.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
    xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
    def point(widget):
        a=widget.get_allocation();px,py=widget.translate_coordinates(m.window,a.width//2,a.height//2)
        ox,oy=m.window.get_window().get_origin()[-2:];return px+ox,py+oy
    start,end=point(source),point(target)
    def motion(p):xt.XTestFakeMotionEvent(display,-1,*p,0);x.XFlush(display)
    motion(start);pump(.2);xt.XTestFakeButtonEvent(display,1,1,0);x.XFlush(display);pump(.2)
    for i in range(1,21):motion(tuple(round(a+(b-a)*i/20) for a,b in zip(start,end)));pump(.035)
    pump(.3);xt.XTestFakeButtonEvent(display,1,0,0);x.XFlush(display);pump(.4);x.XCloseDisplay(display)
try:
    pump(2)
    d=m.desktops
    for i,title in enumerate(('Research notes','Project files','Terminal session')):
        w=Gtk.Window(title=title);windows.append(w);w.set_default_size(550,340);w.move(160+80*i,140+60*i)
        w.set_icon_name('applications-system');box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20);box.set_border_width(30)
        box.pack_start(Gtk.Label(label=title),False,False,0)
        entry=Gtk.Entry();entry.set_text('Unsaved work stays open on every move');box.pack_start(entry,True,True,0)
        w.add(box);w.show_all()
    until(lambda:len(m.windows.windows())==3)
    ids=[w.get_window().get_xid() for w in windows]
    # Start the isolated session with one desktop, as on the user's machine.
    while len(d.items())>1:operation(lambda done:d.remove(len(d.items())-1,done))
    first=operation(d.create);second=operation(d.create);assert(first,second)==(1,2)
    d.rename(0,'Everyday');d.rename(1,'Work');d.rename(2,'Research')
    import json
    assert json.loads((m.config/'multitasking.json').read_text())['desktop_names']['compiz' if d.compiz else 'xfwm4']==['Everyday','Work','Research']
    original=tuple(m.windows.get(ids[0]).get_geometry())
    d.move(ids[1],1);d.move(ids[2],2)
    until(lambda:d.desktop_for(m.windows.get(ids[1]))==1 and d.desktop_for(m.windows.get(ids[2]))==2)
    m.show_tasks();pump(1)
    assert len(visible())==1 and not m.task_view.empty.get_visible()
    assert m.task_view.selected==0 and len(m.task_view.desktop_buttons)==3
    # Actual X11 pointer drag: card -> desktop thumbnail, no backend shortcut.
    drag(visible()[0].get_child(),m.task_view.desktop_buttons[1])
    until(lambda:d.desktop_for(m.windows.get(ids[0]))==1)
    assert m.task_view.alive()
    view=m.task_view;view.selected=1;view.filter();pump(.3)
    assert len(visible())==2
    # Keyboard context menu stays open and Move to leaves focus in Task View.
    card=next(c.get_child() for c in visible() if c.xid==ids[0]);card.grab_focus();keys('Shift_L','F10')
    assert view.menu is not None and view.alive()
    menu=view.menu;item=next(c for c in menu.get_children() if c.get_label()=='Everyday')
    item.activate();menu.popdown();until(lambda:d.desktop_for(m.windows.get(ids[0]))==0);pump(.4)
    assert view.alive()
    view.search.set_text('Terminal');view.search.emit('search-changed');pump(.3)
    assert len(visible())==1 and visible()[0].xid==ids[2]
    view.search.set_text('');view.search.emit('search-changed');view.selected=0;view.filter()
    view.new_button.clicked();until(lambda:len(d.items())==4 and not d.busy)
    assert d.current()==0 and m.task_view.alive()
    # Close the newly created empty desktop through the UI.
    view.remove(3);until(lambda:len(d.items())==3 and not d.busy);pump(.5)
    out=os.environ.get('ZORIN11_TEST_OUTPUT')
    if out:
        path=Path(out);path.mkdir(parents=True,exist_ok=True)
        pix=Gdk.pixbuf_get_from_window(m.window.get_window(),0,0,m.window.get_size().width,m.window.get_size().height)
        pix.savev(str(path/(wm_name+'-desktops.png')),'png',[],[])
    # Click the Research preview, activate only that desktop, then return.
    view.desktop_buttons[2].clicked();until(lambda:d.current()==2);assert m.window is None
    m.desktop_command('left');until(lambda:d.current()==1)
    m.desktop_command('right');until(lambda:d.current()==2)
    m.desktop_command('new');until(lambda:len(d.items())==4 and d.current()==3)
    m.desktop_command('close');until(lambda:len(d.items())==3 and d.current()==2 and not d.busy);pump(.2)
    # Preserve maximized+minimized state and move survivors when closing the
    # middle desktop, rather than accidentally deleting the last desktop.
    d.switch(1);until(lambda:d.current()==1)
    m.windows.get(ids[1]).maximize();until(lambda:m.windows.get(ids[1]).is_maximized())
    m.windows.get(ids[1]).minimize();until(lambda:m.windows.get(ids[1]).is_minimized())
    operation(lambda done:d.remove(1,done))
    assert [x['name'] for x in d.items()]==['Everyday','Research']
    assert d.current()==0 and d.desktop_for(m.windows.get(ids[1]))==0 and d.desktop_for(m.windows.get(ids[2]))==1
    assert m.windows.get(ids[1]).is_minimized() and m.windows.get(ids[1]).is_maximized()
    assert near(m.windows.get(ids[0]).get_geometry(),original)
    assert len(m.windows.windows())==3
    # Destruction during open Task View must not retain borrowed Wnck objects.
    m.show_tasks();pump(.3);windows[2].destroy();pump(.6)
    operation(lambda done:d.remove(1,done));pump(.6)
    import gc
    m.close(False);gc.collect();assert len(m.windows.windows())==2
    m.desktop_command('close');pump(.2);assert len(d.items())==1
    print('PASSED',wm_name,': create/name/persist/switch; per-desktop cards and global search; real pointer drag; keyboard Move to menu; New desktop/Close UI; shortcut dispatcher; middle desktop migration; maximized/minimized state; geometry; closed-window/removed-desktop GC; last desktop guard.',flush=True)
finally:
    m.shutdown()
    for w in windows:w.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    wm.terminate();wm.wait(timeout=10)
