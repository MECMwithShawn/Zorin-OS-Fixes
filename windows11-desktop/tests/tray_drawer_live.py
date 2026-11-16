#!/usr/bin/python3
"""Tray drawer on private GNOME Wayland with the real Zorin taskbar.

A disposable extension runs the production TrayDrawer, adds stand-in tray
icons and drives the arrow with a virtual pointer. No host settings are touched.
Pass --shots DIR to save folded/open taskbar screenshots.
"""
import base64, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from gnome_live import until, systemd_fixture

ROOT = Path(__file__).resolve().parents[1]
UUID = 'zorin11-tray-test@zorin-os-fixes'
EXTENSION = r'''
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {TrayDrawer} from './tray-drawer.js';
const XML='<node><interface name="local.zorin11.TrayTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="Capture"><arg type="s" direction="out"/></method></interface></node>';
const ICONS=['weather-clear-symbolic','folder-symbolic','mail-unread-symbolic','media-eject-symbolic'];
export default class Test extends Extension {
 enable(){this.settings=this.getSettings('org.gnome.shell.extensions.zorin11');this.buttons=[];
  Main.overview.hide();
  this.pointer=Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
  this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/TrayTest');
  this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.TrayTest',0,null,null);}
 Call(text){const p=JSON.parse(text),panels=(global.zorinTaskbar?.panels??[]).map(x=>x.panel),t=GLib.get_monotonic_time();
  if(p.drawer&&!this.drawer)this.drawer=new TrayDrawer(this.settings);
  if(p.add)for(const panel of panels)for(let i=0;i<p.add;i++){const n=this.buttons.length,b=new PanelMenu.Button(0.5,'tray'+n);b.name='tray'+n;
   b.add_child(new St.Icon({icon_name:ICONS[n%ICONS.length],style_class:'system-status-icon'}));b.menu.addMenuItem(new PopupMenu.PopupMenuItem('Item'));
   panel.addToStatusArea('tray-test-'+n,b,0,'right');this.buttons.push(b);}
  if(p.show!==undefined)this.buttons[p.show[0]].container.visible=p.show[1];
  if(p.only!==undefined)for(const [box,state] of this.drawer._boxes)for(const [child,item] of state.items){if(p.only){item.was=item.want;item.want=false;}else item.want=item.was;this.drawer._syncArrow(state);}
  if(p.enabled!==undefined)this.settings.set_boolean('tray-drawer',p.enabled);
  if(p.sync)this.drawer._sync();
  if(p.toggle!==undefined)this.drawer.toggle(p.toggle);
  if(p.click){const a=[...this.drawer._boxes.values()][0].arrow,[x,y]=a.get_transformed_position(),[w,h]=a.get_transformed_size();
   this.pointer.notify_absolute_motion(t,x+w/2,y+h/2);this.pointer.notify_button(t+1,Clutter.BUTTON_PRIMARY,Clutter.ButtonState.PRESSED);this.pointer.notify_button(t+2,Clutter.BUTTON_PRIMARY,Clutter.ButtonState.RELEASED);}
  if(p.park)this.pointer.notify_absolute_motion(t,640,300);
  return JSON.stringify({open:this.drawer?._open??false,rows:panels.map(panel=>{const box=panel._rightBox;
   const arrow=this.drawer?._boxes.get(box)?.arrow;
   return {width:box.width,last:box.get_last_child()===arrow,arrow:arrow?arrow.visible:null,icon:arrow?.child.icon_name??null,
    hasArrow:box.get_children().some(c=>c.has_style_class_name?.('zorin11-tray-drawer')),
    shown:box.get_children().filter(c=>c.visible&&c!==arrow).map(c=>c.get_first_child()?.name||'?'),
    quick:panel.statusArea.quickSettings?.container.visible??null};})});}
 async CaptureAsync(args,inv){try{const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);inv.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));}catch(e){inv.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.drawer?.destroy();for(const b of this.buttons)b.destroy();this.bus.unexport();Gio.bus_unown_name(this.owner);}
}
'''


def session(temp, shots):
    from gi.repository import Gio, GLib
    ext = temp/'data/gnome-shell/extensions'/UUID
    (ext/'schemas').mkdir(parents=True)
    shutil.copy(ROOT/'gnome-extension/tray-drawer.js', ext)
    shutil.copy(next((ROOT/'gnome-extension/schemas').glob('*.gschema.xml')), ext/'schemas')
    subprocess.run(['glib-compile-schemas', '--strict', str(ext/'schemas')], check=True)
    (ext/'extension.js').write_text(EXTENSION)
    (ext/'metadata.json').write_text(json.dumps({'uuid': UUID, 'name': 'Tray test', 'description': 'test',
                                                 'shell-version': ['46']}))
    sys.path.insert(0, str(ROOT)); import gnome_setup
    taskbar = Gio.Settings.new('org.gnome.shell.extensions.zorin-taskbar')
    taskbar.set_string('panel-element-positions',
                       gnome_setup.appearance(['0'])[gnome_setup.TASKBAR]['panel-element-positions'])
    shell = Gio.Settings.new('org.gnome.shell')
    enabled = ['zorin-taskbar@zorinos.com', UUID]
    shell.set_strv('enabled-extensions', enabled)
    shell.set_strv('disabled-extensions', [p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir()
                                           if p.is_dir() and p.name not in enabled])
    shell.set_string('welcome-dialog-last-shown-version', '46.0')
    Gio.Settings.sync()
    log = (temp/'shell.log').open('w'); children = []
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def call(**p):
        while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
        return json.loads(bus.call_sync('local.zorin11.TrayTest', '/local/zorin11/TrayTest', 'local.zorin11.TrayTest',
                                        'Call', GLib.Variant('(s)', (json.dumps(p),)), None, 0, 3000, None).unpack()[0])
    def shot(name):
        if shots:
            data = bus.call_sync('local.zorin11.TrayTest', '/local/zorin11/TrayTest', 'local.zorin11.TrayTest',
                                 'Capture', None, None, 0, 5000, None).unpack()[0]
            (Path(shots)/f'{name}.png').write_bytes(base64.b64decode(data))
    try:
        children.append(subprocess.Popen([sys.executable, __file__, '--systemd-fixture'], stdout=log, stderr=subprocess.STDOUT))
        time.sleep(.3)
        children.append(subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--virtual-monitor', '1280x800',
                                          '--wayland-display', 'tray-test'], stdout=log, stderr=subprocess.STDOUT))
        until(lambda: call()['rows'])
        call(add=4)
        before = until(lambda: (r if (r := call()['rows'][0])['width'] > 100 else None), seconds=5)
        assert len(before['shown']) >= 4, before
        call(drawer=True)
        row = until(lambda: (r if (r := call()['rows'][0])['width'] < before['width'] - 60 else None), seconds=5)
        assert row['hasArrow'] and row['arrow'] and row['last'] and row['shown'] == [] and row['quick'] is not False, row
        assert row['width'] < before['width'] - 60, (row, before)
        print('PASS tray icons fold behind one arrow; the system button stays', flush=True)
        shot('folded')
        call(click=True)
        row = until(lambda: (r if (r := call()['rows'][0])['shown'] else None), seconds=3)
        assert call()['open'] and len(row['shown']) == len(before['shown']) and row['icon'] == 'pan-end-symbolic', row
        print('PASS clicking the arrow shows every icon again', flush=True)
        shot('open')
        row = call(add=1)['rows'][0]
        assert row['last'] and len(row['shown']) == len(before['shown']) + 1, row
        print('PASS an icon added while open shows, and the arrow stays last', flush=True)
        call(park=True)
        until(lambda: not call()['open'], seconds=6)
        assert call()['rows'][0]['shown'] == []
        print('PASS the drawer folds again after the pointer leaves', flush=True)
        call(show=[0, False]); call(show=[0, True])
        assert call()['rows'][0]['shown'] == [], 'an icon showing itself must stay folded'
        call(show=[0, False]); row = call(toggle=True)['rows'][0]
        assert 'tray0' not in row['shown'] and len(row['shown']) == len(before['shown']), row
        print('PASS icons that hide or show themselves while folded keep that choice', flush=True)
        call(toggle=False)
        assert call(only=True)['rows'][0]['arrow'] is False
        assert call(only=False)['rows'][0]['arrow'] is True
        print('PASS with nothing to fold the arrow hides', flush=True)
        call(show=[0, True])
        row = call(enabled=False, sync=True)['rows'][0]
        assert not row['hasArrow'] and len(row['shown']) == len(before['shown']), row
        print('PASS tray-drawer=false puts every icon back', flush=True)
        assert 'JS ERROR' not in (temp/'shell.log').read_text()
    finally:
        for p in reversed(children):
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()


if '--systemd-fixture' in sys.argv:
    systemd_fixture(); raise SystemExit
if '--session' in sys.argv:
    session(Path(sys.argv[-2]), sys.argv[-1] if sys.argv[-1] != '-' else None); raise SystemExit
shots = sys.argv[sys.argv.index('--shots') + 1] if '--shots' in sys.argv else '-'
with tempfile.TemporaryDirectory(prefix='zorin11-tray-') as directory:
    temp = Path(directory)
    for name in ('runtime', 'config', 'data', 'cache'):
        (temp/name).mkdir(mode=0o700)
    env = dict(os.environ, HOME=str(temp), XDG_RUNTIME_DIR=str(temp/'runtime'), XDG_CONFIG_HOME=str(temp/'config'),
               XDG_DATA_HOME=str(temp/'data'), XDG_CACHE_HOME=str(temp/'cache'), GSETTINGS_BACKEND='keyfile',
               XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland', GNOME_SHELL_SESSION_MODE='user',
               WAYLAND_DISPLAY='tray-test', GIO_USE_VFS='local', GTK_USE_PORTAL='0')
    result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--session', str(temp), shots],
                            env=env, capture_output=True, text=True, timeout=120)
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr[-3000:])
        if (temp/'shell.log').exists():
            print('\n'.join(l for l in (temp/'shell.log').read_text().splitlines() if 'xtension' in l or 'JS' in l or 'rror' in l)[-4000:])
    raise SystemExit(result.returncode)
