"""Exercise only disposable windows in a private Xephyr and D-Bus session."""
import os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv:
  for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
    with tempfile.TemporaryDirectory(prefix='z11-personalization-test-') as temp:
        root=Path(temp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
        with (root/'log').open('w') as log:
            server=subprocess.Popen(['Xephyr',display,'-screen','1600x1000','-noreset','-nolisten','tcp'],stdout=log,stderr=log)
            try:
                time.sleep(.7)
                env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0',LIBGL_ALWAYS_SOFTWARE='1')
                shutil.copytree(BASE/'window-theme',root/'data/themes/Zorin11-Dark')
                subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',wm],env=env,stdout=log,stderr=log,check=True,timeout=170)
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

import wallpaper
import desktop_backgrounds
import dbus
from settings_backend import properties,set_property
from gi.repository import GdkPixbuf
desktop=None
def choose(uid,ident):
    result=[];m.backgrounds.choose(uid,ident,lambda error:result.append(error))
    until(lambda:bool(result),10);assert result==[None],result
def backdrop():
    # The bottom-left corner stays outside our disposable normal windows.
    pix=Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),20,960,1,1)
    return tuple(pix.get_pixels()[:3])
def assert_color(color):
    until(lambda:all(abs(a-b)<5 for a,b in zip(backdrop(),color)),10)
try:
    pump(2);d=m.desktops
    set_property('xfce4-desktop','/desktop-icons/style',dbus.Int32(0))
    desktop=subprocess.Popen(['xfdesktop','--disable-wm-check'],env=dict(os.environ,SESSION_MANAGER=''),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for i,title in enumerate(('Design workspace','Research workspace','Personal workspace')):
        w=Gtk.Window(title=title);windows.append(w);w.set_default_size(520,330);w.move(180+60*i,160+40*i)
        w.set_icon_name('applications-system');w.add(Gtk.Label(label=title+' — unsaved work stays open'));w.show_all()
    until(lambda:len(m.windows.windows())==3);ids=[w.get_window().get_xid() for w in windows]
    while len(d.items())>1:operation(lambda done:d.remove(len(d.items())-1,done))
    operation(d.create);operation(d.create)
    d.rename(0,'Design');d.rename(1,'Research');d.rename(2,'Personal')
    identities=[v['uid'] for v in d.items()]
    d.move(ids[1],1);d.move(ids[2],2);until(lambda:d.desktop_for(m.windows.get(ids[2]))==2)
    # Solid local fixtures make actual Xfdesktop pixels unambiguous. No remote
    # downloads, user background files, or real-display properties are touched.
    images=[];colors=[(28,78,120),(94,48,118),(28,110,78)]
    for color in colors:
        pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,1600,1000)
        pix.fill((color[0]<<24)|(color[1]<<16)|(color[2]<<8)|255)
        data=bytes(pix.save_to_bufferv('png',[],[])[1])
        images.append(wallpaper.remember(data,{'source':'local','title':'Test '+str(color)})['id'])
    wallpaper.configure('source','spotlight');wallpaper.configure('daily',True)
    wallpaper.apply(images[0]);pump(.8)
    original_props=properties('xfce4-desktop')
    choose(identities[1],images[1]);choose(identities[2],images[2]);assert_color(colors[0])
    d.switch(1);until(lambda:d.current()==1);assert_color(colors[1])
    d.switch(2);until(lambda:d.current()==2);assert_color(colors[2])
    assert wallpaper.load()['daily'] and wallpaper.load()['source']=='spotlight'
    # Route an actual shared-wallpaper update while the active desktop is
    # customized. Its pixels must not change; the shared desktop uses the new one.
    wallpaper.apply(images[1]);assert_color(colors[2])
    d.switch(0);until(lambda:d.current()==0);assert_color(colors[1])
    wallpaper.apply(images[0]);assert_color(colors[0])
    m.show_tasks();pump(1.2);view=m.task_view
    assert len(view.wallpapers)==3
    # Actual desktop-thumbnail drag, preserving each client's logical desktop.
    drag(view.desktop_buttons[2],view.desktop_buttons[0])
    until(lambda:not d.busy and [i['uid'] for i in d.items()]==[identities[2],identities[0],identities[1]],12)
    until(lambda:len(view.desktop_buttons)==3);pump(.6)
    assert [d.desktop_for(m.windows.get(x)) for x in ids]==[1,2,0]
    assert d.current()==1  # Follow the active Design desktop after it moves.
    assert view.selected==0
    # Menu keyboard path reorders the selected desktop one place to the right.
    assert view.alive()
    view.desktop_buttons[0].grab_focus();keys('Shift_L','F10')
    assert view.menu and view.alive()
    menu=view.menu;next(c for c in menu.get_children() if c.get_label()=='Move right').activate();menu.popdown()
    until(lambda:not d.busy and [i['uid'] for i in d.items()]==[identities[0],identities[2],identities[1]],12);pump(.5)
    assert [d.desktop_for(m.windows.get(x)) for x in ids]==[0,2,1]
    # Choose background uses an actual native file-picker response, preserving
    # Task View's focus while the dialog/worker is open.
    photo=Path(os.environ['ZORIN11_CONFIG_DIR'])/'picked.png'
    photo.write_bytes((wallpaper.ROOT/(images[2]+'.image')).read_bytes())
    view.choose_background(2);pump(.4)
    assert view.alive() and view.modal
    view.picture_dialog.set_filename(str(photo));pump(.2);view.picture_dialog.response(Gtk.ResponseType.OK)
    until(lambda:not view.modal and not view.choosing);pump(.6)
    assert wallpaper.load()['desktopPictures'][identities[1]]==images[2]
    # Reverting one desktop to Spotlight must keep the other's custom picture.
    view.set_background(identities[1],None);until(lambda:not view.choosing);pump(.5)
    assert identities[1] not in wallpaper.load()['desktopPictures']
    assert wallpaper.load()['desktopPictures'][identities[2]]==images[2]
    out=os.environ.get('ZORIN11_TEST_OUTPUT')
    if out:
        path=Path(out);path.mkdir(parents=True,exist_ok=True)
        pix=Gdk.pixbuf_get_from_window(m.window.get_window(),0,0,m.window.get_size().width,m.window.get_size().height)
        pix.savev(str(path/(wm_name+'-personalized-desktops.png')),'png',[],[])
    m.close(False)
    # Refused/timed-out moves leave desktop identities unchanged and send
    # surviving apps back to their original workspace without closing them.
    prior=[i['uid'] for i in d.items()];members=[d.desktop_for(m.windows.get(x)) for x in ids]
    real_wait=d.wait;result=[]
    try:
        d.wait=lambda condition,success,failure:failure('Simulated window-manager refusal.')
        d.reorder(0,2,lambda *args:result.append(args))
    finally:d.wait=real_wait
    assert result and result[0][0] and not d.busy
    until(lambda:[d.desktop_for(m.windows.get(x)) for x in ids]==members)
    assert [i['uid'] for i in d.items()]==prior
    # Reorder maximized/minimized clients as well as ordinary ones, then close
    # the middle desktop and confirm its picture does not attach to a neighbor.
    d.switch(2);until(lambda:d.current()==2)
    client=m.windows.get(ids[1]);client.maximize();until(lambda:client.is_maximized());client.minimize();until(lambda:client.is_minimized())
    operation(lambda done:d.reorder(2,0,done))
    assert client.is_maximized() and client.is_minimized()
    assert [i['uid'] for i in d.items()]==[identities[1],identities[0],identities[2]]
    operation(lambda done:d.remove(1,done));pump(.5)
    assert [i['uid'] for i in d.items()]==[identities[1],identities[2]]
    d.switch(1);until(lambda:d.current()==1);assert_color(colors[2])
    # Reconstruct the controller from persisted preferences (login/upgrade).
    m.shutdown();m=Multitasking(hub,Path(os.environ['ZORIN11_CONFIG_DIR']));d=m.desktops;pump(.6)
    assert [i['uid'] for i in d.items()]==[identities[1],identities[2]]
    assert_color(colors[2]);d.switch(0);until(lambda:d.current()==0);assert_color(colors[0])
    assert len(m.windows.windows())==3
    print('PASSED',wm_name,': actual Xfdesktop per-desktop pixels; shared Spotlight routing; stable IDs; real desktop drag; keyboard Move right; native file picker; per-desktop reset; failed-reorder recovery; minimized/maximized moves; middle-close identity; restart persistence.',flush=True)
finally:
    m.shutdown()
    for w in windows:w.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    if desktop:desktop.terminate();desktop.wait(timeout=5)
    wm.terminate()
    try:wm.wait(timeout=5)
    except subprocess.TimeoutExpired:wm.kill();wm.wait()
