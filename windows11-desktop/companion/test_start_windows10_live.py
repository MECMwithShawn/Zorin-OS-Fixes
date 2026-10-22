"""Native WebKit/GTK checks for the Windows 10 Start layout: rail, app list, letter jumps and tiles."""
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
apps=[app('7zip.desktop','7-Zip',['Utility']),app('nova.desktop','Nova',['Game']),app('orion.desktop','Orion',['Office']),app('vega.desktop','Vega',['Utility'])]
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(780,680);window.add(web);window.show_all()
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
    return dict(mode='start',apps=apps,pins=['orion.desktop','vega.desktop'],startFolders=[],recent=['nova.desktop','orion.desktop'],documents=[],
                groups=[],places=[],groupsVisible=False,user='Test',startStyle=hub.start_preferences.snapshot()['style'],startTiles=hub.start_preferences.snapshot()['tiles'],
                startPlaces=[place(p) for p in (home,docs,music)])
def update():send(dict(type='state',data=payload()))
surface=SimpleNamespace(mode='start',send=send,update=update,hide=lambda:hidden.append(True))
hub=SimpleNamespace(start=surface,surfaces={'start':surface},start_preferences=Preferences(base/'preferences.json',[str(docs)]),
    settings_busy=False,settings_generation=0,settings_data={},update_settings_surface=update,
    search_action=lambda *_:None,refresh_recent_documents=lambda **_:None,recent_history_allowed=lambda:True,
    payload=lambda:payload(),store=SimpleNamespace(state=dict(groups=[])),
    open_explorer=lambda path:opened.append(('folder',path)),open_settings=lambda page:opened.append(('setting',page)))
for name in ('open_path','settings_action'):
    setattr(hub,name,lambda *args,n=name,**kwargs:getattr(Hub,n)(hub,*args,**kwargs))

# Only the actions this layout routes through the hub are dispatched; launching apps,
# searching and session commands are recorded so the test never acts on the desktop.
DISPATCHED={'settings-start-preference','open-path','open-computer','start-tile-size'}
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
def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.2)
        settings()
        assert texts('select[aria-label="Start menu style"] option')==['Windows 11','Windows 10','Modern','Windows 7','App style with tabs','Launcher','Full screen']
        choose_style('windows10');assert hidden
        start();wait('!!document.querySelector(".start-w10")')
        assert texts('.w10-list > .w10-item')==['Nova','Orion'],'Most used comes from recent apps'
        assert texts('.w10-letter')==['#','N','O','V']
        assert [t.split('\n')[-1] for t in texts('.w10-tile')]==['Orion','Vega']
        assert js('[...document.querySelectorAll(".w10-tile")].map(t=>t.className)')==['w10-tile w10-medium']*2
        snapshot('w10-home.png')

        click('V','.w10-letter');wait('!!document.querySelector(".w10-letter-grid")')
        assert js('[...document.querySelectorAll(".w10-letter-grid button")].filter(b=>!b.disabled).map(b=>b.textContent)')==['#','N','O','V']
        snapshot('w10-letters.png')
        click('O','.w10-letter-grid button');wait('document.activeElement?.id==="w10-letter-O"')
        assert js('document.querySelector(".start-shell").scrollTop+document.scrollingElement.scrollTop')==0,'Only the app list scrolls'

        js('(()=>{document.querySelector(".w10-tile .app-tile").dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,clientX:400,clientY:150}));return true})()')
        wait('!!document.querySelector(".context-sizes")')
        assert texts('.context-sizes button')==['Small','Medium','Wide','Large']
        assert js('document.querySelector(".context-sizes [aria-pressed=true]").textContent')=='Medium'
        click('Wide','.context-sizes button')
        wait('document.querySelector(".w10-tile").className==="w10-tile w10-wide"')
        assert Preferences(base/'preferences.json',[]).snapshot()['tiles']=={'orion.desktop':'wide'}
        js('(()=>{document.querySelectorAll(".w10-tile .app-tile")[1].dispatchEvent(new KeyboardEvent("keydown",{key:"F10",shiftKey:true,bubbles:true}));return true})()')
        wait('!!document.querySelector(".context-sizes")');click('Small','.context-sizes button')
        wait('document.querySelectorAll(".w10-tile")[1].className==="w10-tile w10-small"')
        assert js('getComputedStyle(document.querySelector(".w10-small .app-tile>span:last-child")).display')=='none'
        snapshot('w10-tiles.png')
        js('(()=>{document.querySelector(".w10-list .w10-item").dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,clientX:120,clientY:150}));return true})()')
        wait('!!document.querySelector(".context-menu")')
        assert not js('!!document.querySelector(".context-sizes")'),'Only pinned tiles can be resized'
        js('(()=>{document.querySelector(".start-shell").click();return true})()')

        assert not js('!!document.querySelector(".context-menu")')
        click('Expand','.w10-rail-button');wait('!!document.querySelector(".start-w10.rail-open")')
        assert texts('.w10-rail-button')==['Collapse','Test','Documents','Music','Settings','Power']
        snapshot('w10-rail.png')
        click('Documents','.w10-rail-button')
        for _ in range(30):
            if opened:break
            time.sleep(.1)
        assert opened==[('folder',str(docs))],(opened,errors)
        click('Power','.w10-rail-button');wait('!!document.querySelector(".power-menu:not(.account-menu)")')
        assert texts('.session-menu button')==['Sleep','Shut down','Restart']
        assert not js('!!document.querySelector(".start-w10.rail-open")'),'Opening a menu collapses the rail'
        js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true})()')
        wait('!document.querySelector(".session-menu")')
        click('Test','.w10-rail-button');wait('!!document.querySelector(".account-menu")')
        snapshot('w10-account.png')
        js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true})()')
        assert not last('session-action')

        js('(()=>{const i=document.querySelector(".w10-search input");i.focus();i.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));return true})()')
        assert js('document.activeElement.textContent')=='Nova'
        js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"End",bubbles:true}));return true})()')
        assert js('document.activeElement.textContent')=='Vega'
        js('(()=>{const i=document.querySelector(".w10-search input");'
           'Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(i,"veg");'
           'i.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
        wait('!!document.querySelector(".w10-search-results .unified-search")&&!document.querySelector(".w10-tiles")')
        for _ in range(30):
            if last('search-query'):break
            time.sleep(.1)
        assert last('search-query')['query']=='veg'
        snapshot('w10-search.png')

        settings();choose_style('windows11');start()
        wait('!!document.querySelector(".pins")&&!document.querySelector(".start-w10")')
        assert not js('!!document.querySelector(".context-sizes")')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Start: Windows 10 rail, most used, letter jump, tile resize persistence, power/account menus and search passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
window.destroy();workspace.cleanup();raise SystemExit(exit_code)
