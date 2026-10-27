"""Install the update tray without replacing the companion or changing APT policy."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent


def route_files(home=None):
    path=(home or Path.home())/'.local/share/zorin11-hub/settings_backend.py'
    if not path.is_file():return {}
    text=path.read_text()
    block="""    if tool == 'updates' and is_gnome():
        agent = Path.home()/'.local/share/zorin11-hub/update_agent/agent.py'
        if agent.is_file():
            command = ['/usr/bin/env', 'GDK_BACKEND=x11', '/usr/bin/python3', str(agent)]
"""
    if block in text:return {}
    anchor='    command=TOOLS[tool]\n'
    if text.count(anchor)!=1:raise RuntimeError('Settings launch structure changed; refusing to replace local companion code.')
    return {path:text.replace(anchor,anchor+block).encode()}


def files(home=None):
    home=home or Path.home()
    dest=home/'.local/share/zorin11-hub/update_agent'
    result={dest/p.name:p.read_bytes() for p in (ROOT/'update_agent').iterdir() if p.suffix in ('.py','.svg')}
    result[home/'.local/share/applications/zorin11-update-agent.desktop']=(f'''[Desktop Entry]
Type=Application
Name=Axentra Update
Comment=Zorin system updates, notifications and schedules
Exec=/usr/bin/env GDK_BACKEND=x11 /usr/bin/python3 "{dest}/agent.py"
Icon={dest}/update.svg
Terminal=false
Categories=Settings;
StartupWMClass=zorin11-update-agent
Keywords=Windows;Update;Zorin;Schedule;Security;
''').encode()
    result[home/'.config/systemd/user/zorin11-update-agent.service']=b'''[Unit]
Description=Axentra Update tray and update notifications
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
Environment=GDK_BACKEND=x11
ExecStart=/usr/bin/python3 %h/.local/share/zorin11-hub/update_agent/agent.py --tray
Restart=on-failure
RestartSec=15

[Install]
WantedBy=graphical-session.target
'''
    return result


def install():
    import gnome_install
    gnome_install.write_files({**files(),**route_files()})
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','zorin11-update-agent.service'],check=True)
    subprocess.run(['update-desktop-database',str(Path.home()/'.local/share/applications')],check=True)
    print('Axentra Update tray installed. System update policy was preserved.')


if __name__=='__main__': install()
