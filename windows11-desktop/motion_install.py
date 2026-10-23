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
    result[home/'.local/share/applications/zorin11-taskbar-settings.desktop'] = (
        '[Desktop Entry]\nType=Application\nName=Taskbar settings\n'
        'Comment=Taskbar style, position, behavior, actions and motion\n'
        f'Exec=/usr/bin/gjs -m "{extension}/taskbar-settings.js"\n'
        'Icon=preferences-desktop-display\nTerminal=false\nCategories=Settings;DesktopSettings;\n'
        'StartupWMClass=local.zorin11.TaskbarSettings\n'
        'Keywords=Taskbar;Animation;Motion;Panel;Personalization;\nOnlyShowIn=GNOME;\n').encode()
    return result

def route_files(home=None):
    """Patch only the legacy Settings launch route, preserving local companion work."""
    path = (home or Path.home())/'.local/share/zorin11-hub/settings_backend.py'
    if not path.is_file():
        return {}
    text = path.read_text()
    marker = "        taskbar = Path.home()/'.local/share/gnome-shell/extensions/zorin11-motion@zorin-os-fixes/taskbar-settings.js'"
    if marker in text:
        return {}
    before = "    command=TOOLS[tool]\n    if not shutil.which(command[0]):"
    after = """    command=TOOLS[tool]
    if tool == 'panel' and is_gnome():
        taskbar = Path.home()/'.local/share/gnome-shell/extensions/zorin11-motion@zorin-os-fixes/taskbar-settings.js'
        if taskbar.is_file():
            command = ['gjs', '-m', str(taskbar)]
    if not shutil.which(command[0]):"""
    if text.count(before) != 1:
        raise RuntimeError('Settings launch code has changed; use the Taskbar settings Start entry until its route is updated.')
    return {path: text.replace(before, after).encode()}

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
    gnome_install.write_files({**files(), **route_files()})
    compile_schema(); configure()
    print('Installed Taskbar settings → Motion. Apply saves preview changes; first activation needs your next sign-in. Existing Settings processes use the new route on their next start.')
