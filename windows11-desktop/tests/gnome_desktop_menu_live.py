#!/usr/bin/python3
"""Run the real Zorin desktop and menu adapter in a disposable GNOME session."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop_menu_install import UUID, VENDOR, prepare
from gnome_live import systemd_fixture, until

if '--systemd-fixture' in sys.argv:
    systemd_fixture()
    raise SystemExit

if '--session' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='axentra-desktop-session-') as directory:
        root = Path(directory)
        for name in ('runtime', 'config', 'data', 'cache', 'desktop'):
            (root/name).mkdir(mode=0o700)
        (root/'desktop/menu-test.txt').write_text('Disposable desktop fixture\n')
        (root/'config/user-dirs.dirs').write_text(f'XDG_DESKTOP_DIR="{root}/desktop"\n')
        env = dict(os.environ, XDG_RUNTIME_DIR=str(root/'runtime'),
                   XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
                   XDG_CACHE_HOME=str(root/'cache'), GSETTINGS_BACKEND='keyfile',
                   XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='wayland',
                   GNOME_SHELL_SESSION_MODE='user',
                   WAYLAND_DISPLAY='axentra-menu-test', GDK_BACKEND='wayland',
                   GIO_USE_VFS='local', GIO_USE_VOLUME_MONITOR='unix', GTK_USE_PORTAL='0',
                   PULSE_SERVER='unix:'+str(root/'no-pulse'))
        result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--session', str(root)],
                                env=env, capture_output=True, text=True, timeout=80)
        print(result.stdout)
        if result.returncode:
            print(result.stderr[-3000:])
            if (root/'shell.log').exists():
                print((root/'shell.log').read_text()[-6000:])
        raise SystemExit(result.returncode)

from gi.repository import Gio, GLib
root = Path(sys.argv[-1])
extensions = root/'data/gnome-shell/extensions'
# The vendor constructor kills old processes matching its own path. Copy it so
# the private test can never match the user's real desktop process.
vendor = extensions/VENDOR.name
shutil.copytree(VENDOR, vendor)
extension = extensions/UUID
for path, data in prepare(extension, vendor=vendor).items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
subprocess.run(['glib-compile-schemas', str(extension/'schemas')], check=True)
# Test-only instrumentation observes real rendered file items and menu actions.
with (extension/'app/desktopManager.js').open('a') as stream:
    stream.write("""
const drawForTest = DesktopManager.prototype._drawDesktop;
DesktopManager.prototype._drawDesktop = function(files) {
    drawForTest.call(this, files);
    GLib.file_set_contents(GLib.build_filenamev([GLib.get_user_config_dir(), 'menu-state.json']),
        JSON.stringify({files:this._fileList.length, rows:this._menu.get_children().map(
            row => row.get_accessible().accessible_name), codePath:this._codePath,
            pid:GLib.file_read_link('/proc/self')}));
};
""")
(extension/'extension.js').rename(extension/'adapter.js')
(extension/'extension.js').write_text("""
import Base from './adapter.js';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML=`<node><interface name="local.zorin11.DesktopMenuTest"><method name="State"><arg type="s" direction="out"/></method></interface></node>`;
export default class Test extends Base {
 enable(){super.enable();this._bus=Gio.DBusExportedObject.wrapJSObject(XML,this);
 this._bus.export(Gio.DBus.session,'/local/zorin11/DesktopMenuTest');
 this._owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.DesktopMenuTest',Gio.BusNameOwnerFlags.NONE,null,null);}
 State(){const d=Main.extensionManager.lookup('zorin-desktop-icons@zorinos.com')?.stateObj;
 return JSON.stringify({hooked:!!this._ding, pid:d?.data.currentProcess?.subprocess?.get_identifier(), path:d?.path});}
 disable(){this._bus?.unexport();if(this._owner)Gio.bus_unown_name(this._owner);super.disable();}
}
""")
shell_settings = Gio.Settings.new('org.gnome.shell')
shell_settings.set_strv('enabled-extensions', [VENDOR.name, UUID])
shell_settings.set_string('welcome-dialog-last-shown-version', '46.0')
icons = Gio.Settings.new('org.gnome.shell.extensions.zorin-desktop-icons')
for key in ('show-home', 'show-trash', 'show-volumes', 'show-network-volumes'):
    icons.set_boolean(key, False)
Gio.Settings.sync()
stub = subprocess.Popen([sys.executable, __file__, '--systemd-fixture'])
time.sleep(.2)
log = (root/'shell.log').open('w')
shell = subprocess.Popen(['gnome-shell', '--headless', '--wayland', '--virtual-monitor',
                          '1280x800', '--wayland-display', 'axentra-menu-test'], stdout=log, stderr=log)
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
def state():
    return json.loads(bus.call_sync('local.zorin11.DesktopMenuTest', '/local/zorin11/DesktopMenuTest',
        'local.zorin11.DesktopMenuTest', 'State', None, None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0])
def rendered():
    return json.loads((root/'config/menu-state.json').read_text())
def extension_action(method):
    return bus.call_sync('org.gnome.Shell.Extensions', '/org/gnome/Shell/Extensions',
        'org.gnome.Shell.Extensions', method, GLib.Variant('(s)', (UUID,)), None,
        Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
def launched_from(pid):
    return (Path('/proc')/pid/'cmdline').read_bytes().split(b'\0')[1].decode()
def desktops(launcher):
    found = []
    for proc in Path('/proc').iterdir():
        try:
            if proc.name.isdigit() and str(launcher).encode() in (proc/'cmdline').read_bytes():
                found.append(proc.name)
        except OSError:
            pass
    return found
def remove_vendor_links():
    # Reproduce what restore's cleanup leaves: the adapter files without Zorin's
    # launcher links or compiled schema. Move them aside within this session only.
    assert extension.is_relative_to(root) and vendor.is_relative_to(root)
    held = root/'removed-adapter-links'
    held.mkdir()
    for link in (extension/'app').iterdir():
        if link.is_symlink():
            link.rename(held/link.name)
    (extension/'schemas/gschemas.compiled').rename(held/'gschemas.compiled')
def settled(exclude=None, drawn=True):
    # Zorin's first desktop process can exit and relaunch during startup. Act only
    # once one process (which has drawn, for the adapter) is still supervised 1.5 s later.
    for _ in range(5):
        current = until(lambda: (s if (s:=state()).get('pid') not in (None, exclude)
                                 and (not drawn or rendered().get('pid') == s['pid']) else None))
        time.sleep(1.5)
        if state().get('pid') == current['pid']:
            return current
    raise AssertionError('Zorin desktop kept relaunching')
try:
    until(lambda: state().get('hooked'))
    initial = settled()
    until(lambda: rendered()['files'] == 1)
    assert 'Personalize' in rendered()['rows'] and 'Show more options' in rendered()['rows']
    assert initial['path'] == str(vendor), initial  # launch path restored after spawn
    command = Path('/proc')/initial['pid']/'cmdline'
    assert str(extension/'app/ding.js').encode() in command.read_bytes()
    source = Gio.SettingsSchemaSource.new_from_directory(str(extension/'schemas'),
                                                        Gio.SettingsSchemaSource.get_default(), False)
    preferences = Gio.Settings.new_full(source.lookup('org.gnome.shell.extensions.zorin11-desktop', False), None, None)
    preferences.set_boolean('show-icons', False); Gio.Settings.sync()
    until(lambda: rendered()['files'] == 0)
    assert (root/'desktop/menu-test.txt').is_file()
    preferences.set_boolean('show-icons', True); Gio.Settings.sync()
    until(lambda: rendered()['files'] == 1)
    # Fenced icons: skipped while the publishing companion lives, back when it is gone.
    fenced = root/'config/zorin11-hub/fenced.json'
    fenced.parent.mkdir()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    started = (lambda stat: stat[stat.rindex(')')+2:].split()[19])(Path('/proc/self/stat').read_text())
    def publish(**identity):
        fenced.write_text(json.dumps({'version': 1, 'pid': os.getpid(), 'boot': boot, 'start': started,
                                      'paths': [str(root/'desktop/menu-test.txt')], **identity}))
    publish()
    until(lambda: rendered()['files'] == 0)
    publish(start='1')  # same PID, different process (reused PID): hides nothing
    until(lambda: rendered()['files'] == 1)
    publish()
    until(lambda: rendered()['files'] == 0)
    gone = subprocess.Popen(['sleep', '30'])
    try:
        # The publishing process dies without rewriting the list: icons return.
        stat = Path(f'/proc/{gone.pid}/stat').read_text()
        publish(pid=gone.pid, start=stat[stat.rindex(')')+2:].split()[19])
        until(lambda: rendered()['files'] == 0)
    finally:
        gone.kill(); gone.wait()
    until(lambda: rendered()['files'] == 1)
    publish()
    until(lambda: rendered()['files'] == 0)
    fenced.write_text('{not json')
    until(lambda: rendered()['files'] == 1)
    assert (root/'desktop/menu-test.txt').is_file()
    assert extension_action('DisableExtension')
    until(lambda: not command.exists())
    assert extension_action('EnableExtension')
    until(lambda: state().get('hooked') and state().get('pid') != initial['pid'])
    hooked = settled()
    until(lambda: rendered()['files'] == 1)
    # Links removed while the adapter is loaded: the next relaunch must use Zorin's desktop.
    remove_vendor_links()
    os.kill(int(hooked['pid']), signal.SIGTERM)
    fallback = settled(exclude=hooked['pid'], drawn=False)  # Zorin's own manager is not instrumented
    assert launched_from(fallback['pid']) == str(vendor/'app/ding.js'), fallback
    # Login with an incomplete adapter must leave the running Zorin desktop alone.
    assert extension_action('DisableExtension')
    original = until(lambda: desktops(vendor/'app/ding.js'))
    assert extension_action('EnableExtension')
    until(state)
    time.sleep(1.5)  # a killed desktop would have been replaced by now
    incomplete = state()
    assert not incomplete['hooked'] and incomplete['pid'] in original, incomplete
    assert desktops(vendor/'app/ding.js') == original
    # Reinstalling the links restores the adapter at the next enable/login.
    prepare(extension, vendor=vendor)
    subprocess.run(['glib-compile-schemas', str(extension/'schemas')], check=True)
    (root/'config/menu-state.json').unlink()
    assert extension_action('DisableExtension')
    assert extension_action('EnableExtension')
    until(lambda: state().get('hooked'))
    repaired = settled()
    assert launched_from(repaired['pid']) == str(extension/'app/ding.js'), repaired
    until(lambda: rendered()['files'] == 1)
    messages = (root/'shell.log').read_text()
    assert 'JS ERROR' not in messages and 'Exception while Initiating Desktop' not in messages
    assert 'Error while trying to launch DING process' not in messages
    print('PASS fenced desktop files are skipped only while the publishing companion runs (PID reuse and crashes return them); bad lists hide nothing')
    print('PASS GNOME login startup, real Zorin desktop rendering, hide/show preserving files, disable/enable and process supervision')
    print('PASS removed adapter links fall back to Zorin desktop at relaunch and login; repair restores the menu')
finally:
    # Disable the private vendor extension before Shell exits to reap its child.
    try:
        bus.call_sync('org.gnome.Shell.Extensions', '/org/gnome/Shell/Extensions',
            'org.gnome.Shell.Extensions', 'DisableExtension', GLib.Variant('(s)', (VENDOR.name,)),
            None, Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error:
        pass
    for process in (shell, stub):
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
    log.close()
