#!/usr/bin/python3
"""Windows 11 login screen on a private GNOME 'gdm' mode Wayland session.

The real LoginDialog runs against this machine's account list, but the verifier
is never started: choosing the account is recorded and no password is involved.
Pass --shots DIR to save a screenshot of the sign-in page.
"""
import base64, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from gnome_live import until, systemd_fixture

ROOT = Path(__file__).resolve().parents[1]
UUID = 'zorin11-login-test@zorin-os-fixes'
WRAPPER = r'''
import Base from './login.js';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {LoginDialog} from 'resource:///org/gnome/shell/gdm/loginDialog.js';
const XML='<node><interface name="local.zorin11.LoginTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="Capture"><arg type="s" direction="out"/></method></interface></node>';
const native=['_beginVerification','_startSession','_loginScreenSessionActivated','_onPrompted','_onReset'];
const originals=native.map(k=>LoginDialog.prototype[k]);
let chosen=[];
LoginDialog.prototype._onUserListActivated=function(item){chosen.push(item.user.get_user_name());this._user=item.user;this._authPrompt.setUser(item.user);this._hideUserList();this._authPrompt.setQuestion('Password');this._showPrompt();};
export default class Test extends Base {
 enable(){this.missing=false;super.enable();this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/LoginTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.LoginTest',0,null,null);}
 _picture(){return this.missing?null:Gio.File.new_for_path(GLib.getenv('ZORIN11_TEST_PICTURE'));}
 Call(text){const p=JSON.parse(text),d=this._dialog??this.last;
  if(p.startup)d._updateDisableUserList();
  if(p.missing!==undefined){this.missing=p.missing;this._renderBackground();}
  if(p.back){d._user=null;d._showUserList();}
  if(p.detach){this.last=d;super.disable();}
  if(p.again)super.enable();
  return JSON.stringify({mode:Main.sessionMode.currentMode,dialog:!!d,visible:d?.visible,styled:d?.has_style_class_name('zorin11-login'),
   logo:d?._logoBin.visible,date:Main.panel.statusArea.dateMenu?.container.visible,chosen,users:d?._userList.numItems(),
   backgrounds:this._backgrounds?.map(w=>[w.width,w.height]),behind:d?.get_parent().get_child_at_index(0)===this._group,
   time:this._time?.text,dateText:this._date?.text,inGroup:this._clock?.get_parent()===this._group,
   prompt:d?._authPrompt.visible,native:native.every((k,i)=>LoginDialog.prototype[k]===originals[i])});}
 async CaptureAsync(args,inv){try{const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);inv.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));}catch(e){inv.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.bus.unexport();Gio.bus_unown_name(this.owner);super.disable();}
}
'''


def session(temp, shots):
    from gi.repository import Gio, GLib
    ext = temp/'data/gnome-shell/extensions'/UUID
    ext.mkdir(parents=True)
    shutil.copy(ROOT/'gnome-login-extension/extension.js', ext/'login.js')
    shutil.copy(ROOT/'gnome-login-extension/stylesheet.css', ext)
    (ext/'extension.js').write_text(WRAPPER)
    (ext/'metadata.json').write_text(json.dumps({'uuid': UUID, 'name': 'Login test', 'description': 'test',
                                                 'shell-version': ['46'], 'session-modes': ['gdm']}))
    shell = Gio.Settings.new('org.gnome.shell')
    shell.set_strv('enabled-extensions', [UUID])
    Gio.Settings.new('org.gnome.desktop.interface').set_string('clock-format', '12h')
    Gio.Settings.sync()
    log = (temp/'shell.log').open('w'); children = []
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def call(**p):
        return json.loads(bus.call_sync('local.zorin11.LoginTest', '/local/zorin11/LoginTest', 'local.zorin11.LoginTest',
                                        'Call', GLib.Variant('(s)', (json.dumps(p),)), None, 0, 3000, None).unpack()[0])
    def shot(name):
        if shots:
            data = bus.call_sync('local.zorin11.LoginTest', '/local/zorin11/LoginTest', 'local.zorin11.LoginTest',
                                 'Capture', None, None, 0, 5000, None).unpack()[0]
            (Path(shots)/f'{name}.png').write_bytes(base64.b64decode(data))
    try:
        children.append(subprocess.Popen([sys.executable, __file__, '--systemd-fixture'], stdout=log, stderr=subprocess.STDOUT))
        time.sleep(.3)
        children.append(subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--mode=gdm', '--virtual-monitor', '1920x1200',
                                          '--wayland-display', 'login-test'], stdout=log, stderr=subprocess.STDOUT))
        row = until(lambda: (r if (r := call())['dialog'] else None), seconds=20)
        assert row['mode'] == 'gdm' and row['styled'] and row['native'], row
        assert row['behind'] and row['backgrounds'] == [[1920, 1200]], row
        assert row['logo'] is False and row['date'] is False and 'M' in row['time'] and row['dateText'], row
        print('PASS the photo, clock and styling wrap the native dialog; its login methods are untouched', flush=True)
        # Headless startup finishes before the dialog exists; run the step GNOME
        # runs on startup-complete so the account list loads as on a real screen.
        call(startup=True)
        row = until(lambda: (r if (r := call())['chosen'] else None), seconds=8)
        assert len(row['chosen']) == 1 == row['users'], row
        time.sleep(1.5)
        shot('login')
        print('PASS a lone account goes straight to the password box', flush=True)
        row = call(back=True); time.sleep(.6); row = call()
        assert len(row['chosen']) == 1, row
        print('PASS going back shows the account list instead of choosing again', flush=True)
        row = call(missing=True)
        assert row['backgrounds'] == [] and row['styled'], row
        print('PASS a missing photo leaves the working login screen', flush=True)
        row = call(missing=False, detach=True)
        assert row['styled'] is False and row['date'] is True, row
        print('PASS turning it off restores the login screen', flush=True)
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
with tempfile.TemporaryDirectory(prefix='zorin11-login-') as directory:
    temp = Path(directory)
    for name in ('runtime', 'config', 'data', 'cache'):
        (temp/name).mkdir(mode=0o700)
    env = dict(os.environ, HOME=str(temp), XDG_RUNTIME_DIR=str(temp/'runtime'), XDG_CONFIG_HOME=str(temp/'config'),
               XDG_DATA_HOME=str(temp/'data'), XDG_CACHE_HOME=str(temp/'cache'), GSETTINGS_BACKEND='keyfile',
               XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland', WAYLAND_DISPLAY='login-test',
               GIO_USE_VFS='local', GTK_USE_PORTAL='0', GDM_GREETER_TEST='1',
               ZORIN11_TEST_PICTURE=os.environ.get('ZORIN11_TEST_PICTURE', '/usr/share/backgrounds/Zorin.jpg'))
    result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--session', str(temp), shots],
                            env=env, capture_output=True, text=True, timeout=120)
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr[-3000:])
        if (temp/'shell.log').exists():
            print('\n'.join(l for l in (temp/'shell.log').read_text().splitlines() if 'xtension' in l or 'JS' in l or 'rror' in l)[-4000:])
    raise SystemExit(result.returncode)
