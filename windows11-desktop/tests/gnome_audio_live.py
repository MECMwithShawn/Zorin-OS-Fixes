#!/usr/bin/python3
"""Native GNOME menu integration on a private headless Wayland session."""
import json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11-audio@zorin-os-fixes'
if '--systemd-fixture' in sys.argv:
    from gnome_live import systemd_fixture
    systemd_fixture();raise SystemExit
if '--session' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin11-native-eq-') as directory:
        temp=Path(directory)
        for name in ('runtime','config','data','cache'):(temp/name).mkdir(mode=0o700)
        env=dict(os.environ,XDG_RUNTIME_DIR=str(temp/'runtime'),XDG_CONFIG_HOME=str(temp/'config'),XDG_DATA_HOME=str(temp/'data'),XDG_CACHE_HOME=str(temp/'cache'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',ZORIN11_RUNTIME_DIR=str(temp/'hub'),PULSE_SERVER='unix:'+str(temp/'no-pulse'),GIO_USE_VFS='local')
        result=subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--session',str(temp)],env=env,capture_output=True,text=True,timeout=85)
        print(result.stdout)
        if result.returncode:print(result.stderr[-3000:]);print((temp/'shell.log').read_text()[-6000:])
        raise SystemExit(result.returncode)
from gi.repository import Gio,GLib
temp=Path(sys.argv[-1]);sys.path.insert(0,str(ROOT/'companion'));import audio_effects
extension=temp/'data/gnome-shell/extensions'/UUID;shutil.copytree(ROOT/'gnome-audio-extension',extension)
(extension/'extension.js').rename(extension/'audio.js')
# Only this disposable test extension exposes activation and inspection methods.
(extension/'extension.js').write_text('''
import Base from './audio.js';
import Gio from 'gi://Gio';import GLib from 'gi://GLib';import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML=`<node><interface name="local.zorin11.AudioTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>`;
export default class Test extends Base {
 enable(){super.enable();this._bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this._bus.export(Gio.DBus.session,'/local/zorin11/AudioTest');this._owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.AudioTest',Gio.BusNameOwnerFlags.NONE,null,null);}
 Call(text){const p=JSON.parse(text);this._sync();const entry=[...this._menus.values()][0];
 const tile=[...this._tiles.values()][0];
 if(p.activate)tile.rows.get(p.activate).activate(null);
 if(p.show){const output=[...this._menus.keys()][0];output.visible=true;Main.panel.statusArea.quickSettings.menu.open();tile.tile.menu.open();}
 if(p.photo){const stream=Gio.File.new_for_path(p.photo).replace(null,false,Gio.FileCreateFlags.NONE,null);const s=new Shell.Screenshot();s.screenshot(false,stream,(o,r)=>{o.screenshot_finish(r);stream.close(null);});}
 return JSON.stringify({tiles:this._tiles.size,subtitle:tile?.tile.subtitle,checked:tile?.tile.checked,busy:this._busy,menus:this._menus.size,label:entry?.menu.label.text,rows:entry?[...entry.rows.keys()]:[]});}
 disable(){this._bus?.unexport();if(this._owner)Gio.bus_unown_name(this._owner);super.disable();}
}
''')
hub=temp/'hub';hub.mkdir();(hub/'audio-presets.json').write_text(json.dumps(audio_effects.PRESETS))
(hub/'audio_effects.py').write_text('''import json,os,sys
from pathlib import Path
p=Path(os.environ['XDG_CONFIG_HOME'])/'zorin11-hub/audio-effects.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'preset':sys.argv[2]}))
''')
(hub/'app.py').write_text("from pathlib import Path\nPath(__file__).with_name('settings-opened').touch()\n")
s=Gio.Settings.new('org.gnome.shell');s.set_strv('enabled-extensions',[UUID]);s.set_string('welcome-dialog-last-shown-version','46.0');Gio.Settings.sync()
stub=subprocess.Popen([sys.executable,__file__,'--systemd-fixture']);time.sleep(.2)
log=open(temp/'shell.log','w');shell=subprocess.Popen(['gnome-shell','--headless','--wayland','--virtual-monitor','1600x1000','--wayland-display','zorin11-eq-test'],stdout=log,stderr=log)
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def call(**p):return json.loads(bus.call_sync('local.zorin11.AudioTest','/local/zorin11/AudioTest','local.zorin11.AudioTest','Call',GLib.Variant('(s)',(json.dumps(p),)),None,Gio.DBusCallFlags.NONE,2000,None).unpack()[0])
def wait(fn,seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except Exception:pass
        time.sleep(.1)
    raise AssertionError('Native EQ test timed out')
try:
    state=wait(lambda:(s if (s:=call())['menus'] else None));assert state['menus']>=1 and state['tiles']>=1 and len(state['rows'])==len(audio_effects.PRESETS),state
    for preset in audio_effects.PRESETS:
        call(activate=preset['id'])
        wait(lambda:not call()['busy'] and call()['label'].endswith(preset['name']))
        tile_state=call();assert tile_state['subtitle']==preset['name'] and tile_state['checked']==(preset['id']!='off'),tile_state
        assert json.loads((temp/'config/zorin11-hub/audio-effects.json').read_text())['preset']==preset['id']
    call(show=True);time.sleep(.5)
    output=os.environ.get('ZORIN11_TEST_OUTPUT')
    if output:
        from PIL import Image
        target=Path(output)/'native-audio-menu.png';target.parent.mkdir(parents=True,exist_ok=True)
        target.unlink(missing_ok=True)
        def complete_image():
            with Image.open(target) as picture:picture.load()
            return True
        call(photo=str(target));wait(complete_image)
    print('PASS GNOME 46 System EQ quick-settings tile and Sound submenu; all tile preset actions, persisted selection, subtitle and checked state')
    assert 'JS ERROR' not in (temp/'shell.log').read_text()
finally:
    for p in (shell,stub):
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    log.close()
