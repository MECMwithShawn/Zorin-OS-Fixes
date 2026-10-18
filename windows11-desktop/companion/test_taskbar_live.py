"""Disposable native panel tests: private display, bus, config and application windows."""
import os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
if __name__!='__main__':
 import unittest
 raise unittest.SkipTest('Run this isolated panel integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv:
 import taskbar_build
 MODULE=taskbar_build.build()
 for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
  with tempfile.TemporaryDirectory(prefix='z11-taskbar-') as tmp:
   root=Path(tmp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
   share=root/'local/share';plugins=share/'xfce4/panel/plugins';plugins.mkdir(parents=True)
   libs=root/'local/lib/x86_64-linux-gnu/xfce4/panel/plugins';libs.mkdir(parents=True)
   shutil.copy2(MODULE,libs/'libdocklike.so');shutil.copy2('/usr/share/xfce4/panel/plugins/docklike.desktop',plugins/'docklike.desktop')
   hub=share/'zorin11-hub';hub.mkdir();shutil.copy2(BASE/'window_preview.py',hub/'window_preview.py')
   apps=share/'applications';apps.mkdir()
   for name,cls in [('Preview test','Z11PreviewTest'),('Unopened app','Z11Unopened')]:
    (apps/(cls.lower()+'.desktop')).write_text(f'[Desktop Entry]\nType=Application\nName={name}\nExec=true\nIcon=applications-graphics\nStartupWMClass={cls}\n')
   gtk=root/'config/gtk-3.0';gtk.mkdir(parents=True);shutil.copy2(BASE/'taskbar/preview.css',gtk/'gtk.css')
   panel=root/'config/xfce4/panel';panel.mkdir(parents=True)
   (panel/'docklike-1.rc').write_text('[user]\nshowPreviews=true\nnoWindowsListIfSingle=false\nforceIconSize=true\niconSize=32\npreviewSleep=200\npinned=z11previewtest;z11unopened;\n')
   shutil.copytree(BASE/'window-theme',share/'themes/Zorin11-Dark')
   with (root/'log').open('w') as log:
    server=subprocess.Popen(['Xephyr',display,'-screen','1600x1000','-noreset','-nolisten','tcp'],stdout=log,stderr=log)
    try:
     time.sleep(.7)
     env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(share),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0',LIBGL_ALWAYS_SOFTWARE='1')
     result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',wm],env=env,stdout=log,stderr=log,timeout=130)
    finally:
     server.terminate();server.wait();log.flush();print((root/'log').read_text()[-8500:],flush=True)
    if result.returncode:raise SystemExit(result.returncode)
 sys.exit()

sys.path.insert(0,str(BASE))
import ctypes as C,dbus,gi
gi.require_version('Gtk','3.0');gi.require_version('Atspi','2.0')
from gi.repository import Gtk,Gdk,GLib,Atspi
from windowing import Windows
from PIL import Image
wm_name=sys.argv[-1]
if wm_name=='compiz':
 import effects
 subprocess.run(['/usr/bin/python3',str(BASE/'effects.py'),'--configure'],env=effects.environment(),check=True)
 wm=subprocess.Popen(['compiz','--replace','ccp'],env=effects.environment())
else:wm=subprocess.Popen(['xfwm4','--replace'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def pump(s=.1):
 end=time.monotonic()+s
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def until(fn,s=8):
 end=time.monotonic()+s
 while time.monotonic()<end:
  value=fn()
  if value:return value
  pump(.05)
 print('Accessible nodes:',[(n.get_name(),str(n.get_role())) for n in walk(Atspi.get_desktop(0))],flush=True)
 raise AssertionError('Timed out: '+str(fn))
x=C.CDLL('libX11.so.6');xt=C.CDLL('libXtst.so.6');x.XOpenDisplay.restype=C.c_void_p;x.XOpenDisplay.argtypes=[C.c_char_p];d=x.XOpenDisplay(None)
xt.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong];xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong];x.XFlush.argtypes=[C.c_void_p]
def move(px,py):xt.XTestFakeMotionEvent(d,-1,px,py,0);x.XFlush(d);pump(.12)
def walk(n):
 yield n
 for i in range(min(100,n.get_child_count())):
  c=n.get_child_at_index(i)
  if c:yield from walk(c)
def find(name):
 root=Atspi.get_desktop(0)
 for app in [root.get_child_at_index(i) for i in range(root.get_child_count())]:
  if app.get_name() in ('wrapper-2.0','xfce4-panel'):
   for n in walk(app):
    if n.get_name()==name and n.get_state_set().contains(Atspi.StateType.SHOWING):return n

def rect(n):return n.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
def hover(name):
 if name in ('Preview test','Unopened app'):
  buttons=[n for n in walk(Atspi.get_desktop(0)) if n.get_role()==Atspi.Role.PUSH_BUTTON and n.get_state_set().contains(Atspi.StateType.SHOWING) and rect(n).y>950]
  n=buttons[0 if name=='Preview test' else 1]
 else:n=until(lambda:find(name))
 r=rect(n);move(r.x+r.width//2,r.y+r.height//2)
def click(n):
 r=rect(n);move(r.x+r.width//2,r.y+r.height//2)
 xt.XTestFakeButtonEvent(d,1,1,0);xt.XTestFakeButtonEvent(d,1,0,0);x.XFlush(d);pump(.25)
def pixels():
 r=rect(until(lambda:find('Window previews')))
 p=Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),r.x,r.y,r.width,r.height)
 return r,Image.frombytes('RGB',(p.get_width(),p.get_height()),bytes(p.get_pixels()),'raw','RGB',p.get_rowstride())
def colors(color):
 r,im=pixels();return sum(1 for p in im.getdata() if sum(abs(a-b) for a,b in zip(p,color))<35)

# Create a real panel with the local module, avoiding the first-run chooser.
subprocess.run(['xfconf-query','-c','xfce4-panel','-p','/configver','-n','-t','int','-s','2'],check=True)
xf=dbus.Interface(dbus.SessionBus().get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
for key,val in {'/panels':dbus.Array([dbus.Int32(1,variant_level=1)],signature='v',variant_level=1),'/panels/panel-1/plugin-ids':dbus.Array([dbus.Int32(1,variant_level=1)],signature='v',variant_level=1),'/panels/panel-1/position':'p=10;x=800;y=980','/panels/panel-1/size':dbus.UInt32(48),'/panels/panel-1/length':dbus.Double(100),'/panels/panel-1/position-locked':True,'/plugins/plugin-1':'docklike'}.items():xf.SetProperty('xfce4-panel',key,val)
panel=subprocess.Popen(['xfce4-panel']);pump(2);b=Windows();owned=[];paint=[(230,45,50)];close_attempts=[]
def new(title,color=(40,120,190),blocked=False,wmclass='Z11PreviewTest'):
 w=Gtk.Window(title=title);w.set_wmclass(wmclass.lower(),wmclass);w.set_default_size(620,420);w.move(150,150);w.set_icon_name('applications-graphics')
 da=Gtk.DrawingArea();da.connect('draw',lambda _,cr:(cr.set_source_rgb(*(v/255 for v in color())),cr.paint(),False)[-1] if callable(color) else (cr.set_source_rgb(*(v/255 for v in color)),cr.paint(),False)[-1]);w.add(da)
 if blocked:w.connect('delete-event',lambda *_:(close_attempts.append(title),True)[1])
 w.show_all();owned.append(w);return w,da
try:
 w,da=new('Preview alpha',lambda:paint[0]);pump(.4)
 cover,_=new('Preview beta',blocked=True);pump(.5)
 active=b.active().get_xid();hover('Preview test');until(lambda:find('Close Preview alpha'));pump(2)
 until(lambda:colors(paint[0])>10000)
 assert b.active().get_xid()==active,'Hover stole focus'
 r,im=pixels();assert 0<=r.x and r.x+r.width<=1600 and r.y+r.height<=952
 if os.environ.get('ZORIN11_TEST_SCREENSHOTS'):
  out=Path(os.environ['ZORIN11_TEST_SCREENSHOTS']);out.mkdir(parents=True,exist_ok=True);im.save(out/f'taskbar-previews-{wm_name}.png')
 print('Grouped, covered-window thumbnails; focus retained; popup bounded PASSED',flush=True)
 hover('Preview alpha');paint[0]=(25,205,120);da.queue_draw();until(lambda:colors(paint[0])>10000)
 print('Live refresh continues with pointer in preview PASSED',flush=True)
 w.iconify();pump(.5);assert colors(paint[0])>10000
 click(until(lambda:find('Preview alpha')));until(lambda:not b.get(w.get_window().get_xid()).is_minimized());until(lambda:not find('Window previews'))
 print('Cached minimized thumbnail; click restores and dismisses PASSED',flush=True)
 hover('Preview test');until(lambda:find('Close Preview beta'));click(find('Close Preview beta'));until(lambda:close_attempts)
 assert b.get(cover.get_window().get_xid()),'Close killed app instead of requesting normal closure'
 # Cold minimized app gets an icon, title and a working restore/close target.
 move(100,100);pump(1);cold,_=new('Preview cold');cold.iconify();pump(.4);hover('Preview test');until(lambda:find('Close Preview cold'))
 click(find('Close Preview cold'));pump(.4)
 assert all(w.get_name()!='Preview cold' for w in b.windows())
 print('Normal WM close respects application veto; cold minimized close PASSED',flush=True)
 hover('Preview test');until(lambda:find('Close Preview alpha'));xid=w.get_window().get_xid();click(find('Close Preview alpha'));until(lambda:b.get(xid) is None)
 hover('Preview test');until(lambda:find('Close Preview beta'));print('Close removes only selected window; remaining app stays available PASSED',flush=True)
 move(100,100);until(lambda:not find('Window previews'));hover('Unopened app');pump(.7);assert not find('Window previews')
 # Overflow and close/capture races use only disposable windows.
 many=[new('Preview extra '+str(i))[0] for i in range(7)];pump(.5);hover('Preview test');pump(2)
 r,_=pixels();assert r.x>=0 and r.x+r.width<=1600,(r.x,r.width)
 scrollbar=next(n for n in walk(find('Window previews')) if n.get_role()==Atspi.Role.SCROLL_BAR and n.get_state_set().contains(Atspi.StateType.HORIZONTAL))
 value=scrollbar.get_value_iface();assert value.get_maximum_value()>0
 assert value.set_current_value(value.get_maximum_value());pump(.3)
 # GTK's AT-SPI extents can remain offscreen after a viewport scroll.
 # Exercise the visible final Close button with real pointer input instead.
 attempts_before=len(close_attempts)
 move(r.x+r.width-49,r.y+31)
 xt.XTestFakeButtonEvent(d,1,1,0);xt.XTestFakeButtonEvent(d,1,0,0);x.XFlush(d)
 until(lambda:len(close_attempts)>attempts_before)
 print('Horizontal overflow exposes the last window close control PASSED',flush=True)
 for item in many:item.destroy();pump(.02)
 pump(.7);assert panel.poll() is None;hover('Preview test');until(lambda:find('Close Preview beta'))
 cover.destroy();until(lambda:not find('Window previews'))
 print('Overflow bounded; rapid close/capture races; empty and closed groups PASSED',flush=True)
 # Launcher-less apps also share a stable group, including after activation.
 a,_=new('Unregistered alpha',wmclass='Z11Unregistered')
 c,_=new('Unregistered beta',wmclass='Z11Unregistered');pump(.5)
 buttons=[n for n in walk(Atspi.get_desktop(0)) if n.get_role()==Atspi.Role.PUSH_BUTTON and n.get_state_set().contains(Atspi.StateType.SHOWING) and rect(n).y>950]
 target=max(buttons,key=lambda n:rect(n).x);r=rect(target);move(r.x+r.width//2,r.y+r.height//2)
 until(lambda:find('Close Unregistered alpha'));until(lambda:find('Close Unregistered beta'))
 assert len(buttons)==3,'Unregistered app split into multiple taskbar icons'
 print('Windows without a desktop launcher share one preview group PASSED',flush=True)
finally:
 for w in owned:w.destroy()
 pump(.2);b.close();panel.terminate();panel.wait(timeout=10);wm.terminate();wm.wait(timeout=10)
