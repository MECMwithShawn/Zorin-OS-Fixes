#!/usr/bin/python3
"""Repeatable, per-user Zorin Lite desktop setup. Run inside the Xfce session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
CACHE = HOME/'.cache/zorin11-setup'
LOCK = json.loads((ROOT/'dependencies.json').read_text())


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def download(name):
    spec = LOCK[name]
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE/(name+'-'+spec['sha256'][:16])
    if target.exists():
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == spec['sha256']:return target
    print('Downloading', name, flush=True)
    partial = target.with_suffix('.partial')
    with urllib.request.urlopen(spec['url'], timeout=60) as source, partial.open('wb') as output:
        shutil.copyfileobj(source, output)
    with partial.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != spec['sha256']:
            partial.unlink()
            raise RuntimeError('Checksum mismatch: '+name)
    partial.replace(target)
    return target


def check():
    if os.geteuid() == 0:
        raise SystemExit('Run as your desktop user, without sudo.')
    if 'XFCE' not in os.environ.get('XDG_CURRENT_DESKTOP', '').upper() or not os.environ.get('DISPLAY'):
        raise SystemExit('Run from a terminal in the Zorin Lite/Xfce X11 desktop.')
    if os.environ.get('XDG_SESSION_TYPE', 'x11') != 'x11':
        raise SystemExit('This integration needs an X11 session.')
    release = dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID','').strip('"') != 'zorin' or release.get('UBUNTU_CODENAME','').strip('"') != 'noble':
        raise SystemExit('This package is validated for Zorin 18 Lite (Ubuntu 24.04/noble).')
    if platform.machine() != 'x86_64':
        raise SystemExit('The pinned PowerShell/WezTerm binaries require an x86-64 Intel/AMD laptop.')
    missing = [name for name in ('xfconf-query','xfce4-panel','git','gsettings','nmcli','nm-applet','xprop',
               'pactl','pavucontrol','update-desktop-database','gtk-update-icon-cache','fc-cache','exo-open') if not shutil.which(name)]
    try:
        import dbus
        import gi
        from PIL import Image
        for name, version in [('Gtk','3.0'),('WebKit2','4.1'),('Atspi','2.0'),('Wnck','3.0')]:
            gi.require_version(name,version)
        from gi.repository import Gtk, WebKit2, Atspi
    except (ImportError, ValueError):
        missing.append('Python GI / GTK3 / WebKit2 4.1 / AT-SPI / Wnck / Pillow / dbus')
    if missing:
        raise SystemExit('Missing: '+', '.join(missing)+'\nRun ./install-system-deps.sh, then rerun setup.')
    if not Path('/usr/share/themes/ZorinBlue-Dark').is_dir():
        raise SystemExit('The standard ZorinBlue-Dark theme is missing.')
    if not Path('/usr/share/xfce4/panel/plugins/genmon.desktop').exists():
        raise SystemExit('Missing Xfce Generic Monitor plugin. Run ./install-system-deps.sh first.')
    sys.path.insert(0,str(ROOT/'companion'))
    import install as integration
    from panel_layout import find_panel, plan
    manifest=json.loads(integration.MANIFEST.read_text()) if integration.MANIFEST.exists() else {}
    properties=dict(integration.XF.GetAllProperties('xfce4-panel','/'))
    panel=find_panel(properties,manifest.get('panel',0) if manifest else None)
    ids=[int(i) for i in properties[f'/panels/panel-{panel}/plugin-ids']]
    types={i:str(properties.get(f'/plugins/plugin-{i}','')) for i in ids}
    start=manifest.get('plugin') or next(i for i in ids if types[i]=='zorinmenulite')
    available=iter(range(max(ids)+100,max(ids)+200))
    plan(ids,types,start,next(available),next(available),lambda:next(available),True)
    print('Ready: Zorin 18 Lite, Xfce/X11, x86-64, panel',panel,flush=True)


def install_icons():
    icons=HOME/'.local/share/icons'
    if all((icons/name/'index.theme').exists() for name in ('Win11','Win11-dark')):
        print('Keeping installed Win11 icon themes.',flush=True)
        return
    source=CACHE/'win11-icons'
    if not (source/'.git').exists():
        run('git','clone','--filter=blob:none',LOCK['icons']['url'],source)
    run('git','-C',source,'fetch','origin',LOCK['icons']['commit'])
    run('git','-C',source,'checkout','--detach',LOCK['icons']['commit'])
    # Upstream removes its destination before copying. Stage in a private
    # directory so an existing theme belonging to the user is never removed.
    with tempfile.TemporaryDirectory(prefix='themes-',dir=CACHE) as tmp:
        run('bash',source/'install.sh','-d',tmp,'-t','default')
        icons.mkdir(parents=True,exist_ok=True)
        for name in ('Win11','Win11-dark'):
            dest=icons/name
            if dest.exists():
                continue
            staged=Path(tmp)/name
            # Upstream includes one absolute link into the staging directory.
            for link in staged.rglob('*'):
                if link.is_symlink():
                    target=os.readlink(link)
                    if target.startswith(tmp+'/'):
                        link.unlink();link.symlink_to(str(icons/Path(target).relative_to(tmp)))
            shutil.move(staged,dest)


def install_tools():
    bindir=HOME/'.local/bin';bindir.mkdir(parents=True,exist_ok=True)
    ps=HOME/'.local/share/powershell'/LOCK['powershell']['version'].lstrip('v')
    if not (ps/'pwsh').exists():
        archive=download('powershell')
        ps.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ps.parent) as tmp:
            with tarfile.open(archive) as source:
                source.extractall(tmp,filter='data')
            if ps.exists():raise RuntimeError('Incomplete PowerShell folder exists: '+str(ps))
            shutil.move(tmp,ps)
        (ps/'pwsh').chmod(0o755)
    link=bindir/'pwsh'
    if not link.exists():link.symlink_to(ps/'pwsh')
    wz=HOME/'.local/share/wezterm'/LOCK['wezterm']['version']
    if not (wz/'AppRun').exists():
        archive=download('wezterm');archive.chmod(0o755)
        wz.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=wz.parent) as tmp:
            run(archive,'--appimage-extract',cwd=tmp,stdout=subprocess.DEVNULL)
            if wz.exists():raise RuntimeError('Incomplete WezTerm folder exists: '+str(wz))
            shutil.move(Path(tmp)/'squashfs-root',wz)
    wrapper=bindir/'wezterm'
    if not wrapper.exists():
        wrapper.write_text('#!/bin/sh\nexec "$HOME/.local/share/wezterm/'+LOCK['wezterm']['version']+'/AppRun" "$@"\n')
        wrapper.chmod(0o755)
    fonts=HOME/'.local/share/fonts/CascadiaMono'
    if not (fonts/'CascadiaMono.ttf').exists():
        with zipfile.ZipFile(download('cascadia')) as archive:
            fonts.mkdir(parents=True,exist_ok=True)
            for name in ('CascadiaMono.ttf','CascadiaMonoItalic.ttf'):
                entry=next(n for n in archive.namelist() if n=='ttf/'+name)
                (fonts/name).write_bytes(archive.read(entry))
        shutil.copy2(download('cascadia_license'),fonts/'LICENSE.txt')
    icon=HOME/'.local/share/icons/hicolor/256x256/apps/zorin11-powershell.png'
    icon.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(download('powershell_icon'),icon)
    run(bindir/'pwsh','-NoLogo','-NoProfile','-Command','$PSVersionTable.PSVersion.ToString()')
    run(bindir/'wezterm','--version')


def reference_entries(archive):
    """Validate the complete local Windows export before writing any files."""
    import re
    result=[]
    allowed={'folder','drive-harddisk','drive-harddisk-usb','computer','network-workgroup',
             'user-trash','text-x-generic','user-home','drive-harddisk-root','folder-open',
             'system-file-manager','user-desktop','folder-documents','folder-pictures',
             'folder-music','folder-videos','folder-download'}
    total=0
    for entry in archive.infolist():
        if entry.is_dir():continue
        name=entry.filename.replace('\\','/')
        total+=entry.file_size
        if total>50*1024*1024:raise ValueError('Windows export exceeds 50 MB.')
        match=re.fullmatch(r'(16|24|32|48|64|256)/([a-z0-9-]+)\.png',name)
        if match and match[2] in allowed:
            data=archive.read(entry)
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG: '+name)
            result.append(('reference-icons/'+name,data))
        elif name in ('fonts/segoeui.ttf','fonts/SegUIVar.ttf'):
            result.append(('reference-fonts/'+Path(name).name,archive.read(entry)))
        else:
            raise ValueError('Unexpected file in Windows export: '+name)
    if not any(n=='reference-icons/48/computer.png' for n,_ in result):
        raise ValueError('Export is missing 48/computer.png.')
    return result


def import_reference(path):
    with zipfile.ZipFile(path) as archive:entries=reference_entries(archive)
    config=HOME/'.config/zorin11-hub'
    for name,data in entries:
        target=config/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    print('Imported',len(entries),'local Windows reference files.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','install','restore'])
    parser.add_argument('--windows-assets',type=Path,help='ZIP exported on your Windows installation')
    parser.add_argument('--skip-terminal',action='store_true',help='Skip PowerShell/WezTerm downloads')
    args=parser.parse_args()
    if args.action=='restore':
        if os.geteuid()==0:raise SystemExit('Run as your desktop user, without sudo.')
        run('/usr/bin/python3',ROOT/'companion/install.py','--uninstall')
        return
    check()
    if args.action=='check':return
    install_icons()
    if not args.skip_terminal:install_tools()
    if args.windows_assets:import_reference(args.windows_assets)
    action='--upgrade' if (HOME/'.config/zorin11-hub/integration-backup.json').exists() else '--install'
    run('/usr/bin/python3',ROOT/'companion/install.py',action)
    print('Installed. Windows key: Start. Win+E: Explorer. Win+A: Quick Settings. Win+T: Terminal.')


if __name__=='__main__':main()
