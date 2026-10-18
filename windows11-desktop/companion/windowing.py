"""Window-manager requests for real X11 clients. No application data is changed."""
import gi
import re
import subprocess
gi.require_version('Wnck', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Wnck, Gdk, GdkX11, GLib


def layouts(focus=50):
    side = (100 - max(40, min(70, int(focus)))) / 200
    return [
        ('Halves', [(0,0,.5,1),(.5,0,.5,1)]),
        ('Wide left', [(0,0,2/3,1),(2/3,0,1/3,1)]),
        ('Wide right', [(0,0,1/3,1),(1/3,0,2/3,1)]),
        ('Three columns', [(0,0,1/3,1),(1/3,0,1/3,1),(2/3,0,1/3,1)]),
        ('Four corners', [(0,0,.5,.5),(.5,0,.5,.5),(0,.5,.5,.5),(.5,.5,.5,.5)]),
        ('Focus columns', [(0,0,side,1),(side,0,1-2*side,1),(1-side,0,side,1)]),
    ]


def zone_rect(area, zone, gap=6):
    x,y,w,h=area;zx,zy,zw,zh=zone
    left=x+round(w*zx);top=y+round(h*zy)
    right=x+round(w*(zx+zw));bottom=y+round(h*(zy+zh))
    return left+gap,top+gap,max(1,right-left-2*gap),max(1,bottom-top-2*gap)


class WindowRef:
    """Keep an XID across UI callbacks, never a borrowed libwnck window.

    libwnck 43 can crash when a Python reference outlives a closed X11 window.
    Resolve each operation synchronously so the wrapper is released before the
    main loop can process window destruction. Cards/menus may safely keep this
    ID-only object for as long as they need.
    """
    def __init__(self,owner,xid):self.owner=owner;self.xid=xid

    def get_xid(self):return self.xid

    def __getattr__(self,name):
        def invoke(*args):
            window=next((w for w in self.owner.screen.get_windows() if w.get_xid()==self.xid),None)
            if window is None:raise ValueError('That window has closed.')
            return getattr(window,name)(*args)
        return invoke


class Windows:
    def __init__(self):
        # A task switcher is an EWMH pager. Compiz constrains application-origin
        # move requests (including restore positions) to an extra edge margin.
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        self.screen=Wnck.Screen.get_default()
        self.screen.force_update()
        self.mru=[];self.saved={};self.pending={}
        self.handlers=[self.screen.connect('active-window-changed',self.changed),
                       self.screen.connect('window-closed',self.closed)]
        self.changed()

    def close(self):
        self.pending.clear()
        for handler in self.handlers:self.screen.disconnect(handler)
        self.handlers=[]

    def eligible(self,w):
        return w and not w.is_skip_tasklist() and w.get_window_type() in (Wnck.WindowType.NORMAL,Wnck.WindowType.DIALOG)

    def changed(self,*_):
        w=self.screen.get_active_window()
        if self.eligible(w):
            xid=w.get_xid();self.mru=[xid]+[i for i in self.mru if i!=xid]

    def closed(self,screen,w):
        xid=w.get_xid();self.saved.pop(xid,None)
        self.pending.pop(xid,None);self.mru=[i for i in self.mru if i!=xid]

    def windows(self):
        self.screen.force_update()
        windows=[w for w in reversed(self.screen.get_windows_stacked()) if self.eligible(w)]
        order=self.mru+[w.get_xid() for w in windows if w.get_xid() not in self.mru]
        return [WindowRef(self,w.get_xid()) for w in sorted(windows,key=lambda w:order.index(w.get_xid()))]

    def get(self,xid):
        return next((w for w in self.windows() if w.get_xid()==xid),None)

    def active(self):
        self.screen.force_update();w=self.screen.get_active_window()
        return WindowRef(self,w.get_xid()) if self.eligible(w) else next(iter(self.windows()),None)

    def timestamp(self):
        return GdkX11.x11_get_server_time(Gdk.get_default_root_window())

    def activate(self,w):
        if not self.get(w.get_xid()):return
        workspace=w.get_workspace();stamp=self.timestamp()
        if workspace:
            if workspace!=self.screen.get_active_workspace():workspace.activate(stamp)
            if workspace.is_virtual() and not w.is_in_viewport(workspace):
                x,y,_,_=w.get_geometry();sw=self.screen.get_width();sh=self.screen.get_height()
                self.screen.move_viewport(((x+workspace.get_viewport_x())//sw)*sw,((y+workspace.get_viewport_y())//sh)*sh)
        if w.is_minimized():w.unminimize(stamp)
        w.activate(stamp)

    def place(self,xid,rect,remember=True,finished=None):
        w=self.get(xid)
        if not w:raise ValueError('That window has closed.')
        if not self.can_snap(w):raise ValueError('This window cannot be resized.')
        minimum=self.minimum(w)
        if rect[2]<minimum[0] or rect[3]<minimum[1]:raise ValueError('This space is smaller than the app allows. Choose a larger zone.')
        if remember and xid not in self.saved:self.saved[xid]=(tuple(w.get_geometry()),w.is_maximized())
        if w.is_maximized_horizontally() or w.is_maximized_vertically():w.unmaximize()
        if w.is_fullscreen():w.set_fullscreen(False)
        self.activate(w)
        token=object();self.pending[xid]=token
        # Maximize state and frame extents are asynchronous WM properties.
        # Wait for the restored state before sending the outer-frame geometry.
        attempts=[0]
        def apply():
            if self.pending.get(xid) is not token:return False
            current=self.get(xid)
            if not current:return False
            attempts[0]+=1
            if current.is_maximized() and attempts[0]<15:return True
            x,y,width,height=map(int,rect)
            current.set_geometry(Wnck.WindowGravity.STATIC,
                Wnck.WindowMoveResizeMask.X|Wnck.WindowMoveResizeMask.Y|Wnck.WindowMoveResizeMask.WIDTH|Wnck.WindowMoveResizeMask.HEIGHT,
                x,y,width,height)
            self.pending.pop(xid,None)
            if finished:GLib.timeout_add(220,lambda:(finished(),False)[1])
            return False
        GLib.timeout_add(40,apply)

    def can_snap(self,w):
        return bool(w.get_actions() & Wnck.WindowActions.RESIZE) or w.is_maximized()

    def minimum(self,w):
        try:
            hints=subprocess.check_output(['xprop','-id',str(w.get_xid()),'WM_NORMAL_HINTS'],text=True,stderr=subprocess.DEVNULL,timeout=1)
            match=re.search(r'minimum size: (\d+) by (\d+)',hints)
            if match:
                outer=w.get_geometry();inner=w.get_client_window_geometry()
                return int(match[1])+outer[2]-inner[2],int(match[2])+outer[3]-inner[3]
        except (OSError,subprocess.SubprocessError):pass
        return 1,1

    def restore(self,xid):
        saved=self.saved.pop(xid,None);w=self.get(xid)
        if saved and w:
            rect,maximized=saved
            self.place(xid,rect,remember=False,finished=lambda:w.maximize() if maximized and self.get(xid) else None)

    def desktops(self):
        current=self.screen.get_active_workspace()
        return [(w.get_number(),w.get_name(),w==current) for w in self.screen.get_workspaces()]
