"""Install the taskbar-motion add-on without replacing the desktop companion."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
UUID = 'zorin11-motion@zorin-os-fixes'

def files(home=None):
    home = home or Path.home()
    extension = home/'.local/share/gnome-shell/extensions'/UUID
    result = {extension/p.relative_to(ROOT/'gnome-motion-extension'):p.read_bytes()
              for p in (ROOT/'gnome-motion-extension').rglob('*') if p.is_file() and p.name != 'gschemas.compiled'}
    result[home/'.local/share/applications/zorin11-taskbar-motion.desktop'] = (
        '[Desktop Entry]\nType=Application\nName=Taskbar motion\n'
        'Comment=Choose subtle taskbar animations, accent and intensity\n'
        f'Exec=/usr/bin/gjs -m "{extension}/preferences.js"\n'
        'Icon=preferences-desktop-effects\nTerminal=false\nCategories=Settings;DesktopSettings;\n'
        'StartupWMClass=local.zorin11.TaskbarMotion\n'
        'Keywords=Taskbar;Animation;Motion;Aurora;Glow;Personalization;\nOnlyShowIn=GNOME;\n').encode()
    return result

def configure():
    import gnome_setup
    from gi.repository import Gio
    shell = Gio.Settings.new('org.gnome.shell')
    gnome_setup.install(gnome_setup.plan({'org.gnome.shell': {
        'enabled-extensions': list(dict.fromkeys(shell.get_strv('enabled-extensions') + [UUID])),
        'disabled-extensions': [x for x in shell.get_strv('disabled-extensions') if x != UUID],
    }}))

def compile_schema(home=None):
    subprocess.run(['glib-compile-schemas', '--strict', str((home or Path.home())/'.local/share/gnome-shell/extensions'/UUID/'schemas')], check=True)

def cleanup(home=None):
    extension = (home or Path.home())/'.local/share/gnome-shell/extensions'/UUID
    schemas = extension/'schemas'
    # The normal restore already preserves files edited since installation.
    if not list(schemas.glob('*.xml')):
        (schemas/'gschemas.compiled').unlink(missing_ok=True)
    for directory in (schemas, extension):
        try: directory.rmdir()
        except OSError: pass

if __name__ == '__main__':
    import gnome_install
    gnome_install.write_files(files())
    compile_schema(); configure()
    print('Installed Taskbar motion. Open Taskbar motion from Start to preview; the add-on loads at your next sign-in.')
