"""Real GTK picker and pairing agent against BlueZ fixtures on a private bus."""
import os,sys,subprocess,tempfile,json,time
from pathlib import Path
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory() as private:
        env=dict(os.environ,GDK_BACKEND='x11',GIO_USE_VFS='local',GTK_USE_PORTAL='0',GSETTINGS_BACKEND='memory',XDG_CONFIG_HOME=private,
                 ZORIN11_HOST_BUS=os.environ.get('DBUS_SESSION_BUS_ADDRESS',''))
        raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private',*sys.argv[1:]],env=env,timeout=60).returncode)
assert os.environ['DBUS_SESSION_BUS_ADDRESS']!=os.environ.get('ZORIN11_HOST_BUS')
os.environ['DBUS_SYSTEM_BUS_ADDRESS']=os.environ['DBUS_SESSION_BUS_ADDRESS']
import dbus,dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import bluetooth_pairing as pairing
from gi.repository import Gtk,GLib,Gdk
bus=dbus.SessionBus(mainloop=DBusGMainLoop());name=dbus.service.BusName('org.bluez',bus)
objects={};agents={};pairs=[];codes=[];leases={'other-client'}
class Failed(dbus.DBusException):_dbus_error_name='org.bluez.Error.AuthenticationCanceled'
class Properties(dbus.service.Object):
    def __init__(self,path,interface,state):
        super().__init__(bus,path);self.state=state;self.path=path;objects[path]={interface:state}
    @dbus.service.method(pairing.PROPERTIES,in_signature='ssv',out_signature='')
    def Set(self,interface,prop,value):self.state[prop]=value
class Adapter(Properties):
    @dbus.service.method(pairing.ADAPTER,in_signature='',out_signature='',sender_keyword='sender')
    def StartDiscovery(self,sender=None):leases.add(sender)
    @dbus.service.method(pairing.ADAPTER,in_signature='',out_signature='',sender_keyword='sender')
    def StopDiscovery(self,sender=None):leases.discard(sender)
adapter=Adapter('/org/bluez/hci0',pairing.ADAPTER,dict(Powered=True))
class Manager(dbus.service.Object):
    @dbus.service.method(pairing.MANAGER,in_signature='os',out_signature='',sender_keyword='sender')
    def RegisterAgent(self,path,capability,sender=None):agents[sender]=path;assert capability=='KeyboardDisplay'
    @dbus.service.method(pairing.MANAGER,in_signature='o',out_signature='',sender_keyword='sender')
    def UnregisterAgent(self,path,sender=None):agents.pop(sender,None)
manager=Manager(bus,'/org/bluez')
class ObjectManager(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.ObjectManager',in_signature='',out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):return objects
object_manager=ObjectManager(bus,'/')
class Device(Properties):
    mode='confirm';pending=None
    @dbus.service.method(pairing.DEVICE,in_signature='',out_signature='',async_callbacks=('reply','error'),sender_keyword='sender')
    def Pair(self,reply,error,sender=None):
        pairs.append(self.path);self.pending=error
        agent=dbus.Interface(bus.get_object(sender,agents[sender],introspect=False),pairing.AGENT)
        def accepted(*values):
            codes.extend(values);self.state['Paired']=True;self.pending=None;reply()
        if self.mode=='confirm':agent.RequestConfirmation(self.path,dbus.UInt32(7321),reply_handler=accepted,error_handler=error)
        elif self.mode=='passkey':agent.RequestPasskey(self.path,reply_handler=accepted,error_handler=error)
        elif self.mode=='pin':agent.RequestPinCode(self.path,reply_handler=accepted,error_handler=error)
        elif self.mode=='display':agent.DisplayPasskey(self.path,dbus.UInt32(123456),dbus.UInt16(0),reply_handler=lambda:None,error_handler=error)
        else:error(Failed('The device refused pairing'))
    @dbus.service.method(pairing.DEVICE,in_signature='',out_signature='')
    def Connect(self):self.state['Connected']=True
    @dbus.service.method(pairing.DEVICE,in_signature='',out_signature='')
    def CancelPairing(self):
        if self.pending:self.pending(Failed('Pairing canceled'));self.pending=None

def device(ident,alias,number):
    return Device('/org/bluez/hci0/dev_'+ident,pairing.DEVICE,dict(Alias=alias,Address=f'AA:BB:CC:DD:EE:{number:02X}',Adapter=dbus.ObjectPath('/org/bluez/hci0'),Paired=False,Connected=False,RSSI=dbus.Int16(-40)))
headphones=device('AA','Test AirPods',1);keyboard=device('BB','Test Keyboard',2);legacy=device('CC','Test PIN',3);display=device('DD','Test Display',4)
omni=[device('OMNI'+str(i),'Omni',i+10) for i in range(84)]
window=pairing.PairingWindow()
provider=Gtk.CssProvider();provider.load_from_path(str(Path(__file__).with_name('native-controls.css')))
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def pump(seconds=.08):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)
def wait(fn,timeout=6):
    stop=time.monotonic()+timeout
    while time.monotonic()<stop:
        if fn():return
        pump(.04)
    raise AssertionError('Condition not confirmed; '+window.status.get_text())
def descendants(widget):
    yield widget
    if isinstance(widget,Gtk.Container):
        for child in widget.get_children():yield from descendants(child)
def button(label,root=window):
    return next(w for w in descendants(root) if isinstance(w,Gtk.Button) and w.get_label()==label)
def choose(item):
    window.search.set_text(item.state['Alias']);pump(.2)
    row=next(w for w in window.list.get_children() if w.get_accessible().get_name()==item.state['Alias']+', '+item.state['Address'])
    row.clicked();pump(.05)
    dialog=next(w for w in Gtk.Window.list_toplevels() if isinstance(w,Gtk.MessageDialog) and w!=window.prompt_dialog)
    dialog.response(Gtk.ResponseType.OK)
def capture(name):
    if '--output' not in sys.argv:return
    folder=Path(sys.argv[sys.argv.index('--output')+1]);folder.mkdir(parents=True,exist_ok=True)
    pump(.15);width,height=window.get_size()
    Gdk.pixbuf_get_from_window(window.get_window(),0,0,width,height).savev(str(folder/name),'png',[],[])
try:
    wait(lambda:len(window.list.get_children())==5)
    assert len(leases)==2
    capture('grouped-picker.png')
    group=next(w for w in window.list.get_children() if '84 entries' in (w.get_label() or ''));group.clicked();pump(.1)
    assert len(window.list.get_children())==89
    next(w for w in window.list.get_children() if '84 entries' in (w.get_label() or '')).clicked();pump(.1)
    assert len(window.list.get_children())==5
    choose(headphones);wait(lambda:window.prompt_dialog is not None)
    assert '007321' in window.prompt_dialog.get_property('secondary-text')
    window.prompt_dialog.response(Gtk.ResponseType.CANCEL);wait(lambda:window.session.target is None)
    assert not headphones.state['Paired']
    choose(headphones);wait(lambda:window.prompt_dialog is not None)
    window.prompt_dialog.response(Gtk.ResponseType.OK);wait(lambda:headphones.state['Connected'] and window.session.target is None)
    assert headphones.state['Trusted'] and headphones.state['Paired']
    assert pairs==[headphones.path,headphones.path]
    for dev,mode,text,value in [(keyboard,'passkey','000123',123),(legacy,'pin','1234','1234')]:
        dev.mode=mode;choose(dev);wait(lambda:window.prompt_dialog is not None)
        entry=next(w for w in descendants(window.prompt_dialog) if isinstance(w,Gtk.Entry));entry.set_text(text)
        window.prompt_dialog.response(Gtk.ResponseType.OK);wait(lambda:dev.state['Connected'] and window.session.target is None)
        assert codes[-1]==value
    display.mode='failed';choose(display);wait(lambda:window.session.target is None and 'refused' in window.status.get_text())
    display.mode='display';choose(display);wait(lambda:window.prompt_dialog is not None)
    assert '123456' in window.prompt_dialog.get_property('secondary-text')
    window.prompt_dialog.response(Gtk.ResponseType.CANCEL);wait(lambda:window.session.target is None)
    assert not display.state['Paired']
    window.search.set_text('AirPods');pump(.2);assert len(window.list.get_children())==1
    assert isinstance(window.list.get_children()[0],Gtk.Label), 'Paired AirPods still appear as available'
    window.search.set_text('Omni');pump(.2);capture('search-picker.png')
    window.session.start();wait(lambda:len(leases)==2)
    window.session.stop();pump(.1);assert leases=={'other-client'}
    window.session.start();wait(lambda:len(leases)==2)
    # A vanished advertisement cannot start pairing through a stale selection.
    old=objects.pop(display.path);count=len(pairs);window.session.pair(display.path)
    wait(lambda:'no longer available' in window.status.get_text());assert len(pairs)==count
    objects[display.path]=old;window.session.refresh();pump(.1)
    choose(display);wait(lambda:window.prompt_dialog is not None)
    window.destroy();pump(.15)
    assert leases=={'other-client'} and not agents
    assert not display.state['Paired']
    print('Native pairing passed: 84 duplicate names grouped/expanded, search, exact address selection, confirmation/rejection, numeric/legacy PIN, displayed passkey cancellation, trust/connect, retry, and scan cleanup without stopping another client.',flush=True)
finally:
    if not window.session.closed:window.destroy();pump(.1)
