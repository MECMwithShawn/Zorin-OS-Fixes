#!/usr/bin/python3 -I
"""Root-owned APT hook: run all desktop/OneDrive work after dropping privileges."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

CONFIG = Path('/etc/axentra-desktop-guard.json')


def transaction():
    pid = os.getppid()
    for _ in range(20):
        try:
            raw = (Path('/proc')/str(pid)/'stat').read_text()
            name = raw[raw.index('(')+1:raw.rindex(')')]
            fields = raw[raw.rindex(')')+2:].split()
            if name in ('apt','apt-get','aptkitd','packagekitd') or name.startswith('unattended'):
                return str(pid)+'-'+fields[19]  # PID plus kernel start time
            pid = int(fields[1])
            if pid <= 1:
                break
        except (OSError, ValueError, IndexError):
            break
    return str(os.getppid())


def command(user, action):
    account = pwd.getpwnam(user)
    if account.pw_uid < 1000 or account.pw_uid == 65534:
        raise RuntimeError('Configure a regular desktop user.')
    runtime = Path('/run/user')/str(account.pw_uid)
    env = ['HOME='+account.pw_dir, 'USER='+user, 'LOGNAME='+user,
           'PATH=/usr/local/bin:/usr/bin:/bin', 'XDG_RUNTIME_DIR='+str(runtime),
           'XDG_CURRENT_DESKTOP=GNOME']
    target = ['/usr/bin/python3', account.pw_dir+'/.local/share/zorin11-hub/update_guard.py',
              action, '--transaction', transaction()]
    if (runtime/'bus').exists():
        env.append('DBUS_SESSION_BUS_ADDRESS=unix:path='+str(runtime/'bus'))
    else:
        target = ['/usr/bin/dbus-run-session', '--']+target
    return ['/usr/sbin/runuser', '-u', user, '--', '/usr/bin/env', '-i']+env+target


def main():
    if os.geteuid() != 0 or sys.argv[1:] not in (['before'], ['after']):
        raise RuntimeError('Use the installed APT hook as root with before or after.')
    action = sys.argv[1]
    try:
        config = json.loads(CONFIG.read_text())
        subprocess.run(command(config['user'], action), check=True,
                       stdin=subprocess.DEVNULL, timeout=600)
    except Exception as error:
        print('Axentra desktop protection:', error, file=sys.stderr)
        if action == 'before':
            print('Update postponed: a verified pre-update desktop backup could not be saved. '
                  'Sign in and make the configured OneDrive folder available, then retry.',
                  file=sys.stderr)
            raise SystemExit(1)
        # Package installation already finished; leave repair pending for login.


if __name__ == '__main__':
    main()
