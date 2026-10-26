"""Native WebKit/GTK checks for Start history, folder controls and app actions."""
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
    with tempfile.TemporaryDirectory() as private:
        raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],
            env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0',GSETTINGS_BACKEND='memory',
                     XDG_CONFIG_HOME=private+'/config',XDG_DATA_HOME=private+'/data'),timeout=60).returncode)
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib,Gio
from app import Hub
from start_preferences import Preferences

workspace=tempfile.TemporaryDirectory();base=Path(workspace.name)
docs=base/'Documents';docs.mkdir();extra=base/'Extra';extra.mkdir()
file=docs/'Orion sample.txt';file.write_text('A disposable recent document')
(extra/'Orion extra.txt').touch();marker=base/'action-launched'
entry=base/'orion.desktop'
entry.write_text('[Desktop Entry]\nType=Application\nName=Orion\nExec=/usr/bin/true\nActions=verify;\n\n'
                 '[Desktop Action verify]\nName=New verification window\nExec=/usr/bin/touch "'+str(marker)+'"\n')
app=Gio.DesktopAppInfo.new_from_filename(str(entry))
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(832,864);window.add(web);window.show_all()
ready=threading.Event();pool=ThreadPoolExecutor(3);errors=[];opened=[];exit_code=0
output=Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else None
if output:output.mkdir(parents=True,exist_ok=True)

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
def payload():
    if surface.mode=='settings':return dict(mode='settings',**hub.settings_data)
    info=Hub.app_info(hub,app.get_id());info['icon']='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg"/%3E'
    return dict(mode='start',apps=[info],pins=[app.get_id()],startFolders=[],recent=[],documents=hub.recent_documents,
                groups=[],places=[],groupsVisible=False,user='Test')
def update():send(dict(type='state',data=payload()))
surface=SimpleNamespace(mode='start',send=send,update=update,hide=lambda:None)
hub=SimpleNamespace(apps={app.get_id():app},start=surface,surfaces={'start':surface},background=background,
    store=SimpleNamespace(used=lambda ident:opened.append(('app',ident))),broadcast=update,
    start_preferences=Preferences(base/'preferences.json',[str(docs)]),recent_documents=[],recent_generation=0,recent_timer=0,
    recent_manager=Gtk.RecentManager(filename=str(base/'recent.xbel')),privacy=Gio.Settings.new('org.gnome.desktop.privacy'),
    settings_busy=False,settings_generation=0,settings_data={},update_settings_surface=update,
    open_explorer=lambda path:opened.append(('folder',path)),open_settings=lambda page:opened.append(('setting',page)))
for name in ('app_info','launch_app_action','refresh_recent_documents','recent_history_allowed','open_recent_document',
             'start_search','search_action','settings_action'):
    setattr(hub,name,lambda *args,n=name,**kwargs:getattr(Hub,n)(hub,*args,**kwargs))
hub.privacy.connect('changed::remember-recent-files',lambda *_:hub.refresh_recent_documents())
hub.recent_manager.connect('changed',lambda *_:hub.refresh_recent_documents())
choices=[]
def pick(surface,folder=False):
    def choose():
        dialogs=[w for w in Gtk.Window.list_toplevels() if isinstance(w,Gtk.FileChooserDialog)]
        if not dialogs:return True
        dialogs[0].set_filename(str(choices.pop(0)))
        GLib.timeout_add(150,lambda:(dialogs[0].response(Gtk.ResponseType.OK),False)[1])
        return False
    GLib.timeout_add(100,choose)
    return Hub.pick(hub,window,folder=folder)
hub.pick=pick

def on_message(_,result):
    message=json.loads(result.get_js_value().to_string())
    if message['action']=='ready':update();ready.set();return
    try:Hub.dispatch(hub,surface,message)
    except Exception as error:errors.append(str(error)+' '+repr(message));send(dict(type='error',message=str(error)))
manager.connect('script-message-received::desktop',on_message)
web.load_uri((Path(__file__).parent/'dist/index.html').resolve().as_uri())

def wait(code):
    for _ in range(70):
        if js(code):return
        time.sleep(.1)
    raise AssertionError('Timed out: '+code)
def click(text,selector='button'):
    assert js('(()=>{const b=[...document.querySelectorAll('+json.dumps(selector)+')].find(b=>b.textContent.trim()==='+json.dumps(text)+');if(!b)return false;b.click();return true})()'),text
    time.sleep(.12)
def snapshot(name):
    if not output:return
    done=threading.Event()
    def captured(view,result,*_):view.get_snapshot_finish(result).write_to_png(str(output/name));done.set()
    GLib.idle_add(lambda:(web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,captured,None),False)[1])
    assert done.wait(5)
def settings():
    def switch():
        surface.mode='settings'
        hub.settings_data=dict(startPreferences=hub.start_preferences.snapshot(),recentHistoryAllowed=hub.recent_history_allowed())
        update();send(dict(type='show',page='search-start'));return False
    GLib.idle_add(switch);wait('!!document.querySelector(".settings-search-folders")')
def start():
    def switch():surface.mode='start';update();send(dict(type='show',page='home'));hub.refresh_recent_documents();return False
    GLib.idle_add(switch);wait('!!document.querySelector(".start-shell")')
def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.2)
        def remember():
            data=Gtk.RecentData();data.mime_type='text/plain';data.app_name='Orion';data.app_exec='/usr/bin/true %u';data.is_private=False
            assert hub.recent_manager.add_full(file.as_uri(),data)
            hub.refresh_recent_documents();return False
        GLib.idle_add(remember)
        wait('window.desktopState.documents?.length===1')
        snapshot('recommended.png')
        js('(()=>{document.querySelector(".recommended-item").dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,clientX:200,clientY:430}));return true})()')
        click('Open file location','.context-menu button')
        for _ in range(30):
            if opened:break
            time.sleep(.1)
        assert opened and opened[-1]==('folder',str(docs)),errors
        js('(()=>{document.querySelector(".pins .app-tile").dispatchEvent(new KeyboardEvent("keydown",{key:"F10",shiftKey:true,bubbles:true}));return true})()')
        wait('!!document.querySelector(".context-menu")');snapshot('app-actions.png')
        click('New verification window','.context-menu button')
        for _ in range(30):
            if marker.exists():break
            time.sleep(.1)
        assert marker.exists(),'Desktop action did not execute'
        settings();choices.append(extra);click('Add search folder')
        wait('window.desktopState.startPreferences.roots.length===2')
        choices.append(docs);click('Exclude a folder')
        wait('window.desktopState.startPreferences.exclusions.length===1')
        start();time.sleep(.4);assert js('window.desktopState.documents.length')==0
        # The configured exclusion also reaches the actual filename-search worker.
        event=threading.Event();result=[]
        original=surface.send
        def collect(message):
            original(message)
            if message.get('type')=='search-results' and not message.get('searching'):
                result.append(message);event.set()
        surface.send=collect
        GLib.idle_add(lambda:(hub.search_action(surface,dict(action='search-query',id=99,query='Orion')),False)[1])
        assert event.wait(5)
        assert [i['path'] for i in result[-1]['results'] if i.get('path')]==[str(extra/'Orion extra.txt')]
        surface.send=original
        settings();snapshot('search-start-settings.png')
        click('Restore default search folders and clear exclusions');start()
        wait('window.desktopState.documents.length===1')
        settings()
        js('(()=>{document.querySelector("button[role=switch][aria-label=\'Show recently opened documents\']").click();return true})()')
        wait('window.desktopState.startPreferences.recentDocuments===false');start();time.sleep(.3)
        assert js('window.desktopState.documents.length')==0
        assert hub.recent_manager.has_item(file.as_uri()),'Turning suggestions off must retain desktop history'
        settings();js('(()=>{document.querySelector("button[role=switch][aria-label=\'Show recently opened documents\']").click();return true})()');start()
        wait('window.desktopState.documents.length===1')
        GLib.idle_add(lambda:(hub.privacy.set_boolean('remember-recent-files',False),False)[1])
        wait('window.desktopState.documents.length===0')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Start: real recent history, privacy changes, location routing and desktop action execution passed',flush=True)
        print('Settings: native folder pickers, persisted scopes, exclusions, reset and opt-out passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
pool.shutdown(wait=True);window.destroy();workspace.cleanup();raise SystemExit(exit_code)
