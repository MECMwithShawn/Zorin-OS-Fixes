#!/usr/bin/python3
"""Keep-on lock on a private GNOME Wayland session.

Locks through the real org.gnome.ScreenSaver service and watches ActiveChanged,
the signal gsd-power turns the displays off on. Never touches the real session.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from gnome_live import until, systemd_fixture

ROOT = Path(__file__).resolve().parents[1]
UUID = 'zorin11-lock-test@zorin-os-fixes'
WRAPPER = r'''
import Base from './lockscreen.js';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML='<node><interface name="local.zorin11.KeepTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>';
export default class Test extends Base {
 enable(){super.enable();this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/KeepTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.KeepTest',0,null,null);}
 Call(text){const p=JSON.parse(text);Main.overview.hide();
  if(p.idle!==undefined)this._keepAwake._idleTime=()=>p.idle;
  if(p.minutes)this._keepAwake._minutes=p.minutes;
  if(p.unlock)Main.screenShield.deactivate(false);
  return JSON.stringify({active:Main.screenShield.active,locked:Main.screenShield.locked});}
 disable(){this.bus.unexport();Gio.bus_unown_name(this.owner);super.disable();}
}
'''


def session(temp):
    from gi.repository import Gio, GLib
    ext = temp/'data/gnome-shell/extensions'/UUID
    shutil.copytree(ROOT/'gnome-lockscreen-extension', ext)
    (ext/'extension.js').rename(ext/'lockscreen.js')
    (ext/'extension.js').write_text(WRAPPER)
    meta = json.loads((ext/'metadata.json').read_text()); meta['uuid'] = UUID
    (ext/'metadata.json').write_text(json.dumps(meta))
    subprocess.run(['glib-compile-schemas', '--strict', str(ext/'schemas')], check=True)
    shell = Gio.Settings.new('org.gnome.shell')
    shell.set_strv('enabled-extensions', [UUID])
    shell.set_string('welcome-dialog-last-shown-version', '46.0')
    Gio.Settings.sync()
    log = (temp/'shell.log').open('w'); children = []
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    signals = []
    bus.signal_subscribe('org.gnome.ScreenSaver', 'org.gnome.ScreenSaver', 'ActiveChanged', '/org/gnome/ScreenSaver', None, 0,
                         lambda c, s, p, i, n, v: signals.append(v.unpack()[0]))
    def pump(seconds=.4):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            GLib.MainContext.default().iteration(False); time.sleep(.02)
    def call(**p):
        return json.loads(bus.call_sync('local.zorin11.KeepTest', '/local/zorin11/KeepTest', 'local.zorin11.KeepTest',
                                        'Call', GLib.Variant('(s)', (json.dumps(p),)), None, 0, 3000, None).unpack()[0])
    def lock():
        bus.call(  'org.gnome.ScreenSaver', '/org/gnome/ScreenSaver', 'org.gnome.ScreenSaver', 'Lock',
                 None, None, 0, 8000, None, None)
        until(lambda: (pump(.1), call()['active'])[1], seconds=8)
    try:
        children.append(subprocess.Popen([sys.executable, __file__, '--systemd-fixture'], stdout=log, stderr=subprocess.STDOUT))
        time.sleep(.3)
        children.append(subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--virtual-monitor', '1280x800',
                                          '--wayland-display', 'lock-test'], stdout=log, stderr=subprocess.STDOUT))
        until(call, seconds=20)
        assert 'Exception in callback' not in (temp/'shell.log').read_text()
        call(idle=0, minutes=2/60)
        lock(); pump(1)
        assert call()['active'] and signals == [], signals
        assert 'Exception in callback' not in (temp/'shell.log').read_text()
        print('PASS a manual lock activates without telling the power service', flush=True)
        until(lambda: (pump(.1), signals)[1], seconds=4)
        assert signals == [True], signals
        print('PASS the signal goes out after the time limit', flush=True)
        call(unlock=True); until(lambda: (pump(.1), not call()['active'])[1], seconds=5); pump(.6)
        assert signals == [True, False], signals
        signals.clear()
        call(idle=60000)
        lock(); pump(.6)
        assert signals == [True], signals
        print('PASS an idle lock tells the power service at once', flush=True)
        assert 'Exception in callback' not in (temp/'shell.log').read_text()
    finally:
        for p in reversed(children):
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()


if '--systemd-fixture' in sys.argv:
    systemd_fixture(); raise SystemExit
if '--session' in sys.argv:
    session(Path(sys.argv[-1])); raise SystemExit
with tempfile.TemporaryDirectory(prefix='zorin11-lock-') as directory:
    temp = Path(directory)
    for name in ('runtime', 'config', 'data', 'cache'):
        (temp/name).mkdir(mode=0o700)
    env = dict(os.environ, HOME=str(temp), XDG_RUNTIME_DIR=str(temp/'runtime'), XDG_CONFIG_HOME=str(temp/'config'),
               XDG_DATA_HOME=str(temp/'data'), XDG_CACHE_HOME=str(temp/'cache'), GSETTINGS_BACKEND='keyfile',
               XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland', GNOME_SHELL_SESSION_MODE='user',
               WAYLAND_DISPLAY='lock-test', GIO_USE_VFS='local', GTK_USE_PORTAL='0')
    result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--session', str(temp)],
                            env=env, capture_output=True, text=True, timeout=100)
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr[-2500:])
        if (temp/'shell.log').exists():
            print((temp/'shell.log').read_text()[-3500:])
    raise SystemExit(result.returncode)
