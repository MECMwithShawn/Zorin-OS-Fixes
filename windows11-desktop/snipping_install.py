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
RECORD_SHORTCUT=SHORTCUT.replace('snipping-tool/','snipping-record/')
RECORD_BACKUP=BACKUP.with_name('record-shortcut-backup.json')


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
        '[Desktop Entry]\nType=Application\nName=Axentra SnippingTool\nComment=Capture, record, annotate and extract text\n'
        f'Exec="{BINARY}"\nIcon=zorin11-snipping-tool\nTerminal=false\nCategories=Utility;Graphics;\n'
        'StartupWMClass=zorin11-snipping-tool\nKeywords=Screenshot;Capture;Snip;Annotation;\nActions=new-snip;new-recording;\n'
        f'\n[Desktop Action new-snip]\nName=New snip\nExec="{BINARY}" --capture\n'
        f'\n[Desktop Action new-recording]\nName=New recording\nExec="{BINARY}" --record\n').encode()}


def _shortcut(path, backup, key, flag):
    from gi.repository import Gio
    media=Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
    paths=media.get_strv('custom-keybindings')
    for other_path in paths:
        if other_path!=path:
            other=Gio.Settings.new_with_path(SCHEMA,other_path)
            if other.get_string('binding').lower() in (f'<super><shift>{key}',f'<shift><super>{key}'):
                print(f'Win+Shift+{key.upper()} is already assigned; preserving it.');return
    settings=Gio.Settings.new_with_path(SCHEMA,path)
    values={'name':'Axentra SnippingTool'+(' recording' if flag=='--record' else ''),'command':f'"{BINARY}" {flag}','binding':f'<Super><Shift>{key}'}
    before=json.loads(backup.read_text()) if backup.exists() else {'added':path not in paths,'before':{key:settings.get_string(key) for key in values}}
    if 'after' in before and any(settings.get_string(k)!=v for k,v in before['after'].items()):
        print('Preserving later SnippingTool shortcut edits.');return
    before['after']=values
    backup.parent.mkdir(parents=True,exist_ok=True)
    temporary=backup.with_suffix('.tmp');temporary.write_text(json.dumps(before));temporary.chmod(0o600);temporary.replace(backup)
    for key,value in values.items():
        if not settings.set_string(key,value):raise RuntimeError('Could not install SnippingTool shortcut.')
    if path not in paths:media.set_strv('custom-keybindings',paths+[path])
    Gio.Settings.sync()

def shortcut():_shortcut(SHORTCUT,BACKUP,'s','--capture')
def record_shortcut():_shortcut(RECORD_SHORTCUT,RECORD_BACKUP,'r','--record')

def _restore(path,backup):
    if not backup.exists():return
    from gi.repository import Gio
    record=json.loads(backup.read_text());settings=Gio.Settings.new_with_path(SCHEMA,path)
    if any(settings.get_string(k)!=v for k,v in record['after'].items()):
        print('Preserving later SnippingTool shortcut edits.');return
    for key,value in record['before'].items():settings.set_string(key,value)
    media=Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
    if record['added']:media.set_strv('custom-keybindings',[p for p in media.get_strv('custom-keybindings') if p!=path])
    Gio.Settings.sync();backup.unlink()

def restore_shortcut():_restore(SHORTCUT,BACKUP)
def restore_record_shortcut():_restore(RECORD_SHORTCUT,RECORD_BACKUP)


def install():
    import gnome_install
    binary=build()
    gnome_install.write_files(files(binary));BINARY.chmod(0o755);shortcut();record_shortcut()
    subprocess.run(['update-desktop-database',str(HOME/'.local/share/applications')],check=True)


if __name__=='__main__':
    if os.geteuid()==0:raise SystemExit('Run as your desktop user, without sudo.')
    install()
