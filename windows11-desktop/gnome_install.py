"""Install shared companion files and the per-user GNOME Shell extension."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import gnome_setup

ROOT=Path(__file__).resolve().parent
HOME=Path.home()
DEST=HOME/'.local/share/zorin11-hub'
UUID='zorin11@zorin-os-fixes'
EXTENSION=HOME/'.local/share/gnome-shell/extensions'/UUID
FILES=HOME/'.config/zorin11-gnome/files-backup.json'


def write_files(files):
    previous=json.loads(FILES.read_text()) if FILES.exists() else []
    records={r['path']:r for r in previous}
    for path,data in files.items():
        record=records.setdefault(str(path),{'path':str(path),'before':base64.b64encode(path.read_bytes()).decode() if path.exists() else None})
        record['after']=base64.b64encode(data).decode()
    gnome_setup.save(list(records.values()),FILES)
    for path,data in files.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name(path.name+'.zorin11-tmp');temp.write_bytes(data);temp.replace(path)


def desktop(name,args,icon,wmclass='Zorin11-hub',categories='Utility;'):
    launcher=f'/usr/bin/env GDK_BACKEND=x11 /usr/bin/python3 "{DEST / "app.py"}"'
    return f'[Desktop Entry]\nType=Application\nName={name}\nExec={launcher} {args}\nIcon={icon}\nTerminal=false\nCategories={categories}\nStartupWMClass={wmclass}\n'.encode()


def explorer_favorites(favorites):
    replacements={'org.gnome.Nautilus.desktop':'zorin11-explorer.desktop',
                  'org.gnome.SystemMonitor.desktop':'io.missioncenter.MissionCenter.desktop'}
    return list(dict.fromkeys(replacements.get(item,item) for item in favorites))


def folder_defaults(content):
    _,GLib=gnome_setup.bindings()
    keyfile=GLib.KeyFile()
    if content:keyfile.load_from_data(content,len(content.encode()),GLib.KeyFileFlags.KEEP_COMMENTS)
    keyfile.set_string('Default Applications','inode/directory','zorin11-explorer.desktop;')
    return keyfile.to_data()[0].encode()


def install():
    # Sources are managed runtime files; personal state lives under .config.
    DEST.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/'companion',DEST,dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('node_modules','__pycache__','test_*','.pnpm*','src','pnpm-lock.yaml'))
    for helper in ('gnome_setup.py','gnome_install.py'):shutil.copy2(ROOT/helper,DEST/helper)
    extension_files={EXTENSION/p.relative_to(ROOT/'gnome-extension'):p.read_bytes()
                     for p in (ROOT/'gnome-extension').rglob('*') if p.is_file() and p.name!='gschemas.compiled'}
    for icon in ('start.svg','search.svg','taskview.svg'):extension_files[EXTENSION/icon]=(ROOT/'companion'/icon).read_bytes()
    files=dict(extension_files)
    apps=HOME/'.local/share/applications'
    for ident,name,args,icon,wm in [
        ('start','Start','--toggle-start',str(DEST/'start.svg'),'Zorin11-hub'),
        ('explorer','File Explorer','--explorer %U',str(DEST/'explorer.svg'),'Zorin11-explorer'),
        ('computer','This PC','--explorer ::computer','computer','Zorin11-explorer'),
        ('settings','Settings','--settings','preferences-system','Zorin11-settings'),
        ('taskview','Task View','--task-view',str(DEST/'taskview.svg'),'Zorin11-hub'),
        ('quick','Quick Settings','--quick-settings','preferences-system','Zorin11-hub'),
        ('notifications','Notifications and calendar','--notifications','preferences-system-notifications','Zorin11-hub'),
    ]:files[apps/f'zorin11-{ident}.desktop']=desktop(name,args,icon,wm)
    files[apps/'gnome-bluetooth-panel.desktop']=desktop('Bluetooth','--settings devices','bluetooth','Zorin11-settings','Settings;HardwareSettings;')+b'NoDisplay=true\nOnlyShowIn=GNOME;Unity;\n'
    files[apps/'zorin11-explorer.desktop']+=b'MimeType=inode/directory;\nKeywords=Files;Folders;File Manager;Explorer;\n'
    launcher=f'/usr/bin/env GDK_BACKEND=x11 /usr/bin/python3 "{DEST / "app.py"}"'
    files[apps/'zorin11-explorer.desktop']+=(f'Actions=new-window;this-pc;\n\n'
        f'[Desktop Action new-window]\nName=New window\nExec={launcher} --explorer\n\n'
        f'[Desktop Action this-pc]\nName=This PC\nExec={launcher} --explorer ::computer\n').encode()
    # Zorin's desktop-specific defaults take precedence over generic defaults.
    mimeapps=HOME/'.config/zorin-mimeapps.list'
    files[mimeapps]=folder_defaults(mimeapps.read_text() if mimeapps.exists() else '')
    files[HOME/'.config/autostart/zorin11-desktop.desktop']=desktop('Windows 11 Desktop','--background',str(DEST/'start.svg'))+b'X-GNOME-Autostart-Delay=5\n'
    if (HOME/'.local/bin/wezterm').exists():
        for name,ident,extra,icon in [('Terminal','terminal','','utilities-terminal'),('PowerShell','powershell',f' "{HOME / ".local/bin/pwsh"}" -NoLogo','zorin11-powershell')]:
            files[apps/f'zorin11-{ident}.desktop']=(f'[Desktop Entry]\nType=Application\nName={name}\nExec=/usr/bin/python3 "{DEST / "terminal.py"}"{extra}\nIcon={icon}\nTerminal=false\nCategories=System;TerminalEmulator;\nStartupWMClass=org.wezfurlong.wezterm\n').encode()
        files[HOME/'.config/wezterm/wezterm.lua']=(ROOT/'companion/wezterm.lua').read_bytes()
    import sys
    sys.path.insert(0,str(ROOT/'companion'))
    import task_manager
    task_manager.configure()
    files.update(task_manager.app_entries(apps))
    import window_style
    css=HOME/'.config/gtk-3.0/gtk.css'
    files[css]=window_style.css(css.read_text() if css.exists() else '',DEST).encode()
    import audio_effects
    files[HOME/'.config/systemd/user'/audio_effects.UNIT]=audio_effects.unit(DEST).encode()
    import thumbnail_cache
    files.update({HOME/'.config/systemd/user'/name:text.encode()
                  for name,text in thumbnail_cache.units(DEST).items()})
    write_files(files)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','zorin11-thumbnail-cache.timer'],check=True)
    subprocess.run(['glib-compile-schemas',str(EXTENSION/'schemas')],check=True)
    subprocess.run(['update-desktop-database',str(apps)],check=True)
    Gio,GLib=gnome_setup.bindings()
    shell=Gio.Settings.new('org.gnome.shell')
    changes={'org.gnome.shell':{'enabled-extensions':list(dict.fromkeys(shell.get_strv('enabled-extensions')+[UUID,'zorin-window-move-effect@zorinos.com'])),
                             'favorite-apps':explorer_favorites(shell.get_strv('favorite-apps')),
                             'disabled-extensions':[x for x in shell.get_strv('disabled-extensions') if x not in (UUID,'zorin-window-move-effect@zorinos.com')]},
             'org.gnome.mutter':{'dynamic-workspaces':False}}
    gnome_setup.install(gnome_setup.plan(changes))
    # Journal shortcut recovery now, but let the extension take ownership only
    # when it loads. Existing shortcuts keep working before the first logout.
    bindings={'org.gnome.shell.keybindings':{'toggle-application-view':[], 'focus-active-notification':[]},
              'org.gnome.desktop.wm.keybindings':{'switch-applications':[], 'switch-applications-backward':[],
                                                 'switch-windows':[], 'switch-windows-backward':[]}}
    previous=json.loads(gnome_setup.BACKUP.read_text())
    gnome_setup.save(gnome_setup.merge_original(gnome_setup.plan(bindings),previous))
    # GNOME 46 discovers new extension directories at login. Never restart a
    # Wayland session or use unsafe eval to force-load code into the live shell.
    try:
        from gnome_bridge import call
        call('snapshot')
    except Exception:
        print('Installed. Sign out and sign back in to load the new GNOME extension.')
        return False
    subprocess.Popen(['/usr/bin/python3',str(DEST/'app.py'),'--background'],env=dict(os.environ,GDK_BACKEND='x11'),start_new_session=True)
    return True


def restore():
    if os.geteuid()==0:raise RuntimeError("Run as your desktop user, without sudo.")
    subprocess.run(['systemctl','--user','disable','--now','zorin11-audio-effects.service'],capture_output=True)
    subprocess.run(['systemctl','--user','disable','--now','zorin11-thumbnail-cache.timer'],capture_output=True)
    subprocess.run(['systemctl','--user','stop','zorin11-thumbnail-cache.service'],capture_output=True)
    subprocess.run(['gnome-extensions','disable',UUID],capture_output=True)
    if DEST.joinpath('app.py').exists():
        # Ask only an existing instance to quit, without starting a new UI.
        Gio,GLib=gnome_setup.bindings()
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        owner=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',GLib.Variant('(s)',('local.zorin11.DesktopHub',)),None,Gio.DBusCallFlags.NONE,2000,None).unpack()[0]
        if owner:subprocess.run(['/usr/bin/python3',str(DEST/'app.py'),'--quit'],env=dict(os.environ,GDK_BACKEND='x11'),timeout=10)
    import sys
    sys.path.insert(0,str(ROOT/'companion'))
    import wallpaper
    wallpaper.restore()
    import task_manager
    task_manager.restore()
    if FILES.exists():
        remaining=[]
        for record in json.loads(FILES.read_text()):
            path=Path(record['path'])
            try:
                if not path.exists() or path.read_bytes()!=base64.b64decode(record['after']):
                    print('Preserving later file change:',path);continue
                if record['before'] is None:path.unlink()
                else:path.write_bytes(base64.b64decode(record['before']))
            except OSError:
                remaining.append(record)
        if remaining:gnome_setup.save(remaining,FILES)
        else:FILES.unlink()
    subprocess.run(['systemctl','--user','daemon-reload'],capture_output=True)
    gnome_setup.restore()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Restore the previous GNOME desktop.')
    parser.add_argument('action',choices=['restore'])
    parser.parse_args()
    restore()
