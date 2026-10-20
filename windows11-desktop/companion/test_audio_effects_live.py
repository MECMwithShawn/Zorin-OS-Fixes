"""Measure actual EQ output on silent sinks in a private PipeWire session."""
import array
import cmath
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

if __name__ != '__main__':
    import unittest
    raise unittest.SkipTest('Run this private audio integration test directly.')
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin11-audio-test-') as directory:
        root = Path(directory)
        (root/'runtime').mkdir(mode=0o700)
        wp = root/'wireplumber'
        shutil.copytree('/usr/share/wireplumber', wp)
        # Keep the normal session policy, but never open real microphones/speakers.
        for path in wp.rglob('*.lua'):
            text = path.read_text()
            for monitor in ('alsa_monitor', 'bluez_monitor', 'v4l2_monitor', 'libcamera_monitor'):
                text = text.replace('\n'+monitor+'.enable()', '\n-- private test: '+monitor)
            path.write_text(text)
        env = dict(os.environ, GIO_USE_VFS='local', XDG_RUNTIME_DIR=str(root/'runtime'), XDG_CONFIG_HOME=str(root/'config'),
                   XDG_STATE_HOME=str(root/'state'), XDG_CACHE_HOME=str(root/'cache'),
                   XDG_DATA_HOME=str(root/'data'), PIPEWIRE_REMOTE='pipewire-0',
                   PULSE_SERVER='unix:'+str(root/'runtime/pulse/native'), WIREPLUMBER_CONFIG_DIR=str(wp))
        raise SystemExit(subprocess.run(['dbus-run-session', '--', '/usr/bin/python3', __file__, '--private'],
                                        env=env, timeout=110).returncode)

import audio_effects as eq


def wait(condition, timeout=6):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        time.sleep(.08)
    raise AssertionError('Private audio condition timed out')


def expected(gains, frequency):
    z = cmath.exp(-2j*math.pi*frequency/48000)
    response = 10**(eq.headroom(gains)/20)
    for center, gain in zip(eq.FREQUENCIES, gains):
        a = 10**(gain/40)
        w = 2*math.pi*center/48000
        alpha = math.sin(w)/2
        b0, b1, b2 = 1+alpha*a, -2*math.cos(w), 1-alpha*a
        a0, a1, a2 = 1+alpha/a, -2*math.cos(w), 1-alpha/a
        response *= (b0+b1*z+b2*z*z)/(a0+a1*z+a2*z*z)
    return 20*math.log10(abs(response))


processes = []
engine = eq.Engine()
try:
    for command in ('pipewire', 'pipewire-pulse', 'wireplumber'):
        processes.append(subprocess.Popen([command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        if command == 'pipewire':
            wait(lambda:(Path(os.environ['XDG_RUNTIME_DIR'])/'pipewire-0').exists())
    wait(lambda:eq.run(['pactl', 'info']))
    for name in ('test-speakers', 'test-headphones'):
        eq.run(['pactl', 'load-module', 'module-null-sink', 'sink_name='+name,
                'sink_properties=device.description='+name])
    wait(lambda:any(s['name']=='test-speakers' for s in eq.sinks())
         and any(s['name']=='test-headphones' for s in eq.sinks()))
    wait(lambda:eq.run(['pactl', 'set-default-sink', 'test-speakers'])=='')
    assert all(s['name'] in ('test-speakers', 'test-headphones', 'auto_null') for s in eq.sinks()), 'Real device in private test'
    root = Path(os.environ['XDG_RUNTIME_DIR'])
    tone = root/'tones.raw'
    samples = array.array('f')
    for frame in range(48000*3):
        value = sum(.025*math.sin(2*math.pi*f*frame/48000) for f in eq.FREQUENCIES)
        samples.extend((value, value))
    tone.write_bytes(samples.tobytes())

    def measure(preview_gains=None):
        with tempfile.TemporaryFile() as captured, tone.open('rb') as source:
            record = subprocess.Popen(['parec', '--device=test-speakers.monitor', '--format=float32le',
                                       '--rate=48000', '--channels=2', '--latency-msec=20'], stdout=captured)
            time.sleep(.15)
            play = subprocess.Popen(['pacat', '--playback', '--device=test-speakers', '--format=float32le',
                                     '--rate=48000', '--channels=2', '--latency-msec=20'], stdin=source)
            try:
                wait(lambda:any(str(s.get('properties', {}).get('application.process.id')) == str(play.pid) for s in eq.streams()))
                if engine.current:
                    engine.update(engine.current, preview_gains)
                play.wait(timeout=8)
                time.sleep(.1)
            finally:
                play.terminate()
                play.wait()
                record.terminate()
                record.wait()
            captured.seek(0)
            floats = array.array('f')
            content = captured.read()
            floats.frombytes(content[:len(content)//8*8])
            left = floats[::2]
            assert len(left)>72000, ('Too few audio samples', len(left))
            # Exactly one second from the steady middle of playback, integral periods.
            left = left[len(left)//2-24000:len(left)//2+24000]
            return [abs(sum(value*cmath.exp(-2j*math.pi*f*i/48000) for i,value in enumerate(left)))*2/len(left)
                    for f in eq.FREQUENCIES]

    baseline = measure()
    assert min(baseline)>.015, baseline
    node = None
    for choice in eq.PRESETS[1:]:
        assert engine.update(choice['id'])
        if node is None:
            node = engine.node
        else:
            assert engine.node == node, 'Preset switch restarted the audio graph'
        measured = measure()
        deviations = []
        for frequency, original, actual in zip(eq.FREQUENCIES, baseline, measured):
            observed = 20*math.log10(actual/original)
            deviations.append(abs(observed-expected(choice['gains'], frequency)))
        assert max(deviations)<.8, (choice['id'], deviations, measured)
        print('PASS real audio response:',choice['name'], 'maximum error',round(max(deviations),3),'dB',flush=True)

    for gains in ([4, 2, -3, 1, 0, -2], [-2, 0, 3, -1, 2, 1]):
        eq.save(eq.STATE, dict(preset='custom', custom_gains=gains))
        assert engine.update('custom')
        assert engine.node == node
        measured = measure()
        errors = [abs(20*math.log10(actual/original)-expected(gains, frequency))
                  for frequency, original, actual in zip(eq.FREQUENCIES, baseline, measured)]
        assert max(errors)<.8, errors
    engine.stop()
    assert engine.update(eq.selection())
    assert engine.current_controls == eq.controls('custom')
    print('PASS custom curve changes in live DSP and restores after engine restart', flush=True)

    saved = eq.STATE.read_bytes()
    preview = [1, -2, 3, 0, -1, 2]
    eq.write_preview(preview, 'test-editor')
    assert engine.update('custom', eq.preview_gains())
    measured = measure(preview)
    errors = [abs(20*math.log10(actual/original)-expected(preview, frequency))
              for frequency, original, actual in zip(eq.FREQUENCIES, baseline, measured)]
    assert max(errors)<.8, errors
    assert eq.STATE.read_bytes() == saved
    eq.clear_preview('test-editor')
    assert engine.update(eq.selection())
    assert engine.current_controls == eq.controls(eq.selection())
    print('PASS audible preview response, unchanged saved default, and restoration', flush=True)

    # Existing/new streams follow physical output changes and return on Off.
    source = open('/dev/zero', 'rb')
    player = subprocess.Popen(['pacat', '--playback', '--device=test-speakers', '--latency-msec=20'], stdin=source)
    processes.append(player)
    wait(lambda:any(not eq.owned_stream(s) for s in eq.streams()))
    engine.update('bass')
    effect = next(s for s in eq.sinks() if s['name']==eq.SINK)
    assert all(s['sink']==effect['index'] for s in eq.streams() if not eq.owned_stream(s))
    eq.run(['pactl','set-sink-volume','test-headphones','37%'])
    volume = next(s['volume'] for s in eq.sinks() if s['name']=='test-headphones')
    eq.run(['pactl','set-default-sink','test-headphones'])
    assert engine.update('voice')
    wait(lambda:any(eq.owned_stream(s) and s['sink']==next(o['index'] for o in eq.sinks() if o['name']=='test-headphones') for s in eq.streams()))
    assert eq.run(['pactl','get-default-sink'])=='test-headphones'
    engine.stop()
    wait(lambda:all(s['name']!=eq.SINK for s in eq.sinks()))
    target = next(s for s in eq.sinks() if s['name']=='test-headphones')
    assert target['volume']==volume
    assert all(s['sink']==target['index'] for s in eq.streams())
    player.terminate()
    player.wait()
    source.close()
    print('PASS output switching, existing/new streams, preserved hardware volume, and Off restoration',flush=True)
finally:
    engine.stop()
    for process in reversed(processes):
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
