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
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML='<node><interface name="local.zorin11.MotionTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="Capture"><arg type="s" direction="out"/></method></interface></node>';
export default class Test extends Base {
 enable(){const manager=global.zorinTaskbar,panels=manager?.panels;this.emptyStartup=!!manager;if(manager)manager.panels=[];super.enable();if(manager){manager.panels=panels;manager.emit('panels-created');}this.keyboard=Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/MotionTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.MotionTest',0,null,null);}
 Call(text){const p=JSON.parse(text);
 if(p.preset)this._menus[0].options.get(p.preset).activate(null);
 if(p.toggle)this._menus[0].tile.emit('clicked',1);
 if(p.rebuild)this._sync();
 if(p.emptyStartup){const manager=global.zorinTaskbar,panels=manager.panels;super.disable();manager.panels=[];super.enable();manager.panels=panels;this.emptyStartup=true;manager.emit('panels-created');}
 if(p.layout){for(const actor of this.layoutActors||[])actor.destroy();this.layoutActors=[];for(const r of this._panels){if(p.layout.apps){const actor=new St.Widget({width:p.layout.apps,height:32});r.entry.taskbar._box.add_child(actor);this.layoutActors.push(actor);}for(let i=0;i<p.layout.tray;i++){const actor=new St.Widget({width:28,height:32});r.panel._rightBox.add_child(actor);this.layoutActors.push(actor);}}}
 if(p.startup!==undefined)this._menus[0].startup.emit('toggled',p.startup);
 if(p.context!==undefined){const entry=this._panels[p.context].entry;Main.layoutManager.setDummyCursorGeometry(entry.monitor.x+200,entry.monitor.y+entry.monitor.height-20,0,0);entry.showAppsIconWrapper.popupMenu(Main.layoutManager.dummyCursor);}
 if(p.launchMotion){this._panels[p.launchMotion-1].entry.showAppsIconWrapper._menu._getMenuItems().find(i=>i.label?.text==='Taskbar motion…').activate(null);}
 if(p.closeContext)for(const row of this._panels)row.entry.showAppsIconWrapper?._menu?.close();
 if(p.overview===false)Main.overview.hide();
 if(p.overview===true)Main.overview.show();
 if(p.focus)global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()===(p.focus===true?'Taskbar motion':p.focus))?.activate(global.get_current_time());
 if(p.animations!==undefined)this._interface.set_boolean('enable-animations',p.animations);
 if(p.battery!==undefined){this._power={get_cached_property:()=>new GLib.Variant('b',p.battery)};this._refresh();}
 if(p.fullscreen!==undefined){const w=global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='Taskbar motion');if(w){p.fullscreen?w.make_fullscreen():w.unmake_fullscreen();}}
 if(p.menu){Main.panel.statusArea.quickSettings.menu.open();this._menus[0].tile.menu.open();}
 return JSON.stringify({layout:this._panels.map(r=>{const a=r.entry.allocationMap?.taskbar?.actor,t=r.panel._rightBox;return a?{appX:a.get_transformed_position()[0],appWidth:a.width,trayX:t.get_transformed_position()[0],trayWidth:t.width,panelWidth:r.panel.width}:null;}),startup:this._settings.get_boolean('apply-at-startup'),startupMenus:this._menus.map(m=>m.startup.state),emptyStartup:this.emptyStartup,contextMenus:this._panels.map(r=>r.entry.showAppsIconWrapper?._menu?._getMenuItems().map(i=>i.label?.text).filter(Boolean)),timer:!!this._timer,preset:this._config.preset,tiles:this._menus.length,
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
            if(p.startup!==undefined)settings.set_boolean('apply-at-startup',p.startup);
            if(p.defaults)defaults.emit('clicked');
            if(p.apply)apply.emit('clicked');
            if(p.revert)revert.emit('clicked');
            if(p.tab){const visit=w=>{if(w.get_title?.()===p.tab)return w;for(let c=w.get_first_child?.();c;c=c.get_next_sibling()){const found=visit(c);if(found)return found;}return null;};win.visible_page=visit(win);}
            if(p.panelSize){const visit=w=>{if(w.get_buildable_id?.()==='panel_size_scale')return w;for(let c=w.get_first_child?.();c;c=c.get_next_sibling()){const found=visit(c);if(found)return found;}return null;};visit(win).set_value(p.panelSize);}
            if(p.close)GLib.idle_add(GLib.PRIORITY_DEFAULT,()=>{win.close();return GLib.SOURCE_REMOVE;});
            if(p.pause!==undefined)preview.set_active(p.pause);
            return JSON.stringify({startup:settings.get_boolean('apply-at-startup'),preset:config.preset,intensity:config.intensity,period:config.period,accent:config.accent,
                vendor:!!win._settings,page:win.visible_page?.title,timer:!!timer,status:status.label,dirty:settings.get_has_unapplied(),busy,selected:[...presets].filter(([id,b])=>b.active).map(([id])=>id)});}});
        testBus.export(Gio.DBus.session,'/local/zorin11/MotionPrefs');
        Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.MotionPrefs',0,null,null);
'''

def session(temp,output):
    from gi.repository import Gio,GLib
    ext=temp/'data/gnome-shell/extensions'/UUID
    shutil.copytree(ROOT/'gnome-motion-extension',ext)
    (ext/'extension.js').rename(ext/'motion.js');(ext/'extension.js').write_text(WRAPPER)
    prefs=(ext/'controls.js').read_text();assert prefs.count('    return root;')==1
    (ext/'controls.js').write_text(prefs.replace('    return root;',PREFS_TEST+'\n    return root;'))
    subprocess.run(['glib-compile-schemas','--strict',str(ext/'schemas')],check=True)
    apps=temp/'data/applications';apps.mkdir()
    sys.path.insert(0,str(ROOT));import motion_install,gnome_setup
    launcher=temp/'.local/share/applications/zorin11-taskbar-motion.desktop'
    (apps/launcher.name).write_bytes(motion_install.files(temp)[launcher])
    # The isolated desktop entry must point at the private extension.
    (apps/launcher.name).write_text((apps/launcher.name).read_text().replace(str(temp/'.local/share/gnome-shell/extensions'/UUID),str(ext)))
    taskbar=Gio.Settings.new('org.gnome.shell.extensions.zorin-taskbar')
    taskbar.set_string('panel-element-positions',gnome_setup.appearance(['0','1'])[gnome_setup.TASKBAR]['panel-element-positions'])
    for key,value in motion_install.context_menu_settings(['/usr/bin/true'],['My custom action']).items():taskbar.set_strv(key,value)
    shellsettings=Gio.Settings.new('org.gnome.shell')
    theme='user-theme@gnome-shell-extensions.gcampax.github.com'
    enabled=[theme,'zorin-taskbar@zorinos.com',UUID]
    shellsettings.set_strv('enabled-extensions',enabled)
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir() and p.name not in enabled])
    shellsettings.set_strv('favorite-apps',['zorin11-taskbar-motion.desktop','org.gnome.Nautilus.desktop'])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.new('org.gnome.desktop.media-handling').set_boolean('automount',False)
    Gio.Settings.new('org.gnome.desktop.media-handling').set_boolean('automount-open',False)
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
        # Process settings notifications while driving this fixture synchronously.
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        return json.loads(bus.call_sync('local.zorin11.'+target,'/local/zorin11/'+target,'local.zorin11.'+target,'Call',GLib.Variant('(s)',(json.dumps(p),)),None,0,3000,None).unpack()[0])
    def capture(name):
        data=bus.call_sync('local.zorin11.MotionTest','/local/zorin11/MotionTest','local.zorin11.MotionTest','Capture',None,None,0,5000,None).unpack()[0]
        (output/(name+'.png')).write_bytes(base64.b64decode(data))
    try:
        start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
        shellargs=['gnome-shell','--headless','--wayland','--virtual-monitor','1280x900','--virtual-monitor','1024x768','--wayland-display','motion-test']
        shell=start(shellargs)
        until(lambda:len(call()['panels'])==2);call(emptyStartup=True);until(lambda:len(call()['panels'])==2);time.sleep(1)
        call(overview=False,battery=False)
        state=until(lambda:(s if (s:=call())['timer'] and all(r['mapped'] for r in s['panels']) else None))
        assert len(state['panels'])==2 and state['emptyStartup'],state
        assert all(r['rect'][2:]==r['panel'] and not r['reactive'] for r in state['panels']),state
        # Exercise native sizing with synthetic app/tray content; production
        # relies on Zorin's allocator, not a replacement allocation function.
        def layout(apps,tray):
            call(layout=dict(apps=apps,tray=tray));time.sleep(.25)
            rows=call()['layout'];assert len(rows)==2 and all(rows),rows
            for r in rows:assert 0<=r['appWidth']<=r['panelWidth'] and r['appX']+r['appWidth']<=r['trayX']+1,rows
            return rows
        small=layout(96,0)
        many=layout(2000,0)
        assert all(b['appWidth']>a['appWidth'] for a,b in zip(small,many)),(small,many)
        crowded=layout(2000,10)
        assert all(b['trayWidth']>a['trayWidth'] and b['appWidth']<a['appWidth'] for a,b in zip(many,crowded)),(many,crowded)
        restored=layout(2000,0)
        assert all(abs(a['appWidth']-b['appWidth'])<2 for a,b in zip(many,restored)),(many,restored)
        small_again=layout(96,0)
        assert all(abs(a['appWidth']-b['appWidth'])<2 for a,b in zip(small,small_again)),(small,small_again)
        layout(0,0)
        print('PASS: automatic app/tray growth and shrinkage without overlap on two native Zorin panels.',flush=True)
        if os.environ.get('ZORIN11_LAYOUT_ONLY')=='1':return
        env=dict(os.environ,WAYLAND_DISPLAY='motion-test',GDK_BACKEND='wayland')
        subprocess.run(['dbus-update-activation-environment','WAYLAND_DISPLAY=motion-test','GDK_BACKEND=wayland'],env=env,check=True)
        preferences=start(['/usr/bin/gjs','-m',str(ext/'preferences.js')],env)
        until(lambda:call('MotionPrefs')['preset']=='aurora')
        until(lambda:any(w['title']=='Taskbar motion' for w in call()['windows']))
        call(focus=True)
        until(lambda:call('MotionPrefs')['timer']);capture('preferences')
        until(lambda:'is ready' in call('MotionPrefs')['status'])
        assert call('MotionPrefs')['startup']
        call('MotionPrefs',startup=False);assert call()['startup'] and call('MotionPrefs')['dirty']
        call('MotionPrefs',revert=True);assert call('MotionPrefs')['startup']
        call(startup=False);until(lambda:not call('MotionPrefs')['startup']);assert call()['startupMenus']==[False,False]
        call(startup=True);until(lambda:call('MotionPrefs')['startup']);assert call()['startupMenus']==[True,True]
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
        assert state['dirty'] and 'Preview changes' in state['status'],state
        assert call()['preset']=='halo','Draft changes must not alter the taskbar'
        call('MotionPrefs',revert=True)
        assert call('MotionPrefs')['preset']=='halo' and not call('MotionPrefs')['dirty']
        call('MotionPrefs',preset='aurora',intensity=35,period=28,accent='#ae80ff',apply=True)
        until(lambda:call()['preset']=='aurora' and not call('MotionPrefs')['busy'])
        assert not call('MotionPrefs')['dirty']
        assert 'Applied to your taskbar' in call('MotionPrefs')['status']
        capture('applied')
        call('MotionPrefs',pause=True);assert not call('MotionPrefs')['timer']
        assert call()['timer'],'Preview pause must not change the real taskbar'
        call('MotionPrefs',pause=False,defaults=True)
        state=call('MotionPrefs');assert [state[k] for k in ['intensity','period','accent']]==[20,20,'#60cdff'],state
        assert state['dirty'],'Restore defaults must wait for Apply'
        call('MotionPrefs',apply=True);until(lambda:not call('MotionPrefs')['busy'])
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
        taskbar.set_string('panel-sizes',json.dumps({'0':56,'1':56}));Gio.Settings.sync()
        until(lambda:all(r['rect'][3]==56 for r in call()['panels']))
        taskbar.set_boolean('multi-monitors',False);Gio.Settings.sync()
        until(lambda:call()['tiles']==1)
        taskbar.set_boolean('multi-monitors',True);Gio.Settings.sync()
        until(lambda:call()['tiles']==2)
        assert all(r['layers']==1 for r in call()['panels'])
        taskbar.set_string('panel-sizes',json.dumps({'0':48,'1':48}));Gio.Settings.sync()
        shellsettings.set_strv('enabled-extensions',enabled[:-1]);Gio.Settings.sync();time.sleep(.5)
        until(lambda:'disabled' in call('MotionPrefs')['status'])
        call('MotionPrefs',preset='sweep',apply=True)
        until(lambda:call()['tiles']==2 and call()['preset']=='sweep')
        until(lambda:not call('MotionPrefs')['busy'])
        assert 'Applied to your taskbar' in call('MotionPrefs')['status']
        call('MotionPrefs',close=True);preferences.wait(timeout=5)
        for index in range(2):
            call(context=index);state=call();items=state['contextMenus'][index]
            assert items.count('Taskbar motion…')==1 and 'My custom action' in items and 'Taskbar Settings' in items,state
            time.sleep(.2);capture('taskbar-context-'+str(index));call(closeContext=True)
        call(context=0,launchMotion=1)
        taskbarPrefs=None
        until(lambda:any(w['title']=='Taskbar settings' for w in call()['windows']))
        call(focus='Taskbar settings')
        until(lambda:call('MotionPrefs')['preset']=='sweep' and call('MotionPrefs')['timer'])
        time.sleep(.6);capture('taskbar-motion')
        assert call('MotionPrefs')['vendor'],'The installed native taskbar controls must load'
        for tab in ['Style','Position','Behavior','Action']:
            call('MotionPrefs',tab=tab)
            until(lambda:call('MotionPrefs')['page']==tab and not call('MotionPrefs')['timer'])
            time.sleep(.2)
        capture('taskbar-action')
        subprocess.run(['/usr/bin/gjs','-m',str(ext/'taskbar-settings.js'),'--motion'],env=env,check=True,timeout=5,stdout=log,stderr=subprocess.STDOUT)
        until(lambda:call('MotionPrefs')['page']=='Motion')
        assert len([w for w in call()['windows'] if w['title']=='Taskbar settings'])==1
        call('MotionPrefs',panelSize=52)
        until(lambda:any(r['rect'][3]==52 for r in call()['panels']))
        call('MotionPrefs',panelSize=48)
        until(lambda:call('MotionPrefs')['timer'])
        call('MotionPrefs',preset='edge',apply=True)
        until(lambda:call()['preset']=='edge' and not call('MotionPrefs')['busy'])
        call('MotionPrefs',defaults=True,apply=True)
        until(lambda:call()['preset']=='aurora' and not call('MotionPrefs')['busy'])
        call(battery=False,overview=False)
        time.sleep(.6);capture('final')
        call('MotionPrefs',close=True);until(lambda:not any(w['title']=='Taskbar settings' for w in call()['windows']))
        # Real Shell-process restarts exercise persistence; never restart the host.
        schema=Gio.SettingsSchemaSource.new_from_directory(str(ext/'schemas'),Gio.SettingsSchemaSource.get_default(),False).lookup('org.gnome.shell.extensions.zorin11-motion',False)
        saved=Gio.Settings.new_full(schema,None,None)
        saved.set_string('preset','edge');saved.set_boolean('apply-at-startup',False);Gio.Settings.sync()
        def restart_shell():
            nonlocal shell
            shell.terminate();shell.wait(timeout=8)
            shell=start(shellargs)
            try:until(lambda:len(call()['panels'])==2)
            except Exception:
                print('Cold startup settings:',subprocess.check_output(['gsettings','get','org.gnome.shell','enabled-extensions'],text=True),subprocess.check_output(['gsettings','get','org.gnome.shell','disable-user-extensions'],text=True))
                print('Extension:',bus.call_sync('org.gnome.Shell','/org/gnome/Shell','org.gnome.Shell.Extensions','GetExtensionInfo',GLib.Variant('(s)',(UUID,)),None,0,3000,None).unpack())
                try:print('Test state:',call())
                except Exception as error:print('Test call:',str(error))
                raise
            call(overview=False,battery=False)
        restart_shell()
        state=call();assert state['preset']=='edge' and not state['timer'] and not state['checked'] and not state['startup'],state
        manual=start(['/usr/bin/gjs','-m',str(ext/'preferences.js')],env)
        until(lambda:call('MotionPrefs')['preset']=='edge');assert not call('MotionPrefs')['dirty']
        call('MotionPrefs',apply=True);until(lambda:call()['timer'])
        assert call()['preset']=='edge' and not call()['startup'],'Apply must start an unchanged preset without enabling startup'
        call('MotionPrefs',close=True);manual.wait(timeout=5)
        restart_shell();assert not call()['timer']
        call(preset='edge')
        try:until(lambda:call()['timer'])
        except AssertionError:raise AssertionError(('Selecting the same preset must start it for this session',call()))
        shellsettings.set_strv('enabled-extensions',enabled[:-1]);Gio.Settings.sync();time.sleep(.3)
        shellsettings.set_strv('enabled-extensions',enabled);Gio.Settings.sync();until(lambda:call()['panels']);call(battery=False)
        assert call()['timer'],'Re-enabling in the same Shell must retain manual activation'
        call(startup=True);restart_shell();until(lambda:call()['timer']);assert call()['preset']=='edge'
        call(preset='aurora')
        unknown='zorin11-motion-test-missing@zorin-os-fixes'
        (ext/'controls.js').write_text((ext/'controls.js').read_text().replace(UUID,unknown))
        unknownPrefs=start(['/usr/bin/gjs','-m',str(ext/'preferences.js')],env)
        until(lambda:'First activation' in call('MotionPrefs')['status'])
        call('MotionPrefs',apply=True);until(lambda:not call('MotionPrefs')['busy'])
        assert 'First activation' in call('MotionPrefs')['status']
        assert unknown in subprocess.check_output(['gsettings','get','org.gnome.shell','enabled-extensions'],text=True)
        call('MotionPrefs',preset='edge',close=True);unknownPrefs.wait(timeout=5)
        assert call()['preset']=='aurora','Closing an unapplied preview must not save it'
        text=(output/'shell.log').read_text()
        assert 'JS ERROR' not in text and '/motion.js:' not in text and '/preferences.js:' not in text and '/controls.js:' not in text and 'Failed to open preferences' not in text and 'Taskbar preferences:' not in text,text[-6000:]
        print('PASS: automatic app/tray growth and shrinkage without overlap on two panels, cold Shell startup on/off, manual Apply and same-preset activation, empty-panel startup ordering, two native context menus and launcher, two Zorin panels, six styles, active-app geometry, native Taskbar preferences with Motion, draft/Apply/Revert, persistence, reduced motion/battery/overview/fullscreen pauses, rebuild and disable/enable; screenshots captured.')
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
            # A private dconf service/database supports concurrent Shell/GTK
            # writes without the keyfile backend's whole-file overwrite race.
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='dconf',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='motion-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=160)
            print(result.stdout)
            if result.returncode:print(result.stderr[-4000:]);print((output/'shell.log').read_text()[-6000:])
            raise SystemExit(result.returncode)
