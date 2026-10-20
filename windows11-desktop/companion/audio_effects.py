"""Playback-only PipeWire equalizer; hardware volume and default output stay intact."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

ROOT = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'zorin11-hub'
STATE = ROOT/'audio-effects.json'
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))/'zorin11-audio'
STATUS = RUNTIME/'status.json'
SINK = 'zorin11.eq.input'
PLAYBACK = 'zorin11.eq.output'
UNIT = 'zorin11-audio-effects.service'
FREQUENCIES = [60, 170, 500, 2000, 6000, 12000]
PRESETS = [
    dict(id='off', name='Off', detail='Original sound, without equalization.', gains=[0]*6),
    dict(id='balanced', name='Balanced', detail='A gentle lift to bass and detail.', gains=[2, 1, -1, 0, 1, 1]),
    dict(id='music', name='Music', detail='Warm bass and a gentle treble lift for music.', gains=[3, 1, -1, 0, 2, 2]),
    dict(id='bass', name='Bass boost', detail='More low-end weight for music.', gains=[6, 3, 0, -1, 0, 0]),
    dict(id='voice', name='Vocal clarity', detail='Less rumble and clearer voices for speech and calls.', gains=[-5, -3, 0, 3, 2, -1]),
    dict(id='movies', name='Movies', detail='Fuller bass with clearer dialogue.', gains=[4, 2, -1, 2, 1, 0]),
    dict(id='gaming', name='Gaming', detail='Less low-end masking and more upper-mid detail.', gains=[-3, -1, 0, 3, 3, 1]),
    dict(id='night', name='Night listening', detail='Reduced bass and treble for softer listening; no loudness compression.', gains=[-6, -3, 0, 1, -2, -4]),
]


def preset(ident):
    value = next((p for p in PRESETS if p['id'] == ident), None)
    if value is None:
        raise ValueError('Choose one of the available audio presets.')
    return value


def run(args, timeout=4):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=timeout).strip()


def read_json(path, default):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default


def save(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def selection():
    value = read_json(STATE, {}).get('preset', 'off')
    return value if any(p['id'] == value for p in PRESETS) else 'off'


def available():
    if not all(shutil.which(p) for p in ('pipewire', 'pw-cli', 'pw-dump', 'pactl', 'systemctl')):
        return False
    try:
        return 'PipeWire' in run(['pactl', 'info'])
    except (OSError, subprocess.SubprocessError):
        return False


def snapshot():
    status = read_json(STATUS, {})
    selected = selection()
    active = bool(status.get('active') and status.get('preset') == selected
                  and time.time()-status.get('updated', 0) < 6)
    return dict(available=available(), preset=selected, active=active,
                error=status.get('error', '') if selected != 'off' else '',
                presets=PRESETS, frequencies=FREQUENCIES)


def configure(ident):
    preset(ident)
    if ident != 'off' and not available():
        raise ValueError('Audio presets require PipeWire playback on this desktop.')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(ROOT/'audio-effects.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = selection()
        save(STATE, dict(preset=ident))
        try:
            if ident == 'off':
                run(['systemctl', '--user', 'disable', '--now', UNIT], timeout=12)
                return
            run(['systemctl', '--user', 'enable', '--now', UNIT], timeout=8)
            deadline = time.monotonic()+8
            while time.monotonic() < deadline:
                status = read_json(STATUS, {})
                if status.get('preset') == ident and time.time()-status.get('updated', 0) < 3:
                    if status.get('active'):
                        return
                    if status.get('error'):
                        raise RuntimeError(status['error'])
                time.sleep(.1)
            raise RuntimeError('Audio processing did not start. Your original output remains available.')
        except Exception:
            save(STATE, dict(preset=previous))
            if previous == 'off':
                subprocess.run(['systemctl', '--user', 'disable', '--now', UNIT], capture_output=True, timeout=12)
            raise


def headroom(gains):
    # Every band is a peaking filter; the sum of positive boosts is an upper bound.
    return -sum(max(0, gain) for gain in gains)


def controls(ident):
    gains = preset(ident)['gains']
    return {'preamp:Gain 1': 10**(headroom(gains)/20),
            **{f'band{i}:Gain': float(gain) for i, gain in enumerate(gains)}}


def graph(ident, target):
    gains = preset(ident)['gains']
    nodes = [dict(type='builtin', name='preamp', label='mixer',
                  control={'Gain 1': controls(ident)['preamp:Gain 1']})]
    nodes += [dict(type='builtin', name=f'band{i}', label='bq_peaking',
                   control={'Freq': float(freq), 'Q': 1.0, 'Gain': float(gain)})
              for i, (freq, gain) in enumerate(zip(FREQUENCIES, gains))]
    links = [dict(output='preamp:Out', input='band0:In')]
    links += [dict(output=f'band{i}:Out', input=f'band{i+1}:In') for i in range(5)]
    return {
        'context.properties': {'log.level': 0},
        'context.spa-libs': {'audio.convert.*': 'audioconvert/libspa-audioconvert', 'support.*': 'support/libspa-support'},
        'context.modules': [
            {'name': 'libpipewire-module-protocol-native'},
            {'name': 'libpipewire-module-client-node'},
            {'name': 'libpipewire-module-adapter'},
            {'name': 'libpipewire-module-filter-chain', 'args': {
                'node.description': 'Audio enhancements', 'media.name': 'Zorin11 Audio Effects',
                'filter.graph': {'nodes': nodes, 'links': links, 'inputs': ['preamp:In 1'], 'outputs': ['band5:Out']},
                'audio.channels': 2, 'audio.position': ['FL', 'FR'],
                'capture.props': {'node.name': SINK, 'media.class': 'Audio/Sink',
                                  'node.virtual': True, 'priority.session': 0},
                'playback.props': {'node.name': PLAYBACK, 'media.name': 'Zorin11 Audio Effects',
                                   'application.name': 'Zorin11 Audio Effects',
                                   'node.passive': True, 'target.object': target,
                                   'node.dont-fallback': True, 'node.dont-reconnect': True},
            }},
        ]}


def sinks():
    return json.loads(run(['pactl', '--format=json', 'list', 'sinks']))


def streams():
    return json.loads(run(['pactl', '--format=json', 'list', 'sink-inputs']))


def owned_stream(stream):
    props = stream.get('properties', {})
    return props.get('node.name') == PLAYBACK or props.get('application.name') == 'Zorin11 Audio Effects'


def move(source_index, destination):
    """Move playback only, excluding our filter output (which would feed back)."""
    for stream in streams():
        if stream['sink'] == source_index and not owned_stream(stream):
            try:
                run(['pactl', 'move-sink-input', str(stream['index']), destination])
            except subprocess.CalledProcessError:
                pass  # A playback stream can disappear between enumeration and move.


class Engine:
    def __init__(self):
        self.process = None
        self.target = None
        self.current = None
        self.node = None

    def stop(self, destination=None):
        try:
            outputs = sinks()
            effect = next((s for s in outputs if s['name'] == SINK), None)
            target = next((s for s in outputs if s['name'] == (destination or self.target)), None)
            if target is None:
                target = next((s for s in outputs if s['name'] != SINK), None)
            if effect and target:
                if run(['pactl', 'get-default-sink']) == SINK:
                    run(['pactl', 'set-default-sink', target['name']])
                move(effect['index'], target['name'])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        finally:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
            self.target = self.current = self.node = None

    def start(self, ident, target):
        self.stop(target)
        RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = RUNTIME/'filter.conf'
        save(path, graph(ident, target))
        self.target = target
        self.process = subprocess.Popen(['pipewire', '-c', str(path)], stdout=subprocess.DEVNULL)
        deadline = time.monotonic()+4
        while time.monotonic() < deadline and self.process.poll() is None:
            data = json.loads(run(['pw-dump']))
            node = next((n for n in data if n.get('info', {}).get('props', {}).get('node.name') == SINK), None)
            if node and any(s['name'] == SINK for s in sinks()):
                self.node = node['id']
                self.current = ident
                return
            time.sleep(.08)
        self.stop()
        raise RuntimeError('PipeWire could not create the audio equalizer.')

    def update(self, ident):
        outputs = sinks()
        default = run(['pactl', 'get-default-sink'])
        if default == SINK:
            default = self.target
        target = next((s for s in outputs if s['name'] == default and s['name'] != SINK), None)
        if ident == 'off' or target is None:
            self.stop()
            return False
        if self.target != target['name'] or not self.process or self.process.poll() is not None:
            self.start(ident, target['name'])
            outputs = sinks()
        elif self.current != ident:
            params = [part for item in controls(ident).items() for part in item]
            run(['pw-cli', 'set-param', str(self.node), 'Props', json.dumps({'params': params})])
            self.current = ident
        effect = next((s for s in outputs if s['name'] == SINK), None)
        if effect is None:
            raise RuntimeError('The audio equalizer disconnected.')
        move(target['index'], SINK)
        return True


def unit(destination):
    path = str(Path(destination)/'audio_effects.py').replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"')
    return f'''[Unit]
Description=Windows 11 playback audio enhancements
After=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
ExecStart=/usr/bin/python3 "{path}"
Restart=on-failure
RestartSec=3
TimeoutStopSec=8
KillMode=mixed
UMask=0077

[Install]
WantedBy=default.target
'''


def main():
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(RUNTIME/'daemon.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        engine = Engine()
        try:
            while not stopped.is_set():
                ident = selection()
                try:
                    active = engine.update(ident)
                    error = '' if active or ident == 'off' else 'Connect an audio output to use this preset.'
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    engine.stop()
                    active, error = False, 'Audio processing is unavailable. Original playback has been restored.'
                save(STATUS, dict(preset=ident, active=active, error=error, updated=time.time()))
                stopped.wait(.5)
        finally:
            engine.stop()
            save(STATUS, dict(preset=selection(), active=False, error='', updated=time.time()))


if __name__ == '__main__':
    main()
