"""On-demand Bluetooth discovery and pairing, without an endless nearby list."""
import re
from pathlib import Path
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

DEVICE = 'org.bluez.Device1'
ADAPTER = 'org.bluez.Adapter1'
PROPERTIES = 'org.freedesktop.DBus.Properties'
AGENT = 'org.bluez.Agent1'
MANAGER = 'org.bluez.AgentManager1'
AGENT_PATH = '/local/zorin11/PairingAgent'


def nearby_groups(objects, query=''):
    """Group display names only; every address retains its own selectable identity."""
    groups = {}
    query = query.strip().casefold()
    for path, interfaces in objects.items():
        info = interfaces.get(DEVICE, {})
        if not info or info.get('Paired') or info.get('Blocked') or ('Connectable' in info and not info['Connectable']):
            continue
        if not objects.get(info.get('Adapter'), {}).get(ADAPTER, {}).get('Powered'):
            continue
        address = str(info.get('Address', ''))
        name = str(info.get('Alias') or info.get('Name') or '')
        if not name or re.fullmatch(r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', name):
            name = 'Unnamed devices'
        if query and query not in name.casefold() and query not in address.casefold():
            continue
        item = dict(id=str(path), name=name, address=address, icon=str(info.get('Icon') or 'bluetooth'),
                    signal=int(info['RSSI']) if 'RSSI' in info else None)
        groups.setdefault(name.casefold(), dict(name=name, devices=[]))['devices'].append(item)
    for group in groups.values():
        group['devices'].sort(key=lambda d: (-(d['signal'] if d['signal'] is not None else -999), d['address'], d['id']))
    return sorted(groups.values(), key=lambda g: (g['name']=='Unnamed devices', g['name'].casefold()))


class Rejected(dbus.DBusException):
    _dbus_error_name = 'org.bluez.Error.Rejected'


class PairingAgent(dbus.service.Object):
    def __init__(self, session):
        self.session = session
        super().__init__(session.bus, AGENT_PATH)

    def check(self, sender, device=None):
        if sender != self.session.owner or (device is not None and str(device) != self.session.target):
            raise Rejected('This pairing request was not initiated here.')

    @dbus.service.method(AGENT, in_signature='', out_signature='', sender_keyword='sender')
    def Release(self, sender=None):
        self.check(sender)
        self.session.registered = False

    @dbus.service.method(AGENT, in_signature='o', out_signature='s', async_callbacks=('reply','error'), sender_keyword='sender')
    def RequestPinCode(self, device, reply, error, sender=None):
        self.check(sender, device)
        self.session.prompt('pin', '', reply, error)

    @dbus.service.method(AGENT, in_signature='o', out_signature='u', async_callbacks=('reply','error'), sender_keyword='sender')
    def RequestPasskey(self, device, reply, error, sender=None):
        self.check(sender, device)
        self.session.prompt('passkey', '', lambda value:reply(dbus.UInt32(int(value))), error)

    @dbus.service.method(AGENT, in_signature='ou', out_signature='', async_callbacks=('reply','error'), sender_keyword='sender')
    def RequestConfirmation(self, device, passkey, reply, error, sender=None):
        self.check(sender, device)
        self.session.prompt('confirm', f'{int(passkey):06d}', reply, error)

    @dbus.service.method(AGENT, in_signature='o', out_signature='', async_callbacks=('reply','error'), sender_keyword='sender')
    def RequestAuthorization(self, device, reply, error, sender=None):
        self.check(sender, device)
        self.session.prompt('authorize', '', reply, error)

    @dbus.service.method(AGENT, in_signature='os', out_signature='', sender_keyword='sender')
    def DisplayPinCode(self, device, pincode, sender=None):
        self.check(sender, device)
        self.session.prompt('display', str(pincode), None, None)

    @dbus.service.method(AGENT, in_signature='ouq', out_signature='', sender_keyword='sender')
    def DisplayPasskey(self, device, passkey, entered, sender=None):
        self.check(sender, device)
        self.session.prompt('display', f'{int(passkey):06d}', None, None)

    @dbus.service.method(AGENT, in_signature='os', out_signature='', sender_keyword='sender')
    def AuthorizeService(self, device, uuid, sender=None):
        self.check(sender, device)

    @dbus.service.method(AGENT, in_signature='', out_signature='', sender_keyword='sender')
    def Cancel(self, sender=None):
        self.check(sender)
        self.session.dismiss()


class PairingSession:
    def __init__(self, changed, status, prompt, dismiss):
        self.changed, self.status, self.prompt, self.dismiss = changed, status, prompt, dismiss
        self.bus = dbus.SystemBus(private=True, mainloop=DBusGMainLoop())
        self.bus.set_exit_on_disconnect(False)
        self.owner = self.bus.get_name_owner('org.bluez')
        self.agent = PairingAgent(self)
        self.objects = {}; self.started = set(); self.starting = set()
        self.scanning = False; self.closed = False; self.registered = False
        self.target = None; self.pending = False; self.waiters = []; self.timer = 0; self.deadline = 0

    def call(self, path, interface, method, args=(), done=lambda *_:None, failed=None, timeout=5):
        if self.closed: return
        def failure(error):
            if not self.closed: (failed or self.failure)(error)
        def success(*values):
            if not self.closed: done(*values)
        try:
            obj = self.bus.get_object('org.bluez', path, introspect=False)
            getattr(dbus.Interface(obj, interface), method)(*args, reply_handler=success, error_handler=failure, timeout=timeout)
        except dbus.DBusException as error: failure(error)

    def failure(self, error):
        self.status(str(error).split(': ',1)[-1])

    def refresh(self, done=None):
        if self.closed: return False
        if done: self.waiters.append(done)
        if self.pending: return True
        self.pending = True
        def received(objects):
            self.pending = False; self.objects = objects; self.changed(objects)
            waiters,self.waiters=self.waiters,[]
            for callback in waiters: callback()
        def failed(error):
            self.pending = False; self.waiters=[]; self.failure(error)
        self.call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects', done=received, failed=failed)
        return True

    def start(self):
        if self.closed or self.scanning or self.target: return
        self.scanning = True; self.status('Searching nearby… Put your device in pairing mode.')
        if not self.timer: self.timer = GLib.timeout_add_seconds(1, self.refresh)
        if self.deadline: GLib.source_remove(self.deadline)
        self.deadline = GLib.timeout_add_seconds(60, self.stop)
        def begin():
            if not self.scanning: return
            adapters = [str(p) for p,v in self.objects.items() if v.get(ADAPTER,{}).get('Powered')]
            if not adapters:
                self.stop(); self.status('Turn on Bluetooth to search for a device.'); return
            for path in adapters:
                self.starting.add(path)
                def started(p=path):
                    self.starting.discard(p); self.started.add(p)
                    if not self.scanning: self.stop()
                def failed(error,p=path):
                    self.starting.discard(p); self.failure(error)
                self.call(path, ADAPTER, 'StartDiscovery', done=started, failed=failed)
        self.refresh(begin)

    def stop(self):
        self.scanning = False
        if self.deadline: GLib.source_remove(self.deadline); self.deadline = 0
        for path in list(self.started):
            self.started.discard(path)
            self.call(path, ADAPTER, 'StopDiscovery', failed=lambda _e:None)
        if not self.target: self.status('Search stopped. Choose a device or search again.')
        return False

    def pair(self, ident):
        if self.target: return
        # Re-read at the moment of selection; never trust a stale row or name.
        def begin():
            if self.target or self.closed: return
            devices = [d for g in nearby_groups(self.objects) for d in g['devices']]
            if ident not in {d['id'] for d in devices}:
                self.status('This device is no longer available. Search again.'); return
            self.target = ident; self.stop(); self.status('Pairing… Follow any instructions on your device.')
            def pair_now():
                self.call(ident, DEVICE, 'Pair', done=paired, failed=failed, timeout=90)
            def registered():
                self.registered = True; pair_now()
            def failed(error):
                self.dismiss(); self.target = None; self.failure(error); self.refresh()
            def paired():
                self.dismiss()
                self.call(ident, PROPERTIES, 'Set', (DEVICE,'Trusted',dbus.Boolean(True)), done=trusted, failed=trust_failed)
            def trust_failed(error):
                self.target = None; self.status('Paired, but automatic reconnection could not be enabled: '+str(error)); self.refresh()
            def trusted():
                self.call(ident, DEVICE, 'Connect', done=connected, failed=connect_failed, timeout=20)
            def connected():
                self.target = None; self.status('Your device is paired and connected.'); self.refresh()
            def connect_failed(error):
                self.target = None; self.status('Paired. Connect it from Bluetooth settings when it is ready. '+str(error)); self.refresh()
            if self.registered: pair_now()
            else: self.call('/org/bluez', MANAGER, 'RegisterAgent', (dbus.ObjectPath(AGENT_PATH),'KeyboardDisplay'), done=registered, failed=failed)
        self.refresh(begin)

    def close(self):
        if self.closed: return
        self.dismiss()
        if self.target: self.call(self.target, DEVICE, 'CancelPairing', failed=lambda _e:None)
        self.stop()
        if self.timer: GLib.source_remove(self.timer); self.timer = 0
        if self.registered: self.call('/org/bluez', MANAGER, 'UnregisterAgent', (dbus.ObjectPath(AGENT_PATH),), failed=lambda _e:None)
        self.bus.flush(); self.closed = True
        self.agent.remove_from_connection(); self.bus.close()


class PairingWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title='Add a Bluetooth device')
        self.set_default_size(560,620); self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name('bluetooth'); self.objects={}; self.expanded=set(); self.signature=None
        self.prompt_dialog=None; self.prompt_error=None; self.session=None
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);box.set_border_width(24);self.add(box)
        heading=Gtk.Label(xalign=0);heading.set_markup('<span size="x-large" weight="bold">Add a device</span>');box.pack_start(heading,False,False,0)
        hint=Gtk.Label(label='Choose your Bluetooth device. Repeated names are grouped; expand a group to select an address.',xalign=0)
        hint.set_line_wrap(True);box.pack_start(hint,False,False,0)
        self.search=Gtk.SearchEntry();self.search.set_placeholder_text('Search by device name or address');self.search.get_accessible().set_name('Search Bluetooth devices')
        self.search.connect('search-changed',lambda *_:self.render());box.pack_start(self.search,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_min_content_height(300)
        self.list=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);scroll.add(self.list);box.pack_start(scroll,True,True,0)
        self.status=Gtk.Label(xalign=0);self.status.set_line_wrap(True);self.status.set_selectable(True);box.pack_start(self.status,False,False,0)
        footer=Gtk.Box(spacing=10);box.pack_end(footer,False,False,0)
        self.scan=Gtk.Button(label='Stop search');self.scan.connect('clicked',self.toggle_scan);footer.pack_start(self.scan,False,False,0)
        close=Gtk.Button(label='Close');close.connect('clicked',lambda *_:self.destroy());footer.pack_end(close,False,False,0)
        self.connect('destroy',lambda *_:self.session.close() if self.session else None)
        self.connect('key-press-event',self.key)
        try:
            self.session=PairingSession(self.receive,self.set_status,self.prompt,self.dismiss_prompt)
            self.session.start()
        except dbus.DBusException as error:
            self.set_status('Bluetooth is unavailable: '+str(error));self.scan.set_sensitive(False)
        self.show_all();self.search.grab_focus()

    def key(self,_window,event):
        if event.keyval==Gdk.KEY_Escape:self.destroy();return True
        return False

    def set_status(self,text):
        self.status.set_text(text)
        if self.session:
            self.scan.set_label('Stop search' if self.session.scanning else 'Search again')
            self.scan.set_sensitive(not bool(self.session.target))
            self.list.set_sensitive(not bool(self.session.target))

    def toggle_scan(self,*_):
        if self.session.scanning:self.session.stop()
        else:self.session.start()

    def receive(self,objects):
        self.objects=objects;self.render()

    def render(self):
        groups=nearby_groups(self.objects,self.search.get_text())
        signature=repr((groups,sorted(self.expanded)))
        if signature==self.signature:return
        self.signature=signature
        focused=self.get_focus()
        focus_name=focused.get_accessible().get_name() if focused and focused.is_ancestor(self.list) else None
        for child in self.list.get_children():child.destroy()
        if not groups:
            label=Gtk.Label(label='No matching devices. Check the name and put your device in pairing mode.',xalign=0)
            label.set_line_wrap(True);self.list.pack_start(label,False,False,16)
        for group in groups:
            devices=group['devices'];name=group['name']
            if len(devices)==1:self.device_row(devices[0])
            else:
                button=Gtk.Button(label=('▾ ' if name in self.expanded else '▸ ')+name+'  ·  '+str(len(devices))+' entries')
                button.get_child().set_ellipsize(3);button.set_tooltip_text(name)
                button.set_halign(Gtk.Align.FILL);button.connect('clicked',self.expand,name);self.list.pack_start(button,False,False,0)
                if name in self.expanded:
                    for device in devices:self.device_row(device,True)
        self.list.show_all()
        if focus_name:
            for child in self.list.get_children():
                if child.get_accessible().get_name()==focus_name:child.grab_focus();break

    def expand(self,_button,name):
        if name in self.expanded:self.expanded.remove(name)
        else:self.expanded.add(name)
        self.render()

    def device_row(self,device,indent=False):
        button=Gtk.Button();button.set_margin_start(16 if indent else 0)
        row=Gtk.Box(spacing=12);row.set_border_width(10);button.add(row)
        row.pack_start(Gtk.Image.new_from_icon_name(device['icon'],Gtk.IconSize.DND),False,False,0)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);row.pack_start(text,True,True,0)
        name=Gtk.Label(label=device['name'],xalign=0);name.set_ellipsize(3);text.pack_start(name,False,False,0)
        signal=device['signal'];strength='Signal unavailable' if signal is None else 'Strong signal' if signal>=-60 else 'Medium signal' if signal>=-80 else 'Weak signal'
        detail=Gtk.Label(label=device['address']+' · '+strength,xalign=0);text.pack_start(detail,False,False,0)
        button.get_accessible().set_name(device['name']+', '+device['address'])
        button.connect('clicked',lambda *_:self.confirm_pair(device));self.list.pack_start(button,False,False,0)

    def confirm_pair(self,device):
        if self.session.target:return
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,destroy_with_parent=True,message_type=Gtk.MessageType.QUESTION,text='Pair with '+device['name']+'?')
        dialog.format_secondary_text('Device address: '+device['address'])
        dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Pair',Gtk.ResponseType.OK)
        def response(d,result):
            d.destroy()
            if result==Gtk.ResponseType.OK:self.session.pair(device['id'])
        dialog.connect('response',response);dialog.show_all()

    def dismiss_prompt(self):
        error=self.prompt_error;self.prompt_error=None
        if self.prompt_dialog:
            self.prompt_dialog.destroy();self.prompt_dialog=None
        if error:error(Rejected('Pairing canceled.'))

    def prompt(self,kind,code,reply,error):
        self.dismiss_prompt()
        titles={'confirm':'Does this code match your device?','authorize':'Allow this device to pair?',
                'pin':'Enter the device PIN','passkey':'Enter the device passkey','display':'Enter this code on your Bluetooth device'}
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,destroy_with_parent=True,message_type=Gtk.MessageType.QUESTION,text=titles[kind])
        self.prompt_dialog=dialog;self.prompt_error=error
        dialog.format_secondary_text(code+ ('\nPress Enter on that device when finished.' if kind=='display' else ''))
        entry=None
        if kind in ('pin','passkey'):
            entry=Gtk.Entry();entry.set_max_length(6 if kind=='passkey' else 16);entry.get_accessible().set_name('Pairing code')
            dialog.get_content_area().pack_start(entry,False,False,8)
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
        if kind!='display':dialog.add_button('Confirm',Gtk.ResponseType.OK)
        def response(d,result):
            if result==Gtk.ResponseType.OK and entry:
                value=entry.get_text()
                if not value or not value.isascii() or (kind=='passkey' and not value.isdigit()):return
            self.prompt_error=None;self.prompt_dialog=None;d.destroy()
            if result!=Gtk.ResponseType.OK:
                if error:error(Rejected('Pairing canceled.'))
                elif self.session.target:self.session.call(self.session.target,DEVICE,'CancelPairing')
            elif entry:reply(value)
            else:reply()
        dialog.connect('response',response);dialog.show_all()
        if entry:entry.grab_focus()


class Application(Gtk.Application):
    def __init__(self):super().__init__(application_id='local.zorin11.BluetoothPairing')
    def do_activate(self):
        if self.get_windows():self.get_windows()[0].present();return
        provider=Gtk.CssProvider();provider.load_from_path(str(Path(__file__).with_name('native-controls.css')))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        window=PairingWindow();self.add_window(window);window.present()

if __name__=='__main__':
    import sys
    raise SystemExit(Application().run(sys.argv))
