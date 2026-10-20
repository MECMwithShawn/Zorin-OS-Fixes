"""Build and install the native Rust Snipping Tool, with reversible Win+Shift+S."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
HOME=Path.home()
BINARY=HOME/'.local/bin/zorin11-snipping-tool'
SHORTCUT='/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/zorin11-snipping-tool/'
SCHEMA='org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
BACKUP=HOME/'.config/zorin11-snipping-tool/shortcut-backup.json'


def build():
    cargo=shutil.which('cargo') or str(HOME/'.cargo/bin/cargo')
    if not Path(cargo).is_file():
        raise RuntimeError('Building Snipping Tool needs cargo/rustc and libgtk-3-dev. Run install-system-deps.sh.')
    subprocess.run([cargo,'build','--release','--locked','--manifest-path',str(ROOT/'snipping-tool/Cargo.toml'),
                    '--target-dir',str(ROOT/'snipping-tool/target')],check=True)
    return ROOT/'snipping-tool/target/release/zorin11-snipping-tool'


def files(binary):
    return {BINARY:Path(binary).read_bytes(),
      HOME/'.local/share/icons/hicolor/scalable/apps/zorin11-snipping-tool.svg':(ROOT/'snipping-tool/icon.svg').read_bytes(),
      HOME/'.local/share/applications/zorin11-snipping-tool.desktop':(
        '[Desktop Entry]\nType=Application\nName=Snipping Tool\nComment=Capture and annotate your screen\n'
        f'Exec="{BINARY}"\nIcon=zorin11-snipping-tool\nTerminal=false\nCategories=Utility;Graphics;\n'
        'StartupWMClass=zorin11-snipping-tool\nKeywords=Screenshot;Capture;Snip;Annotation;\nActions=new-snip;\n'
        f'\n[Desktop Action new-snip]\nName=New snip\nExec="{BINARY}" --capture\n').encode()}


def shortcut():
    from gi.repository import Gio,GLib
    media=Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
    paths=media.get_strv('custom-keybindings')
    for path in paths:
        if path!=SHORTCUT:
            other=Gio.Settings.new_with_path(SCHEMA,path)
            if other.get_string('binding').lower() in ('<super><shift>s','<shift><super>s'):
                print('Win+Shift+S is already assigned. Snipping Tool remains available from Start.');return
    settings=Gio.Settings.new_with_path(SCHEMA,SHORTCUT)
    values={'name':'Snipping Tool','command':f'"{BINARY}" --capture','binding':'<Super><Shift>s'}
    before=json.loads(BACKUP.read_text()) if BACKUP.exists() else {'added':SHORTCUT not in paths,'before':{key:settings.get_string(key) for key in values}}
    before['after']=values
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    temporary=BACKUP.with_suffix('.tmp');temporary.write_text(json.dumps(before));temporary.chmod(0o600);temporary.replace(BACKUP)
    for key,value in values.items():
        if not settings.set_string(key,value):raise RuntimeError('Could not install Snipping Tool shortcut.')
    if SHORTCUT not in paths:media.set_strv('custom-keybindings',paths+[SHORTCUT])
    Gio.Settings.sync()


def restore_shortcut():
    if not BACKUP.exists():return
    from gi.repository import Gio
    record=json.loads(BACKUP.read_text());settings=Gio.Settings.new_with_path(SCHEMA,SHORTCUT)
    if any(settings.get_string(k)!=v for k,v in record['after'].items()):
        print('Preserving later Snipping Tool shortcut edits.');return
    for key,value in record['before'].items():settings.set_string(key,value)
    media=Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
    if record['added']:media.set_strv('custom-keybindings',[p for p in media.get_strv('custom-keybindings') if p!=SHORTCUT])
    Gio.Settings.sync();BACKUP.unlink()


def install():
    import gnome_install
    binary=build()
    gnome_install.write_files(files(binary));BINARY.chmod(0o755);shortcut()
    subprocess.run(['update-desktop-database',str(HOME/'.local/share/applications')],check=True)


if __name__=='__main__':
    if os.geteuid()==0:raise SystemExit('Run as your desktop user, without sudo.')
    install()
