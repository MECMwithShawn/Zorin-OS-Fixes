"""Read-only update inventory and persistent notification decisions."""
import hashlib
import json
from pathlib import Path
import time


def scan():
    import apt
    import apt_pkg
    cache = apt.Cache()
    packages = []
    for package in cache:
        if not package.is_upgradable or not package.candidate: continue
        version = package.candidate
        packages.append(dict(name=package.name, version=version.version,
            security=any('security' in origin.archive.lower() for origin in version.origins),
            held=package._pkg.selected_state == apt_pkg.SELSTATE_HOLD,
            size=version.size))
    packages.sort(key=lambda p: (not p['security'], p['name']))
    stamp = Path('/var/lib/apt/periodic/update-success-stamp')
    return dict(packages=packages, checked=int(time.time()),
        refreshed=int(stamp.stat().st_mtime) if stamp.exists() else 0,
        reboot=Path('/var/run/reboot-required').exists(),
        system_auto=apt_pkg.config.find_i('APT::Periodic::Unattended-Upgrade', 0) > 0)


def fingerprint(report):
    data = [(p['name'], p['version']) for p in report['packages']]
    return hashlib.sha256(json.dumps([data, report['reboot']], sort_keys=True).encode()).hexdigest()


def notification(report, preferences, now=None):
    now = time.time() if now is None else now
    if not preferences.get('notifications', True) or preferences.get('snooze_until', 0) > now: return None
    key = fingerprint(report)
    if key == preferences.get('notified'): return None
    if report['reboot']: return key, 'Restart required', 'System updates need a restart. Restart when you are ready.'
    count = len(report['packages'])
    if count: return key, 'Zorin updates available', f'{count} package updates are ready for review in Axentra Update.'
    return None


def clear_notification(report, preferences):
    """Rearm a resolved alert, including across reboot-required cycles."""
    if not report['packages'] and not report['reboot']:
        return preferences.pop('notified', None) is not None
    return False


def policy_summary(config, system_auto=False, now=None):
    now = time.time() if now is None else now
    mode = config.get('mode', 'system')
    if mode == 'system':
        return 'Zorin manages updates · automatic installs ' + ('enabled' if system_auto else 'disabled')
    if mode == 'manual':
        return 'Manual updates · Axentra scheduled installs are off'
    schedule = 'Daily' if mode == 'daily' else 'Weekly on ' + config.get('day', 'Sun')
    scope = 'all repository updates' if config.get('scope') == 'all' else 'security updates'
    text = f"{schedule} at {config.get('hour', 3):02d}:{config.get('minute', 0):02d} local time · {scope}"
    if config.get('paused_until', 0) > now:
        text = 'Paused until ' + time.strftime('%b %d, %H:%M', time.localtime(config['paused_until'])) + ' · ' + text
    return text + ' · no automatic restart'
