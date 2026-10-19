"""Watch real X11 DestroyNotify events in an isolated, disposable process.

Wnck may report a window closed during a Compiz remap. X11 destruction events
identify the resource lifetime even if a client later reuses its numeric XID.
No pixels, titles, keyboard events or application contents are observed here.
"""
import os
from pathlib import Path
import subprocess
import sys


class WindowWatch:
    def __init__(self,closed,failed):
        from gi.repository import GLib
        self.closed=closed;self.failed=failed;self.ids=set();self.buffer=b''
        self.process=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).resolve()),'--watch'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        os.set_blocking(self.process.stdout.fileno(),False)
        self.source=GLib.io_add_watch(self.process.stdout.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.read)

    def read(self,fd,condition):
        try:data=os.read(fd,65536)
        except BlockingIOError:return True
        except OSError:data=b''
        if not data:
            self.source=0;self.failed();return False
        self.buffer+=data
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:xid=int(line)
            except ValueError:continue
            self.ids.discard(xid);self.closed(xid)
        return True

    def track(self,ids):
        ids=set(ids)
        commands=[f'+ {x}\n' for x in ids-self.ids]+[f'- {x}\n' for x in self.ids-ids]
        try:
            if self.process.poll() is not None:return False
            if commands:self.process.stdin.write(''.join(commands).encode())
            self.ids=ids;return True
        except (BrokenPipeError,OSError):return False

    def close(self):
        from gi.repository import GLib
        if self.source:GLib.source_remove(self.source);self.source=0
        self.process.stdin.close()
        try:self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process.stdout.close()


def watch():
    import ctypes as C
    import select
    x=C.CDLL('libX11.so.6')
    for name,restype,args in [
        ('XOpenDisplay',C.c_void_p,[C.c_char_p]),
        ('XConnectionNumber',C.c_int,[C.c_void_p]),
        ('XSelectInput',C.c_int,[C.c_void_p,C.c_ulong,C.c_long]),
        ('XSync',C.c_int,[C.c_void_p,C.c_int]),
        ('XPending',C.c_int,[C.c_void_p]),
        ('XNextEvent',C.c_int,[C.c_void_p,C.c_void_p]),
        ('XCloseDisplay',C.c_int,[C.c_void_p]),
    ]:
        fn=getattr(x,name);fn.restype=restype;fn.argtypes=args
    display=x.XOpenDisplay(None)
    if not display:return
    error=[False]
    @C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)
    def handler(*_):error[0]=True;return 0
    x.XSetErrorHandler.argtypes=[C.c_void_p];x.XSetErrorHandler(handler)
    class Destroy(C.Structure):
        _fields_=[('type',C.c_int),('serial',C.c_ulong),('send_event',C.c_int),
                  ('display',C.c_void_p),('event',C.c_ulong),('window',C.c_ulong)]
    event=(C.c_long*24)();fd=x.XConnectionNumber(display);buffer=b'';ids=set()
    def gone(xid):
        ids.discard(xid);print(xid,flush=True)
    try:
        while True:
            while x.XPending(display):
                x.XNextEvent(display,C.byref(event));destroy=C.cast(C.byref(event),C.POINTER(Destroy)).contents
                if destroy.type==17 and not destroy.send_event:gone(destroy.window)
            ready,_,_=select.select([0,fd],[],[])
            if 0 not in ready:continue
            data=os.read(0,65536)
            if not data:return
            buffer+=data
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1)
                command,value=line.split();xid=int(value);add=command==b'+'
                if add and len(ids)>=1024:gone(xid);continue
                error[0]=False;x.XSelectInput(display,xid,(1<<17) if add else 0);x.XSync(display,0)
                if add:
                    if error[0]:gone(xid)
                    else:ids.add(xid)
                else:ids.discard(xid)
    finally:x.XCloseDisplay(display)


if __name__=='__main__':watch()
