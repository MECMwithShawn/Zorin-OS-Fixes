"""Native WebKit/GTK checks for Windows 11 Start options: pages, grid size, layout, Recommended and pin tabs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory() as private:
        raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],
            env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0',GSETTINGS_BACKEND='memory',
                     XDG_CONFIG_HOME=private+'/config',XDG_DATA_HOME=private+'/data'),timeout=60).returncode)
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib
from app import Hub
from start_preferences import Preferences

workspace=tempfile.TemporaryDirectory();base=Path(workspace.name)
home=base/'home';docs=home/'Documents';music=home/'Music'
for folder in (docs,music):folder.mkdir(parents=True)
blank='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg"/%3E'
def app(ident,name,categories):return dict(kind='app',id=ident,name=name,description='',icon=blank,categories=categories,actions=[])
apps=[app(f'app{n:02}.desktop',f'App {n:02}',['Utility']) for n in range(20)]
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(832,864);window.add(web);window.show_all()
ready=threading.Event();errors=[];opened=[];sent=[];hidden=[];exit_code=0
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
def place(path):return Hub.path_info(None,path)
def payload():
    if surface.mode=='settings':return dict(mode='settings',**hub.settings_data)
    return dict(mode='start',apps=apps,pins=[a['id'] for a in apps],startFolders=[],recent=[a['id'] for a in apps[:10]],documents=[],
                groups=[],places=[],groupsVisible=False,user='Test',startStyle=hub.start_preferences.snapshot()['style'],startOptions=Hub.start_options(hub),
                startPlaces=[place(p) for p in (home,docs,music)])
def update():send(dict(type='state',data=payload()))
surface=SimpleNamespace(mode='start',send=send,update=update,hide=lambda:hidden.append(True))
hub=SimpleNamespace(apps={a['id']:None for a in apps},start=surface,surfaces={'start':surface},start_preferences=Preferences(base/'preferences.json',[str(docs)]),
    settings_busy=False,settings_generation=0,settings_data={},update_settings_surface=update,
    search_action=lambda *_:None,refresh_recent_documents=lambda **_:None,recent_history_allowed=lambda:True,
    payload=lambda:payload(),store=SimpleNamespace(state=dict(groups=[])),
    open_explorer=lambda path:opened.append(('folder',path)),open_settings=lambda page:opened.append(('setting',page)))
for name in ('open_path','settings_action'):
    setattr(hub,name,lambda *args,n=name,**kwargs:getattr(Hub,n)(hub,*args,**kwargs))

# Only the actions this layout routes through the hub are dispatched; launching apps,
# searching and session commands are recorded so the test never acts on the desktop.
DISPATCHED={'settings-start-preference','open-path','open-computer','start-tab'}
def on_message(_,result):
    message=json.loads(result.get_js_value().to_string())
    if message['action']=='ready':update();ready.set();return
    sent.append(message)
    if message['action'] not in DISPATCHED:return
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
def texts(selector):return js('[...document.querySelectorAll('+json.dumps(selector)+')].map(e=>e.textContent.trim())')
def last(action):return next((m for m in reversed(sent) if m['action']==action),None)
def snapshot(name):
    if not output:return
    done=threading.Event()
    def captured(view,result,*_):view.get_snapshot_finish(result).write_to_png(str(output/name));done.set()
    GLib.idle_add(lambda:(web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,captured,None),False)[1])
    assert done.wait(5)
def settings():
    def switch():
        surface.mode='settings'
        hub.settings_data=dict(startPreferences=hub.start_preferences.snapshot(),recentHistoryAllowed=True)
        update();send(dict(type='show',page='search-start'));return False
    GLib.idle_add(switch);wait('!!document.querySelector("select[aria-label=\'Start menu style\']")')
def choose_style(value):
    js('(()=>{const s=document.querySelector("select[aria-label=\'Start menu style\']");'
       'Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value").set.call(s,'+json.dumps(value)+');'
       's.dispatchEvent(new Event("change",{bubbles:true}));return true})()')
    wait('window.desktopState.startPreferences?.style==='+json.dumps(value))
def start():
    def switch():surface.mode='start';update();send(dict(type='show',page='home'));return False
    GLib.idle_add(switch);wait('!!document.querySelector(".start-shell")')
def choose(label,value,settle):
    js('(()=>{const s=document.querySelector("select[aria-label='+json.dumps(json.dumps(label))[1:-1]+']");'
       'Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value").set.call(s,'+json.dumps(str(value))+');'
       's.dispatchEvent(new Event("change",{bubbles:true}));return true})()')
    wait(settle)
def type_into(selector,text):
    js('(()=>{const i=document.querySelector('+json.dumps(selector)+');i.focus();'
       'Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(i,'+json.dumps(text)+');'
       'i.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
def tabs():return Preferences(base/'preferences.json',[]).snapshot()['tabs']
def context_on(index):
    js('(()=>{document.querySelectorAll(".pins .app-tile")['+str(index)+'].dispatchEvent(new KeyboardEvent("keydown",{key:"F10",shiftKey:true,bubbles:true}));return true})()')
    wait('!!document.querySelector(".context-menu")')
def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.2)
        tiles='document.querySelectorAll(".pins .app-tile").length'
        assert js(tiles)==18,'Default layout: 3 rows of 6'
        assert texts('.pin-pages button')==['',''] and js('document.querySelector(".pin-pages [aria-current]").getAttribute("aria-label")')=='Page 1 of 2'
        assert js('document.querySelectorAll(".recommended-item").length')==6,'Default shows six recommendations'
        snapshot('w11-default.png')
        js('(()=>{document.querySelectorAll(".pin-pages button")[1].click();return true})()');wait(tiles+'===2')
        js('(()=>{document.querySelector(".pins").dispatchEvent(new KeyboardEvent("keydown",{key:"PageUp",bubbles:true}));return true})()');wait(tiles+'===18')

        settings()
        assert texts('select[aria-label="Start layout"] option')==['More pins','Default','More recommendations']
        choose('Pinned columns',8,'window.desktopState.startPreferences.columns===8')
        choose('Start layout','more-pins','window.desktopState.startPreferences.layout==="more-pins"')
        start();wait(tiles+'===20')
        assert js('getComputedStyle(document.querySelector(".pins")).gridTemplateColumns.split(" ").length')==8
        assert not js('!!document.querySelector(".pin-pages")'),'Everything fits on one page'
        assert js('document.querySelectorAll(".recommended-item").length')==2,'More pins shows fewer recommendations'
        settings();choose('Start layout','more-recommendations','window.desktopState.startPreferences.layout==="more-recommendations"')
        choose('Pinned columns',6,'window.desktopState.startPreferences.columns===6')
        start();wait(tiles+'===12')
        assert js('document.querySelectorAll(".recommended-item").length')==8,'More recommendations shows eight'
        settings();js('(()=>{document.querySelector("button[role=switch][aria-label=\'Show Recommended\']").click();return true})()')
        wait('window.desktopState.startPreferences.showRecommended===false')
        start();wait(tiles+'===20');assert not js('!!document.querySelector(".recommended-heading")'),'Recommended hidden; pins gain two rows'
        snapshot('w11-no-recommended.png')
        settings();js('(()=>{document.querySelector("button[role=switch][aria-label=\'Show Recommended\']").click();return true})()')
        choose('Start layout','default','window.desktopState.startPreferences.layout==="default"&&window.desktopState.startPreferences.showRecommended')
        start();wait(tiles+'===18')

        click('','.pin-tab-add');wait('!!document.querySelector(".pin-tab-name input")')
        type_into('.pin-tab-name input','Nope')
        js('(()=>{document.querySelector(".pin-tab-name input").dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true})()')
        wait('!document.querySelector(".pin-tab-name")');time.sleep(.3)
        assert tabs()==[] and not last('close'),'Escape cancels the name without closing Start'
        click('','.pin-tab-add');type_into('.pin-tab-name input','Work')
        js('(()=>{document.querySelector(".pin-tab-name form,.pin-tab-name").requestSubmit();return true})()')
        wait('window.desktopState.startOptions.tabs.length===1')
        assert texts('.pin-tabs [role=tab]')==['Pinned','Work']
        context_on(3);click('Add to Work','.context-menu button')
        context_on(1);click('Add to Work','.context-menu button')
        wait('window.desktopState.startOptions.tabs[0].apps.length===2')
        click('Work','.pin-tabs [role=tab]');wait(tiles+'===2')
        assert texts('.pins .app-tile')==['App 03','App 01']
        context_on(1)
        assert 'Add to Work' not in texts('.context-menu button')
        click('Move to first in Work','.context-menu button');wait('window.desktopState.startOptions.tabs[0].apps[0]==="app01.desktop"')
        context_on(1);click('Remove from Work','.context-menu button');wait(tiles+'===1')
        snapshot('w11-tab.png')
        js('(()=>{document.querySelector("button[aria-label=\'Rename Work\']").click();return true})()')
        wait('!!document.querySelector(".pin-tab-name input")');type_into('.pin-tab-name input','Office')
        js('(()=>{document.querySelector(".pin-tab-name").requestSubmit();return true})()')
        wait('window.desktopState.startOptions.tabs[0]?.name==="Office"')
        assert tabs()==[dict(id='tab1',name='Office',apps=['app01.desktop'])]
        js('(()=>{document.querySelector("button[aria-label=\'Delete Office\']").click();return true})()')
        wait('window.desktopState.startOptions.tabs.length===0')
        assert js('document.querySelector(".pin-tabs [aria-selected=true]").textContent')=='Pinned' and js(tiles)==18
        assert tabs()==[]

        settings();choose_style('windows10')
        wait('!document.querySelector("select[aria-label=\'Start layout\']")')  # Windows 11 options only show for that style
        choose_style('windows11')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Start: Windows 11 pages, columns, layouts, Recommended toggle and pin tabs (create, cancel, add, reorder, remove, rename, delete) passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
window.destroy();workspace.cleanup();raise SystemExit(exit_code)
