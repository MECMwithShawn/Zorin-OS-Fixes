"""Exercise only disposable windows in a private Xephyr and D-Bus session."""
import os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv:
  for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
    with tempfile.TemporaryDirectory(prefix='z11-motion-test-') as temp:
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
    import desktop_motion as motion
    pump(2);d=m.desktops
    set_property('xfce4-desktop','/desktop-icons/style',dbus.Int32(0))
    desktop=subprocess.Popen(['xfdesktop','--disable-wm-check'],env=dict(os.environ,SESSION_MANAGER=''),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    colors=[(28,78,120),(28,110,78),(94,48,118)];images=[]
    for color in colors:
        pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,1600,1000);pix.fill((color[0]<<24)|(color[1]<<16)|(color[2]<<8)|255)
        images.append(wallpaper.remember(bytes(pix.save_to_bufferv('png',[],[])[1]),{'source':'local','title':'Motion fixture'})['id'])
    while len(d.items())>1:operation(lambda done:d.remove(len(d.items())-1,done))
    operation(d.create);operation(d.create)
    d.switch(0);until(lambda:d.current()==0)
    wallpaper.apply(images[0]);choose(d.items()[1]['uid'],images[1]);choose(d.items()[2]['uid'],images[2]);assert_color(colors[0])
    for i,color in enumerate(((.9,.1,.1),(.95,.8,.1))):
        w=Gtk.Window(title='Motion test '+str(i));windows.append(w);w.set_default_size(420,320);w.move(180,180)
        drawing=Gtk.DrawingArea();drawing.connect('draw',lambda _,cr,c=color:(cr.set_source_rgb(*c),cr.paint(),True)[-1]);w.add(drawing);w.show_all();pump(.3)
        xid=w.get_window().get_xid()
        until(lambda:m.windows.get(xid) is not None)
        if i:d.move(xid,i);until(lambda:d.desktop_for(m.windows.get(xid))==i)
    motion.configure('desktopAnimationDuration',480);motion.configure('desktopAnimations',True);pump(.5)
    snapshots=[];samples=[];centers=[];incoming=[];opacities=[];overlay_seen=False;start=time.monotonic();d.switch(1)
    def record():
        global overlay_seen
        elapsed=time.monotonic()-start;rgb=backdrop();samples.append((elapsed,rgb));overlay_seen=overlay_seen or bool(m.backgrounds.fade.window)
        if m.backgrounds.fade.window:
            opacities.append(m.backgrounds.fade.opacity)
            if len(opacities)==7:m.backgrounds.request()  # A redundant sync must not restart the fade.
        row=Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,300,1600,1);data=bytes(row.get_pixels());channels=row.get_n_channels()
        red=[i for i in range(1600) if data[i*channels]>200 and data[i*channels+1]<70 and data[i*channels+2]<70]
        if red:centers.append((elapsed,sum(red)/len(red)))
        yellow=[i for i in range(1600) if data[i*channels]>200 and data[i*channels+1]>150 and data[i*channels+2]<70]
        if yellow:incoming.append((elapsed,sum(yellow)/len(yellow)))
        if os.environ.get('ZORIN11_TEST_OUTPUT') and len(snapshots)<4 and elapsed>len(snapshots)*.17:
            snapshots.append(Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,1600,1000))
    while time.monotonic()-start<1.7:record();pump(.012)
    assert d.current()==1;assert_color(colors[1]);assert m.backgrounds.fade.window is None
    out=os.environ.get('ZORIN11_TEST_OUTPUT')
    if out:
        path=Path(out);path.mkdir(parents=True,exist_ok=True)
        for i,pix in enumerate(snapshots):pix.savev(str(path/(wm_name+'-motion-'+str(i)+'.png')),'png',[],[])
    if wm_name=='compiz':
        assert overlay_seen,'No wallpaper fade surface'
        assert all(a>=b for a,b in zip(opacities,opacities[1:])),('Fade restarted during a redundant sync',opacities)
        intermediate=[(t,c) for t,c in samples if max(abs(a-b) for a,b in zip(c,colors[0]))>5 and max(abs(a-b) for a,b in zip(c,colors[1]))>5]
        assert len(intermediate)>=3,('No actual wallpaper crossfade',samples)
        # The outgoing window begins near the left edge, so it exits early.
        # Track the incoming app through the whole screen, including positions
        # that differ from its final geometry, rather than counting static frames.
        moved=[p for t,p in incoming if 0<t<.6 and p>420]
        assert len(moved)>=3 and max(moved)-min(moved)>100,('No native app slide',centers,incoming)
        print('Motion samples:',len(intermediate),'intermediate backdrop frames;',len(moved),'moving app frames',flush=True)
    else:assert not overlay_seen,'Xfwm fallback should not install a fake app slide'
    # Rapid direction changes and non-adjacent switching coalesce to the last
    # request, without retaining an input/focus-grabbing overlay.
    d.switch(2);pump(.06);d.switch(0);pump(.06);d.switch(2);pump(.06);d.switch(1)
    until(lambda:d.current()==1);assert_color(colors[1]);pump(1.6);assert m.backgrounds.fade.window is None
    motion.configure('desktopAnimations',False);pump(.2);d.switch(0);assert_color(colors[0]);pump(.2)
    assert m.backgrounds.fade.window is None
    assert motion.load()['enabled'] is False
    motion.configure('desktopAnimations',True)
    # Honor the native system reduced-motion preference independently of the
    # saved companion switch, and clean up on shutdown during a transition.
    settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False);pump(.4)
    assert not m.backgrounds.fade.enabled();d.switch(1);assert_color(colors[1]);assert m.backgrounds.fade.window is None
    settings.set_property('gtk-enable-animations',True);pump(.4)
    d.switch(2);pump(.15);m.shutdown();pump(.3)
    assert m.backgrounds.fade.window is None
    print('PASSED',wm_name,':',('native slide frames and wallpaper crossfade' if wm_name=='compiz' else 'instant native fallback'),'; rapid reversal/jumps; animation off; GTK reduced motion; shutdown cleanup.',flush=True)
finally:
    if not m.desktops.stopped:m.shutdown()
    for w in windows:w.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    if desktop:desktop.terminate();desktop.wait(timeout=5)
    wm.terminate()
    try:wm.wait(timeout=5)
    except subprocess.TimeoutExpired:wm.kill();wm.wait()
