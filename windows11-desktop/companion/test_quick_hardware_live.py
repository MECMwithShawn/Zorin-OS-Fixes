"""Real WebKit → Hub → D-Bus tests; all service names live on a private bus."""
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
    with tempfile.TemporaryDirectory() as home:
        raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],
            env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0',GIO_USE_VFS='local',NO_AT_BRIDGE='1',GSETTINGS_BACKEND='memory',XDG_CURRENT_DESKTOP='XFCE',
                     ZORIN11_HOST_BUS=os.environ.get('DBUS_SESSION_BUS_ADDRESS',''),
                     XDG_CONFIG_HOME=home+'/config',XDG_DATA_HOME=home+'/data',ZORIN11_CONFIG_DIR=home+'/hub'),timeout=60).returncode)
assert os.environ['DBUS_SESSION_BUS_ADDRESS']!=os.environ.get('ZORIN11_HOST_BUS')
os.environ['DBUS_SYSTEM_BUS_ADDRESS']=os.environ['DBUS_SESSION_BUS_ADDRESS']
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
# Only the service connection needs an event loop. Synchronous worker clients
# must not register their short-lived connections with the GTK event loop.
service_loop=DBusGMainLoop()
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib
from app import Hub
from model import Store
import hardware_controls as controls
import quick_controls,settings_backend,notifications

workspace=tempfile.TemporaryDirectory();base=Path(workspace.name)
controls.PROFILE_STATE=base/'power-profile.json'
bus=dbus.SessionBus(mainloop=service_loop);names=[dbus.service.BusName(name,bus) for name in ('net.hadess.PowerProfiles',controls.RFKILL,'org.bluez')]
class Rejected(dbus.DBusException):_dbus_error_name='org.bluez.Error.Failed'
class Properties(dbus.service.Object):
    def __init__(self,path,interface,state):
        super().__init__(bus,path);self.interface=interface;self.state=state
    @dbus.service.method(controls.PROPERTIES,in_signature='s',out_signature='a{sv}')
    def GetAll(self,interface):return self.state
    @dbus.service.method(controls.PROPERTIES,in_signature='ss',out_signature='v')
    def Get(self,interface,name):return self.state[name]
    @dbus.service.method(controls.PROPERTIES,in_signature='ssv',out_signature='')
    def Set(self,interface,name,value):self.state[name]=value
power=Properties('/net/hadess/PowerProfiles','net.hadess.PowerProfiles',dict(ActiveProfile='performance',
    Profiles=dbus.Array([dbus.Dictionary({'Profile':p},signature='sv') for p in controls.PROFILE_NAMES],signature='a{sv}')))
radio=Properties(controls.RFKILL_PATH,controls.RFKILL,dict(AirplaneMode=False,HasAirplaneMode=True,HardwareAirplaneMode=False))
adapter=Properties('/org/bluez/hci0','org.bluez.Adapter1',dict(Powered=True))
class Device(Properties):
    fail=False
    @dbus.service.method('org.bluez.Device1',in_signature='',out_signature='')
    def Connect(self):self.state['Connected']=True
    @dbus.service.method('org.bluez.Device1',in_signature='',out_signature='')
    def Disconnect(self):
        if self.fail:raise Rejected('The test device refused the connection change')
        self.state['Connected']=False
headset=Device('/org/bluez/hci0/dev_AA','org.bluez.Device1',dict(Alias='Studio Headphones',Paired=True,Connected=False,
    Adapter=dbus.ObjectPath('/org/bluez/hci0'),Icon='audio-headphones'))
keyboard=Device('/org/bluez/hci0/dev_BB','org.bluez.Device1',dict(Alias='Keyboard',Paired=True,Connected=True,
    Adapter=dbus.ObjectPath('/org/bluez/hci0'),Icon='input-keyboard'))
class ObjectManager(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.ObjectManager',in_signature='',out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        return {'/org/bluez/hci0':{'org.bluez.Adapter1':adapter.state},
                '/org/bluez/hci0/dev_AA':{'org.bluez.Device1':headset.state,'org.bluez.Battery1':{'Percentage':dbus.Byte(78)}},
                '/org/bluez/hci0/dev_BB':{'org.bluez.Device1':keyboard.state}}
objects=ObjectManager(bus,'/')
manager=WebKit2.UserContentManager();manager.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(manager)
window=Gtk.Window();window.set_default_size(368,574);window.add(web);window.show_all()
ready=threading.Event();pool=ThreadPoolExecutor(3);errors=[];exit_code=0
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
def snapshot():
    return dict(mode='quick',wifi=True,wifiAvailable=True,bluetooth=bool(adapter.state['Powered']),bluetoothAvailable=True,
                devices=controls.bluetooth_snapshot(settings_backend.bluetooth_objects()),network='Local test connection',
                networkType='wifi',volume=35,outputs=[],sink='Speakers',batteries=[dict(percent=76,status='Discharging')],
                backlights=[dict(id='test',value=60)],**controls.power_snapshot(),**controls.airplane_snapshot())
quick_controls.snapshot=snapshot;notifications.has_unread=lambda:False
hub=SimpleNamespace(status={},quick_busy=False,status_generation=0,settings_busy=False,settings_generation=0,settings_data={},
    store=Store(base/'layout.json',[],base),background=background,refresh_settings=lambda:None,
    refresh_notifications=lambda:None,refresh_status=lambda:None,settings_snapshot=snapshot)
def update():
    data=dict(hub.status,mode='quick',busy=hub.quick_busy,quickTiles=hub.store.state.get('quick_tiles',list(quick_controls.TILES))) if surface.mode=='quick' else dict(hub.settings_data,mode='settings',busy=hub.settings_busy)
    send(dict(type='state',data=data))
surface=SimpleNamespace(mode='quick',send=send,update=update,get_visible=lambda:False)
hub.quick=surface;hub.surfaces={'quick':surface,'settings':surface};hub.update_settings_surface=update
hub.accept_status=lambda data:(setattr(hub,'status',data),update())
for name in ('quick_change','quick_action','settings_change','settings_action'):
    setattr(hub,name,lambda *args,n=name:getattr(Hub,n)(hub,*args))
def on_message(_,result):
    message=json.loads(result.get_js_value().to_string())
    if message['action']=='ready':background(snapshot,lambda data:(hub.accept_status(data),ready.set()),lambda e:errors.append(e));return
    try:Hub.dispatch(hub,surface,message)
    except Exception as error:errors.append(str(error));send(dict(type='error',message=str(error)))
manager.connect('script-message-received::desktop',on_message)
web.load_uri((Path(__file__).parent/'dist/index.html').resolve().as_uri())

def wait(code):
    for _ in range(70):
        if js(code):return
        time.sleep(.1)
    raise AssertionError('Timed out: '+code)
def click(name,aria=True):
    selector='button';prop='getAttribute("aria-label")' if aria else 'textContent.trim()'
    assert js('(()=>{const b=[...document.querySelectorAll("button")].find(b=>b.'+prop+'==='+json.dumps(name)+');if(!b||b.disabled)return false;b.click();return true})()'),name
    time.sleep(.12)
def settled():wait('!window.desktopState.busy')
def capture(name):
    if not output:return
    done=threading.Event()
    def captured(view,result,*_):view.get_snapshot_finish(result).write_to_png(str(output/name));done.set()
    GLib.idle_add(lambda:(web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,captured,None),False)[1])
    assert done.wait(5)
def refresh():GLib.idle_add(lambda:(background(snapshot,hub.accept_status,errors.append),False)[1]);time.sleep(.2)
def verify():
    global exit_code
    try:
        assert ready.wait(8);time.sleep(.2)
        assert js('document.querySelectorAll(".flyout-tile-wrap").length')==8
        capture('quick-settings.png')
        click('Battery saver');wait('window.desktopState.batterySaver===true&&!window.desktopState.busy')
        assert power.state['ActiveProfile']=='power-saver'
        click('Battery saver');wait('window.desktopState.powerProfile==="performance"&&!window.desktopState.busy')
        click('Airplane mode');wait('window.desktopState.airplane===true&&!window.desktopState.busy')
        click('Airplane mode');wait('window.desktopState.airplane===false&&!window.desktopState.busy')
        radio.state['HardwareAirplaneMode']=True;refresh()
        wait('document.querySelector("button[aria-label=\\"Airplane mode\\"]").disabled')
        radio.state['HardwareAirplaneMode']=False;refresh()
        click('Manage Bluetooth');wait('document.querySelector(".flyout-subheading h2")?.textContent==="Bluetooth"')
        assert js('document.body.textContent.includes("78% battery")')
        click('Connect Studio Headphones');wait('!!document.querySelector("button[aria-label=\\"Disconnect Studio Headphones\\"]")&&!window.desktopState.busy')
        assert headset.state['Connected'];capture('bluetooth-devices.png')
        headset.fail=True;click('Disconnect Studio Headphones');settled()
        wait('document.querySelector("[role=alert]")?.textContent.includes("refused")')
        assert headset.state['Connected']
        GLib.idle_add(lambda:(send(dict(type='notice',message='')),False)[1])
        headset.fail=False;click('Disconnect Studio Headphones');wait('!!document.querySelector("button[aria-label=\\"Connect Studio Headphones\\"]")&&!window.desktopState.busy')
        click('Bluetooth');wait('window.desktopState.bluetooth===false&&!window.desktopState.busy')
        assert js('document.querySelector("button[aria-label=\\"Connect Studio Headphones\\"]").disabled')
        click('Bluetooth');wait('window.desktopState.bluetooth===true&&!window.desktopState.busy')
        click('Back to Quick Settings');click('Edit quick settings')
        js('(()=>{document.querySelector("input[aria-label=\\"Show Screenshot\\"]").click();return true})()')
        click('Done',False);time.sleep(.2)
        assert 'screenshot' not in json.loads((base/'layout.json').read_text())['quick_tiles']
        def settings_page():
            surface.mode='settings';hub.settings_data=hub.status.copy();window.resize(1120,760);update();send(dict(type='show',page='power'));return False
        GLib.idle_add(settings_page);wait('!!document.querySelector("select[aria-label=\\"Power mode\\"]")')
        js('(()=>{const s=document.querySelector("select[aria-label=\\"Power mode\\"]");s.value="balanced";s.dispatchEvent(new Event("change",{bubbles:true}));return true})()')
        wait('window.desktopState.powerProfile==="balanced"&&!window.desktopState.busy')
        click('Battery saver');wait('window.desktopState.batterySaver===true&&!window.desktopState.busy')
        click('Battery saver');wait('window.desktopState.powerProfile==="balanced"&&!window.desktopState.busy');capture('power-settings.png')
        GLib.idle_add(lambda:(send(dict(type='show',page='network')),False)[1]);time.sleep(.2)
        click('Airplane mode');wait('window.desktopState.airplane===true&&!window.desktopState.busy')
        click('Airplane mode');wait('window.desktopState.airplane===false&&!window.desktopState.busy')
        GLib.idle_add(lambda:(send(dict(type='show',page='devices')),False)[1]);time.sleep(.2)
        click('Connect Studio Headphones');wait('window.desktopState.devices.some(d=>d.name==="Studio Headphones"&&d.connected)&&!window.desktopState.busy')
        click('Disconnect Studio Headphones');wait('window.desktopState.devices.some(d=>d.name==="Studio Headphones"&&!d.connected)&&!window.desktopState.busy')
        assert not errors,errors
        assert js('window.desktopErrors.length')==0
        print('Native Quick Settings: power restore, airplane mode and hardware lock, device connect/disconnect, rejection, Bluetooth power and tile persistence passed',flush=True)
        print('Native Settings: power-mode dropdown, battery saver, airplane mode and Bluetooth device actions passed',flush=True)
    except Exception:
        import traceback;traceback.print_exc();exit_code=1
    finally:GLib.idle_add(Gtk.main_quit)
threading.Thread(target=verify,daemon=True).start();Gtk.main()
pool.shutdown(wait=True);window.destroy();workspace.cleanup();raise SystemExit(exit_code)
