"""Opt-in, read-only suspend/resume diagnostics. Never suspends or changes settings."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
from gi.repository import Gio, GLib


def snapshot():
    result = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    checks = {
        'displays': ('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                     'org.gnome.Mutter.DisplayConfig', 'GetCurrentState', None),
        'onedrive': ('io.github.mecmwithshawn.AxentraOneDrive', '/io/github/mecmwithshawn/AxentraOneDrive',
                     'io.github.mecmwithshawn.AxentraOneDrive1', 'Status', None),
        'panels': ('local.zorin11.Gnome', '/local/zorin11/Gnome', 'local.zorin11.Gnome',
                   'Call', GLib.Variant('(s)', ('{"op":"panels"}',))),
    }
    for key, args in checks.items():
        try:
            value = bus.call_sync(*args, None, Gio.DBusCallFlags.NONE, 5000, None).unpack()
            if key == 'displays':
                result[key] = {'logical': value[2], 'properties': value[3],
                              'physical': [{'identity': spec, 'current': [m[:4] for m in modes if m[-1].get('is-current')]}
                                           for spec, modes, _ in value[1]]}
            else:
                value = json.loads(value[0])
                if key == 'onedrive':
                    # Do not include filenames or account details in diagnostics.
                    value = {k: value.get(k) for k in ('state', 'pending', 'uploading', 'downloading')}
                result[key] = value
        except Exception as error:
            result[key] = {'error': str(error)}
    try:
        process = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,pstate', '--format=csv,noheader'],
                                 capture_output=True, text=True, timeout=10)
        result['gpu'] = {'returncode': process.returncode, 'output': process.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        result['gpu'] = {'error': str(error)}
    result['onedrive_mounted'] = os.path.ismount(Path.home() / 'OneDrive')
    try:
        network = subprocess.run(['nmcli', '-t', '-f', 'STATE,CONNECTIVITY,WIFI', 'general'],
                                 capture_output=True, text=True, timeout=5)
        result['network'] = {'returncode': network.returncode, 'status': network.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        result['network'] = {'error': str(error)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--watch', action='store_true', help='Observe one suspend/resume cycle, then exit')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save(name):
        target = args.output / (name + '.json')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(snapshot(), indent=2) + '\n')
        temporary.chmod(0o600)
        temporary.replace(target)
        print(name, flush=True)
        return False

    if not args.watch:
        save('snapshot')
        return
    loop = GLib.MainLoop()
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    suspended = [False]

    def changed(_bus, _sender, _path, _interface, _signal, parameters):
        sleeping = parameters.unpack()[0]
        # Never delay suspend with D-Bus or GPU queries while drivers quiesce.
        (args.output / ('suspend-event' if sleeping else 'resume-event')).write_text(
            datetime.datetime.now(datetime.timezone.utc).isoformat() + '\n')
        if sleeping:
            suspended[0] = True
        elif suspended[0]:
            suspended[0] = False
            GLib.timeout_add_seconds(15, lambda: save('resume-15s'))
            def finish():
                save('resume-45s')
                loop.quit()
                return False
            GLib.timeout_add_seconds(45, finish)

    watch = bus.signal_subscribe('org.freedesktop.login1', 'org.freedesktop.login1.Manager',
                                'PrepareForSleep', '/org/freedesktop/login1', None,
                                Gio.DBusSignalFlags.NONE, changed)
    save('before')
    try:
        loop.run()
    finally:
        bus.signal_unsubscribe(watch)


if __name__ == '__main__':
    main()
