#!/usr/bin/python3
"""Browser picture-in-picture windows stay on top, in a private headless GNOME Shell with stand-in
GTK windows (never the signed-in session or a real browser)."""
import json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11@zorin-os-fixes'
FIXTURE_JS=r'''
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const XML='<node><interface name="local.zorin11.PipTest"><method name="Windows"><arg direction="out" type="s"/></method><method name="Unpin"><arg direction="in" type="s"/></method><method name="Companion"><arg direction="in" type="b"/></method></interface></node>';
const windows=()=>global.get_window_actors().map(a=>a.meta_window);
export default class Fixture extends Extension {
 enable(){this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/PipTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.PipTest',0,null,null);}
 Windows(){return JSON.stringify(windows().map(w=>({title:w.get_title(),wmClass:w.get_wm_class(),above:w.is_above()})));}
 Unpin(title){windows().find(w=>w.get_title()===title)?.unmake_above();}
 Companion(on){on?Main.extensionManager.enableExtension('zorin11@zorin-os-fixes'):Main.extensionManager.disableExtension('zorin11@zorin-os-fixes');}
 disable(){this.bus.unexport();Gio.bus_unown_name(this.owner);}
}
'''
# One GTK window: app ID, first title, then (after a moment) a later title, as browsers can do.
CLIENT=r'''
import sys
from gi.repository import GLib
GLib.set_prgname(sys.argv[1])
import gi;gi.require_version('Gtk','3.0')
from gi.repository import Gtk
w=Gtk.Window(title=sys.argv[2]);w.set_default_size(320,180);w.connect('destroy',Gtk.main_quit);w.show_all()
if len(sys.argv)>3:GLib.timeout_add(400,lambda:w.set_title(sys.argv[3]))
Gtk.main()
'''

def session(temp,output):
    from gi.repository import Gio
    extensions=temp/'data/gnome-shell/extensions'
    extension=extensions/UUID
    shutil.copytree(ROOT/'gnome-extension',extension)
    subprocess.run(['glib-compile-schemas',str(extension/'schemas')],check=True)
    fixture=extensions/'pip-fixture@test';fixture.mkdir()
    (fixture/'metadata.json').write_text(json.dumps(dict(uuid='pip-fixture@test',name='PiP test',description='Isolated test only',**{'shell-version':['46']})))
    (fixture/'extension.js').write_text(FIXTURE_JS)
    (temp/'client.py').write_text(CLIENT)
    shellsettings=Gio.Settings.new('org.gnome.shell')
    shellsettings.set_strv('enabled-extensions',[UUID,'pip-fixture@test'])
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir()])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.sync()
    children=[]
    log=(output/'shell.log').open('w')
    def start(args,**kw):
        p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,**kw);children.append(p);return p
    start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
    start(['gnome-shell','--headless','--wayland','--no-x11','--virtual-monitor','1280x800','--wayland-display','pip-test'])
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def fixture(method,args=None):
        from gi.repository import GLib
        return bus.call_sync('local.zorin11.PipTest','/local/zorin11/PipTest','local.zorin11.PipTest',method,args and GLib.Variant(*args),None,0,5000,None).unpack()
    def windows():return {w['title']:w for w in json.loads(fixture('Windows')[0])}
    def client(app,*titles):
        return start(['/usr/bin/python3',str(temp/'client.py'),app,*titles],env=dict(os.environ,GDK_BACKEND='wayland'))
    def above(title):
        until(lambda:title in windows());time.sleep(.3);return windows()[title]['above']
    try:
        until(lambda:fixture('Windows'))
        until(lambda:'Registering session with GDM' in (output/'shell.log').read_text())
        client('brave-browser','Picture in picture')
        assert above('Picture in picture'),windows()
        assert windows()['Picture in picture']['wmClass']=='brave-browser',windows()
        client('firefox','Picture-in-Picture')
        assert above('Picture-in-Picture'),windows()
        # Named just after it appears.
        client('brave-browser','','Picture in picture ')
        until(lambda:'Picture in picture ' in windows())
        until(lambda:windows()['Picture in picture ']['above'],5)
        # Normal browser windows and other apps are left alone.
        client('brave-browser','YouTube - Brave')
        client('notes-app','Picture in picture?')
        client('notes-app','Picture  in picture')
        for title in ('YouTube - Brave','Picture in picture?','Picture  in picture'):
            assert not above(title),(title,windows())
        # Unpinning sticks, also when the companion restarts after the lock screen.
        fixture('Unpin',('(s)',('Picture in picture',)))
        until(lambda:not windows()['Picture in picture']['above'])
        fixture('Companion',('(b)',(False,)));time.sleep(.5)
        # A video that opens while the companion is off is pinned when it comes back.
        client('chromium','Picture-in-picture')
        assert not above('Picture-in-picture'),windows()
        fixture('Companion',('(b)',(True,)))
        until(lambda:windows()['Picture-in-picture']['above'],5)
        time.sleep(.5)
        assert not windows()['Picture in picture']['above'],'an unpinned video stays unpinned'
        assert windows()['Picture-in-Picture']['above']
        print('PiP on top: Brave, Firefox and Chromium videos pinned (also when named late or opened while off); other windows untouched; unpinning sticks',flush=True)
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
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-pip-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-pip-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='pip-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=120)
            print(result.stdout)
            if result.returncode:print(result.stderr[-5000:]);print((output/'shell.log').read_text()[-5000:])
            raise SystemExit(result.returncode)
