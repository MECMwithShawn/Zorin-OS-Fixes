"""Exercise notification focus and native Escape routing in real WebKit.

Only fictional notifications are loaded. No notification daemon is contacted.
The GTK animation preference is changed only inside this test process.
"""
import json

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("Run this isolated GUI fixture directly.")
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib,Gdk
from app import Surface

manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window(title='Notification keyboard validation');window.set_default_size(400,640);window.add(web)
ready=threading.Event();messages=[];exit_code=0
fixture=dict(mode='notifications',available=True,logging=True,entries=[dict(id='fixture',time=1000000000000,app='Validation',appId='fixture',title='Saved locally',body='Fictional notification for keyboard testing.',read=False)])
def send(value):web.evaluate_javascript('window.receive('+json.dumps(value)+')',-1,None,None,None,None,None)
def receive(_,result):
 value=json.loads(result.get_js_value().to_string());messages.append(value)
 if value['action']=='ready':send(dict(type='state',data=fixture));ready.set()
 if value['action']=='close':window.hide()
manager.connect('script-message-received::desktop',receive)
surface=SimpleNamespace(mode='notifications',ready=True,send=send)
window.connect('key-press-event',lambda _,event:Surface.on_key(surface,window,event))
web.load_uri((Path(__file__).resolve().parent/'dist/index.html').as_uri());window.show_all()
def on_main(fn):
 done=threading.Event();result=[]
 def invoke():
  try:result.append(fn())
  except Exception as e:result.append(e)
  done.set();return False
 GLib.idle_add(invoke);assert done.wait(5)
 if isinstance(result[0],Exception):raise result[0]
 return result[0]
def js(code):
 done=threading.Event();result=[]
 def cb(view,res,*_):
  try:result.append(json.loads(view.evaluate_javascript_finish(res).to_string()))
  except Exception as e:result.append(e)
  done.set()
 on_main(lambda:web.evaluate_javascript('JSON.stringify(('+code+'))',-1,None,None,None,cb,None))
 assert done.wait(5)
 if isinstance(result[0],Exception):raise result[0]
 return result[0]
def wait_js(code):
 for _ in range(80):
  if js(code):return
  time.sleep(.05)
 raise AssertionError(code)
def escape():
 event=Gdk.Event.new(Gdk.EventType.KEY_PRESS);event.keyval=Gdk.KEY_Escape
 on_main(lambda:window.emit('key-press-event',event))
def run():
 global exit_code
 try:
  assert ready.wait(10)
  wait_js('!!document.querySelector(".notification-toolbar button")')
  js('([...document.querySelectorAll("button")].find(b=>b.textContent==="Clear all").click(),true)')
  wait_js('document.activeElement.textContent==="Cancel"')
  assert js('document.querySelector("[role=alertdialog]").getAttribute("aria-modal")==="true"')
  assert js('document.querySelector(".calendar-pane").inert===true')
  escape();wait_js('!document.querySelector("[role=alertdialog]")')
  wait_js('document.activeElement.textContent==="Clear all"')
  assert on_main(window.get_visible)
  assert not any(m['action']=='notification-clear' for m in messages)
  print('PASS native GTK Escape cancels dialog and restores focus',flush=True)
  js('(()=>{const e=document.createElement("div");e.className="file-progress";e.id="motion-check";document.body.append(e);return true})()')
  on_main(lambda:Gtk.Settings.get_default().set_property('gtk-enable-animations',False))
  wait_js('matchMedia("(prefers-reduced-motion:reduce)").matches')
  wait_js('getComputedStyle(document.getElementById("motion-check")).animationName==="none"')
  print('PASS WebKit follows reduced motion',flush=True)
  assert js('[...document.querySelectorAll(".notification-flyout>section")].every(e=>e.scrollWidth<=e.clientWidth+1)')
  on_main(lambda:Gtk.Settings.get_default().set_property('gtk-enable-animations',True))
  wait_js('getComputedStyle(document.getElementById("motion-check")).animationName==="progress"')
  escape()
  for _ in range(50):
   if not on_main(window.get_visible):break
   time.sleep(.05)
  assert not on_main(window.get_visible)
  assert not js('window.desktopErrors.length')
  print('PASS second Escape closes flyout; no script errors',flush=True)
 except Exception:
  import traceback;traceback.print_exc();exit_code=1
 finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=run,daemon=True).start();Gtk.main();window.destroy();raise SystemExit(exit_code)
