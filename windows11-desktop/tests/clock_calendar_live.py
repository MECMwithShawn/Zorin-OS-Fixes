#!/usr/bin/python3
"""Taskbar clock opens the merged notifications-and-calendar panel, in a private headless GNOME Shell; never touches the signed-in session."""
import base64,json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11@zorin-os-fixes'
FIXTURE_JS=r'''
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const XML='<node><interface name="local.zorin11.ClockTest"><method name="Clocks"><arg direction="out" type="s"/></method><method name="Click"><arg direction="in" type="i"/><arg direction="out" type="s"/></method><method name="Toggle"><arg direction="out" type="s"/></method><method name="Close"><arg direction="out" type="s"/></method><method name="SetEnabled"><arg direction="in" type="b"/><arg direction="out" type="s"/></method><method name="Capture"><arg direction="out" type="s"/></method></interface></node>';
const panels=()=>global.zorinTaskbar?.panels?.map(p=>p.panel)||[Main.panel];
export default class Fixture extends Extension {
 enable(){this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/ClockTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.ClockTest',0,null,null);
  this.pointer=Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);}
 Clocks(){return JSON.stringify(panels().map(panel=>{const d=panel.statusArea.dateMenu;if(!d)return null;
  const [x,y]=d.get_transformed_position(),[w,h]=d.get_transformed_size();
  return {mapped:d.is_mapped(),open:!!d.menu?.isOpen,rect:[x,y,w,h],bell:!!panel.statusArea['zorin11-notifications']};}));}
 Click(i){const d=panels()[i].statusArea.dateMenu,[x,y]=d.get_transformed_position(),[w,h]=d.get_transformed_size();
  const t=GLib.get_monotonic_time();this.pointer.notify_absolute_motion(t,x+w/2,y+h/2);
  this.pointer.notify_button(t+1000,Clutter.BUTTON_PRIMARY,Clutter.ButtonState.PRESSED);
  this.pointer.notify_button(t+2000,Clutter.BUTTON_PRIMARY,Clutter.ButtonState.RELEASED);return 'ok';}
 Toggle(){Main.panel.toggleCalendar();return 'ok';}
 Close(){for(const p of panels())p.statusArea.dateMenu?.menu?.close();return 'ok';}
 SetEnabled(on){const m=Main.extensionManager;on?m.enableExtension('zorin11@zorin-os-fixes'):m.disableExtension('zorin11@zorin-os-fixes');return 'ok';}
 async CaptureAsync(_args,invocation){try{
  const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);
  invocation.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));
 }catch(e){invocation.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.pointer=null;this.bus.unexport();Gio.bus_unown_name(this.owner);}
}
'''

def session(temp,output):
    from gi.repository import Gio,GLib
    sys.path[:0]=[str(ROOT),str(ROOT/'companion')]
    from gnome_bridge import call
    import gnome_setup
    extensions=temp/'data/gnome-shell/extensions'
    extension=extensions/UUID
    shutil.copytree(ROOT/'gnome-extension',extension)
    for icon in ('start.svg','search.svg','taskview.svg'):shutil.copy(ROOT/'companion'/icon,extension/icon)
    subprocess.run(['glib-compile-schemas',str(extension/'schemas')],check=True)
    # A stand-in companion records what the extension asks it to open.
    runtime=temp/'companion';runtime.mkdir()
    launches=temp/'launches.txt'
    (runtime/'app.py').write_text(f'import sys\nopen({str(launches)!r},"a").write(" ".join(sys.argv[1:])+"\\n")\n')
    fixture=extensions/'clock-fixture@test';fixture.mkdir()
    (fixture/'metadata.json').write_text(json.dumps(dict(uuid='clock-fixture@test',name='Clock test',description='Isolated test only',**{'shell-version':['46']})))
    (fixture/'extension.js').write_text(FIXTURE_JS)
    shellsettings=Gio.Settings.new('org.gnome.shell')
    shellsettings.set_strv('enabled-extensions',['zorin-taskbar@zorinos.com',UUID,'clock-fixture@test'])
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir() and p.name!='zorin-taskbar@zorinos.com'])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.sync()
    children=[]
    log=(output/'shell.log').open('w')
    def start(args,env=None):
        p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=env);children.append(p);return p
    start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
    start(['gnome-shell','--headless','--wayland','--virtual-monitor','1280x800','--wayland-display','clock-test'],dict(os.environ,ZORIN11_RUNTIME_DIR=str(runtime)))
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def fixture_call(method,args=None):
        return bus.call_sync('local.zorin11.ClockTest','/local/zorin11/ClockTest','local.zorin11.ClockTest',method,args,None,0,5000,None).unpack()[0]
    def clocks():return json.loads(fixture_call('Clocks'))
    def launched():return launches.read_text().splitlines() if launches.exists() else []
    def capture(name):(output/name).write_bytes(base64.b64decode(fixture_call('Capture')))
    try:
        until(lambda:call('snapshot'))
        until(lambda:'Registering session with GDM' in (output/'shell.log').read_text())
        time.sleep(1)
        gnome_setup.install(gnome_setup.plan({gnome_setup.TASKBAR:gnome_setup.appearance(gnome_setup.monitor_ids())[gnome_setup.TASKBAR]}),temp/'recovery.json')
        until(lambda:clocks() and all(c and c['mapped'] and c['bell'] for c in clocks()))
        # A real pointer click on the taskbar clock opens the companion panel, not GNOME's calendar.
        fixture_call('Click',GLib.Variant('(i)',(0,)))
        until(lambda:launched()==['--notifications'])
        time.sleep(.5)
        assert not any(c['open'] for c in clocks()),'GNOME date menu must stay closed'
        capture('clock-click.png')
        # A second click toggles the companion again; GNOME's popup still never opens.
        fixture_call('Click',GLib.Variant('(i)',(0,)))
        until(lambda:launched()==['--notifications']*2)
        # Super+V / Super+M route through Main.panel.toggleCalendar().
        fixture_call('Toggle')
        until(lambda:launched()==['--notifications']*3)
        assert not any(c['open'] for c in clocks()),'Keyboard toggle must not open GNOME date menu'
        # Disabling the extension gives the clock its GNOME popup back.
        fixture_call('SetEnabled',GLib.Variant('(b)',(False,)))
        until(lambda:clocks() and not any(c['bell'] for c in clocks() if c))
        fixture_call('Click',GLib.Variant('(i)',(0,)))
        until(lambda:clocks()[0]['open'])
        assert len(launched())==3
        fixture_call('Close')
        fixture_call('SetEnabled',GLib.Variant('(b)',(True,)))
        until(lambda:clocks() and all(c and c['bell'] for c in clocks()))
        fixture_call('Click',GLib.Variant('(i)',(0,)))
        until(lambda:len(launched())==4)
        time.sleep(.5);assert not any(c['open'] for c in clocks())
        print('Clock: clicks and Super+V open the companion notifications-and-calendar panel; GNOME date menu stays closed and returns when the extension is disabled',flush=True)
        assert 'JS ERROR' not in (output/'shell.log').read_text(),(output/'shell.log').read_text()[-6000:]
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        log.close()

if __name__=='__main__':
    if '--systemd-fixture' in sys.argv:systemd_fixture()
    elif '--session' in sys.argv:session(Path(sys.argv[-2]),Path(sys.argv[-1]))
    else:
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-clock-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-clock-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='clock-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=120)
            print(result.stdout)
            if result.returncode:print(result.stderr[-5000:]);print((output/'shell.log').read_text()[-5000:])
            raise SystemExit(result.returncode)
