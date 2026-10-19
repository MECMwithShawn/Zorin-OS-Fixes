"""Mission Center integration for grouped apps, process icons and GPU graphs."""
import json
from pathlib import Path
import shutil
import subprocess

APP_ID='io.missioncenter.MissionCenter'
BACKUP=Path.home()/'.config/zorin11-gnome/task-manager-backup.json'
DEFAULTS={'window-width':'1200','window-height':'840','window-interface-style':"'dark'",
          'window-selected-page':"'apps-page'",'apps-page-merged-process-stats':'true',
          'performance-show-gpus':'true'}


def desktop_entry():
    return (
        '[Desktop Entry]\nType=Application\nName=Task Manager\nComment=Grouped apps, processes and GPU performance\n'
        f'Exec=/usr/bin/flatpak run {APP_ID}\nIcon={APP_ID}\nX-Flatpak={APP_ID}\n'
        f'Terminal=false\nCategories=System;Monitor;\nStartupWMClass={APP_ID}\n'
        'Keywords=Processes;CPU;Memory;GPU;Performance;System Monitor;Mission Center;\n').encode()


def chatgpt_entry(content, wrapper, executable):
    """Detection metadata for the known pass-through launcher.

    Mission Center matches /proc/PID/exe to desktop Exec. Preserve custom
    launchers and wrappers that do additional setup or change arguments.
    OnlyShowIn keeps this extra entry out of desktop menus; Mission Center's
    process matcher reads it without changing the real application's launcher.
    """
    expected='#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/ChatGPT" "$@"'
    if wrapper.strip()!=expected:return None
    from gi.repository import GLib
    keyfile=GLib.KeyFile()
    keyfile.load_from_data(content,len(content.encode()),GLib.KeyFileFlags.KEEP_COMMENTS|GLib.KeyFileFlags.KEEP_TRANSLATIONS)
    if keyfile.get_string('Desktop Entry','Exec')!='chatgpt %U':return None
    keyfile.set_string('Desktop Entry','Exec',f'"{executable}" %U')
    keyfile.set_string('Desktop Entry','OnlyShowIn','X-Zorin11-ProcessMonitor;')
    for key in ('MimeType','Actions','NotShowIn'):
        if key in keyfile.get_keys('Desktop Entry')[0]:keyfile.remove_key('Desktop Entry',key)
    return keyfile.to_data()[0].encode()


def app_entries(apps):
    result={apps/(APP_ID+'.desktop'):desktop_entry(),
            apps/'org.gnome.SystemMonitor.desktop':desktop_entry()+b'NoDisplay=true\n'}
    launcher=shutil.which('chatgpt')
    if launcher:
        launcher=Path(launcher).resolve()
        executable=launcher.parent/'ChatGPT'
        source=apps/'chatgpt.desktop'
        if not source.exists():source=Path('/usr/share/applications/chatgpt.desktop')
        if source.is_file() and executable.is_file() and launcher.stat().st_size<1024:
            try:entry=chatgpt_entry(source.read_text(),launcher.read_text(),executable)
            except (UnicodeDecodeError,ValueError):entry=None
            if entry:result[apps/'zorin11-chatgpt-processes.desktop']=entry
    return result


def available():
    try:return subprocess.run(['flatpak','info',APP_ID],capture_output=True).returncode==0
    except FileNotFoundError:return False


def setting(action,key,value=None):
    args=['flatpak','run','--command=gsettings',APP_ID,action,APP_ID,key]
    if value is not None:args.append(value)
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout.strip()


def configure(backup=BACKUP):
    if not available():raise RuntimeError('Install Mission Center with ./install-system-deps.sh first.')
    import gnome_setup
    records=json.loads(backup.read_text()) if backup.exists() else {}
    for key,value in DEFAULTS.items():
        if key not in records:records[key]={'before':setting('get',key)}
        records[key]['after']=value
    gnome_setup.save(records,backup)
    for key,value in DEFAULTS.items():setting('set',key,value)


def restore(backup=BACKUP):
    if not backup.exists() or not available():return
    records=json.loads(backup.read_text())
    for key,record in records.items():
        if setting('get',key)==record['after']:setting('set',key,record['before'])
    backup.unlink()
