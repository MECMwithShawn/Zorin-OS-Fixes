#!/usr/bin/python3
"""Native GNOME taskbar test on a private bus/display; never touches host windows."""
import json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11@zorin-os-fixes'
APP='local.zorin11.TaskbarTest.desktop'
FIXTURE_JS=r'''
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const XML='<node><interface name="local.zorin11.TaskbarTest"><method name="Call"><arg direction="in" type="s"/><arg direction="out" type="s"/></method><method name="Capture"><arg direction="out" type="s"/></method></interface></node>';
export default class Fixture extends Extension {
 enable(){this.pointer=Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/TaskbarTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.TaskbarTest',0,null,null);}
 Call(action){
  const panel=global.zorinTaskbar.panels[0],button=panel._showDesktopButton;
  if(action==='desktop'){this.pointer.notify_button(GLib.get_monotonic_time(),1,Clutter.ButtonState.PRESSED);this.pointer.notify_button(GLib.get_monotonic_time(),1,Clutter.ButtonState.RELEASED);}
  if(action==='enter'){const [x,y]=button.get_transformed_position(),[w,h]=button.get_transformed_size();this.pointer.notify_absolute_motion(GLib.get_monotonic_time(),x+w/2,y+h/2);}
  if(action==='leave')this.pointer.notify_absolute_motion(GLib.get_monotonic_time(),500,200);
  if(action==='overview-close')Main.overview.hide();
  return JSON.stringify({style:button.get_style(),icon:button.icon.get_parent()===button,visible:button.visible,
   windows:global.get_window_actors().map(a=>({title:a.meta_window.get_title(),visible:a.visible,minimized:a.meta_window.minimized}))});
 }
 async CaptureAsync(_args,invocation){try{
  const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);
  invocation.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));
 }catch(e){invocation.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.pointer=null;this.bus.unexport();Gio.bus_unown_name(this.owner);}
}
'''

def session(temp,output):
    import base64,dbus
    from gi.repository import Gio,GLib
    sys.path[:0]=[str(ROOT),str(ROOT/'companion')]
    from gnome_bridge import call
    import gnome_setup
    extensions=temp/'data/gnome-shell/extensions'
    extension=extensions/UUID
    shutil.copytree(ROOT/'gnome-extension',extension)
    for icon in ('start.svg','search.svg','taskview.svg'):shutil.copy(ROOT/'companion'/icon,extension/icon)
    subprocess.run(['glib-compile-schemas',str(extension/'schemas')],check=True)
    fixture=extensions/'taskbar-fixture@test';fixture.mkdir()
    (fixture/'metadata.json').write_text(json.dumps(dict(uuid='taskbar-fixture@test',name='Taskbar test',description='Isolated test only',**{'shell-version':['46']})))
    (fixture/'extension.js').write_text(FIXTURE_JS)
    apps=temp/'data/applications';apps.mkdir()
    (apps/APP).write_text('[Desktop Entry]\nType=Application\nName=Taskbar Test\nExec=true\nIcon=utilities-terminal\nStartupWMClass=Zorin11TaskbarTest\n')
    shellsettings=Gio.Settings.new('org.gnome.shell')
    shellsettings.set_strv('enabled-extensions',['zorin-taskbar@zorinos.com',UUID,'taskbar-fixture@test'])
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir() and p.name!='zorin-taskbar@zorinos.com'])
    shellsettings.set_strv('favorite-apps',[APP]);shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.new('org.gnome.mutter').set_boolean('dynamic-workspaces',False)
    Gio.Settings.sync()
    children=[]
    def start(args,env=None):
        p=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    log=(output/'shell.log').open('w')
    start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
    start(['gnome-shell','--headless','--wayland','--virtual-monitor','1280x800','--wayland-display','taskbar-test'])
    def test_call(action):
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        return json.loads(bus.call_sync('local.zorin11.TaskbarTest','/local/zorin11/TaskbarTest','local.zorin11.TaskbarTest','Call',GLib.Variant('(s)',(action,)),None,0,3000,None).unpack()[0])
    try:
        until(lambda:call('snapshot'))
        until(lambda:'Registering session with GDM' in (output/'shell.log').read_text())
        time.sleep(1)
        gnome_setup.install(gnome_setup.plan({gnome_setup.TASKBAR:gnome_setup.appearance(gnome_setup.monitor_ids())[gnome_setup.TASKBAR]}),temp/'recovery.json')
        until(lambda:re.search(r'public X11 display (:\d+)',(output/'shell.log').read_text()))
        display=re.search(r'public X11 display (:\d+)',(output/'shell.log').read_text()).group(1)
        env=dict(os.environ,DISPLAY=display,XAUTHORITY=str(next((temp/'runtime').glob('.mutter-Xwaylandauth.*'))),GDK_BACKEND='x11',WAYLAND_DISPLAY='taskbar-test')
        subprocess.run(['dbus-update-activation-environment','DISPLAY='+env['DISPLAY'],'XAUTHORITY='+env['XAUTHORITY'],'WAYLAND_DISPLAY=taskbar-test'],env=env,check=True)
        code="import gi;gi.require_version('Gtk','3.0');from gi.repository import Gtk;w=Gtk.Window(title='Taskbar progress fixture');w.set_wmclass('Zorin11TaskbarTest','Zorin11TaskbarTest');w.set_default_size(500,300);w.add(Gtk.Label(label='Taskbar progress and badge fixture'));w.show_all();Gtk.main()"
        start(['/usr/bin/python3','-c',code],env)
        until(lambda:any(w['title']=='Taskbar progress fixture' for w in call('snapshot')['windows']))
        test_call('overview-close')
        until(lambda:[r for r in call('taskbar-status') if r['app']==APP])
        bus=dbus.SessionBus(private=True)
        def update(**values):
            from dbus.lowlevel import SignalMessage
            message=SignalMessage('/local/zorin11/test','com.canonical.Unity.LauncherEntry','Update')
            message.append('application://'+APP,dbus.Dictionary(values,signature='sv'),signature='sa{sv}')
            bus.send_message(message);bus.flush()
        def row():return next(r for r in call('taskbar-status') if r['app']==APP)
        update(progress=dbus.Double(.35),**{'progress-visible':dbus.Boolean(True)})
        until(lambda:row()['progress']==.35)
        until(lambda:'35%' in row()['label'] and (row()['rect'][2] or 0)>0)
        update(progress=dbus.Double(.8));until(lambda:row()['progress']==.8)
        # A second window leaves the first app unfocused, so its native badge is visible.
        start(['/usr/bin/python3','-c',code.replace('Taskbar progress fixture','Taskbar focus fixture').replace('Zorin11TaskbarTest','Zorin11FocusTest')],env)
        until(lambda:any(w['title']=='Taskbar focus fixture' and w['focused'] for w in call('snapshot')['windows']))
        update(count=dbus.Int64(3),**{'count-visible':dbus.Boolean(True)})
        until(lambda:row()['badge']=='3' and row()['badgeVisible'])
        time.sleep(.5)
        gb=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        image=gb.call_sync('local.zorin11.TaskbarTest','/local/zorin11/TaskbarTest','local.zorin11.TaskbarTest','Capture',None,None,0,5000,None).unpack()[0]
        (output/'taskbar-progress.png').write_bytes(base64.b64decode(image))
        update(count=dbus.Int64(0),**{'count-visible':dbus.Boolean(False)})
        until(lambda:row()['badge']=='')
        settings=Gio.Settings.new(gnome_setup.TASKBAR)
        settings.set_int('panel-size',52);Gio.Settings.sync();time.sleep(.5)
        until(lambda:row()['progress']==.8 and (row()['rect'][2] or 0)>0)
        settings.set_int('panel-size',48);Gio.Settings.sync();time.sleep(.5)
        until(lambda:row()['progress']==.8)
        settings.set_boolean('progress-show-bar',False);Gio.Settings.sync();until(lambda:not row()['progressVisible'])
        settings.set_boolean('progress-show-bar',True);Gio.Settings.sync();until(lambda:row()['progress']==.8)
        update(**{'progress-visible':dbus.Boolean(False)});until(lambda:row()['progress'] is None)
        update(progress=dbus.Double(.5),**{'progress-visible':dbus.Boolean(True)})
        until(lambda:row()['progress']==.5)
        bus.close();until(lambda:row()['progress'] is None)
        print('Native taskbar progress: update, visible badge, screenshot, settings toggle, hide and sender-exit cleanup passed',flush=True)
        desktop=test_call('snapshot');assert desktop['visible'] and not desktop['icon'] and 'width:8px' in desktop['style'],desktop
        test_call('enter')
        until(lambda:any(w['title']=='Taskbar focus fixture' and not w['visible'] for w in test_call('snapshot')['windows']))
        test_call('leave')
        until(lambda:any(w['title']=='Taskbar focus fixture' and w['visible'] for w in test_call('snapshot')['windows']))
        test_call('enter');time.sleep(.1)
        test_call('desktop')
        until(lambda:all(w['minimized'] for w in call('snapshot')['windows'] if w['title'].endswith('fixture')))
        test_call('desktop')
        until(lambda:all(not w['minimized'] for w in call('snapshot')['windows'] if w['title'].endswith('fixture')))
        print('Narrow desktop strip: real enter/leave and click handlers peek, restore and toggle windows passed',flush=True)
        # Disable/enable tears down and reattaches overlays without touching the taskbar.
        enabled=shellsettings.get_strv('enabled-extensions')
        shellsettings.set_strv('enabled-extensions',[u for u in enabled if u!=UUID]);Gio.Settings.sync()
        until(lambda:not gb.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',GLib.Variant('(s)',('local.zorin11.Gnome',)),None,0,2000,None).unpack()[0])
        shellsettings.set_strv('enabled-extensions',enabled);Gio.Settings.sync()
        until(lambda:row()['progress'] is None)
        assert not any(s in (output/'shell.log').read_text() for s in ['JS ERROR','taskbar-progress.js']), (output/'shell.log').read_text()[-6000:]
        print('Extension disable/enable and no companion JavaScript errors passed',flush=True)
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
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-taskbar-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-taskbar-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='taskbar-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=120)
            print(result.stdout)
            if result.returncode:print(result.stderr[-5000:]);print((output/'shell.log').read_text()[-5000:])
            raise SystemExit(result.returncode)
