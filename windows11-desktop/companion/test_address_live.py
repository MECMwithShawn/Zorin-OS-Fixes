"""WebKit address editing and real clipboard, against source or preserved live bundle."""
import os,sys,json,time,subprocess
from pathlib import Path
if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0',WEBKIT_DISABLE_COMPOSITING_MODE='1'),timeout=35).returncode)
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib,Gdk
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
messages=[]
manager.connect('script-message-received::desktop',lambda _,r:messages.append(json.loads(r.get_js_value().to_string())))
web=WebKit2.WebView(user_content_manager=manager)
w=Gtk.Window();w.set_default_size(1100,750);w.add(web);w.show_all()
def pump():
    while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
    time.sleep(.01)
def wait(fn):
    until=time.monotonic()+8
    while time.monotonic()<until:
        pump()
        if fn():return
    raise AssertionError('Timed out')
def js(code):
    result=[]
    def done(view,r):
        try:result.append(view.evaluate_javascript_finish(r).to_json(0))
        except Exception as e:result.append(e)
    web.evaluate_javascript('JSON.stringify((()=>{'+code+'})())',-1,None,None,None,done)
    wait(lambda:bool(result))
    if isinstance(result[0],Exception):raise result[0]
    return json.loads(json.loads(result[0])) if result[0] else None
folder='/home/test/OneDrive/Documents/Photo & notes'
bundle=Path(sys.argv[-1]) if sys.argv[-1]!='--private' else Path(__file__).parent/'dist'
web.load_uri((bundle/'index.html').resolve().as_uri())
wait(lambda:any(m['action']=='ready' for m in messages))
data=dict(mode='explorer',path=folder,title='Photo & notes',entries=[],places=[],clouds=[dict(name='OneDrive',path='/home/test/OneDrive',icon='folder')])
js('window.receive('+json.dumps(dict(type='state',data=data))+');return true;')
wait(lambda:js('return !!document.querySelector(".address");'))
js('document.querySelector(".address").click();return true;')
wait(lambda:js('return !!document.querySelector(".address input");'))
assert js('let e=document.querySelector(".address input");return [e.value,e.selectionStart,e.selectionEnd];')==[folder,0,len(folder)]
web.execute_editing_command('Copy')
wait(lambda:Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()==folder)
js('document.querySelector(".address input").dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true;')
wait(lambda:js('return !document.querySelector(".address input");'))
assert js('return document.activeElement.className;').startswith('explorer-shell')
js('document.querySelector(".folder-search input").focus();document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"l",ctrlKey:true,bubbles:true}));return true;')
wait(lambda:js('return document.activeElement.getAttribute("aria-label")==="Folder address";'))
assert js('return document.activeElement.value;')==folder
js('document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true;')
wait(lambda:js('return !document.querySelector(".address input");'))
js('document.querySelector(".breadcrumbs button:last-child").click();return true;')
wait(lambda:js('return !!document.querySelector(".address input");'))
js('document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));return true;')
wait(lambda:any(m.get('action')=='file-navigate' and m.get('path')==folder for m in messages))
js('document.querySelectorAll(".breadcrumbs button")[1].click();return true;')
wait(lambda:any(m.get('action')=='file-navigate' and m.get('path')=='/home' for m in messages))
js('document.querySelector(".cloud-place").click();return true;')
wait(lambda:any(m.get('action')=='file-navigate' and m.get('path')=='/home/test/OneDrive' for m in messages))
print('PASS: click/last breadcrumb editing, full selection, real clipboard, Ctrl+L from search, Escape focus, Enter, ancestor and OneDrive navigation')
w.destroy()
