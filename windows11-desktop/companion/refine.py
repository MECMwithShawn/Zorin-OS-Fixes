"""Upgrade the companion, preserving the original reversible integration record."""
import base64
import json
from pathlib import Path
import re
import shutil
import subprocess
import dbus
from panel_layout import find_panel, plan
import appearance
import window_style
import taskbar_build


def upgrade():
    import install as installer
    source,home,dest,config=installer.SOURCE,installer.HOME,installer.DEST,installer.CONFIG
    if not installer.MANIFEST.exists():
        raise SystemExit('Install the desktop companion first.')
    # Complete the native build before touching the running panel.
    taskbar_module=taskbar_build.build()
    manifest=json.loads(installer.MANIFEST.read_text())
    properties=dict(installer.XF.GetAllProperties('xfce4-panel','/'))
    panel=find_panel(properties,manifest.get('panel',0) if 'plugin' in manifest else None)
    manifest['panel']=panel
    quick=manifest.get('quick_plugin',21)
    while not manifest.get('quick_plugin') and installer.XF.PropertyExists('xfce4-panel',f'/plugins/plugin-{quick}'):
        quick+=1
    manifest['quick_plugin']=quick
    search=manifest.get('search_plugin',22)
    while not manifest.get('search_plugin') and (search==quick or installer.XF.PropertyExists('xfce4-panel',f'/plugins/plugin-{search}')):
        search+=1
    manifest['search_plugin']=search
    launcher=f'/usr/bin/python3 "{dest/"app.py"}"'
    new_settings=[]
    new_gsettings=[]
    new_files={}
    updated_state=None
    def setting(channel,key,value):
        found=next((r for r in manifest['settings'] if r['channel']==channel and r['key']==key),None)
        if found is None:
            found={'channel':channel,'key':key,'before':installer.current(channel,key)}
            manifest['settings'].append(found)
        found['after']=installer.encode(value)
        new_settings.append((channel,key,value))
    def file(path,content):
        content=content.encode() if isinstance(content,str) else content
        found=next((r for r in manifest['files'] if r['path']==str(path)),None)
        if found is None:
            found={'path':str(path),'before':base64.b64encode(path.read_bytes()).decode() if path.exists() else None}
            manifest['files'].append(found)
        found['after']=base64.b64encode(content).decode()
        new_files[path]=content
    def gsetting(schema,key,value):
        records=manifest.setdefault('gsettings',[])
        found=next((r for r in records if r['schema']==schema and r['key']==key),None)
        if found is None:
            before=subprocess.check_output(['gsettings','get',schema,key],text=True).strip()
            found={'schema':schema,'key':key,'before':before}
            records.append(found)
        found['after']=value
        new_gsettings.append((schema,key,value))
    if dbus.SessionBus().name_has_owner('local.zorin11.DesktopHub'):
        subprocess.run(['/usr/bin/python3',str(dest/'app.py'),'--quit'],check=True,timeout=10)
        installer.wait_owner('local.zorin11.DesktopHub',False)
    installer.stop_panel()
    try:
        ids=[int(i) for i in installer.XF.GetProperty('xfce4-panel',f'/panels/panel-{panel}/plugin-ids')]
        start=int(manifest['plugin'])
        used={int(k.split('/')[2].split('-')[1]) for k in properties if k.startswith('/plugins/plugin-')}
        used.update([start,quick,search])
        def allocate():
            result=max(used|{19})+1
            used.add(result)
            return result
        types={i:str(properties.get(f'/plugins/plugin-{i}','')) for i in ids}
        if manifest.get('notification_plugin') in ids:
            types[manifest['notification_plugin']]='notification-plugin'
        battery=any(p.read_text().strip()=='Battery' for p in Path('/sys/class/power_supply').glob('*/type'))
        layout=plan(ids,types,start,quick,search,allocate,battery)
        clock,tray,dock,notification=(layout[k] for k in ('clock','tray','dock','notification'))
        if notification is None:
            notification=allocate();layout['new'][notification]='genmon';layout['order'].insert(-1,notification)
        manifest['notification_plugin']=notification
        taskview=manifest.get('taskview_plugin')
        if taskview is None:
            taskview=allocate();manifest['taskview_plugin']=taskview
        layout['order']=[i for i in layout['order'] if i!=taskview]
        layout['order'].insert(layout['order'].index(search)+1,taskview)
        channel='xfce4-panel'
        setting(channel,f'/plugins/plugin-{taskview}',dbus.String('launcher'))
        setting(channel,f'/plugins/plugin-{taskview}/items',dbus.Array([dbus.String('zorin11-taskview.desktop')],signature='v'))
        setting(channel,f'/plugins/plugin-{taskview}/show-label',dbus.Boolean(False))
        file(home/f'.config/xfce4/panel/launcher-{taskview}/zorin11-taskview.desktop',installer.desktop_file('Task view','--task-view',str(dest/'taskview.svg'),hidden=True))
        file(home/'.local/share/applications/zorin11-taskview.desktop',installer.desktop_file('Task view','--task-view',str(dest/'taskview.svg')))
        for plugin,kind in layout['new'].items():setting(channel,f'/plugins/plugin-{plugin}',dbus.String(kind))
        setting(channel,f'/panels/panel-{panel}/plugin-ids',dbus.Array([dbus.Int32(i) for i in layout['order']],signature='v'))
        if not manifest.get('base_appearance'):
            appearance.apply(home,panel,layout,setting,file,gsetting)
            manifest['base_appearance']=True
        setting(channel,f'/panels/panel-{panel}/icon-size',dbus.UInt32(32))
        setting(channel,f'/plugins/plugin-{notification}',dbus.String('genmon'))
        file(home/f'.config/xfce4/panel/genmon-{notification}.rc',f'''Command=/usr/bin/python3 "{dest/'notification_panel.py'}"
UseLabel=0
Text=Notification center
UpdatePeriod=2000
Font=Segoe UI 10
''')
        setting(channel,f'/plugins/plugin-{quick}',dbus.String('genmon'))
        file(home/f'.config/xfce4/panel/genmon-{quick}.rc',f'''Command=/usr/bin/python3 "{dest/'tray_panel.py'}"
UseLabel=0
Text=Quick settings
UpdatePeriod=1000
Font=Segoe UI 10
''')
        setting(channel,f'/plugins/plugin-{quick}/items',dbus.Array([dbus.String('zorin11-quick.desktop')],signature='v'))
        setting(channel,f'/plugins/plugin-{quick}/show-label',dbus.Boolean(False))
        setting(channel,f'/plugins/plugin-{search}',dbus.String('launcher'))
        setting(channel,f'/plugins/plugin-{search}/items',dbus.Array([dbus.String('zorin11-search.desktop')],signature='v'))
        setting(channel,f'/plugins/plugin-{search}/show-label',dbus.Boolean(True))
        file(home/f'.config/xfce4/panel/launcher-{search}/zorin11-search.desktop',installer.desktop_file('Search','--search',str(dest/'search.svg'),hidden=True))

        setting(channel,f'/plugins/plugin-{clock}/digital-time-format',dbus.String('%-I:%M %p\n%-m/%-d/%Y'))
        setting(channel,f'/plugins/plugin-{clock}/command',dbus.String(launcher+' --notifications'))
        file(home/'.local/share/themes/Zorin11-Notifications/xfce-notify-4.0/gtk.css',(source/'notification-theme.css').read_bytes())
        if not manifest.get('notification_integration'):
            setting('xfce4-notifyd','/theme',dbus.String('Zorin11-Notifications'))
            setting('xfce4-notifyd','/notify-location',dbus.String('bottom-right'))
            setting('xfce4-notifyd','/notification-log',dbus.Boolean(True))
            setting('xfce4-notifyd','/log-level',dbus.String('always'))
            setting('xfce4-notifyd','/log-max-size-enabled',dbus.Boolean(True))
            if not installer.XF.PropertyExists('xfce4-notifyd','/log-max-size'):
                setting('xfce4-notifyd','/log-max-size',dbus.UInt32(1000))
            manifest['notification_integration']=True
        setting(channel,f'/plugins/plugin-{clock}/digital-layout',dbus.UInt32(3))
        setting(channel,f'/plugins/plugin-{clock}/digital-time-font',dbus.String('Selawik 9'))
        # Optional personal reference fonts stay local and are never bundled.
        fonts = config/'reference-fonts'
        if (fonts/'segoeui.ttf').exists():
            for font in fonts.glob('*.ttf'):
                file(home/'.local/share/fonts/Zorin11Reference'/font.name,font.read_bytes())
            setting('xsettings','/Gtk/FontName',dbus.String('Segoe UI 10'))
            setting('xfwm4','/general/title_font',dbus.String('Segoe UI Semibold 10'))
        setting(channel,f'/plugins/plugin-{tray}/icon-size',dbus.Int32(16))
        setting(channel,f'/plugins/plugin-{tray}/square-icons',dbus.Boolean(False))
        # Keep NetworkManager's secret agent running, but show network status
        # only in our combined Quick Settings launcher, even with overflow open.
        gsetting('org.gnome.nm-applet','show-applet','false')
        # Ubuntu's nm-applet 1.34 indicator backend ignores show-applet.
        # Its X11 backend honors it and retains the same password/VPN agent.
        autostart=home/'.config/autostart/nm-applet.desktop'
        original=autostart if autostart.exists() else Path('/etc/xdg/autostart/nm-applet.desktop')
        if original.exists():
            content=original.read_text()
            content=re.sub(r'^Exec=.*$', 'Exec=nm-applet --no-indicator',content,flags=re.M)
            file(autostart,content)
        known=list(installer.XF.GetProperty(channel,f'/plugins/plugin-{tray}/known-items')) if installer.XF.PropertyExists(channel,f'/plugins/plugin-{tray}/known-items') else []
        setting(channel,f'/plugins/plugin-{tray}/hidden-items',dbus.Array([dbus.String(x) for x in dict.fromkeys(known+['blueman','nm-applet'])],signature='v'))
        legacy=list(installer.XF.GetProperty(channel,f'/plugins/plugin-{tray}/known-legacy-items')) if installer.XF.PropertyExists(channel,f'/plugins/plugin-{tray}/known-legacy-items') else []
        setting(channel,f'/plugins/plugin-{tray}/hidden-legacy-items',dbus.Array([dbus.String(x) for x in dict.fromkeys(legacy+['network'])],signature='v'))
        keys={'<Super>n':launcher+' --notifications','<Super>i':launcher+' --settings','<Super>s':launcher+' --search', '<Super>e':launcher+' --explorer','<Super>a':launcher+' --quick-settings',
              'XF86AudioRaiseVolume':'pactl set-sink-volume @DEFAULT_SINK@ +5%',
              'XF86AudioLowerVolume':'pactl set-sink-volume @DEFAULT_SINK@ -5%',
              'XF86AudioMute':'pactl set-sink-mute @DEFAULT_SINK@ toggle'}
        keys.update({'<Super>z':launcher+' --snap-layouts','<Super>Tab':launcher+' --task-view'})
        for binding,argument in [('<Alt>Tab','--switch-next'),('<Alt><Shift>Tab','--switch-previous')]:
            setting('xfce4-keyboard-shortcuts','/xfwm4/custom/'+binding,dbus.String(''))
            # Xfce's command grabber resolves Shift+Tab as ISO_Left_Tab.
            command_binding=binding.replace('Tab','ISO_Left_Tab') if 'Shift' in binding else binding
            keys[command_binding]=launcher+' '+argument
        for key,action in [('d','new'),('F4','close'),('Left','left'),('Right','right')]:
            binding='<Primary><Super>'+key
            keys[binding]=launcher+' --desktop '+action
            setting('xfce4-keyboard-shortcuts','/xfwm4/custom/'+binding,dbus.String(''))
        # Xfwm's default Super+Tab binding otherwise competes with Task View.
        setting('xfce4-keyboard-shortcuts','/xfwm4/custom/<Super>Tab',dbus.String(''))
        for key,value in keys.items():setting('xfce4-keyboard-shortcuts','/commands/custom/'+key,dbus.String(value))
        quickfile=home/f'.config/xfce4/panel/launcher-{quick}/zorin11-quick.desktop'
        file(quickfile,installer.desktop_file('Quick settings','--quick-settings',str(dest/'tray-offline-0.svg'),hidden=True))
        explorerfile=home/'.local/share/applications/zorin11-explorer.desktop'
        explorer_icon='system-file-manager' if (config/'reference-icons/48/system-file-manager.png').exists() else str(dest/'explorer.svg')
        desktop=installer.desktop_file('File Explorer','--explorer %U',explorer_icon).replace('Categories=Utility;','Categories=System;FileTools;FileManager;')
        desktop+='MimeType=inode/directory;x-scheme-handler/computer;\nStartupWMClass=Zorin11-explorer\n'
        file(explorerfile,desktop)
        computer=installer.desktop_file('This PC','--explorer ::computer','computer')
        computer=computer.replace('Categories=Utility;','Categories=System;FileTools;FileManager;')
        file(home/'.local/share/applications/zorin11-computer.desktop',computer)
        settings=installer.desktop_file('Settings','--settings','preferences-system').replace('Categories=Utility;','Categories=Settings;System;')
        file(home/'.local/share/applications/zorin11-settings.desktop',settings+'StartupWMClass=Zorin11-settings\n')
        effects=f'''[Desktop Entry]
Type=Application
Name=Window Effects
Comment=Enable or disable wobbly windows
Exec=/usr/bin/python3 "{dest/'effects.py'}"
Icon=preferences-system-windows
Terminal=false
Categories=Settings;DesktopSettings;
'''
        file(home/'.local/share/applications/zorin11-effects.desktop',effects)
        file(home/'.config/autostart/zorin11-effects.desktop',effects.replace(str(dest/'effects.py')+'"',str(dest/'effects.py')+'" --login')+'OnlyShowIn=XFCE;\nNoDisplay=true\n')
        # Existing Start and group entries point to the new desktop ID. Keep
        # Thunar installed and directly available for advanced operations.
        store=config/'layout.json'
        if store.exists():
            state=json.loads(store.read_text())
            state['pins']=['zorin11-explorer.desktop' if x=='thunar.desktop' else x for x in state['pins']]
            state['recent']=['zorin11-explorer.desktop' if x=='thunar.desktop' else x for x in state['recent']]
            for group in state['groups']:
                for item in group['items']:
                    if item.get('kind')=='app' and item.get('id')=='thunar.desktop':item['id']='zorin11-explorer.desktop'
            for field in ('pins','recent'):
                state[field]=list(dict.fromkeys('zorin11-settings.desktop' if i=='xfce-settings-manager.desktop' else i for i in state[field]))
            for group in state['groups']:
                for item in group['items']:
                    if item.get('kind')=='app' and item.get('id')=='xfce-settings-manager.desktop':item['id']='zorin11-settings.desktop'
            manifest['settings_migration']=True
            # Store original IDs for reversible migration without overwriting later pin order.
            manifest['explorer_migration']=True
            updated_state=state
        dock=home/f'.config/xfce4/panel/docklike-{dock}.rc'
        taskbar_build.integrate(home,taskbar_module,file)
        if dock.exists():
            content=dock.read_text()
            content=re.sub(r'(?<=;)thunar(?=;|$)','zorin11-explorer',content,flags=re.M)
            content=content.replace('pinned=thunar;','pinned=zorin11-explorer;')
            content=re.sub(r'(?<=;)xfce-settings-manager(?=;|$)','zorin11-settings',content,flags=re.M)
            content=content.replace('pinned=xfce-settings-manager;','pinned=zorin11-settings;')
            # Draw inset indicators with CSS: the plugin's old bottom-edge dots
            # were clipped by the 48px panel and almost invisible in dark mode.
            for key,value in {'indicatorStyle':'5','inactiveIndicatorStyle':'5','forceIconSize':'true','iconSize':'32','showPreviews':'true','noWindowsListIfSingle':'false','previewSleep':'200'}.items():
                content=re.sub(r'^'+key+r'=.*\n?','',content,flags=re.M)
                content=content.replace('[user]','[user]\n'+key+'='+value,1)
            file(dock,content)
        helpers=home/'.config/xfce4/helpers.rc'
        content=helpers.read_text() if helpers.exists() else ''
        content=re.sub(r'^FileManager=.*\n?','',content,flags=re.M)
        terminal=(home/'.local/bin/wezterm').exists() and (home/'.local/bin/pwsh').exists()
        if terminal:
            content=re.sub(r'^TerminalEmulator=.*\n?','',content,flags=re.M).rstrip()+'\nTerminalEmulator=zorin11-terminal\n'
            terminal_command=f'/usr/bin/python3 "{dest/"terminal.py"}"'
            file(home/'.local/share/xfce4/helpers/zorin11-terminal.desktop',f'''[Desktop Entry]
Version=1.0
Type=X-XFCE-Helper
Name=Terminal
Icon=utilities-terminal
StartupNotify=false
X-XFCE-Category=TerminalEmulator
X-XFCE-Commands={terminal_command};
X-XFCE-CommandsWithParameter={terminal_command} %s;
''')
            for name,desktop_id,command,icon in [
                ('Terminal','zorin11-terminal',terminal_command,'utilities-terminal'),
                ('PowerShell','zorin11-powershell',terminal_command+f' "{home/".local/bin/pwsh"}" -NoLogo','zorin11-powershell'),
            ]:
                file(home/'.local/share/applications'/(desktop_id+'.desktop'),f'''[Desktop Entry]
Type=Application
Name={name}
Comment=Tabbed terminal with PowerShell and Bash profiles
Exec={command}
Icon={icon}
Terminal=false
Categories=System;TerminalEmulator;
StartupWMClass=org.wezfurlong.wezterm
''')
            file(home/'.config/wezterm/wezterm.lua',(source/'wezterm.lua').read_text())
            for shortcut in ('<Super>t','<Primary><Alt>t'):
                setting('xfce4-keyboard-shortcuts','/commands/custom/'+shortcut,dbus.String('exo-open --launch TerminalEmulator'))
            if updated_state is not None:
                for field in ('pins','recent'):
                    updated_state[field]=list(dict.fromkeys('zorin11-terminal.desktop' if i=='xfce4-terminal.desktop' else i for i in updated_state[field]))
                manifest['terminal_migration']=True
        file(helpers,content.rstrip()+'\nFileManager=zorin11-explorer\n')
        file(home/'.local/share/xfce4/helpers/zorin11-explorer.desktop',f'''[Desktop Entry]
Version=1.0
Type=X-XFCE-Helper
Name=File Explorer
Icon={explorer_icon}
StartupNotify=false
X-XFCE-Category=FileManager
X-XFCE-Commands={launcher} --explorer;
X-XFCE-CommandsWithParameter={launcher} --explorer "%s";
''')
        mime=home/'.config/mimeapps.list'
        content=mime.read_text() if mime.exists() else '[Default Applications]\n'
        # Only change inode/directory under Default Applications.
        sections=re.split(r'(?m)(^\[[^\n]+\]\n)',content)
        for i,part in enumerate(sections):
            if part=='[Default Applications]\n':
                body=re.sub(r'^(inode/directory|x-scheme-handler/computer)=.*\n?','',sections[i+1],flags=re.M)
                sections[i+1]='inode/directory=zorin11-explorer.desktop\nx-scheme-handler/computer=zorin11-explorer.desktop\n'+body
                break
        else:sections+=['\n[Default Applications]\n','inode/directory=zorin11-explorer.desktop\nx-scheme-handler/computer=zorin11-explorer.desktop\n']
        file(mime,''.join(sections))
        css=home/'.config/gtk-3.0/gtk.css'
        content=css.read_text() if css.exists() else ''
        content=appearance.css(content,layout['show'])
        window_style.apply(home,source,setting,file)
        content=window_style.css(content,dest)
        content=re.sub(r'/\* BEGIN Windows 11 previews \*/.*?/\* END Windows 11 previews \*/\n?','',content,flags=re.S)
        content+='\n/* BEGIN Windows 11 previews */\n'+(source/'taskbar/preview.css').read_text()+'\n/* END Windows 11 previews */\n'
        content=re.sub(r'/\* BEGIN Windows 11 tray \*/.*?/\* END Windows 11 tray \*/\n?','',content,flags=re.S)
        content+=f'''\n/* BEGIN Windows 11 tray */
#launcher-{search} button {{ border-radius: 18px; min-width: 160px; padding: 0 10px; margin: 6px 4px; background-color: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.086); background-image: url('{dest/'search.svg'}'); background-repeat: no-repeat; background-position: 12px center; background-size: 16px 16px; }}
#launcher-{search} button:hover {{ background-color: rgba(255,255,255,0.125); }}
#launcher-{start} button, #launcher-{taskview} button {{ min-width: 40px; padding: 0 3px; }}
#docklike-plugin button.group {{ min-width: 42px; min-height: 36px; margin: 4px 2px; padding: 0 3px 2px; border: 1px solid transparent; border-radius: 5px; background-color: transparent; background-image: none; }}
#docklike-plugin button.open_group {{ background-color: rgba(255,255,255,0.035); background-image: linear-gradient(to right,#b5b5b5,#b5b5b5); background-size: 8px 3px; background-repeat: no-repeat; background-position: center bottom; }}
#docklike-plugin button.active_group {{ background-color: rgba(255,255,255,0.105); border-color: rgba(255,255,255,0.06); background-image: linear-gradient(to right,#60cdff,#60cdff); background-size: 22px 3px; }}
#docklike-plugin button.group:hover {{ background-color: rgba(255,255,255,0.08); }}
#docklike-plugin button.active_group:hover {{ background-color: rgba(255,255,255,0.15); }}
#launcher-{search} label {{ font-size: 14px; padding-left: 24px; padding-right: 84px; color: #dedede; }}
#genmon-{quick} button {{ margin: 5px 0; border-radius: 4px; padding: 0 6px; }}
.xfce4-panel.background {{ background-color: rgba(28,32,38,0.96); border-top-color: rgba(255,255,255,0.094); font-family: 'Segoe UI', Selawik; }}
#clock-button {{ font-family: 'Segoe UI', Selawik; font-size: 12px; padding: 0 9px; }}
#clock-button label, #clock-button:checked label {{ color: #f3f3f3; }}
#genmon-{notification} button {{ padding: 0 5px; margin: 5px 0; border-radius: 4px; }}
#systray-{tray} button {{ padding: 0 3px; margin: 5px 0; }}
#systray-{tray} > box > button {{ -gtk-icon-transform: none; color: transparent; background-image: url('{dest/'fluent/chevron-up.svg'}'); background-size: 20px 20px; background-position: center; background-repeat: no-repeat; min-width: 24px; }}
#systray-{tray} > box > button:checked {{ background-image: url('{dest/'fluent/chevron-down.svg'}'); }}
/* END Windows 11 tray */
'''
        file(css,content)
        icons=home/'.local/share/icons/CodexWindows11'
        theme=(icons/'index.theme').read_text() if (icons/'index.theme').exists() else '''[Icon Theme]
Name=Windows 11 Inspired
Comment=Windows-inspired icons with local reference overrides
Inherits=Win11-dark,ZorinBlue-Dark,hicolor
Directories=scalable/apps

[scalable/apps]
Size=24
Type=Scalable
MinSize=16
MaxSize=256
Context=Applications
'''
        file(icons/'scalable/apps/xfce4-zorinmenulite.svg',(source/'start.svg').read_bytes())
        file(icons/'index.theme',theme)
        if (home/'.local/share/icons/Win11-dark/index.theme').exists():
            theme=re.sub(r'^Inherits=.*$', 'Inherits=Win11-dark,ZorinBlue-Dark,hicolor',theme,flags=re.M)
            theme=re.sub(r'^Comment=.*$', 'Comment=Win11 dark icons with custom Start and notification artwork',theme,flags=re.M)
            file(icons/'index.theme',theme)
        if 'scalable/status' not in theme:
            theme=theme.replace('Directories=scalable/apps','Directories=scalable/apps,scalable/status')+'\n[scalable/status]\nSize=16\nType=Scalable\nMinSize=12\nMaxSize=48\nContext=Status\n'
            file(icons/'index.theme',theme)
        reference_icons=config/'reference-icons'
        if reference_icons.exists():
            directories=[]
            for size in (16,24,32,48,64,256):
                directory=f'reference/{size}'
                if not (reference_icons/str(size)).is_dir():continue
                directories.append(directory)
                for icon in (reference_icons/str(size)).glob('*.png'):
                    file(icons/directory/icon.name,icon.read_bytes())
                if f'[{directory}]' not in theme:
                    theme+=f'\n[{directory}]\nSize={size}\nType=Fixed\nContext=Places\n'
            existing=re.search(r'^Directories=(.*)$',theme,re.M)[1].split(',')
            theme=re.sub(r'^Directories=.*$', 'Directories='+','.join(dict.fromkeys(directories+existing)),theme,flags=re.M)
            file(icons/'index.theme',theme)
        for name in ['notification','notifications','notification-new','notifications-new','notification-disabled','notifications-disabled','notification-disabled-new','notifications-disabled-new','notification-new-disabled','notifications-new-disabled']:
            svg=(source/'fluent'/('alert-off.svg' if 'disabled' in name else 'alert.svg')).read_text()
            if 'new' in name:svg=svg.replace('</svg>','<circle cx="16" cy="4" r="2" fill="#60cdff"/></svg>')
            file(icons/'scalable/status'/(name+'-symbolic.svg'),svg)
        installer.write_json(installer.MANIFEST,manifest)
        shutil.copytree(source,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','__pycache__','.git','test_*.py','test_*.cjs'))
        if updated_state is not None:installer.write_json(store,updated_state)
        for path,content in new_files.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.suffix=='.so':
                # A just-stopped plugin wrapper may still have the old library
                # mapped briefly. Replace its inode instead of truncating it.
                temporary=path.with_name(path.name+'.new')
                temporary.write_bytes(content)
                temporary.replace(path)
            else:path.write_bytes(content)
        subprocess.run(['fc-cache','-f',str(home/'.local/share/fonts')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for channel,key,value in new_settings:installer.XF.SetProperty(channel,key,value)
        for schema,key,value in new_gsettings:
            subprocess.run(['gsettings','set',schema,key,value],check=True)
        subprocess.run(['update-desktop-database',str(home/'.local/share/applications')],check=True)
        subprocess.run(['gtk-update-icon-cache','-f','-t',str(icons)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    finally:
        installer.start_panel()
    # Restart only our user's UI agent when switching backends. NetworkManager
    # and its active network connections are unaffected.
    installer.network_applet_backend(['nm-applet','--no-indicator'])
    log=open(config/'desktop.log','a')
    subprocess.Popen(['/usr/bin/python3',str(dest/'app.py'),'--background'],stdout=log,stderr=log,start_new_session=True)
    installer.wait_owner('local.zorin11.DesktopHub',True)
    if shutil.which('compiz'):
        subprocess.run(['/usr/bin/python3',str(dest/'effects.py'),'--refresh'],check=True,timeout=15)
    print('Installed anchored Start, compact tray with Quick Settings, and File Explorer integration.')
