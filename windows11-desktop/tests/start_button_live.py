#!/usr/bin/python3
"""Taskbar Start button image in a private headless GNOME Shell; never touches the signed-in session."""
import base64,json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11@zorin-os-fixes'
FIXTURE_JS=r'''
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const XML='<node><interface name="local.zorin11.StartButtonTest"><method name="Icons"><arg direction="out" type="s"/></method><method name="Capture"><arg direction="out" type="s"/></method></interface></node>';
export default class Fixture extends Extension {
 enable(){this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/StartButtonTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.StartButtonTest',0,null,null);}
 Icons(){
  const panels=global.zorinTaskbar?.panels?.map(p=>p.panel)||[Main.panel];
  return JSON.stringify(panels.map(panel=>{const button=panel.statusArea['zorin11-start'];const icon=button?.get_first_child();
   return {visible:!!button?.visible,file:icon?.gicon?.get_file?.()?.get_path()??null};}));
 }
 async CaptureAsync(_args,invocation){try{
  const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);
  invocation.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));
 }catch(e){invocation.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.bus.unexport();Gio.bus_unown_name(this.owner);}
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
    fixture=extensions/'start-button-fixture@test';fixture.mkdir()
    (fixture/'metadata.json').write_text(json.dumps(dict(uuid='start-button-fixture@test',name='Start button test',description='Isolated test only',**{'shell-version':['46']})))
    (fixture/'extension.js').write_text(FIXTURE_JS)
    shellsettings=Gio.Settings.new('org.gnome.shell')
    shellsettings.set_strv('enabled-extensions',['zorin-taskbar@zorinos.com',UUID,'start-button-fixture@test'])
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir() and p.name!='zorin-taskbar@zorinos.com'])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.sync()
    children=[]
    log=(output/'shell.log').open('w')
    def start(args):
        p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
    start(['gnome-shell','--headless','--wayland','--virtual-monitor','1280x800','--wayland-display','start-button-test'])
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def fixture_call(method):
        return bus.call_sync('local.zorin11.StartButtonTest','/local/zorin11/StartButtonTest','local.zorin11.StartButtonTest',method,None,None,0,5000,None).unpack()[0]
    def icons():return json.loads(fixture_call('Icons'))
    def capture(name):(output/name).write_bytes(base64.b64decode(fixture_call('Capture')))
    try:
        until(lambda:call('snapshot'))
        until(lambda:'Registering session with GDM' in (output/'shell.log').read_text())
        time.sleep(1)
        gnome_setup.install(gnome_setup.plan({gnome_setup.TASKBAR:gnome_setup.appearance(gnome_setup.monitor_ids())[gnome_setup.TASKBAR]}),temp/'recovery.json')
        default=str(extension/'start.svg')
        until(lambda:icons() and all(i['visible'] and i['file']==default for i in icons()))
        capture('start-button-default.png')

        # The companion writes the key through the installed extension's schema, as it does live.
        os.environ['ZORIN11_EXTENSION_SCHEMAS']=str(extension/'schemas')
        os.environ['ZORIN11_CONFIG_DIR']=str(temp/'config/zorin11-hub')
        import app
        from start_preferences import Preferences
        hub=SimpleNamespace(start_preferences=Preferences(temp/'search-start.json',[]))
        hub.start_button_file=lambda:app.Hub.start_button_file(hub)
        def choose(button):hub.start_preferences.change('button',value=button);app.Hub.apply_start_button(hub)
        choose('orb')
        orb=str(ROOT/'companion/start-buttons/orb.svg')
        until(lambda:all(i['file']==orb for i in icons()))
        time.sleep(.5);capture('start-button-orb.png')
        choose('windows10')
        until(lambda:all(i['file']==str(ROOT/'companion/start-buttons/windows10.svg') for i in icons()))
        # A custom image is converted to a 64 px PNG in the companion's config folder.
        app.Hub.save_custom_start_button(hub,ROOT/'companion/start-buttons/orb.svg')
        choose('custom')
        custom=str(temp/'config/zorin11-hub/start-button-custom.png')
        until(lambda:all(i['file']==custom for i in icons()))
        from gi.repository import GdkPixbuf
        info=GdkPixbuf.Pixbuf.get_file_info(custom)
        assert info[0].get_name()=='png' and max(info[1],info[2])==64,info
        Path(custom).rename(custom+'.moved')
        settings=Gio.Settings.new_full(Gio.SettingsSchemaSource.new_from_directory(str(extension/'schemas'),Gio.SettingsSchemaSource.get_default(),False).lookup('org.gnome.shell.extensions.zorin11',False),None,None)
        settings.set_string('start-button','');Gio.Settings.sync();until(lambda:all(i['file']==default for i in icons()))
        settings.set_string('start-button',custom);Gio.Settings.sync();time.sleep(.6)
        assert all(i['file']==default for i in icons()),'A missing image falls back to the bundled icon'
        choose('windows11');until(lambda:settings.get_string('start-button')=='')
        until(lambda:all(i['file']==default for i in icons()))
        print('Start button: bundled, Windows 10, orb and custom images apply live through the extension key; a missing file falls back',flush=True)
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
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-start-button-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-start-button-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='start-button-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=120)
            print(result.stdout)
            if result.returncode:print(result.stderr[-5000:]);print((output/'shell.log').read_text()[-5000:])
            raise SystemExit(result.returncode)
