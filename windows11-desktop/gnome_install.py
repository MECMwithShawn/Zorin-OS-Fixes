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

def display_details_entry():
    return (f'[Desktop Entry]\nType=Application\nName=Advanced display\n'
            f'Comment=Display resolution, refresh rate, scaling and graphics details\n'
            f'Exec=/usr/bin/python3 "{DEST / "display_details.py"}"\n'
            'Icon=video-display\nTerminal=false\nCategories=Settings;HardwareSettings;\n'
            'Keywords=Monitor;Resolution;Refresh;Scale;DPI;GPU;Graphics;\n'
            'StartupWMClass=Zorin11-display-details\nOnlyShowIn=GNOME;\n').encode()


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

def personalization_entries(apps):
    entries={}
    for ident,name,page,icon in [
        ('gnome-background-panel','Personalize','background','preferences-desktop-wallpaper'),
        ('gnome-display-panel','Display settings','display','video-display'),
        ('org.gnome.Settings','Settings','home','preferences-system'),
    ]:
        categories='GNOME;GTK;Settings;HardwareSettings;X-GNOME-Settings-Panel;X-GNOME-DevicesSettings;' if ident.endswith('-panel') else 'Settings;'
        entries[apps/(ident+'.desktop')]=desktop(name,'--settings '+page,icon,'Zorin11-settings',categories)+b'NoDisplay=true\nOnlyShowIn=GNOME;Unity;\nKeywords=Settings;Display;Background;\n'
    return entries


def device_manager_entry():
    return (f'[Desktop Entry]\nType=Application\nName=Device Manager\n'
            f'Comment=Hardware devices, drivers and properties\n'
            f'Exec=/usr/bin/python3 "{DEST / "device_manager.py"}"\n'
            'Icon=computer\nTerminal=false\nCategories=Settings;HardwareSettings;\n'
            'Keywords=Hardware;Devices;Drivers;GPU;USB;PCI;\n'
            'StartupWMClass=Zorin11-device-manager\nOnlyShowIn=GNOME;\n').encode()


def event_viewer_entry():
    return (f'[Desktop Entry]\nType=Application\nName=Event Viewer\n'
            f'Comment=Application, system and kernel event logs\n'
            f'Exec=/usr/bin/python3 "{DEST / "event_viewer.py"}"\n'
            'Icon=utilities-system-monitor\nTerminal=false\nCategories=System;Monitor;\n'
            'Keywords=Logs;Events;Journal;Errors;Warnings;\n'
            'StartupWMClass=Zorin11-event-viewer\nOnlyShowIn=GNOME;\n').encode()


def install():
    import snipping_install
    import desktop_menu_install
    import motion_install
    import update_agent_install
    import lockscreen_install
    import heif_install
    snipping_binary=snipping_install.build()
    heif_install.ensure(DEST/'heif-runtime')
    # Sources are managed runtime files; personal state lives under .config.
    DEST.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/'companion',DEST,dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('node_modules','__pycache__','test_*','.pnpm*','src','pnpm-lock.yaml','event_logs.py','event_viewer.py'))
    for helper in ('gnome_setup.py','gnome_install.py','snipping_install.py','desktop_menu_install.py',
                   'desktop_backup.py','lockscreen_install.py','motion_install.py','update_agent_install.py','heif_install.py','heif-requirements.txt',
                   'update_guard.py','update_guard_root.py','install_update_guard.py'):
        shutil.copy2(ROOT/helper,DEST/helper)
    extension_files={EXTENSION/p.relative_to(ROOT/'gnome-extension'):p.read_bytes()
                     for p in (ROOT/'gnome-extension').rglob('*') if p.is_file() and p.name!='gschemas.compiled'}
    for icon in ('start.svg','search.svg','taskview.svg'):extension_files[EXTENSION/icon]=(ROOT/'companion'/icon).read_bytes()
    files=dict(extension_files)
    files.update(desktop_menu_install.prepare())
    files.update(motion_install.files())
    files.update(update_agent_install.files())
    files.update(lockscreen_install.files())
    files.update(snipping_install.files(snipping_binary))
    audio_extension=HOME/'.local/share/gnome-shell/extensions/zorin11-audio@zorin-os-fixes'
    files.update({audio_extension/p.name:p.read_bytes() for p in (ROOT/'gnome-audio-extension').iterdir() if p.is_file()})
    # Journal these standalone helpers before writing, like their launcher.
    for helper in ('event_logs.py','event_viewer.py'):
        files[DEST/helper]=(ROOT/'companion'/helper).read_bytes()
    apps=HOME/'.local/share/applications'
    files[apps/'zorin11-display-details.desktop']=display_details_entry()
    for ident,name,args,icon,wm in [
        ('start','Start','--toggle-start',str(DEST/'start.svg'),'Zorin11-hub'),
        ('explorer','File Explorer','--explorer %U',str(DEST/'explorer.svg'),'Zorin11-explorer'),
        ('computer','This PC','--explorer ::computer','computer','Zorin11-explorer'),
        ('settings','Settings','--settings','preferences-system','Zorin11-settings'),
        ('taskview','Task View','--task-view',str(DEST/'taskview.svg'),'Zorin11-hub'),
        ('quick','Quick Settings','--quick-settings','preferences-system','Zorin11-hub'),
        ('notifications','Notifications and calendar','--notifications','preferences-system-notifications','Zorin11-hub'),
    ]:files[apps/f'zorin11-{ident}.desktop']=desktop(name,args,icon,wm)
    files[apps/'gnome-sound-panel.desktop']=desktop('Sound','--settings sound','multimedia-volume-control','Zorin11-settings','Settings;HardwareSettings;')+b'NoDisplay=true\nOnlyShowIn=GNOME;Unity;\nKeywords=Settings;Display;Background;\n'
    files[apps/'zorin11-device-manager.desktop']=device_manager_entry()
    files[apps/'gnome-bluetooth-panel.desktop']=desktop('Bluetooth','--settings devices','bluetooth','Zorin11-settings','Settings;HardwareSettings;')+b'NoDisplay=true\nOnlyShowIn=GNOME;Unity;\nKeywords=Settings;Display;Background;\n'
    files.update(personalization_entries(apps))
    files[apps/'zorin11-explorer.desktop']+=b'MimeType=inode/directory;\nKeywords=Files;Folders;File Manager;Explorer;\n'
    files[apps/'zorin11-event-viewer.desktop']=event_viewer_entry()
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
    files[DEST/'audio-presets.json']=json.dumps(audio_effects.PRESETS).encode()
    files[HOME/'.config/systemd/user'/audio_effects.UNIT]=audio_effects.unit(DEST).encode()
    import thumbnail_cache
    files.update({HOME/'.config/systemd/user'/name:text.encode()
                  for name,text in thumbnail_cache.units(DEST).items()})
    write_files(files)
    motion_install.compile_schema()
    motion_install.configure()
    lockscreen_install.compile_schema()
    lockscreen_install.configure()
    snipping_install.BINARY.chmod(0o755)
    snipping_install.shortcut()
    snipping_install.record_shortcut()
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','zorin11-update-agent.service'],check=True)
    # A running Python daemon keeps its old preset catalog after files are upgraded.
    subprocess.run(['systemctl','--user','try-restart','zorin11-audio-effects.service'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','zorin11-thumbnail-cache.timer'],check=True)
    subprocess.run(['systemctl','--user','enable','--now',lockscreen_install.UNIT+'.timer'],check=True)
    subprocess.run(['glib-compile-schemas',str(EXTENSION/'schemas')],check=True)
    subprocess.run(['glib-compile-schemas',str(HOME/'.local/share/gnome-shell/extensions'/desktop_menu_install.UUID/'schemas')],check=True)
    subprocess.run(['update-desktop-database',str(apps)],check=True)
    Gio,GLib=gnome_setup.bindings()
    shell=Gio.Settings.new('org.gnome.shell')
    changes={'org.gnome.shell':{'enabled-extensions':list(dict.fromkeys(shell.get_strv('enabled-extensions')+[UUID,'zorin11-audio@zorin-os-fixes','zorin-window-move-effect@zorinos.com'])),
                             'favorite-apps':explorer_favorites(shell.get_strv('favorite-apps')),
                             'disabled-extensions':[x for x in shell.get_strv('disabled-extensions') if x not in (UUID,'zorin11-audio@zorin-os-fixes','zorin-window-move-effect@zorinos.com')]},
             'org.gnome.mutter':{'dynamic-workspaces':False}}
    gnome_setup.install(gnome_setup.plan(changes))
    if not desktop_menu_install.activate():
        print('Desktop menu installed; it will activate at the next sign-in.')
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
    import snipping_install
    import desktop_menu_install
    import motion_install
    import lockscreen_install
    snipping_install.restore_shortcut()
    snipping_install.restore_record_shortcut()
    subprocess.run(['systemctl','--user','disable','--now','zorin11-audio-effects.service'],capture_output=True)
    subprocess.run(['systemctl','--user','disable','--now','zorin11-update-agent.service'],capture_output=True)
    subprocess.run(['systemctl','--user','disable','--now','zorin11-thumbnail-cache.timer'],capture_output=True)
    subprocess.run(['systemctl','--user','stop','zorin11-thumbnail-cache.service'],capture_output=True)
    subprocess.run(['systemctl','--user','disable','--now',lockscreen_install.UNIT+'.timer'],capture_output=True)
    subprocess.run(['systemctl','--user','stop',lockscreen_install.UNIT+'.service'],capture_output=True)
    subprocess.run(['gnome-extensions','disable',lockscreen_install.UUID],capture_output=True)
    subprocess.run(['gnome-extensions','disable','zorin11-motion@zorin-os-fixes'],capture_output=True)
    subprocess.run(['gnome-extensions','disable','zorin11-audio@zorin-os-fixes'],capture_output=True)
    subprocess.run(['gnome-extensions','disable',desktop_menu_install.UUID],capture_output=True)
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
    desktop_menu_install.cleanup()
    motion_install.cleanup()
    lockscreen_install.cleanup()
    subprocess.run(['systemctl','--user','daemon-reload'],capture_output=True)
    gnome_setup.restore()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Restore the previous GNOME desktop.')
    parser.add_argument('action',choices=['restore'])
    parser.parse_args()
    restore()
