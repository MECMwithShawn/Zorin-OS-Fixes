"""Real WebKit → Hub → local search, clipboard and transfer workers in isolation."""
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
from unittest.mock import patch

if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],
        env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0'),timeout=60).returncode)
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib,Gdk
from app import Hub
import explorer
import file_transfer
from start_preferences import Preferences

workspace=tempfile.TemporaryDirectory();base=Path(workspace.name)
source=base/'source';destination=base/'destination';source.mkdir();destination.mkdir()
(source/'Orion notes.txt').write_text('Local search preview. <script>window.executed=true</script>')
(source/'Orion folder').mkdir()
(destination/'Orion notes.txt').write_text('Keep this original')
apps=[dict(id='orion.desktop',name='Orion',description='Test application',categories=['Utility'],icon='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="32" height="32"%3E%3Crect width="32" height="32" fill="%2360cdff"/%3E%3C/svg%3E')]
output=Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else None
if output:output.mkdir(parents=True,exist_ok=True)
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(832,864);window.add(web);window.show_all()
ready=threading.Event();errors=[];pool=ThreadPoolExecutor(3);exit_code=0;opened=[]

def payload():return dict(mode='start',apps=apps,pins=['orion.desktop'],startFolders=[],recent=[],groups=[],groupsVisible=False,places=[],user='Test')
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

def load_folder(s,path,hidden=False):
    s.location=path;s.file_state=explorer.listing(path)
    send(dict(type='state',data=dict(s.file_state,mode='explorer')))
surface=SimpleNamespace(mode='start',location=str(source),send=send,file_state=None)
hub=SimpleNamespace(apps={a['id']:a for a in apps},app_info=lambda ident:apps[0],background=background,
    start_preferences=Preferences(base/'preferences.json',[str(source)]),
    surfaces={'start':surface},copied_files=([],False,''),start=SimpleNamespace(hide=lambda:None),
    load_folder=load_folder,launch=lambda ident:opened.append(('app',ident)),
    open_settings=lambda page:opened.append(('setting',page)),open_explorer=lambda path:opened.append(('path',path)))
for name in ('start_search','search_action','preview_file','start_preview','file_action','start_transfer'):
    setattr(hub,name,lambda *args,n=name:getattr(Hub,n)(hub,*args))
hub.clipboard_owner=Gtk.Invisible()
targets=[Gtk.TargetEntry.new(name,0,i) for i,name in enumerate(['x-special/gnome-copied-files','text/uri-list','UTF8_STRING','TEXT','STRING'])]
Gtk.selection_add_targets(hub.clipboard_owner,Gdk.SELECTION_CLIPBOARD,targets)
hub.clipboard_owner.connect('selection-get',lambda *args:Hub.clipboard_get(hub,*args))

def on_message(_,result):
    message=json.loads(result.get_js_value().to_string())
    if message['action']=='ready':send(dict(type='state',data=payload()));ready.set();return
    try:Hub.dispatch(hub,surface,message)
    except Exception as error:errors.append(str(error)+' '+repr(message));send(dict(type='error',message=str(error)))
manager.connect('script-message-received::desktop',on_message)
web.load_uri((Path(__file__).parent/'dist/index.html').resolve().as_uri())

def click(text,selector='button'):
    assert js('(()=>{const b=[...document.querySelectorAll('+json.dumps(selector)+')].find(b=>b.textContent.trim()==='+json.dumps(text)+');if(!b)return false;b.click();return true})()'),text
    time.sleep(.1)
def wait(code):
    for _ in range(65):
        if js(code):return
        time.sleep(.1)
    raise AssertionError('Timed out: '+code)
def query(text):
    js('(()=>{const input=document.querySelector(".search-box input");input.focus();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,'+json.dumps(text)+');input.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
    wait('document.querySelector(".unified-search")?.dataset.query==='+json.dumps(text)+' && document.querySelector(".unified-search")?.dataset.searching==="false"')
def snapshot(name):
    if not output:return
    done=threading.Event()
    def captured(view,result,*_):view.get_snapshot_finish(result).write_to_png(str(output/name));done.set()
    GLib.idle_add(lambda:(web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,captured,None),False)[1])
    assert done.wait(5)
def navigate(path):
    GLib.idle_add(lambda:(load_folder(surface,str(path)),False)[1]);time.sleep(.2)
def transfer(choice):
    navigate(source)
    js('(()=>{document.querySelector(".file-item[title=\\"Orion notes.txt\\"]").click();return true})()')
    assert js('(()=>{document.querySelector("button[aria-label=Copy]").click();return true})()')
    time.sleep(.1)
    js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"l",ctrlKey:true,bubbles:true}));return true})()')
    wait('!!document.querySelector("input[aria-label=\\"Folder address\\"]")')
    js('(()=>{const input=document.querySelector("input[aria-label=\\"Folder address\\"]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,'+json.dumps(str(destination))+');input.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
    time.sleep(.1)
    js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));return true})()')
    wait('window.desktopState.path==='+json.dumps(str(destination))+' && document.activeElement.classList.contains("explorer-shell")')
    assert js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"v",ctrlKey:true,bubbles:true}));return true})()')
    wait('!!document.querySelector(".transfer-conflict")')
    if choice=='Keep both':snapshot('transfer-conflict.png')
    click(choice,'.transfer-dialog button')
    wait('document.querySelector(".transfer-dialog h2")?.textContent==="Transfer complete"')
    snapshot('transfer-complete.png');click('Close','.transfer-dialog button')

def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.3)
        with patch.object(explorer,'place_paths',return_value=[dict(path=str(source),name='Documents',symbol='document')]):
            query('Orion')
            # Start search opens on Apps; the preview icon launches and the pane lists package details.
            assert js('document.querySelector(".search-filters button[aria-pressed=true]").textContent')=='Apps'
            assert js('document.querySelectorAll(".unified-result").length')==1
            wait('document.querySelector(".search-app-details")?.getAttribute("aria-busy")==="false"')
            assert 'Built in' in js('document.querySelector(".search-app-details").textContent')
            assert 'Utility' in js('document.querySelector(".search-app-details").textContent')
            assert js('!document.querySelector(".search-result-actions")')
            snapshot('unified-search-app.png')
            js('(()=>{document.querySelector(".search-launch").click();return true})()')
            time.sleep(.1);assert opened[-1]==('app','orion.desktop')
            # A single click on an app row in the left list launches it too.
            opened.clear();js('(()=>{document.querySelector(".unified-result").click();return true})()')
            time.sleep(.1);assert opened==[('app','orion.desktop')],opened
            click('All','.search-filters button')
            assert js('document.querySelectorAll(".unified-result").length')==3
            # Arrow keys from the input select the next result; Enter routes its action.
            js('(()=>{document.querySelector(".search-box input").dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));return true})()')
            time.sleep(.1);assert opened[-1]==('app','orion.desktop')
            click('Files','.search-filters button')
            wait('!!document.querySelector(".search-detail pre")')
            assert 'Local search preview' in js('document.querySelector(".search-detail pre").textContent')
            assert js('window.executed===undefined')
            snapshot('unified-search.png')
            click('Open file location','.search-result-actions button');assert opened[-1]==('path',str(source))
            click('All','.search-filters button');query('volume')
            click('Open','.search-result-actions button');assert opened[-1]==('setting','sound')
            query('Orion');query('monitor')
            assert js('[...document.querySelectorAll(".unified-result")].every(b=>!b.textContent.includes("Orion"))')
        print('Unified search: apps/files/folders/settings, keyboard launch, stale query, inert preview and location routing passed',flush=True)
        js('(()=>{const input=document.querySelector(".search-box input");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,"");input.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
        time.sleep(.2)
        surface.mode='explorer'
        GLib.idle_add(lambda:(window.resize(1120,760),load_folder(surface,str(source)),False)[2]);time.sleep(.3)
        transfer('Keep both')
        assert (destination/'Orion notes.txt').read_text()=='Keep this original'
        assert (destination/'Orion notes - Copy.txt').read_text()==(source/'Orion notes.txt').read_text()
        transfer('Replace the file');assert (destination/'Orion notes.txt').read_text()==(source/'Orion notes.txt').read_text()
        (destination/'Orion notes.txt').write_text('Skip this version');transfer('Skip')
        assert (destination/'Orion notes.txt').read_text()=='Skip this version'
        # Cancel from the actual conflict dialog retains both originals.
        navigate(source)
        js('(()=>{document.querySelector(".file-item[title=\\"Orion notes.txt\\"]").click();document.querySelector("button[aria-label=Cut]").click();return true})()')
        time.sleep(.15);navigate(destination)
        js('(()=>{document.querySelector("button[aria-label=Paste]").click();return true})()')
        wait('!!document.querySelector(".transfer-conflict")');click('Cancel transfer','.transfer-dialog button')
        wait('document.querySelector(".transfer-dialog h2")?.textContent==="Transfer cancelled"')
        assert (source/'Orion notes.txt').exists();assert (destination/'Orion notes.txt').read_text()=='Skip this version'
        click('Close','.transfer-dialog button')
        # Real file error is displayed and Retry uses the same operation.
        (source/'retry.txt').write_text('retry payload');navigate(source)
        js('(()=>{document.querySelector(".file-item[title=\\"retry.txt\\"]").click();return true})()')
        time.sleep(.15)
        js('(()=>{document.querySelector("button[aria-label=Copy]").click();return true})()')
        time.sleep(.15);navigate(destination)
        original=file_transfer.publish_new;calls=[0]
        def fail_once(src,dst):
            calls[0]+=1
            if calls[0]==1:raise PermissionError('Injected read-only destination')
            original(src,dst)
        with patch.object(file_transfer,'publish_new',side_effect=fail_once):
            js('(()=>{document.querySelector("button[aria-label=Paste]").click();return true})()')
            wait('document.querySelector(".transfer-dialog h2")?.textContent==="Unable to transfer item"')
            snapshot('transfer-error.png');click('Retry','.transfer-dialog button')
            wait('document.querySelector(".transfer-dialog h2")?.textContent==="Transfer complete"')
        assert (destination/'retry.txt').read_text()=='retry payload'
        click('Close','.transfer-dialog button')
        # Slow a disposable copy so real Pause/Resume/Cancel controls can be exercised.
        (source/'large.bin').write_bytes(b'x'*(32*1024*1024));navigate(source)
        js('(()=>{document.querySelector(".file-item[title=\\"large.bin\\"]").click();return true})()')
        time.sleep(.1);js('(()=>{document.querySelector("button[aria-label=Copy]").click();return true})()')
        time.sleep(.1);navigate(destination)
        checkpoint=file_transfer.Transfer.checkpoint
        def slowed(job):
            if job.state=='running':time.sleep(.04)
            checkpoint(job)
        with patch.object(file_transfer.Transfer,'checkpoint',slowed):
            js('(()=>{document.querySelector("button[aria-label=Paste]").click();return true})()')
            wait('document.querySelector(".transfer-dialog h2")?.textContent==="Copying items"')
            click('Pause','.transfer-dialog button')
            wait('document.querySelector(".transfer-dialog h2")?.textContent==="Transfer paused"')
            time.sleep(.15);paused=surface.transfer.done_bytes;time.sleep(.15)
            assert surface.transfer.done_bytes==paused
            click('Resume','.transfer-dialog button');click('Cancel transfer','.transfer-dialog button')
            wait('document.querySelector(".transfer-dialog h2")?.textContent==="Transfer cancelled"')
        assert not (destination/'large.bin').exists()
        assert not list(destination.glob('.zorin11-transfer-*'))
        assert not errors,errors;assert js('window.desktopErrors.length')==0
        print('Transfers: real clipboard copy/cut/paste, keep both/replace/skip, cancel, pause/resume and error/retry dialogs passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start()
Gtk.main()
if getattr(surface,'transfer',None):surface.transfer.cancel();surface.transfer.thread.join(5)
pool.shutdown();workspace.cleanup();raise SystemExit(exit_code)
