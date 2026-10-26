"""Native WebKit/GTK checks for the App style with tabs, Launcher and Full screen Start layouts."""
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
window=Gtk.Window();window.set_default_size(1280,800);window.add(web);window.show_all()
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
def type_into(selector,text):
    js('(()=>{const i=document.querySelector('+json.dumps(selector)+');i.focus();'
       'Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(i,'+json.dumps(text)+');'
       'i.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
def clear_search():
    type_into('.start-shell .search-box input','');wait('!document.querySelector(".unified-search")')
def menu_check(button,expected):
    js('(()=>{document.querySelector('+json.dumps(button)+').click();return true})()')
    wait('!!document.querySelector(".session-menu")')
    assert texts('.session-menu button')==expected,texts('.session-menu button')
    rect=js('(()=>{const r=document.querySelector(".session-menu").getBoundingClientRect();return [r.top,r.bottom,innerHeight]})()')
    assert rect[0]>=0 and rect[1]<=rect[2],('Menu stays on screen',rect)
    js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true})()')
    wait('!document.querySelector(".session-menu")')
def search_hands_off(results):
    type_into('.start-shell .search-box input','veg')
    wait('!!document.querySelector('+json.dumps(results+' .unified-search')+')')
    for _ in range(30):
        if last('search-query'):break
        time.sleep(.1)
    assert last('search-query')['query']=='veg'
def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.2)
        settings()
        assert texts('select[aria-label="Start menu style"] option')[-3:]==['App style with tabs','Launcher','Full screen']

        # App style with tabs
        choose_style('tabbed');assert hidden
        GLib.idle_add(lambda:(hub.start_preferences.change('tab-create',value='Work'),False)[1]);time.sleep(.2)
        start();wait('!!document.querySelector(".start-tabbed")')
        assert texts('.tabbed-list .list-letter')==['#','N','O','V']
        assert texts('.tabbed-list .w10-item')==['7-Zip','Nova','Orion','Vega']
        assert texts('.tabbed-canvas .pin-tabs [role=tab]')==['Pinned','Work']
        assert texts('.tabbed-canvas .pins .app-tile')==['Orion','Vega']
        assert 'All apps' not in texts('.tabbed-canvas button'),'The All apps list is already beside the canvas'
        assert not js('!!document.querySelector(".start-tabbed [aria-label=\'Desktop groups\']")')
        js('(()=>{document.querySelector(".tabbed-list .w10-item").dispatchEvent(new KeyboardEvent("keydown",{key:"F10",shiftKey:true,bubbles:true}));return true})()')
        wait('!!document.querySelector(".context-menu")');click('Add to Work','.context-menu button')
        wait('window.desktopState.startOptions.tabs[0].apps.length===1')
        click('Work','.pin-tabs [role=tab]');wait('document.querySelectorAll(".tabbed-canvas .pins .app-tile").length===1')
        snapshot('tabbed.png')
        menu_check('.start-tabbed .footer-actions [aria-label=\'Power options\']',['Sleep','Shut down','Restart'])
        js('(()=>{const i=document.querySelector(".tabbed-search input");i.focus();i.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));return true})()')
        assert js('document.activeElement.textContent')=='7-Zip'
        search_hands_off('.tabbed-canvas');assert not js('!!document.querySelector(".tabbed-list")')
        clear_search()

        # Launcher
        settings();choose_style('launcher');start();wait('!!document.querySelector(".start-launcher")')
        assert texts('.launcher-chips [role=tab]')==['Pinned','All apps','Games','Productivity','Utilities']
        assert texts('.launcher-canvas .app-tile')==['Orion','Vega']
        assert js('document.querySelector(".launcher-header .avatar").getBoundingClientRect().width')>=48,'Prominent account picture'
        click('All apps','.launcher-chips button');wait('document.querySelectorAll(".launcher-canvas .app-tile").length===4')
        click('Utilities','.launcher-chips button');wait('document.querySelectorAll(".launcher-canvas .app-tile").length===2')
        assert texts('.launcher-canvas .app-tile')==['7-Zip','Vega']
        snapshot('launcher.png')
        click('7-Zip','.launcher-canvas .app-tile');assert last('launch')=={'action':'launch','id':'7zip.desktop'}
        menu_check('.launcher-header .profile',['Account settings','Lock','Switch user','Sign out'])
        menu_check('.launcher-header [aria-label=\'Power options\']',['Sleep','Shut down','Restart'])
        search_hands_off('.launcher-results');assert not js('!!document.querySelector(".launcher-chips")')
        clear_search()

        # Full screen
        settings();choose_style('fullscreen');start();wait('!!document.querySelector(".start-fullscreen")')
        assert texts('.fullscreen-list .w10-item')==['7-Zip','Nova','Orion','Vega']
        assert js('document.querySelector(".fullscreen-canvas .pin-tabs [aria-selected=true]").textContent')=='Work','The chosen tab is remembered across layouts'
        click('Pinned','.pin-tabs [role=tab]');wait('document.querySelectorAll(".fullscreen-canvas .pins .app-tile").length===2')
        assert texts('.fullscreen-canvas .pins .app-tile')==['Orion','Vega']
        assert js('!!document.querySelector(".fullscreen-canvas .recommended-heading")')
        assert js('getComputedStyle(document.querySelector(".start-fullscreen")).borderRadius')=='0px'
        snapshot('fullscreen.png')
        menu_check('.fullscreen-session [aria-label=\'Power options\']',['Sleep','Shut down','Restart'])
        menu_check('.fullscreen-session .profile',['Account settings','Lock','Switch user','Sign out'])
        search_hands_off('.fullscreen-results');assert not js('!!document.querySelector(".fullscreen-list")')
        snapshot('fullscreen-search.png')
        clear_search()
        assert not last('session-action'),'No session command was sent'

        settings();choose_style('windows11');start();wait('!!document.querySelector(".pins")&&!!document.querySelector(".start-all-section")')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Start: App style with tabs, Launcher and Full screen layouts (lists, tabs, chips, canvas, menus, search) passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
window.destroy();workspace.cleanup();raise SystemExit(exit_code)
