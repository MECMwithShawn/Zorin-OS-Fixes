#!/usr/bin/python3
"""Install per user, with a reversible Start-button and keyboard integration."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import dbus

SOURCE = Path(__file__).resolve().parent
HOME = Path.home()
DEST = HOME/'.local/share/zorin11-hub'
CONFIG = HOME/'.config/zorin11-hub'
MANIFEST = CONFIG/'integration-backup.json'
XF = dbus.Interface(dbus.SessionBus().get_object('org.xfce.Xfconf', '/org/xfce/Xfconf'), 'org.xfce.Xfconf')


def wait_owner(name, expected):
    bus = dbus.SessionBus()
    deadline = time.monotonic()+6
    while time.monotonic()<deadline:
        if bool(bus.name_has_owner(name))==expected:
            return
        time.sleep(.05)
    raise RuntimeError('Timed out waiting for '+name)


def stop_panel():
    # A preceding --restart may still be spawning its replacement. If that
    # replacement acquires the name during shutdown, send quit to it as well.
    for attempt in range(3):
        if not dbus.SessionBus().name_has_owner('org.xfce.Panel'):
            return
        recover_panel_plugin_dialog()
        subprocess.run(['xfce4-panel','--quit'],check=True,timeout=20)
        try:
            wait_owner('org.xfce.Panel', False)
            return
        except RuntimeError:
            if attempt==2:raise


def recover_panel_plugin_dialog():
    # Xfce may leave a modal plugin-recovery dialog after repeated restarts.
    # Choosing Execute retains the plugin/configuration and allows quit to finish.
    import gi
    gi.require_version('Atspi','2.0')
    from gi.repository import Atspi
    Atspi.set_timeout(150,300)
    def execute(node, depth=0):
        if depth>6:return False
        if node.get_name()=='Execute' and node.get_role()==Atspi.Role.PUSH_BUTTON:
            return node.get_action_iface().do_action(0)
        return any(execute(node.get_child_at_index(i),depth+1) for i in range(node.get_child_count()))
    try:
        desktop=Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app=desktop.get_child_at_index(i)
            if app.get_name()!='xfce4-panel':continue
            for j in range(app.get_child_count()):
                dialog=app.get_child_at_index(j)
                if dialog.get_name()=='Plugin Restart':execute(dialog)
    except Exception:
        pass


def start_panel():
    if not dbus.SessionBus().name_has_owner('org.xfce.Panel'):
        subprocess.Popen(['xfce4-panel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    wait_owner('org.xfce.Panel', True)


def network_applet_backend(argv):
    import signal
    result=subprocess.run(['pgrep','-u',str(os.getuid()),'-x','nm-applet'],capture_output=True,text=True)
    restarted=False
    for value in result.stdout.split():
        pid=int(value)
        try:
            args=Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')
            if (b'--no-indicator' in args)==('--no-indicator' in argv):
                continue
            os.kill(pid,signal.SIGTERM)
            deadline=time.monotonic()+3
            while Path(f'/proc/{pid}').exists() and time.monotonic()<deadline:
                time.sleep(.05)
            if Path(f'/proc/{pid}').exists():
                raise RuntimeError('Network applet did not exit; retained existing agent.')
            restarted=True
        except (ProcessLookupError,FileNotFoundError):
            restarted=True
    if restarted:
        log=open(CONFIG/'network-applet.log','a')
        subprocess.Popen(argv,stdout=log,stderr=log,start_new_session=True)


def encode(v):
    kind = type(v).__name__
    if isinstance(v, dbus.Array):
        return {'type': kind, 'signature': str(v.signature), 'value': [encode(x) for x in v]}
    return {'type': kind, 'value': bool(v) if isinstance(v, dbus.Boolean) else str(v) if isinstance(v, dbus.String) else float(v) if isinstance(v, dbus.Double) else int(v)}


def decode(v):
    if v['type'] == 'Array':
        return dbus.Array([decode(x) for x in v['value']], signature=v['signature'], variant_level=1)
    return getattr(dbus, v['type'])(v['value'], variant_level=1)


def current(channel, key):
    return encode(XF.GetProperty(channel, key)) if XF.PropertyExists(channel, key) else None


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    os.replace(temporary, path)


def desktop_file(name, argument, icon, hidden=False):
    return f'''[Desktop Entry]
Type=Application
Name={name}
Comment=Windows 11-inspired Start menu and desktop shortcut groups
Exec=/usr/bin/python3 "{DEST / 'app.py'}" {argument}
Icon={icon}
Terminal=false
StartupNotify=false
Categories=Utility;
NoDisplay={'true' if hidden else 'false'}
'''


def install():
    if 'XFCE' not in os.environ.get('XDG_CURRENT_DESKTOP', ''):
        raise SystemExit('This desktop integration is designed for the active Xfce session.')
    CONFIG.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists():
        raise SystemExit('Already installed. Use --uninstall before reinstalling; your pinned apps are preserved.')
    if not (SOURCE/'dist/main.js').is_file():
        raise SystemExit('Build the frontend first (node build.mjs).')
    manifest = {'settings': [], 'files': []}
    channel = 'xfce4-panel'
    from panel_layout import find_panel
    panel = find_panel(dict(XF.GetAllProperties(channel, '/')))
    panel_key = f'/panels/panel-{panel}/plugin-ids'
    ids = list(XF.GetProperty(channel, panel_key))
    menu = next((i for i in ids if str(XF.GetProperty(channel, f'/plugins/plugin-{i}')) == 'zorinmenulite'), None)
    if menu is None:
        raise SystemExit('No native Zorin menu found; inspect the layout before replacing its button.')
    plugin = 20
    while XF.PropertyExists(channel, f'/plugins/plugin-{plugin}'):
        plugin += 1
    menu_file = HOME/'.local/share/applications/zorin11-start.desktop'
    # Use an existing launcher-owned file. Xfce copies external .desktop files
    # and rewrites the items setting, which would invalidate the undo record.
    panel_file = HOME/f'.config/xfce4/panel/launcher-{plugin}/zorin11-start.desktop'
    groups_file = HOME/'.local/share/applications/zorin11-groups.desktop'
    autostart = HOME/'.config/autostart/zorin11-hub.desktop'
    launcher = f'/usr/bin/python3 "{DEST / "app.py"}"'
    settings = [
        (channel, f'/plugins/plugin-{plugin}', dbus.String('launcher')),
        (channel, f'/plugins/plugin-{plugin}/items', dbus.Array([dbus.String(panel_file.name)], signature='v')),
        (channel, f'/plugins/plugin-{plugin}/show-label', dbus.Boolean(False)),
        (channel, f'/plugins/plugin-{plugin}/disable-tooltips', dbus.Boolean(False)),
        (channel, panel_key, dbus.Array([dbus.Int32(plugin if i==menu else i) for i in ids], signature='v')),
    ]
    for key in ['Super_L', 'Super_R', '<Primary>Escape', '<Super>s']:
        settings.append(('xfce4-keyboard-shortcuts', '/commands/custom/'+key, dbus.String(launcher+' --toggle-start')))
    peek_key = '/commands/custom/<Super><Shift>f'
    if XF.PropertyExists('xfce4-keyboard-shortcuts', peek_key):
        raise SystemExit('Win+Shift+F is already assigned. Choose another Peek shortcut before installing.')
    settings.append(('xfce4-keyboard-shortcuts', peek_key, dbus.String(launcher+' --peek')))
    for c,k,v in settings:
        manifest['settings'].append({'channel':c, 'key':k, 'before':current(c,k), 'after':encode(v)})
    file_content = {
        menu_file: desktop_file('Start', '--toggle-start', str(DEST/'start.svg'), hidden=True),
        panel_file: desktop_file('Start', '--toggle-start', str(DEST/'start.svg'), hidden=True),
        groups_file: desktop_file('Desktop Groups', '--groups', 'view-grid-symbolic'),
        autostart: desktop_file('Zorin 11 Desktop', '--background', str(DEST/'start.svg'), hidden=True)+'OnlyShowIn=XFCE;\nX-GNOME-Autostart-enabled=true\n',
    }
    for p,content in file_content.items():
        manifest['files'].append({'path':str(p),'before':base64.b64encode(p.read_bytes()).decode() if p.exists() else None,
            'after':base64.b64encode(content.encode()).decode()})
    manifest['plugin'] = plugin
    manifest['panel'] = panel
    # Preserve the recovery record before editing the live desktop.
    write_json(MANIFEST, manifest)
    shutil.copytree(SOURCE, DEST, dirs_exist_ok=True, ignore=shutil.ignore_patterns('node_modules','__pycache__','.git','test_*.py','test_*.cjs'))
    try:
        stop_panel()
        for p,content in file_content.items():
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(content)
        for c,k,v in settings:
            XF.SetProperty(c,k,v)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database',str(menu_file.parent)],check=True)
        for change in manifest['settings']:
            if current(change['channel'],change['key']) != change['after']:
                raise RuntimeError('Integration setting did not apply: '+change['key'])
        # Apply the tray/Explorer additions before starting the panel once.
        # Rapidly starting the old audio plugin and then stopping it can trigger
        # Xfce's crash-recovery dialog during a fresh installation.
        from refine import upgrade
        upgrade()
    except Exception:
        uninstall()
        raise
    print('Installed Start menu, Desktop Groups, Windows-key shortcuts, and login startup.')
    print('Recovery manifest:',MANIFEST)


def uninstall():
    if not MANIFEST.exists():
        raise SystemExit('No integration backup found. Nothing was changed.')
    if (DEST/'effects.py').exists():
        subprocess.run(['/usr/bin/python3',str(DEST/'effects.py'),'--disable'],check=True)
    if dbus.SessionBus().name_has_owner('local.zorin11.DesktopHub'):
        subprocess.run(['/usr/bin/python3',str(DEST/'app.py'),'--quit'],timeout=15)
        wait_owner('local.zorin11.DesktopHub', False)
    manifest=json.loads(MANIFEST.read_text())
    skipped=[]
    # Stop the panel before restoring plugin settings: launchers flush their
    # item list when removed or stopped, otherwise recreating deleted keys.
    stop_panel()
    for change in reversed(manifest.get('gsettings',[])):
        schema,key=change['schema'],change['key']
        value=subprocess.check_output(['gsettings','get',schema,key],text=True).strip()
        if value==change['after']:
            subprocess.run(['gsettings','set',schema,key,change['before']],check=True)
        elif value!=change['before']:
            skipped.append(schema+':'+key)
    for change in reversed(manifest['settings']):
        c,k=change['channel'],change['key']
        value=current(c,k)
        if value==change['before']:
            continue
        if value!=change['after']:
            skipped.append(c+':'+k)
            continue
        if change['before'] is None:
            XF.ResetProperty(c,k,False)
        else:
            XF.SetProperty(c,k,decode(change['before']))
    for change in reversed(manifest['files']):
        p=Path(change['path'])
        value=base64.b64encode(p.read_bytes()).decode() if p.exists() else None
        if value==change['before']:
            continue
        if value!=change['after']:
            skipped.append(str(p))
            continue
        if change['before'] is None:
            p.unlink(missing_ok=True)
        else:
            p.write_bytes(base64.b64decode(change['before']))
    start_panel()
    if any(r['path'].endswith('/autostart/nm-applet.desktop') for r in manifest['files']):
        # Match the restored autostart command, including any prior arguments.
        import shlex
        autostart=HOME/'.config/autostart/nm-applet.desktop'
        if not autostart.exists():autostart=Path('/etc/xdg/autostart/nm-applet.desktop')
        command=next((line[5:] for line in autostart.read_text().splitlines() if line.startswith('Exec=')),'nm-applet')
        argv=shlex.split(command)
        if argv and Path(argv[0]).name=='nm-applet':network_applet_backend(argv)
    if manifest.get('explorer_migration') or manifest.get('terminal_migration'):
        state_path=CONFIG/'layout.json'
        if state_path.exists():
            state=json.loads(state_path.read_text())
            for field in ('pins','recent'):
                state[field]=['thunar.desktop' if x=='zorin11-explorer.desktop' else x for x in state[field]]
                if manifest.get('terminal_migration'):
                    state[field]=['xfce4-terminal.desktop' if x=='zorin11-terminal.desktop' else x for x in state[field]]
            for group in state['groups']:
                for item in group['items']:
                    if item.get('id')=='zorin11-explorer.desktop':item['id']='thunar.desktop'
            write_json(state_path,state)
        subprocess.run(['update-desktop-database',str(HOME/'.local/share/applications')],check=False)
        subprocess.run(['gtk-update-icon-cache','-f','-t',str(HOME/'.local/share/icons/CodexWindows11')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if skipped:
        print('Preserved integration items changed since installation:\n'+'\n'.join(skipped))
    else:
        MANIFEST.rename(CONFIG/'integration-restored.json')
    print('Restored the previous menu and shortcuts. Saved pins and groups are retained.')


if __name__=='__main__':
    if sys.argv[1:]==['--install']:
        install()
    elif sys.argv[1:]==['--uninstall']:
        uninstall()
    elif sys.argv[1:]==['--upgrade']:
        from refine import upgrade
        upgrade()
    else:
        raise SystemExit('Usage: install.py --install | --upgrade | --uninstall')
