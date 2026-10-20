"""Install per-user repair checks, or the root-owned APT hooks with pkexec."""
import argparse
import os
from pathlib import Path
import pwd
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
HOOK = Path('/etc/apt/apt.conf.d/99axentra-desktop-guard')
HELPER = Path('/usr/local/libexec/axentra-desktop-update-guard')
CONFIG = Path('/etc/axentra-desktop-guard.json')
SERVICE = 'zorin11-update-repair.service'
TIMER = 'zorin11-update-repair.timer'


def atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.axentra-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def units():
    return {
        SERVICE: '''[Unit]
Description=Check and repair managed Windows 11 layout after package updates

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/.local/share/zorin11-hub/update_guard.py repair
Environment=XDG_CURRENT_DESKTOP=GNOME
TimeoutStartSec=300
Nice=10
''',
        TIMER: '''[Unit]
Description=Deferred desktop layout checks after updates or next sign-in

[Timer]
OnStartupSec=90
OnUnitActiveSec=60
AccuracySec=10
Unit=zorin11-update-repair.service

[Install]
WantedBy=timers.target
'''}


def user_install():
    if os.geteuid() == 0:
        raise RuntimeError('Install user files without sudo.')
    import desktop_backup
    destination = desktop_backup.configured_destination()
    if not destination.is_dir():
        raise RuntimeError('Configured backup folder is unavailable.')
    runtime = Path.home()/'.local/share/zorin11-hub'
    for name in ('desktop_backup.py', 'update_guard.py', 'update_guard_root.py', 'install_update_guard.py'):
        atomic(runtime/name, (ROOT/name).read_bytes())
    directory = Path.home()/'.config/systemd/user'
    for name, text in units().items():
        atomic(directory/name, text.encode())
    subprocess.run(['systemctl','--user','daemon-reload'], check=True)
    subprocess.run(['systemctl','--user','enable','--now',TIMER], check=True)
    print('User repair checks enabled. System APT hooks require --system --user NAME.')


def system_install(user, remove=False):
    if os.geteuid() != 0:
        raise RuntimeError('System hooks need administrator authentication via pkexec.')
    if remove:
        # Remove the APT entry first so no new transaction enters the hook.
        for path in (HOOK, HELPER, CONFIG):
            path.unlink(missing_ok=True)
        print('APT desktop protection removed. User snapshots are retained.')
        return
    account = pwd.getpwnam(user)
    if account.pw_uid < 1000 or account.pw_uid == 65534:
        raise RuntimeError('Choose a regular desktop user.')
    if not Path(account.pw_dir+'/.local/share/zorin11-hub/update_guard.py').is_file():
        raise RuntimeError('Install the user-side guard first.')
    import json
    atomic(CONFIG, json.dumps({'user':user}).encode())
    atomic(HELPER, (ROOT/'update_guard_root.py').read_bytes(), 0o755)
    # Prove privilege dropping and the real OneDrive backup before enabling
    # package-manager interception. This test installs no packages.
    subprocess.run([str(HELPER), 'before'], check=True)
    subprocess.run([str(HELPER), 'after'], check=True)
    text = ('// Axentra: verified OneDrive snapshot before APT invokes dpkg.\n'
            'DPkg::Pre-Invoke { "/usr/local/libexec/axentra-desktop-update-guard before"; };\n'
            'DPkg::Post-Invoke { "/usr/local/libexec/axentra-desktop-update-guard after"; };\n')
    atomic(HOOK, text.encode())
    subprocess.run(['/usr/bin/apt-config','dump'], check=True, stdout=subprocess.DEVNULL)
    print('Automatic APT backups and deferred desktop repair enabled for', user)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', action='store_true')
    parser.add_argument('--user')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if args.system:
        system_install(args.user, args.remove)
    elif args.remove:
        subprocess.run(['systemctl','--user','disable','--now',TIMER], check=True)
    else:
        user_install()
