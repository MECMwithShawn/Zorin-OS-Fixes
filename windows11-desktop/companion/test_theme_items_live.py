"""Exercise Start folders and previews through real WebKit and backend routes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],
        env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0'),timeout=60).returncode)

import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib
from model import Store
from app import Hub
import explorer
from PIL import Image

workspace=tempfile.TemporaryDirectory();base=Path(workspace.name)
ids=['alpha.desktop','beta.desktop','gamma.desktop']
store=Store(base/'layout.json',ids,base)
for ident in ids:store.pin(ident,True)
apps=[{'id':ident,'name':ident.split('.')[0].title(),'description':'Test app','categories':['Utility'],
       'icon':'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="32" height="32"%3E%3Crect width="32" height="32" rx="6" fill="%2360cdff"/%3E%3C/svg%3E'} for ident in ids]
textfile=base/'example.html';textfile.write_text('<script>window.previewExecuted=true</script>\nPreview contents')
imagefile=base/'picture.png';Image.new('RGB',(1600,800),'#2176c1').save(imagefile)
output=Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else None
if output:output.mkdir(parents=True,exist_ok=True)
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(832,864);window.add(web);window.show_all()
ready=threading.Event();errors=[];pool=ThreadPoolExecutor(2);exit_code=0

def payload():
    return dict(mode='start',apps=apps,pins=store.state['pins'],startFolders=[dict(f,id=i) for i,f in store.state['start_folders'].items()],
                recent=[],groups=[],groupsVisible=False,places=[],user='Test')

def js(code):
    done=threading.Event();result=[]
    def evaluated(view,res,*_):
        try:result.append(json.loads(view.evaluate_javascript_finish(res).to_json(0)))
        except Exception as error:result.append(error)
        done.set()
    GLib.idle_add(lambda:(web.evaluate_javascript('JSON.stringify(('+code+'))',-1,None,None,None,evaluated,None),False)[1])
    assert done.wait(5),'WebKit evaluation timed out'
    if isinstance(result[0],Exception):raise result[0]
    return json.loads(result[0])

def send(message):web.evaluate_javascript('window.receive('+json.dumps(message)+')',-1,None,None,None,None,None)
def background(task,success,failure):
    def work():
        try:value=task();GLib.idle_add(lambda:(success(value),False)[1])
        except Exception as error:GLib.idle_add(lambda value=str(error):(failure(value),False)[1])
    pool.submit(work)

surface=SimpleNamespace(mode='start',location=str(base),file_state=explorer.listing(str(base)),send=send)
hub=SimpleNamespace(store=store,apps={a['id']:a for a in apps},broadcast=lambda:send({'type':'state','data':payload()}),
    background=background,surfaces={str(id(surface)):surface},launch=lambda ident:None)
hub.preview_file=lambda s,r:Hub.preview_file(hub,s,r)
hub.start_preview=lambda s:Hub.start_preview(hub,s)
hub.file_action=lambda s,m:Hub.file_action(hub,s,m)

def on_message(_,result):
    message=json.loads(result.get_js_value().to_string())
    if message['action']=='ready':hub.broadcast();ready.set();return
    try:Hub.dispatch(hub,surface,message)
    except Exception as error:errors.append(str(error));send({'type':'error','message':str(error)})
manager.connect('script-message-received::desktop',on_message)
web.load_uri((Path(__file__).parent/'dist/index.html').resolve().as_uri())

def click(text,selector='button'):
    assert js('(()=>{const b=[...document.querySelectorAll('+json.dumps(selector)+')].find(b=>b.textContent.trim()==='+json.dumps(text)+');if(!b)return false;b.click();return true})()'),text
    time.sleep(.15)

def snapshot(name):
    if not output:return
    done=threading.Event()
    def captured(view,result,*_):
        view.get_snapshot_finish(result).write_to_png(str(output/name));done.set()
    GLib.idle_add(lambda:(web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,captured,None),False)[1])
    assert done.wait(5)

def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.3)
        assert js('(()=>{const [a,b]=document.querySelectorAll(".pins .app-tile"),d=new DataTransfer(),r=b.getBoundingClientRect();a.dispatchEvent(new DragEvent("dragstart",{bubbles:true,dataTransfer:d}));b.dispatchEvent(new DragEvent("drop",{bubbles:true,dataTransfer:d,clientX:r.x+r.width/2,clientY:r.y+r.height/2}));a.dispatchEvent(new DragEvent("dragend",{bubbles:true,dataTransfer:d}));return true})()')
        time.sleep(.2);folder=next(iter(store.state['start_folders']))
        assert store.start_folder(folder)['apps']==['beta.desktop','alpha.desktop']
        click('Folder','.pins button')
        assert js('document.querySelector(".start-folder-dialog")!==null')
        js('(()=>{const input=document.querySelector(".start-folder-name input");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,"Work");input.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
        click('Save name')
        assert Store(base/'layout.json',ids,base).start_folder(folder)['name']=='Work'
        snapshot('start-folder.png')
        js('(()=>{const b=document.querySelector(".start-folder-apps .app-tile");b.dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,clientX:250,clientY:300}));return true})()')
        click('Move to Start','.context-menu button')
        assert 'beta.desktop' in store.state['pins'] and store.start_folder(folder)['apps']==['alpha.desktop']
        click('Move all apps out of folder')
        assert not store.state['start_folders'] and set(store.state['pins'])==set(ids)
        print('Start: real drag/drop, rename, restart persistence, move-out and ungroup passed',flush=True)
        surface.mode='explorer'
        GLib.idle_add(lambda:(window.resize(1120,760),send({'type':'state','data':dict(surface.file_state,mode='explorer')}),False)[2])
        time.sleep(.3)
        assert js('''(()=>{document.querySelector('[aria-label="Preview pane"]').click();[...document.querySelectorAll(".file-item")].find(e=>e.title==="example.html").click();return true})()''')
        for _ in range(35):
            if js('!!document.querySelector(".preview-content pre")'):break
            time.sleep(.1)
        assert 'window.previewExecuted=true' in js('document.querySelector(".preview-content pre").textContent')
        assert js('window.previewExecuted===undefined')
        snapshot('explorer-text-preview.png')
        js('(()=>{[...document.querySelectorAll(".file-item")].find(e=>e.title==="picture.png").click();return true})()')
        for _ in range(35):
            if js('!!document.querySelector(".preview-content img")?.naturalWidth'):break
            time.sleep(.1)
        assert js('document.querySelector(".preview-content img").naturalWidth')==1024
        snapshot('explorer-image-preview.png')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Explorer: real text/image decoding, inert HTML, selection update and rendering passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start()
Gtk.main();pool.shutdown();workspace.cleanup();raise SystemExit(exit_code)
