"""Native WebKit/GTK checks for shared Start appearance: transparency, corners and the Start button choice."""
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
    return dict(mode='start',apps=apps,pins=['orion.desktop'],startFolders=[],recent=['nova.desktop','orion.desktop'],documents=[],
                groups=[],places=[],groupsVisible=False,user='Test',startStyle=hub.start_preferences.snapshot()['style'],startOptions=Hub.start_options(hub),startTiles={},
                startAppearance={k:hub.start_preferences.snapshot()[k] for k in ('transparency','corners')},
                startPlaces=[place(p) for p in (home,docs,music)])
def update():send(dict(type='state',data=payload()))
surface=SimpleNamespace(mode='start',send=send,update=update,hide=lambda:hidden.append(True))
applied=[];picked=[]
hub=SimpleNamespace(apps={a['id']:None for a in apps},start=surface,apply_start_button=lambda:applied.append(hub.start_preferences.snapshot()['button']),
    pick=lambda surface,**kw:picked.append(kw) or [str(Path(__file__).parent/'start-buttons/orb.svg')],surfaces={'start':surface},start_preferences=Preferences(base/'preferences.json',[str(docs)]),
    settings_busy=False,settings_generation=0,settings_data={},update_settings_surface=update,
    search_action=lambda *_:None,refresh_recent_documents=lambda **_:None,recent_history_allowed=lambda:True,
    payload=lambda:payload(),store=SimpleNamespace(state=dict(groups=[])),
    open_explorer=lambda path:opened.append(('folder',path)),open_settings=lambda page:opened.append(('setting',page)))
for name in ('open_path','settings_action','save_custom_start_button'):
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
def choose(label,value,key):
    js('(()=>{const s=document.querySelector("select[aria-label=\''+label+'\']");'
       'Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value").set.call(s,'+json.dumps(str(value))+');'
       's.dispatchEvent(new Event("change",{bubbles:true}));return true})()')
    wait('window.desktopState.startPreferences.'+key+'==='+json.dumps(value))
def look():
    return js('(()=>{const s=document.querySelector(".start-shell");return {tint:getComputedStyle(s,"::after").opacity,'
              'background:getComputedStyle(s).backgroundColor,radius:getComputedStyle(s).borderTopLeftRadius}})()')
def verify():
    global exit_code
    try:
        import app as app_module
        app_module.CUSTOM_START_BUTTON=base/'start-button-custom.png'
        assert ready.wait(8);time.sleep(.2)
        default=look();assert default['tint']=='1' and default['background']!='rgba(0, 0, 0, 0)',default
        settings()
        assert js('document.documentElement.dataset.startCorners===undefined'),'Only Start pages are restyled'
        assert texts('[aria-label="Start button image"] [role=radio]')==['Windows 11','Windows 10','Orb','Your image…']
        assert js('document.querySelector("[role=radio][aria-checked=true]").textContent')=='Windows 11'
        choose('Start transparency',40,'transparency');choose('Start corners','square','corners')
        assert hub.start_preferences.snapshot()['transparency']==40
        start();wait('document.documentElement.dataset.startCorners==="square"')
        current=look();assert current['tint']=='0.6' and current['background']=='rgba(0, 0, 0, 0)' and current['radius']=='0px',current
        snapshot('appearance-transparent-square.png')
        settings();choose_style('windows10');choose('Start corners','rounded','corners')
        start();wait('!!document.querySelector(".start-w10")');assert look()['radius']=='8px','Rounded overrides the square Windows 10 style'
        settings();choose('Start corners','style','corners');choose('Start transparency',0,'transparency')
        start();wait('!!document.querySelector(".start-w10")&&document.documentElement.dataset.startCorners===undefined')
        current=look();assert current['radius']=='0px' and current['tint']=='1' and current['background']!='rgba(0, 0, 0, 0)',current
        settings();choose_style('windows11')

        click('Orb','[role=radio]');wait('window.desktopState.startPreferences.button==="orb"')
        assert applied==['orb'] and not picked
        click('Your image…','[role=radio]');wait('window.desktopState.startPreferences.button==="custom"')
        assert picked==[{'title':'Choose a Start button image'}] and applied==['orb','custom']
        assert (base/'start-button-custom.png').is_file()
        wait('document.querySelectorAll("[role=radio] img")[3]?.getAttribute("src").startsWith("zorin11://start-button/custom?v=")')
        snapshot('appearance-settings.png')
        click('Windows 11','[role=radio]');wait('window.desktopState.startPreferences.button==="windows11"')
        assert applied[-1]=='windows11'
        assert Preferences(base/'preferences.json',[]).snapshot()['button']=='windows11'
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Start appearance: transparency, corners per style, Start button radios and custom picture passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
window.destroy();workspace.cleanup();raise SystemExit(exit_code)
