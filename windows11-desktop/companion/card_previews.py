"""Bounded live window previews for Task View and Snap Assist.

Only mapped, visible cards are sampled. One capture can be queued/running at a
time, including across panel rebuilds. Results stay in memory and are rejected
if their panel, window or visibility changed while capture was in flight.
"""
from pathlib import Path
import struct
import subprocess
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf, GLib

BASE=Path(__file__).resolve().parent


def decode(data):
    if not data or len(data)>1048576 or len(data)<24:return None
    if data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':return None
    width,height=struct.unpack('!II',data[16:24])
    if not 1<=width<=480 or not 1<=height<=280:return None
    loader=GdkPixbuf.PixbufLoader.new_with_type('png')
    try:
        loader.write(data);loader.close()
        return loader.get_pixbuf()
    except GLib.Error:return None


class CardPreviews:
    def __init__(self,m):
        self.m=m;self.timer=0;self.revision=0;self.pending=False;self.cursor=0
        self.scroll=None;self.flow=None;self.view=None

    def watch(self,scroll,flow,view=None):
        self.stop()
        self.scroll=scroll;self.flow=flow;self.view=view
        revision=self.revision
        flow.connect('destroy',lambda *_:self.stop() if revision==self.revision else None)
        # Let the chooser map first, then share a global capture budget between
        # visible cards instead of queuing every open window at panel creation.
        self.timer=GLib.timeout_add(300,self.tick)

    def stop(self):
        self.revision+=1;self.cursor=0
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        self.scroll=None;self.flow=None;self.view=None
        # Keep pending until the existing job completes. Reopening a panel
        # cannot create a second capture or a queue of obsolete subprocesses.

    def targets(self):
        if self.flow is None or not self.flow.get_mapped():return []
        adjustment=self.scroll.get_vadjustment()
        low=adjustment.get_value();high=low+adjustment.get_page_size()
        visible=[]
        for child in self.flow.get_children():
            if not child.get_child_visible() or not child.get_mapped():continue
            bounds=child.get_allocation()
            if bounds.y+bounds.height<=low or bounds.y>=high:continue
            visible.append(child)
        if not visible:return []
        try:
            live={w.get_xid() for w in self.m.windows.windows() if not w.is_minimized()}
            return [child for child in visible if child.xid in live]
        except (GLib.Error,ValueError):return []

    def tick(self):
        if self.flow is None:return False
        if self.pending:return True
        targets=self.targets()
        if not targets:return True
        self.cursor%=len(targets);xid=targets[self.cursor].xid;self.cursor+=1
        self.pending=True;revision=self.revision
        def capture():
            if revision!=self.revision:return b''
            return subprocess.run(['/usr/bin/python3',str(BASE/'window_preview.py'),str(xid)],
                                  capture_output=True,timeout=3,check=False).stdout
        def done(data):
            self.pending=False
            if revision!=self.revision:return
            child=next((c for c in self.targets() if c.xid==xid),None)
            if child is None:return
            pix=decode(data)
            if pix is None:return
            self.m.preview_cache.pop(xid,None);self.m.preview_cache[xid]=pix
            while len(self.m.preview_cache)>36:self.m.preview_cache.pop(next(iter(self.m.preview_cache)))
            ratio=min(230/pix.get_width(),136/pix.get_height())
            child.preview_image.set_from_pixbuf(pix.scale_simple(
                max(1,int(pix.get_width()*ratio)),max(1,int(pix.get_height()*ratio)),GdkPixbuf.InterpType.BILINEAR))
            if self.view:self.view.preview_ready(xid,pix)
        try:self.m.hub.background(capture,done,lambda _:done(b''))
        except RuntimeError:self.pending=False
        return True
