"""Native WebKit/GTK checks for the Modern Start layout: tabs, flat app list, places, power and search."""
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
apps=[app('orion.desktop','Orion',['Office']),app('nova.desktop','Nova',['Game']),app('vega.desktop','Vega',['Utility'])]
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(520,640);window.add(web);window.show_all()
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
    return dict(mode='start',apps=apps,pins=['orion.desktop'],startFolders=[],recent=['nova.desktop','orion.desktop'],documents=[],
                groups=[],places=[],groupsVisible=False,user='Test',startStyle=hub.start_preferences.snapshot()['style'],
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
DISPATCHED={'settings-start-preference','open-path','open-computer'}
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
        settings();choose_style('modern');assert hidden
        assert Preferences(base/'preferences.json',[]).snapshot()['style']=='modern'
        start();wait('!!document.querySelector(".start-classic.start-modern")')
        assert texts('.modern-tabs [role=tab]')==['Pinned','All apps']
        assert js('document.querySelector(".modern-tabs [aria-selected=true]").textContent')=='Pinned'
        assert not js('!!document.querySelector(".classic-all")'),'Modern uses tabs instead of All Programs'
        assert texts('.classic-list .classic-item')==['Orion','Nova']
        assert texts('.classic-place')==['Test','Documents','Music','Computer','Settings','Start settings']
        assert js('getComputedStyle(document.querySelector(".start-modern")).borderRadius')=='0px'
        assert js('getComputedStyle(document.querySelector(".classic-programs")).backgroundColor')=='rgba(0, 0, 0, 0)','Programs pane is dark, not the Windows 7 light pane'
        snapshot('modern-home.png')

        click('All apps','.modern-tabs button')
        wait('document.querySelector(".modern-tabs [aria-selected=true]").textContent==="All apps"')
        assert texts('.classic-list .classic-item')==['Orion','Nova','Vega'],'All apps is the flat app list'
        assert not js('!!document.querySelector(".classic-category")')
        snapshot('modern-all-apps.png')
        click('Vega','.classic-list .classic-item');assert last('launch')=={'action':'launch','id':'vega.desktop'}
        js('(()=>{document.querySelectorAll(".classic-list .classic-item")[1].dispatchEvent(new KeyboardEvent("keydown",{key:"F10",shiftKey:true,bubbles:true}));return true})()')
        wait('!!document.querySelector(".context-menu")')
        assert 'Pin to Start' in texts('.context-menu button')
        assert not js('!!document.querySelector(".context-sizes")'),'Tile sizes belong to Windows 10 only'
        js('(()=>{document.querySelector(".start-shell").click();return true})()')
        click('Pinned','.modern-tabs button');wait('document.querySelector(".classic-list").getAttribute("aria-label")==="Pinned and frequent programs"')

        click('Documents','.classic-place');click('Computer','.classic-place')
        for _ in range(30):
            if len(opened)>=2:break
            time.sleep(.1)
        assert opened==[('folder',str(docs)),('folder','::computer')],(opened,errors)
        click('','.classic-power-more');wait('!!document.querySelector(".classic-menu")')
        assert texts('.classic-menu button')==['Switch user','Sign out','Lock','Restart','Sleep']
        snapshot('modern-power.png')
        js('(()=>{document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));return true})()')
        wait('!document.querySelector(".classic-menu")')
        assert not last('session-action')
        click('Shut down','.classic-shutdown');assert last('session-action')=={'action':'session-action','command':'shutdown'}

        assert js('document.querySelector(".classic-search input").placeholder')=='Search apps, files and settings'
        js('(()=>{const i=document.querySelector(".classic-search input");i.focus();i.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowUp",bubbles:true}));return true})()')
        assert js('document.activeElement.textContent')=='Nova'
        js('(()=>{const i=document.querySelector(".classic-search input");'
           'Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(i,"veg");'
           'i.dispatchEvent(new Event("input",{bubbles:true}));return true})()')
        wait('!!document.querySelector(".classic-programs .unified-search")&&!document.querySelector(".modern-tabs")')
        for _ in range(30):
            if last('search-query'):break
            time.sleep(.1)
        assert last('search-query')['query']=='veg'
        snapshot('modern-search.png')

        settings();choose_style('windows7');start()
        wait('!!document.querySelector(".start-classic")&&!document.querySelector(".start-modern")&&!!document.querySelector(".classic-all")')
        settings();choose_style('windows11');start();wait('!!document.querySelector(".pins")')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Start: Modern tabs, flat All apps, places, power menu, keyboard and search passed; Windows 7 still distinct',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
window.destroy();workspace.cleanup();raise SystemExit(exit_code)
