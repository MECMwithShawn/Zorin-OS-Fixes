#!/usr/bin/python3 -I
"""Root-owned scheduler. No user-controlled scripts or shell commands run as root."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

HELPER = Path('/usr/local/libexec/axentra-update-agent')
CONFIG = Path('/etc/axentra-update-agent.json')
POLICY = Path('/etc/apt/apt.conf.d/99zz-axentra-update-agent')
STATE = Path('/var/lib/axentra-update-agent')
UNITS = Path('/etc/systemd/system')
HOOK = Path('/etc/apt/apt.conf.d/99axentra-desktop-guard')
LOG = Path('/var/log/axentra-update-agent.log')
SERVICE = 'axentra-update-agent.service'
TIMER = 'axentra-update-agent.timer'
DEFAULT = dict(mode='system', scope='security', day='Sun', hour=3, minute=0, paused_until=0)
DAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
ENV = dict(PATH='/usr/sbin:/usr/bin:/sbin:/bin', HOME='/root', LANG='C.UTF-8', DEBIAN_FRONTEND='noninteractive')


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise ValueError('Invalid update settings')
    if value['mode'] not in ('system', 'manual', 'daily', 'weekly') or value['scope'] not in ('security', 'all') or value['day'] not in DAYS:
        raise ValueError('Invalid update mode, scope or day')
    for key, limit in [('hour', 23), ('minute', 59), ('paused_until', int(time.time())+8*86400)]:
        if type(value[key]) is not int or not 0 <= value[key] <= limit:
            raise ValueError('Invalid '+key)
    return dict(value)


def atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.axentra-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, mode); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def read_config():
    return validate(json.loads(CONFIG.read_text())) if CONFIG.exists() else dict(DEFAULT)


def calendar(config):
    prefix = config['day']+' ' if config['mode'] == 'weekly' else ''
    return f"{prefix}*-*-* {config['hour']:02}:{config['minute']:02}:00"


def units(config):
    return {
        SERVICE: '''[Unit]
Description=Axentra scheduled Zorin updates with desktop backup protection
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/systemd-inhibit --what=sleep:shutdown --mode=block --who=Axentra-Update --why=Installing-system-updates /usr/local/libexec/axentra-update-agent run
TimeoutStartSec=infinity
KillMode=process
Nice=10
IOSchedulingClass=idle
''',
        TIMER: f'''[Unit]
Description=Axentra Zorin update schedule

[Timer]
OnCalendar={calendar(config)}
OnBootSec=5min
OnUnitInactiveSec=30min
Persistent=true
RandomizedDelaySec=300
Unit={SERVICE}

[Install]
WantedBy=timers.target
'''}


def status(state, message, **extra):
    row = dict(time=int(time.time()), state=state, message=message, **extra)
    path = STATE/'history.json'
    history = json.loads(path.read_text()) if path.exists() else []
    atomic(path, (json.dumps((history+[row])[-100:], indent=2)+'\n').encode())
    return row


def configure(config):
    config = validate(config)
    # Stopping a timer never cancels an in-progress package transaction.
    subprocess.run(['systemctl', 'stop', TIMER], check=True)
    if config['mode'] == 'system':
        POLICY.unlink(missing_ok=True)
    else:
        atomic(POLICY, b'// Axentra owns scheduling; return to System managed to restore Zorin policy.\nAPT::Periodic::Unattended-Upgrade "0";\n')
    for name, content in units(config).items():
        atomic(UNITS/name, content.encode())
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    atomic(CONFIG, (json.dumps(config, indent=2)+'\n').encode())
    if config['mode'] in ('daily', 'weekly'):
        subprocess.run(['systemctl', 'enable', '--now', TIMER], check=True)
    else:
        subprocess.run(['systemctl', 'disable', TIMER], check=True)
    status('configured', 'Update policy saved', mode=config['mode'], scope=config['scope'])


def skip_reason(config, now, metered, on_battery):
    if config['mode'] not in ('daily', 'weekly'): return 'Automatic installs are not managed by Axentra.'
    if config['paused_until'] > now: return 'Automatic updates are paused.'
    if on_battery: return 'Waiting for AC power.'
    if metered not in ('no', 'guess-no'): return 'Waiting for a confirmed unmetered network.'
    return ''


def scheduled_slot(config, now):
    current = datetime.datetime.fromtimestamp(now)
    slot = current.replace(hour=config['hour'], minute=config['minute'], second=0, microsecond=0)
    if config['mode'] == 'weekly':
        slot -= datetime.timedelta(days=(slot.weekday()-DAYS.index(config['day'])) % 7)
    if slot > current: slot -= datetime.timedelta(days=7 if config['mode']=='weekly' else 1)
    return int(slot.timestamp())


def run():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        config = read_config()
        slot = scheduled_slot(config, time.time())
        history = json.loads((STATE/'history.json').read_text()) if (STATE/'history.json').exists() else []
        if any(row['state']=='completed' and row.get('slot',0)>=slot for row in history): return
        network = subprocess.run(['/usr/bin/busctl', '--system', 'get-property', 'org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager', 'org.freedesktop.NetworkManager', 'Metered'], capture_output=True, text=True, env=ENV, timeout=15)
        metered = {'u 2':'no', 'u 4':'guess-no'}.get(network.stdout.strip(), 'unknown') if network.returncode == 0 else 'unknown'
        power = subprocess.run(['/usr/sbin/on_ac_power'], env=ENV) if Path('/usr/sbin/on_ac_power').exists() else None
        reason = skip_reason(config, time.time(), metered, power is None or power.returncode != 0)
        if reason: status('deferred', reason); return
        if not HOOK.exists() or 'axentra-desktop-update-guard before' not in HOOK.read_text():
            status('failed', 'Desktop backup hooks are missing; automatic installation was blocked.')
            raise RuntimeError('Install the desktop backup hooks first')
        status('running', 'Refreshing package lists', scope=config['scope'])
        with LOG.open('a') as log:
            refresh = subprocess.run(['/usr/bin/apt-get', '-o', 'APT::Update::Error-Mode=any', '-o', 'Acquire::Retries=2', '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30', 'update'], env=ENV, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            if refresh.returncode: raise RuntimeError('Repository refresh failed; no packages were installed.')
            status('running', 'Installing updates; desktop backup hooks run before package changes', scope=config['scope'])
            if config['scope'] == 'all':
                command = ['/usr/bin/apt-get', '-y', '--with-new-pkgs', '--no-remove', '-o', 'DPkg::Lock::Timeout=120', '-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold', 'upgrade']
                result = subprocess.run(command, env=ENV, stdout=log, stderr=subprocess.STDOUT)
            else:
                # Snapshot the effective APT policy, preserving allowed origins,
                # package holds and backup hooks, but forbid automatic restarts
                # and removals. Prevent apt.conf.d from overriding this snapshot.
                dump = subprocess.check_output(['/usr/bin/apt-config', 'dump'], env=ENV)
                overrides = b'''\nDir::Etc::parts "-";
Dir::Etc::main "-";
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "false";
Unattended-Upgrade::Remove-New-Unused-Dependencies "false";
Unattended-Upgrade::Remove-Unused-Dependencies "false";
Unattended-Upgrade::OnlyOnACPower "true";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
'''
                policy = STATE/'run.conf'; atomic(policy, dump+overrides, 0o600)
                try:
                    result = subprocess.run(['/usr/bin/unattended-upgrade'], env=dict(ENV, APT_CONFIG=str(policy)), stdout=log, stderr=subprocess.STDOUT)
                finally: policy.unlink(missing_ok=True)
            if result.returncode: raise RuntimeError(f'Update installation failed (exit {result.returncode}); see the system update log.')
        status('completed', 'Scheduled update run completed; some updates may require manual review.', slot=slot, reboot=Path('/var/run/reboot-required').exists())


def install():
    if not Path('/usr/bin/unattended-upgrade').exists(): raise RuntimeError('Install unattended-upgrades first')
    atomic(HELPER, Path(__file__).read_bytes(), 0o755)
    config = read_config()
    # Installing the helper does not change existing system policy or install packages.
    for name, content in units(config).items(): atomic(UNITS/name, content.encode())
    if not CONFIG.exists(): atomic(CONFIG, (json.dumps(config, indent=2)+'\n').encode())
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Administrator scheduler installed; existing update policy preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'configure', 'run'])
    parser.add_argument('--config')
    args = parser.parse_args()
    if os.geteuid() != 0: raise SystemExit('Administrator authentication is required.')
    try:
        if args.action == 'install': install()
        elif args.action == 'configure': configure(json.loads(args.config or '{}'))
        else: run()
    except Exception as error:
        if args.action == 'run': status('failed', str(error))
        raise SystemExit(str(error))
