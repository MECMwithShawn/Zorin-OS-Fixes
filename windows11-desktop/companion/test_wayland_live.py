"""Opt-in live Wayland snap, preview and restore test on a disposable window.
Run with GDK_BACKEND=x11; the child uses native Wayland.
"""
import gi,sys,time,subprocess,os
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
if '--window' in sys.argv:
 w=Gtk.Window(title='Axentra Wayland validation');w.set_default_size(640,420);w.add(Gtk.Label(label='Disposable native Wayland test window\nSnapping and preview validation'));w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main();raise SystemExit
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gnome_bridge,windowing,window_preview
assert os.environ.get('XDG_SESSION_TYPE')=='wayland', 'Requires a live Wayland session'
p=subprocess.Popen(['/usr/bin/python3',__file__,'--window'],env=dict(os.environ,GDK_BACKEND='wayland'))
def wait(fn):
 end=time.monotonic()+8
 while time.monotonic()<end:
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  v=fn()
  if v:return v
  time.sleep(.04)
 raise AssertionError('Timed out')
manager=None
try:
 row=wait(lambda:next((r for r in gnome_bridge.call('snapshot')['windows'] if r['pid']==p.pid and min(r['rect'][2:])>0),None));ident=row['id'];manager=windowing.Windows()
 from gi.repository import Gdk
 display=Gdk.Display.get_default()
 areas=[display.get_monitor(i).get_workarea() for i in range(display.get_n_monitors())]
 for a in areas:
  for name,zones in windowing.layouts():
   rect=windowing.zone_rect((a.x,a.y,a.width,a.height),zones[0])
   manager.place(ident,rect)
   wait(lambda:manager.get(ident) and tuple(manager.get(ident).get_geometry())==rect)
   image=window_preview.capture(ident);assert image.startswith(b'\x89PNG\r\n\x1a\n')
   print('PASS native Wayland',name,'snap and preview',rect,len(image),flush=True)
 saved=manager.saved[ident][0];manager.restore(ident);wait(lambda:manager.get(ident) and tuple(manager.get(ident).get_geometry())==saved);print('PASS restore',flush=True)
finally:
 if manager:manager.close()
 p.terminate();p.wait(timeout=5)
