"""Session-only Snap Groups and the typed bridge used by native taskbar previews.

Only known group tokens can be activated over D-Bus. The preferred focus XID
must be a member; the panel cannot supply membership or placement rectangles.
Groups are never persisted or resurrected after their clients have closed.
"""
import uuid
from gi.repository import Gio, GLib, Gdk

BUS='local.zorin11.SnapGroups'
PATH='/local/zorin11/SnapGroups'
XML='''<node><interface name="local.zorin11.SnapGroups">
 <method name="List"><arg direction="out" type="a(sa(tiiii))"/></method>
 <method name="Activate"><arg direction="in" type="s"/><arg direction="in" type="t"/>
  <arg direction="out" type="b"/></method>
 <signal name="Changed"/>
</interface></node>'''


class Group(list):
    def __init__(self,placements):
        super().__init__((int(x),tuple(map(int,r))) for x,r in placements)
        self.token=uuid.uuid4().hex


class SnapGroups:
    def __init__(self,m):
        self.m=m;self.serial=0;self.stopped=False
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.info=Gio.DBusNodeInfo.new_for_xml(XML)
        self.registration=self.bus.register_object(PATH,self.info.interfaces[0],self.call,None,None)
        self.owner=Gio.bus_own_name_on_connection(self.bus,BUS,Gio.BusNameOwnerFlags.NONE,None,None)
        from window_watch import WindowWatch
        self.watch=WindowWatch(self.prune,self.watch_failed)

    def close(self):
        self.stopped=True;self.serial+=1
        self.watch.close()
        self.bus.unregister_object(self.registration);Gio.bus_unown_name(self.owner)
        self.m.groups=[]

    def watch_failed(self):
        # Without lifetime events, retaining group tokens could target reused
        # XIDs. Drop the registry; a later Snap Assist can start a fresh watcher.
        self.m.groups=[];self.changed()

    def changed(self):
        if not self.watch.track(x for g in self.m.groups for x,_ in g):self.m.groups=[]
        self.bus.emit_signal(None,PATH,BUS,'Changed',None)

    def prune(self,closed=None):
        # Both Wnck snapshots and window-closed signals can be transient while
        # Compiz remaps a client. Only X11 DestroyNotify invalidates its identity.
        changed=False;groups=[]
        for group in self.m.groups:
            kept=[(x,r) for x,r in group if x!=closed]
            changed|=len(kept)!=len(group)
            group[:]=kept
            if len(group)>1:groups.append(group)
            else:changed=True
        self.m.groups=groups
        if changed:self.changed()

    def forget(self,ids):
        groups=[g for g in self.m.groups if not ids.intersection(x for x,_ in g)]
        if len(groups)!=len(self.m.groups):self.m.groups=groups;self.changed()

    def remember(self,placements):
        if self.watch.process.poll() is not None:
            from window_watch import WindowWatch
            self.watch.close();self.watch=WindowWatch(self.prune,self.watch_failed)
        self.prune();self.forget({x for x,_ in placements})
        if len(placements)<2:return
        live={w.get_xid() for w in self.m.windows.windows()}
        group=Group([(x,r) for x,r in placements if x in live])
        if len(group)<2:return
        self.m.groups.insert(0,group);self.m.groups=self.m.groups[:8];self.changed()
        if any(g is group for g in self.m.groups):self.m.switcher.group_activated(group.token,restoring=False)

    def desktop(self,group):
        desktops=set()
        for xid,_ in group:
            w=self.m.windows.get(xid)
            if not w:return None
            index=self.m.desktops.desktop_for(w)
            if index is not None:desktops.add(index)
        # A window moved away individually no longer forms a restorable group.
        if len(desktops)>1:return None
        return next(iter(desktops),self.m.desktops.current())

    def listing(self):
        self.prune()
        if self.m.desktops.busy:return []
        return [(g.token,[(x,*r) for x,r in g]) for g in self.m.groups if self.desktop(g) is not None]

    def rectangles(self,group):
        left=min(r[0] for _,r in group);top=min(r[1] for _,r in group)
        width=max(r[0]+r[2] for _,r in group)-left
        height=max(r[1]+r[3] for _,r in group)-top
        display=Gdk.Display.get_default()
        area=display.get_monitor_at_point(left+width//2,top+height//2).get_workarea()
        if left>=area.x and top>=area.y and left+width<=area.x+area.width and top+height<=area.y+area.height:return list(group)
        # Fit the whole layout onto an available monitor after a display change.
        sx=max(1,area.width-12)/width;sy=max(1,area.height-12)/height
        return [(x,(area.x+6+round((r[0]-left)*sx),area.y+6+round((r[1]-top)*sy),
                    max(1,round(r[2]*sx)),max(1,round(r[3]*sy)))) for x,r in group]

    def activate(self,token,preferred=0):
        self.prune()
        group=next((g for g in self.m.groups if g.token==token),None)
        if not group or self.stopped or self.m.desktops.busy:return False
        desktop=self.desktop(group)
        if desktop is None:return False
        placements=self.rectangles(group)
        for xid,rect in placements:
            w=self.m.windows.get(xid)
            # Hidden clients (minimized or on another Xfwm desktop) may not
            # advertise RESIZE until mapped. place() checks it after returning.
            if not w or any(a>b for a,b in zip(self.m.windows.minimum(w),rect[2:])):return False
        self.serial+=1;serial=self.serial
        self.m.close(False)
        self.m.switcher.group_activated(group.token)
        generation=self.m.generation
        preferred=preferred if any(x==preferred for x,_ in group) else group[0][0]
        def valid():
            return (not self.stopped and serial==self.serial and generation==self.m.generation
                    and any(g is group for g in self.m.groups))
        def apply():
            if not valid() or self.desktop(group)!=desktop or self.m.desktops.current()!=desktop:return
            pending={x for x,_ in placements}
            def finished(xid):
                pending.discard(xid)
                if pending or not valid():return
                # A new Task View/menu or a user-selected app takes precedence
                # over this delayed focus request after WM resize completion.
                if self.m.window:return
                active=self.m.windows.screen.get_active_window()
                active_xid=active.get_xid() if active else 0
                del active
                if active_xid not in {x for x,_ in placements}:return
                w=self.m.windows.get(preferred)
                if w:self.m.windows.activate(w)
            for xid,rect in placements:
                try:self.m.windows.place(xid,rect,finished=lambda x=xid:finished(x))
                except ValueError:finished(xid)
        def restore():
            if not valid():return
            for xid,_ in placements:
                w=self.m.windows.get(xid)
                if w and w.is_minimized():w.unminimize(self.m.windows.timestamp())
            # Xfwm removes RESIZE from a minimized client's allowed actions.
            # Mapping and allowed actions can arrive in separate WM updates.
            # Wait for both, rather than silently skipping a remapping client.
            def ready():
                if not valid():return True
                for xid,_ in placements:
                    w=self.m.windows.get(xid)
                    if not w or w.is_minimized() or not self.m.windows.can_snap(w):return False
                return True
            if not ready():self.m.desktops.wait(ready,apply,lambda _:None)
            else:apply()
        if self.m.desktops.current()==desktop:restore()
        else:
            self.m.desktops.switch(desktop)
            self.m.desktops.wait(lambda:self.m.desktops.current()==desktop,restore,lambda _:None)
        return True

    def call(self,connection,sender,path,interface,method,parameters,invocation):
        try:
            if method=='List':invocation.return_value(GLib.Variant('(a(sa(tiiii)))',(self.listing(),)))
            elif method=='Activate':invocation.return_value(GLib.Variant('(b)',(self.activate(*parameters.unpack()),)))
        except (ValueError,RuntimeError) as error:
            invocation.return_dbus_error(BUS+'.Unavailable',str(error))
