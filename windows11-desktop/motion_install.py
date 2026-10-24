"""Install the taskbar-motion add-on without replacing the desktop companion."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
UUID = 'zorin11-motion@zorin-os-fixes'
MENU_COMMAND = '/usr/bin/gtk-launch zorin11-taskbar-motion'
MENU_TITLE = 'Taskbar motion…'

def files(home=None):
    home = home or Path.home()
    extension = home/'.local/share/gnome-shell/extensions'/UUID
    result = {extension/p.relative_to(ROOT/'gnome-motion-extension'):p.read_bytes()
              for p in (ROOT/'gnome-motion-extension').rglob('*') if p.is_file() and p.name != 'gschemas.compiled'}
    result[home/'.local/share/applications/zorin11-taskbar-motion.desktop'] = (
        '[Desktop Entry]\nType=Application\nName=Taskbar motion\n'
        'Comment=Choose subtle taskbar animations, accent and intensity\n'
        f'Exec=/usr/bin/gjs -m "{extension}/taskbar-settings.js" --motion\n'
        'Icon=preferences-desktop-effects\nTerminal=false\nCategories=Settings;DesktopSettings;\n'
        'StartupWMClass=local.zorin11.TaskbarSettings\n'
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
    anchor = "    command=TOOLS[tool]\n"
    block = """    if tool == 'panel' and is_gnome():
        taskbar = Path.home()/'.local/share/gnome-shell/extensions/zorin11-motion@zorin-os-fixes/taskbar-settings.js'
        if taskbar.is_file():
            command = ['gjs', '-m', str(taskbar)]
"""
    if text.count(anchor) != 1:
        raise RuntimeError('Settings launch code has changed; use the Taskbar settings Start entry until its route is updated.')
    return {path: text.replace(anchor, anchor+block).encode()}


def context_menu_settings(commands, titles):
    """Use Zorin's supported menu entries, preserving every unrelated command."""
    if len(commands) != len(titles):
        raise RuntimeError('Zorin taskbar context-menu commands and titles have different lengths.')
    pairs = [(command, title) for command, title in zip(commands, titles) if command != MENU_COMMAND]
    pairs.append((MENU_COMMAND, MENU_TITLE))
    return {'panel-context-menu-commands': [p[0] for p in pairs],
            'panel-context-menu-titles': [p[1] for p in pairs]}

def configure():
    import gnome_setup
    from gi.repository import Gio
    shell = Gio.Settings.new('org.gnome.shell')
    taskbar = Gio.Settings.new('org.gnome.shell.extensions.zorin-taskbar')
    menu = context_menu_settings(taskbar.get_strv('panel-context-menu-commands'), taskbar.get_strv('panel-context-menu-titles'))
    gnome_setup.install(gnome_setup.plan({'org.gnome.shell': {
        'enabled-extensions': list(dict.fromkeys(shell.get_strv('enabled-extensions') + [UUID])),
        'disabled-extensions': [x for x in shell.get_strv('disabled-extensions') if x != UUID],
    }, 'org.gnome.shell.extensions.zorin-taskbar': menu}))

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
    print('Installed Taskbar settings → Motion and right-click Taskbar motion. Apply at startup restores the saved effect at sign-in; updated Shell code loads at the next sign-in.')
