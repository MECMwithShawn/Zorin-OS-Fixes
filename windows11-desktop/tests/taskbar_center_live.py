#!/usr/bin/python3
"""Adaptive taskbar centering on private GNOME Wayland with the real Zorin taskbar.

A disposable extension runs the production TaskbarCentering watcher and adds
synthetic app/tray widths. No host settings or windows are touched.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from gnome_live import until, systemd_fixture

ROOT = Path(__file__).resolve().parents[1]
UUID = 'zorin11-center-test@zorin-os-fixes'
EXTENSION = r'''
import Gio from 'gi://Gio';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {TaskbarCentering} from './taskbar-centering.js';
const XML='<node><interface name="local.zorin11.CenterTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>';
export default class Test extends Extension {
 enable(){this.settings=this.getSettings('org.gnome.shell.extensions.zorin11');this.taskbar=new Gio.Settings({schema_id:'org.gnome.shell.extensions.zorin-taskbar'});
  this.centering=new TaskbarCentering(this.settings);this.actors=[];
  this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/CenterTest');
  this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.CenterTest',0,null,null);}
 Call(text){const p=JSON.parse(text),panels=global.zorinTaskbar?.panels??[];
  if(p.layout){for(const a of this.actors)a.destroy();this.actors=[];
   for(const panel of panels){const add=(box,width)=>{const a=new St.Widget({width,height:32});box.add_child(a);this.actors.push(a);};
    if(p.layout.apps)add(panel.taskbar._box,p.layout.apps);
    for(let i=0;i<p.layout.tray;i++)add(panel._rightBox??panel.panel._rightBox,100);}}
  if(p.enabled!==undefined)this.settings.set_boolean('adaptive-taskbar-center',p.enabled);
  return JSON.stringify({mode:this.centering._panelSettings?.getPanelElementPositions(this.taskbar,0)?.find(e=>e.element==='taskbar')?.position,positions:this.taskbar.get_string('panel-element-positions'),rows:panels.map(panel=>{
   const t=panel.taskbar.actor,adj=panel.taskbar._scrollView.hadjustment,tray=panel._rightBox??panel.panel._rightBox;
   return {appX:t.get_transformed_position()[0],appWidth:t.width,trayX:tray.get_transformed_position()[0],
    panelX:panel.panel.get_transformed_position()[0],panelWidth:panel.panel.width,overflow:adj.upper-adj.page_size};})});}
 disable(){this.centering.destroy();for(const a of this.actors)a.destroy();this.bus.unexport();Gio.bus_unown_name(this.owner);}
}
'''


def session(temp):
    from gi.repository import Gio, GLib
    ext = temp/'data/gnome-shell/extensions'/UUID
    (ext/'schemas').mkdir(parents=True)
    for name in ('taskbar-centering.js', 'taskbar-center-state.js'):
        shutil.copy(ROOT/'gnome-extension'/name, ext/name)
    shutil.copy(next((ROOT/'gnome-extension/schemas').glob('*.gschema.xml')), ext/'schemas')
    subprocess.run(['glib-compile-schemas', '--strict', str(ext/'schemas')], check=True)
    (ext/'extension.js').write_text(EXTENSION)
    (ext/'metadata.json').write_text(json.dumps({'uuid': UUID, 'name': 'Center test', 'description': 'test',
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
    def start(args):
        p = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT); children.append(p); return p
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def call(**p):
        while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
        return json.loads(bus.call_sync('local.zorin11.CenterTest', '/local/zorin11/CenterTest', 'local.zorin11.CenterTest',
                                        'Call', GLib.Variant('(s)', (json.dumps(p),)), None, 0, 3000, None).unpack()[0])
    def mode():  # as Zorin Taskbar reads it for this monitor
        return call()['mode']
    try:
        start(['/usr/bin/python3', __file__, '--systemd-fixture']); time.sleep(.3)
        # 1280 logical pixels: a 1920-pixel screen at 150%.
        start(['gnome-shell', '--headless', '--wayland', '--virtual-monitor', '1280x800', '--wayland-display', 'center-test'])
        until(lambda: call()['rows'] and call()['mode'])
        assert mode() == 'centerMonitor'
        # Few apps, small tray: apps sit on the screen centre and stay there.
        call(layout=dict(apps=144, tray=0)); time.sleep(3)
        row = call()['rows'][0]
        assert mode() == 'centerMonitor' and row['overflow'] <= 1, row
        # Many apps and a crowded tray: screen-centred apps would be clipped,
        # so they move into the free space and every app is shown.
        call(layout=dict(apps=500, tray=2))
        until(lambda: mode() == 'centered', seconds=10)
        row = until(lambda: (r if (r := call()['rows'][0])['overflow'] <= 1 else None))
        assert row['appWidth'] >= 500 and row['appX'] + row['appWidth'] <= row['trayX'] + 1, row
        print('PASS crowded taskbar moves into the free space; no app is clipped', flush=True)
        # Room again: back to the screen centre.
        call(layout=dict(apps=144, tray=1))
        until(lambda: mode() == 'centerMonitor', seconds=10)
        row = call()['rows'][0]
        assert abs(row['appX'] + row['appWidth'] / 2 - 640) < 40 and row['overflow'] <= 1, row
        time.sleep(3); assert mode() == 'centerMonitor', 'must not flap'
        print('PASS fitting apps return to the screen centre and stay there', flush=True)
        # Turned off: the user's chosen centering is left alone.
        call(enabled=False); call(layout=dict(apps=500, tray=2)); time.sleep(4)
        assert mode() == 'centerMonitor'
        print('PASS adaptive-taskbar-center=false leaves the taskbar setting unchanged', flush=True)
        assert 'JS ERROR' not in (temp/'shell.log').read_text()
    finally:
        for p in reversed(children):
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()


if '--systemd-fixture' in sys.argv:
    systemd_fixture(); raise SystemExit
if '--session' in sys.argv:
    session(Path(sys.argv[-1])); raise SystemExit
with tempfile.TemporaryDirectory(prefix='zorin11-center-') as directory:
    temp = Path(directory)
    for name in ('runtime', 'config', 'data', 'cache'):
        (temp/name).mkdir(mode=0o700)
    env = dict(os.environ, HOME=str(temp), XDG_RUNTIME_DIR=str(temp/'runtime'), XDG_CONFIG_HOME=str(temp/'config'),
               XDG_DATA_HOME=str(temp/'data'), XDG_CACHE_HOME=str(temp/'cache'), GSETTINGS_BACKEND='keyfile',
               XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland', GNOME_SHELL_SESSION_MODE='user',
               WAYLAND_DISPLAY='center-test', GIO_USE_VFS='local', GTK_USE_PORTAL='0')
    result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--session', str(temp)],
                            env=env, capture_output=True, text=True, timeout=120)
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr[-3000:])
        if (temp/'shell.log').exists():
            print((temp/'shell.log').read_text()[-4000:])
    raise SystemExit(result.returncode)
