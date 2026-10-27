#!/usr/bin/python3
"""Private two-monitor Wayland presentation test; never locks the user's session.
Native authentication widgets are rendered without starting a verifier/session.
Test-only D-Bus surfaces live solely in disposable extension/UI copies.
"""
import base64,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1];UUID='zorin11-lockscreen@zorin-os-fixes'
WRAPPER=r'''
import Base from './lockscreen.js';
import Gio from 'gi://Gio';import GLib from 'gi://GLib';import St from 'gi://St';import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {UnlockDialog} from 'resource:///org/gnome/shell/ui/unlockDialog.js';
import * as AuthPrompt from 'resource:///org/gnome/shell/gdm/authPrompt.js';
const methods=['_ensureAuthPrompt','_showPrompt','_onReset','vfunc_key_press_event','cancel','finish','open'];
const originals=methods.map(k=>UnlockDialog.prototype[k]);
const XML='<node><interface name="local.zorin11.LockTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="Capture"><arg type="s" direction="out"/></method></interface></node>';
export default class Test extends Base {
 enable(){super.enable();this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/LockTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.LockTest',0,null,null);}
 Call(text){const p=JSON.parse(text);Main.overview.hide();
 if(p.mode==='unlock')Main.sessionMode.pushMode('unlock-dialog');
 if(p.mode==='user')Main.sessionMode.popMode('unlock-dialog');
 if(p.create){this.dialog=new UnlockDialog(Main.layoutManager.uiGroup);this.dialog.set_size(global.stage.width,global.stage.height);this.dialog.show();this.media=new St.Label({text:'Media controls remain available',style:'font-size: 14px; margin-top: 24px;'});this.dialog._clock.add_child(this.media);}
 if(p.prompt){this.dialog._authPrompt=new AuthPrompt.AuthPrompt(this.dialog._gdmClient,AuthPrompt.AuthPromptMode.UNLOCK_ONLY);this.dialog._authPrompt.setUser(this.dialog._user);this.dialog._promptBox.add_child(this.dialog._authPrompt);this.dialog._adjustment.value=1;}
 if(p.clock)this.dialog._adjustment.value=0;
 if(p.enabled!==undefined)this._settings.set_boolean('enabled',p.enabled);
 if(p.path)this._settings.set_string('picture-uri',Gio.File.new_for_path(p.path).get_uri());
 if(p.source)this._settings.set_string('source',p.source);
 if(p.refresh)this._refresh();
 if(p.hide)this.dialog.hide();
 if(p.show)this.dialog.show();
 if(p.detach)super.disable();
 const row=this._dialogs.get(this.dialog);
 return JSON.stringify({native:methods.every((k,i)=>UnlockDialog.prototype[k]===originals[i]),style:this.dialog?.has_style_class_name('zorin11-lockscreen'),
 opacity:this.dialog?._backgroundGroup.opacity,media:!!this.media?.get_parent(),layers:row?.backgrounds.map(w=>({size:[w.width,w.height],actor:[w.get_first_child().width,w.get_first_child().height],reactive:w.reactive,blur:w.get_effect('zorin11-lock-blur').radius})),creditOpacity:row?.credit?.opacity,credit:row?.credit?.get_first_child().get_transformed_position(),
 windows:global.get_window_actors().map(a=>a.meta_window.get_title())});}
 async CaptureAsync(args,inv){try{const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);inv.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));}catch(e){inv.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.dialog?.destroy();this.bus.unexport();Gio.bus_unown_name(this.owner);if(this._signals.length)super.disable();}
}
'''
PREFS=r'''
from lockscreen_settings import Preferences
from gi.repository import Gio,GLib
import json
class Test(Preferences):
 def activate_window(self,*args):
  super().activate_window(*args)
  xml='<node><interface name="local.zorin11.LockPrefs"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>'
  bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
  def call(conn,sender,path,interface,method,args,invocation):
   p=json.loads(args.unpack()[0])
   if 'source' in p:self.source.set_active_id(p['source'])
   if 'dimming' in p:self.dimming.set_value(p['dimming'])
   if p.get('apply'):self.apply_button.clicked()
   if p.get('revert'):self.revert_button.clicked()
   if p.get('close'):self.window.close()
   invocation.return_value(GLib.Variant('(s)',(json.dumps(dict(source=self.draft['source'],dimming=self.draft['dimming'],status=self.status.get_text())),)))
  self.registration=bus.register_object('/local/zorin11/LockPrefs',Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0],call,None,None)
  self.owner=Gio.bus_own_name_on_connection(bus,'local.zorin11.LockPrefs',0,None,None)
Test().run(None)
'''

def session(temp,output):
    from gi.repository import Gio,GLib
    ext=temp/'data/gnome-shell/extensions'/UUID;shutil.copytree(ROOT/'gnome-lockscreen-extension',ext)
    (ext/'extension.js').rename(ext/'lockscreen.js');(ext/'extension.js').write_text(WRAPPER)
    subprocess.run(['glib-compile-schemas','--strict',str(ext/'schemas')],check=True)
    os.environ['ZORIN11_LOCKSCREEN_SCHEMA']=str(ext/'schemas');os.environ['ZORIN11_LOCKSCREEN_DIR']=str(temp/'lockscreen')
    sys.path.insert(0,str(ROOT/'companion'));import lockscreen
    lockscreen.apply({'source':'zorin'})
    shellsettings=Gio.Settings.new('org.gnome.shell');enabled=['user-theme@gnome-shell-extensions.gcampax.github.com',UUID]
    shellsettings.set_strv('enabled-extensions',enabled);shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir() and p.name not in enabled]);shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.new('org.gnome.shell.extensions.user-theme').set_string('name','ZorinBlue-Dark');Gio.Settings.sync()
    log=(output/'shell.log').open('w');children=[]
    def start(args,env=None):
        p=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def call(target='LockTest',**p):return json.loads(bus.call_sync('local.zorin11.'+target,'/local/zorin11/'+target,'local.zorin11.'+target,'Call',GLib.Variant('(s)',(json.dumps(p),)),None,0,4000,None).unpack()[0])
    def capture(name):
        data=bus.call_sync('local.zorin11.LockTest','/local/zorin11/LockTest','local.zorin11.LockTest','Capture',None,None,0,5000,None).unpack()[0];(output/(name+'.png')).write_bytes(base64.b64decode(data))
    try:
        start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
        start(['gnome-shell','--headless','--wayland','--virtual-monitor','1280x900','--virtual-monitor','1024x768','--wayland-display','lock-test'])
        until(lambda:call()['native']);call(create=True)
        state=until(lambda:(s if (s:=call()).get('opacity')==0 else None));assert state['native'] and state['media'] and len(state['layers'])==2,state
        assert all(not l['reactive'] and l['size']==l['actor'] for l in state['layers']),state
        time.sleep(.6);state=call();assert state['credit'][0]<100 and state['credit'][1]>700,state;capture('clock')
        call(mode='unlock');assert call()['native'] and call()['style'];
        call(prompt=True);time.sleep(.5);state=call();assert state['native'] and state['creditOpacity']==0 and all(l['blur']>0 for l in state['layers']),state;capture('native-prompt')
        call(clock=True,path='/missing-image');time.sleep(.2);state=call();assert state['opacity']==255 and not state['layers'],state
        call(path='/usr/share/backgrounds/Zorin.jpg',source='desktop');until(lambda:call()['opacity']==0);capture('desktop')
        call(enabled=False);state=call();assert not state['style'] and state['opacity']==255 and state['media'],state
        call(enabled=True,source='zorin');until(lambda:call()['opacity']==0)
        for _ in range(4):call(refresh=True)
        assert len(call()['layers'])==2
        call(mode='user',hide=True)
        prefs=temp/'prefs.py';prefs.write_text(PREFS)
        env=dict(os.environ,WAYLAND_DISPLAY='lock-test',GDK_BACKEND='wayland',PYTHONPATH=str(ROOT/'companion'))
        subprocess.run(['dbus-update-activation-environment','WAYLAND_DISPLAY=lock-test','GDK_BACKEND=wayland'],env=env,check=True)
        start(['/usr/bin/python3',str(prefs)],env)
        until(lambda:call('LockPrefs')['source']=='zorin');assert 'Applied.' in call('LockPrefs')['status'];time.sleep(.6);capture('preferences')
        lockscreen.apply({'dimming':18});until(lambda:call('LockPrefs')['dimming']==18)
        call('LockPrefs',dimming=25,source='desktop');lockscreen.apply({'dimming':14});time.sleep(.3)
        assert call('LockPrefs')['dimming']==25,'Daily refresh must not overwrite an unsaved draft'
        call('LockPrefs',revert=True);assert call('LockPrefs')['dimming']==14 and call('LockPrefs')['source']=='zorin'
        call('LockPrefs',dimming=25,source='desktop',apply=True);until(lambda:lockscreen.load()['dimming']==25);assert lockscreen.load()['source']=='desktop'
        call('LockPrefs',close=True);call(show=True);capture('applied')
        state=call(detach=True);assert state['native'] and state['media'] and not state['style'] and state['opacity']==255,state
        text=(output/'shell.log').read_text();assert 'JS ERROR' not in text and 'Traceback' not in text and 'Axentra lock screen:' not in text,text[-6000:]
        print('PASS: real GNOME clock/account prompt on two Wayland monitors, native auth methods unchanged, backgrounds/blur/credits, fallback, desktop source, disable/re-enable, child preservation, GTK draft/Apply/Revert.')
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
        output=Path('/tmp/zorin11-lockscreen-test');output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-lockscreen-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='lock-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=90)
            print(result.stdout)
            if result.returncode:print(result.stderr[-3000:]);print((output/'shell.log').read_text()[-6000:])
            raise SystemExit(result.returncode)
