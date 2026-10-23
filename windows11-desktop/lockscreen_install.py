"""Install only lock-screen presentation; preserve the live companion/OneDrive."""
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parent
UUID = 'zorin11-lockscreen@zorin-os-fixes'
UNIT = 'zorin11-lockscreen-wallpaper'
ROUTE = """    if tool == 'lock' and is_gnome():
        lockscreen = Path.home()/'.local/share/zorin11-hub/lockscreen_settings.py'
        if lockscreen.is_file():
            command = ['/usr/bin/python3', str(lockscreen)]
"""

def files(home=None):
    home=home or Path.home();extension=home/'.local/share/gnome-shell/extensions'/UUID;runtime=home/'.local/share/zorin11-hub'
    result={extension/p.relative_to(ROOT/'gnome-lockscreen-extension'):p.read_bytes() for p in (ROOT/'gnome-lockscreen-extension').rglob('*') if p.is_file() and p.name!='gschemas.compiled'}
    result[runtime/'lockscreen_install.py']=(ROOT/'lockscreen_install.py').read_bytes()
    for name in ('lockscreen.py','lockscreen_settings.py'):result[runtime/name]=(ROOT/'companion'/name).read_bytes()
    result[home/'.local/share/applications/zorin11-lockscreen.desktop']=(
        '[Desktop Entry]\nType=Application\nName=Lock screen settings\nComment=Windows 11 lock screen, Spotlight, Bing and Zorin wallpapers\n'
        f'Exec=/usr/bin/python3 "{runtime}/lockscreen_settings.py"\nIcon=preferences-desktop-wallpaper\n'
        'Terminal=false\nCategories=Settings;DesktopSettings;\nStartupWMClass=local.zorin11.LockScreenSettings\n'
        'Keywords=Lock;Screen;Spotlight;Bing;Wallpaper;Personalization;\nOnlyShowIn=GNOME;\n').encode()
    units=home/'.config/systemd/user'
    result[units/(UNIT+'.service')]=('[Unit]\nDescription=Refresh the Axentra lock-screen photo\nAfter=graphical-session.target\n'
        '[Service]\nType=oneshot\n'
        f'ExecStart=/usr/bin/python3 "{runtime}/lockscreen.py" --refresh\n'
        'TimeoutStartSec=90\nUMask=0077\nNice=10\nNoNewPrivileges=true\n').encode()
    result[units/(UNIT+'.timer')]=('[Unit]\nDescription=Check for a daily lock-screen photo\nPartOf=graphical-session.target\n'
        '[Timer]\nOnStartupSec=3min\nOnCalendar=hourly\nRandomizedDelaySec=2min\nPersistent=true\n'
        '[Install]\nWantedBy=graphical-session.target\n').encode()
    return result

def route_files(home=None):
    path=(home or Path.home())/'.local/share/zorin11-hub/settings_backend.py'
    if not path.exists():return {}
    text=path.read_text()
    if ROUTE in text:return {}
    marker='    command=TOOLS[tool]\n'
    if text.count(marker)!=1:raise RuntimeError('Settings routing changed; use the Lock screen settings Start entry.')
    return {path:text.replace(marker,marker+ROUTE).encode()}

def compile_schema(home=None):
    subprocess.run(['glib-compile-schemas','--strict',str((home or Path.home())/'.local/share/gnome-shell/extensions'/UUID/'schemas')],check=True)

def configure():
    import gnome_setup
    from gi.repository import Gio
    s=Gio.Settings.new('org.gnome.shell')
    gnome_setup.install(gnome_setup.plan({'org.gnome.shell':{'enabled-extensions':list(dict.fromkeys(s.get_strv('enabled-extensions')+[UUID])), 'disabled-extensions':[x for x in s.get_strv('disabled-extensions') if x!=UUID]}}))
    subprocess.run(['/usr/bin/python3',str(Path.home()/'.local/share/zorin11-hub/lockscreen.py'),'--initialize'],check=True)

def cleanup(home=None):
    extension=(home or Path.home())/'.local/share/gnome-shell/extensions'/UUID;schemas=extension/'schemas'
    if not list(schemas.glob('*.xml')):(schemas/'gschemas.compiled').unlink(missing_ok=True)
    for directory in (schemas,extension):
        try:directory.rmdir()
        except OSError:pass

if __name__=='__main__':
    import gnome_install
    gnome_install.write_files({**files(),**route_files()});compile_schema();configure()
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now',UNIT+'.timer'],check=True)
    subprocess.run(['update-desktop-database',str(Path.home()/'.local/share/applications')],check=True)
    print('Installed Lock screen settings. First activation requires your next normal sign-in; native unlocking is unchanged.')
