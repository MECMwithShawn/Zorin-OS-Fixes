#!/usr/bin/python3
"""Motion and GTK controls on private GNOME Wayland with the real Zorin taskbar.

Only disposable copies expose test D-Bus interfaces. No host settings/windows.
"""
import base64,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11-motion@zorin-os-fixes'
WRAPPER=r'''
import Base from './motion.js';
import Gio from 'gi://Gio';import GLib from 'gi://GLib';import Shell from 'gi://Shell';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML='<node><interface name="local.zorin11.MotionTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="Capture"><arg type="s" direction="out"/></method></interface></node>';
export default class Test extends Base {
 enable(){super.enable();this.keyboard=Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/MotionTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.MotionTest',0,null,null);}
 Call(text){const p=JSON.parse(text);
 if(p.preset)this._menus[0].options.get(p.preset).activate(null);
 if(p.toggle)this._menus[0].tile.emit('clicked',1);
 if(p.rebuild)this._sync();
 if(p.overview===false)Main.overview.hide();
 if(p.overview===true)Main.overview.show();
 if(p.focus)global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='Taskbar motion')?.activate(global.get_current_time());
 if(p.animations!==undefined)this._interface.set_boolean('enable-animations',p.animations);
 if(p.battery!==undefined){this._power={get_cached_property:()=>new GLib.Variant('b',p.battery)};this._refresh();}
 if(p.fullscreen!==undefined){const w=global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='Taskbar motion');if(w){p.fullscreen?w.make_fullscreen():w.unmake_fullscreen();}}
 if(p.menu){Main.panel.statusArea.quickSettings.menu.open();this._menus[0].tile.menu.open();}
 return JSON.stringify({timer:!!this._timer,preset:this._config.preset,tiles:this._menus.length,
  subtitle:this._menus[0]?.tile.subtitle,checked:this._menus[0]?.tile.checked,
  panels:this._panels.filter(r=>!r.dead).map(r=>({visible:r.moving,mapped:r.actor.mapped,reason:r.reason,focus:this._focus(r,r.actor.width),
   rect:[...r.actor.get_transformed_position(),...r.actor.get_transformed_size()],panel:[r.panel.width,r.panel.height],reactive:r.actor.reactive,layers:r.panel.get_children().filter(c=>c.name==='zorin11-motion-layer').length})),
  windows:global.get_window_actors().map(a=>({title:a.meta_window.get_title(),focused:a.meta_window.has_focus()}))});}
 async CaptureAsync(args,inv){try{const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);inv.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));}catch(e){inv.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.keyboard=null;this.bus.unexport();Gio.bus_unown_name(this.owner);super.disable();}
}
'''
PREFS_TEST=r'''
        const testXML='<node><interface name="local.zorin11.MotionPrefs"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>';
        const testBus=Gio.DBusExportedObject.wrapJSObject(testXML,{Call(text){const p=JSON.parse(text);
            if(p.preset)presets.get(p.preset).emit('clicked');
            if(p.intensity)ranges[0].scale.set_value(p.intensity);
            if(p.period)ranges[1].scale.set_value(p.period);
            if(p.accent){const c=new Gdk.RGBA();c.parse(p.accent);color.set_rgba(c);color.emit('color-set');}
            if(p.defaults)defaults.emit('clicked');
            if(p.pause!==undefined)preview.set_active(p.pause);
            return JSON.stringify({preset:config.preset,intensity:config.intensity,period:config.period,accent:config.accent,
                timer:!!timer,status:status.label,selected:[...presets].filter(([id,b])=>b.active).map(([id])=>id)});}});
        testBus.export(Gio.DBus.session,'/local/zorin11/MotionPrefs');
        Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.MotionPrefs',0,null,null);
'''

def session(temp,output):
    from gi.repository import Gio,GLib
    ext=temp/'data/gnome-shell/extensions'/UUID
    shutil.copytree(ROOT/'gnome-motion-extension',ext)
    (ext/'extension.js').rename(ext/'motion.js');(ext/'extension.js').write_text(WRAPPER)
    prefs=(ext/'preferences.js').read_text();assert prefs.count('refresh(); win.present();')==1
    (ext/'preferences.js').write_text(prefs.replace('refresh(); win.present();','refresh(); win.present();\n'+PREFS_TEST))
    subprocess.run(['glib-compile-schemas','--strict',str(ext/'schemas')],check=True)
    apps=temp/'data/applications';apps.mkdir()
    sys.path.insert(0,str(ROOT));import motion_install
    launcher=temp/'.local/share/applications/zorin11-taskbar-motion.desktop'
    (apps/launcher.name).write_bytes(motion_install.files(temp)[launcher])
    shellsettings=Gio.Settings.new('org.gnome.shell')
    theme='user-theme@gnome-shell-extensions.gcampax.github.com'
    enabled=[theme,'zorin-taskbar@zorinos.com',UUID]
    shellsettings.set_strv('enabled-extensions',enabled)
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir() and p.name not in enabled])
    shellsettings.set_strv('favorite-apps',['zorin11-taskbar-motion.desktop','org.gnome.Nautilus.desktop'])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.new('org.gnome.desktop.interface').set_boolean('enable-animations',True)
    Gio.Settings.new('org.gnome.desktop.interface').set_string('color-scheme','prefer-dark')
    Gio.Settings.new('org.gnome.shell.extensions.user-theme').set_string('name','ZorinBlue-Dark')
    Gio.Settings.new('org.gnome.shell.extensions.zorin-taskbar').set_boolean('multi-monitors',True)
    Gio.Settings.sync()
    log=(output/'shell.log').open('w');children=[]
    def start(args,env=None):
        p=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def call(target='MotionTest',**p):
        return json.loads(bus.call_sync('local.zorin11.'+target,'/local/zorin11/'+target,'local.zorin11.'+target,'Call',GLib.Variant('(s)',(json.dumps(p),)),None,0,3000,None).unpack()[0])
    def capture(name):
        data=bus.call_sync('local.zorin11.MotionTest','/local/zorin11/MotionTest','local.zorin11.MotionTest','Capture',None,None,0,5000,None).unpack()[0]
        (output/(name+'.png')).write_bytes(base64.b64decode(data))
    try:
        start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
        start(['gnome-shell','--headless','--wayland','--virtual-monitor','1280x900','--virtual-monitor','1024x768','--wayland-display','motion-test'])
        until(lambda:call()['panels']);time.sleep(1)
        call(overview=False,battery=False)
        state=until(lambda:(s if (s:=call())['timer'] and all(r['mapped'] for r in s['panels']) else None))
        assert len(state['panels'])==2,state
        assert all(r['rect'][2:]==r['panel'] and not r['reactive'] for r in state['panels']),state
        env=dict(os.environ,WAYLAND_DISPLAY='motion-test',GDK_BACKEND='wayland')
        subprocess.run(['dbus-update-activation-environment','WAYLAND_DISPLAY=motion-test','GDK_BACKEND=wayland'],env=env,check=True)
        start(['/usr/bin/gjs','-m',str(ext/'preferences.js')],env)
        until(lambda:call('MotionPrefs')['preset']=='aurora')
        until(lambda:any(w['title']=='Taskbar motion' for w in call()['windows']))
        call(focus=True)
        until(lambda:call('MotionPrefs')['timer']);capture('preferences')
        until(lambda:'Applied' in call('MotionPrefs')['status'])
        for preset in ['off','aurora','breathe','sweep','edge','halo']:
            call(preset=preset)
            state=until(lambda:(s if (s:=call('MotionPrefs'))['preset']==preset else None))
            assert state['selected']==[preset],state
            time.sleep(.25)
            native=call();assert native['timer']==(preset!='off'),native
            assert native['checked']==(preset!='off'),native
            if preset=='halo':assert any(r['focus'] for r in native['panels']),native
            capture(preset)
        call('MotionPrefs',preset='aurora',intensity=35,period=28,accent='#ae80ff')
        state=call('MotionPrefs');assert [state[k] for k in ['intensity','period','accent']]==[35,28,'#ae80ff'],state
        call('MotionPrefs',pause=True);assert not call('MotionPrefs')['timer']
        assert call()['timer'],'Preview pause must not change the real taskbar'
        call('MotionPrefs',pause=False,defaults=True)
        state=call('MotionPrefs');assert [state[k] for k in ['intensity','period','accent']]==[20,20,'#60cdff'],state
        call(animations=False);until(lambda:not call()['timer'] and not call('MotionPrefs')['timer'])
        call(animations=True);until(lambda:call()['timer'])
        call(battery=True);assert not call()['timer']
        call(battery=False);assert call()['timer']
        call(overview=True);until(lambda:not call()['timer'])
        call(overview=False);until(lambda:call()['timer'])
        call(fullscreen=True);until(lambda:any('Fullscreen' in r['reason'] for r in call()['panels']))
        call(fullscreen=False);until(lambda:all(not r['reason'] for r in call()['panels']))
        call(toggle=True);assert call()['preset']=='off'
        call(toggle=True);assert call()['preset']=='aurora'
        for _ in range(3):call(rebuild=True)
        assert call()['tiles']==2
        taskbar=Gio.Settings.new('org.gnome.shell.extensions.zorin-taskbar')
        taskbar.set_int('panel-size',56);Gio.Settings.sync()
        until(lambda:all(r['rect'][3]==56 for r in call()['panels']))
        taskbar.set_boolean('multi-monitors',False);Gio.Settings.sync()
        until(lambda:call()['tiles']==1)
        taskbar.set_boolean('multi-monitors',True);Gio.Settings.sync()
        until(lambda:call()['tiles']==2)
        assert all(r['layers']==1 for r in call()['panels'])
        taskbar.set_int('panel-size',48);Gio.Settings.sync()
        shellsettings.set_strv('enabled-extensions',enabled[:-1]);Gio.Settings.sync();time.sleep(.5)
        shellsettings.set_strv('enabled-extensions',enabled);Gio.Settings.sync()
        until(lambda:call()['tiles']==2)
        call(battery=False,overview=False)
        capture('final')
        text=(output/'shell.log').read_text()
        assert 'JS ERROR' not in text and '/motion.js:' not in text and '/preferences.js:' not in text,text[-6000:]
        print('PASS: two Zorin panels, six styles, active-app geometry, native GTK controls, persistence, reduced motion/battery/overview/fullscreen pauses, rebuild and disable/enable; screenshots captured.')
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
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-motion-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-motion-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='motion-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=100)
            print(result.stdout)
            if result.returncode:print(result.stderr[-4000:]);print((output/'shell.log').read_text()[-6000:])
            raise SystemExit(result.returncode)
