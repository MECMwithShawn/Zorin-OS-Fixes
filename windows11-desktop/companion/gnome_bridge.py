"""Allowlisted local GNOME Shell bridge, including native Wayland windows."""
import json
import os
import time
from gi.repository import Gio, GLib

def active():
    return 'GNOME' in os.environ.get('XDG_CURRENT_DESKTOP','').upper().split(':')

def call(op, **values):
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    result=bus.call_sync('local.zorin11.Gnome','/local/zorin11/Gnome','local.zorin11.Gnome','Call',
        GLib.Variant('(s)',(json.dumps(dict(op=op,**values)),)),GLib.VariantType.new('(s)'),
        Gio.DBusCallFlags.NONE,3000,None)
    return json.loads(result.unpack()[0])

def snapshot_async(callback):
    """One cancellable background read; callbacks run on the GTK main loop."""
    cancel=Gio.Cancellable()
    def finished(bus,result):
        try:
            data=json.loads(bus.call_finish(result).unpack()[0])
        except (GLib.Error,ValueError,TypeError) as error:
            callback(None,error)
        else:callback(data,None)
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    bus.call('local.zorin11.Gnome','/local/zorin11/Gnome','local.zorin11.Gnome','Call',
        GLib.Variant('(s)',(json.dumps({'op':'snapshot'}),)),GLib.VariantType.new('(s)'),
        Gio.DBusCallFlags.NONE,3000,cancel,finished)
    return cancel


class Workspace:
    def __init__(self,screen,index):self.screen=screen;self.index=index
    def __eq__(self,other):return isinstance(other,Workspace) and self.index==other.index
    def get_number(self):return self.index
    def get_name(self):
        names=self.screen.data.get('names',[])
        return names[self.index] if self.index<len(names) else f'Desktop {self.index+1}'
    def activate(self,*_):call('workspace',index=self.index);self.screen.force_update()
    def change_name(self,name):call('rename',index=self.index,name=name);self.screen.force_update()
    def is_virtual(self):return False
    def get_viewport_x(self):return 0
    def get_viewport_y(self):return 0
    def get_width(self):return self.screen.get_width()
    def get_height(self):return self.screen.get_height()

class Window:
    def __init__(self,screen,ident,row=None):self.screen=screen;self.ident=ident;self.last=row or {}
    def row(self):
        self.last=next((r for r in self.screen.data['windows'] if r['id']==self.ident),self.last)
        return self.last
    def get_xid(self):return self.ident
    def get_name(self):return self.row()['title']
    def get_class_group_name(self):return self.row()['cls']
    def get_class_instance_name(self):return self.row()['app'].removesuffix('.desktop') or self.get_class_group_name()
    def get_pid(self):return self.row()['pid']
    def get_application_id(self):return self.row().get('app','')
    def get_geometry(self):return tuple(self.row()['rect'])
    def get_client_window_geometry(self):return self.get_geometry()
    def is_minimized(self):return self.row()['minimized']
    def is_maximized(self):return self.row()['maximized']
    is_maximized_horizontally=is_maximized
    is_maximized_vertically=is_maximized
    def is_fullscreen(self):return self.row()['fullscreen']
    def is_skip_tasklist(self):return self.row()['skip'] or min(self.row()['rect'][2:]) <= 0 or self.get_name() in ('Zorin 11 Start','Quick settings','Notifications and calendar','Desktop group','Task view','Snap layouts','Snap assist','Window switcher','Switch windows')
    def get_window_type(self):
        from gi.repository import Wnck
        return {0:Wnck.WindowType.NORMAL,1:Wnck.WindowType.DESKTOP,2:Wnck.WindowType.DOCK,3:Wnck.WindowType.DIALOG,4:Wnck.WindowType.DIALOG}.get(self.row()['type'],Wnck.WindowType.UTILITY)
    def get_workspace(self):return Workspace(self.screen,self.row()['workspace'])
    def is_pinned(self):return self.row()['sticky']
    is_sticky=is_pinned
    def get_actions(self):
        from gi.repository import Wnck
        return Wnck.WindowActions.RESIZE if self.row()['resizable'] else Wnck.WindowActions(0)
    def action(self,action,**kw):call('window',id=self.ident,action=action,**kw);self.screen.force_update()
    def activate(self,*_):self.action('activate')
    def close(self,*_):self.action('close')
    def minimize(self):self.action('minimize')
    def unminimize(self,*_):self.action('unminimize')
    def maximize(self):self.action('maximize')
    def unmaximize(self):self.action('unmaximize')
    def set_fullscreen(self,value):self.action('fullscreen',value=value)
    def move_to_workspace(self,workspace):self.action('workspace',index=workspace.index)
    def set_geometry(self,gravity,mask,x,y,w,h):self.action('move',rect=[x,y,w,h])
    def get_icon(self):
        from gi.repository import Gtk
        try:app=Gio.DesktopAppInfo.new(self.row()['app']) if self.row()['app'] else None
        except TypeError:app=None
        icon=app.get_icon() if app else Gio.ThemedIcon.new('application-x-executable')
        info=Gtk.IconTheme.get_default().lookup_by_gicon(icon,64,0)
        return info.load_icon() if info else None
    get_mini_icon=get_icon

class Screen:
    def __init__(self):
        self.handlers={};self.serial=0;self.data={};self.revision=0;self.closed=False;self.pending=None;self.force_update()
        self.timer=GLib.timeout_add(350,self.poll)
    def force_update(self):
        data=call('snapshot');self.revision+=1;self.data=data
    def connect(self,name,callback):
        self.serial+=1;self.handlers[self.serial]=(name,callback);return self.serial
    def disconnect(self,ident):self.handlers.pop(ident,None)
    def emit(self,name,*args):
        for event,callback in list(self.handlers.values()):
            if event==name:callback(self,*args)
    def poll(self):
        if self.closed:return False
        if self.pending:return True
        revision=self.revision
        def received(data,error):
            self.pending=None
            if self.closed or error or revision!=self.revision:return
            old=self.data;self.data=data;self.revision+=1
            live={r['id'] for r in self.data['windows']}
            for row in old['windows']:
                if row['id'] not in live:self.emit('window-closed',Window(self,row['id'],row))
            focus=lambda d:next((r['id'] for r in d['windows'] if r['focused']),None)
            if focus(old)!=focus(self.data):self.emit('active-window-changed',None)
            if old['current']!=self.data['current']:self.emit('active-workspace-changed',None)
        try:self.pending=snapshot_async(received)
        except GLib.Error:pass
        return True
    def get_windows(self):return [Window(self,r['id'],r) for r in self.data['windows']]
    get_windows_stacked=get_windows
    def get_active_window(self):return next((w for w in self.get_windows() if w.row()['focused']),None)
    def get_active_workspace(self):return Workspace(self,self.data['current'])
    def get_workspaces(self):return [Workspace(self,i) for i in range(self.data['count'])]
    def get_workspace(self,i):return Workspace(self,i) if 0<=i<self.data['count'] else None
    def change_workspace_count(self,n):call('count',count=n);self.force_update()
    def get_width(self):return self.data['width']
    def get_height(self):return self.data['height']
    def get_window_manager_name(self):return 'GNOME Mutter'
    def close(self):
        if self.closed:return
        self.closed=True;GLib.source_remove(self.timer);self.handlers.clear()
        if self.pending:self.pending.cancel();self.pending=None

class LifetimeWatch:
    def __init__(self,closed,failed):
        self.closed=closed;self.ids=set();self.process=self;self.stopped=False;self.pending=None
        self.timer=GLib.timeout_add(500,self.tick)
    def poll(self):return None
    def track(self,ids):self.ids=set(ids);return True
    def tick(self):
        if self.stopped:return False
        if self.pending:return True
        tracked=set(self.ids)
        def received(data,error):
            self.pending=None
            if self.stopped or error:return
            live={w['id'] for w in data['windows']}
            # A newly tracked window may not have existed when the request began.
            missing=(tracked & self.ids)-live
            self.ids-=missing
            for ident in missing:self.closed(ident)
        try:self.pending=snapshot_async(received)
        except GLib.Error:pass
        return True
    def close(self):
        if self.stopped:return
        self.stopped=True;GLib.source_remove(self.timer)
        if self.pending:self.pending.cancel();self.pending=None
