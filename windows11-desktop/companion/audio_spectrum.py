"""Live playback spectrum. Explicit output monitors only; no microphone or storage."""
import array
import cmath
import json
import math
import os
import select
import signal
import subprocess
import sys
import threading
import time

SIZE = 2048
RATE = 48000
BANDS = 16
WINDOW = [0.5-0.5*math.cos(2*math.pi*i/(SIZE-1)) for i in range(SIZE)]
EDGES = [40*(400**(i/BANDS)) for i in range(BANDS+1)]
TWIDDLES = {width:[cmath.exp(-2j*math.pi*k/width) for k in range(width//2)]
            for width in (2**i for i in range(1,12))}
REVERSED = [int(f'{i:011b}'[::-1],2) for i in range(SIZE)]


def levels(pcm):
    samples = array.array('f')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':samples.byteswap()
    if len(samples) != SIZE:return [0.]*BANDS
    data = [complex(samples[i]*WINDOW[i] if math.isfinite(samples[i]) else 0) for i in REVERSED]
    if not any(abs(v)>1e-6 for v in data):return [0.]*BANDS
    for width, twiddles in TWIDDLES.items():
        half=width//2
        for start in range(0,SIZE,width):
            for k,w in enumerate(twiddles):
                a,b=data[start+k],data[start+k+half]*w
                data[start+k],data[start+k+half]=a+b,a-b
    result=[]
    for low,high in zip(EDGES,EDGES[1:]):
        first=max(1,round(low*SIZE/RATE))
        last=max(first+1,round(high*SIZE/RATE))
        peak=max(abs(v) for v in data[first:last])/(SIZE/4)
        result.append(round(max(0.,min(1.,(20*math.log10(max(peak,1e-8))+60)/60)),4))
    return result


def command(args):
    return subprocess.check_output(args,text=True,stderr=subprocess.DEVNULL,timeout=2).strip()


def output_monitor():
    default=command(['pactl','get-default-sink'])
    sinks=json.loads(command(['pactl','--format=json','list','sinks']))
    sink=next((s for s in sinks if s['name']==default),None)
    if not sink:return None
    # This name comes only from the chosen sink's monitor field. No default source.
    source=sink.get('monitor_source_name') or sink.get('monitor_source')
    return source if isinstance(source,str) and source else None


class Monitor:
    def __init__(self):
        self.enabled=False
        self.stopped=threading.Event()
        self.data=dict(levels=[0.]*BANDS,available=False)
        self.worker=threading.Thread(target=self._work,daemon=True)
        self.worker.start()

    def enable(self,value):
        self.enabled=bool(value)

    def close(self):
        self.stopped.set()
        self.worker.join(timeout=3)

    def _work(self):
        child=None;source=None;checked=0.;last=0.;buffer=b''
        def stop_capture():
            nonlocal child,source,buffer
            if child:
                child.terminate()
                try:child.wait(timeout=.5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                child.stdout.close()
            child=None;source=None;buffer=b''
            self.data=dict(levels=[0.]*BANDS,available=False)
        try:
            while not self.stopped.wait(.08):
                if not self.enabled:
                    if child:stop_capture()
                    checked=0.
                    continue
                now=time.monotonic()
                if now-checked>1.5:
                    checked=now
                    try:target=output_monitor()
                    except (OSError,ValueError,subprocess.SubprocessError):target=None
                    if target!=source or (child and child.poll() is not None):
                        stop_capture()
                    if target and child is None:
                        try:
                            child=subprocess.Popen(['parec','--raw','--format=float32le',
                                f'--rate={RATE}','--channels=1','--latency-msec=40',
                                '--client-name=Zorin11 playback spectrum','--device='+target],
                                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                            os.set_blocking(child.stdout.fileno(),False)
                            source=target;last=now
                        except OSError:stop_capture()
                if child:
                    try:
                        # Bound both queued input and work per refresh; prefer newest audio.
                        for _ in range(8):
                            if not select.select([child.stdout],[],[],0)[0]:break
                            chunk=os.read(child.stdout.fileno(),65536)
                            if not chunk:break
                            buffer=(buffer+chunk)[-SIZE*8:]
                        if len(buffer)>=SIZE*4:
                            usable=len(buffer)//4*4
                            current=levels(buffer[usable-SIZE*4:usable])
                            buffer=buffer[usable:]
                            old=self.data['levels']
                            self.data=dict(levels=[max(n,o*.72) for n,o in zip(current,old)],available=True)
                            last=now
                        elif now-last>.35:
                            self.data=dict(levels=[0.]*BANDS,available=child.poll() is None)
                    except (OSError,ValueError):stop_capture()
        finally:stop_capture()


if __name__=='__main__':
    if sys.argv[1:]!=['--stream']:raise SystemExit('Usage: audio_spectrum.py --stream')
    def terminate(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,terminate)
    monitor=Monitor();monitor.enable(True)
    try:
        while True:
            print(json.dumps(monitor.data),flush=True)
            time.sleep(.1)
    except (BrokenPipeError,KeyboardInterrupt):pass
    finally:monitor.close()
