"""Per-desktop pictures routed through Xfdesktop, including Compiz viewports.

Native Wnck objects stay on the GTK thread. Files/Xfconf writes run serially
under wallpaper.LOCK. Stable desktop identities keep pictures attached when
the physical workspace/viewport order changes.
"""
import re
import copy
from pathlib import Path
import dbus
import gi
gi.require_version('Gdk','3.0')
from gi.repository import GLib, Gdk
from settings_backend import properties, set_property

CONTEXT=None


def picture_path(state,uid):
    import wallpaper
    ident=state.get('desktopPictures',{}).get(uid)
    if ident and re.fullmatch('[a-f0-9]{24}',ident):
        path=wallpaper.ROOT/(ident+'.image')
        if path.is_file():return path
    return None


def encode(value):
    if value is None:return None
    if isinstance(value,(bool,dbus.Boolean)):return {'type':'bool','value':bool(value)}
    if isinstance(value,(int,dbus.Int32,dbus.UInt32)):return {'type':'uint' if isinstance(value,dbus.UInt32) else 'int','value':int(value)}
    return {'type':'string','value':str(value)}


def decode(value):
    return {'bool':dbus.Boolean,'int':dbus.Int32,'uint':dbus.UInt32,'string':dbus.String}[value['type']](value['value'])


def restore_records(state,props):
    """Compare-safe rollback, including a partially written transition."""
    bus=dbus.SessionBus(private=True);restored=set()
    try:
        xf=dbus.Interface(bus.get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
        for key,record in state.get('desktopWrites',{}).items():
            actual=encode(props.get(key))
            if actual not in (record['after'],record.get('previous',record['after'])):continue
            if record['before'] is None:xf.ResetProperty('xfce4-desktop',key,False)
            else:xf.SetProperty('xfce4-desktop',key,decode(record['before']))
            restored.add(key)
    finally:bus.close()
    state.pop('desktopWrites',None)
    return restored


def sync(shared=None):
    """Apply the newest context, never the context at worker submission time."""
    import wallpaper
    with wallpaper.LOCK:
        context=CONTEXT
        if not context:return
        state=wallpaper.load();before=copy.deepcopy(state);pictures=state.get('desktopPictures',{})
        valid=set(context['all_ids'])
        pictures={uid:ident for uid,ident in pictures.items() if uid in valid}
        state['desktopPictures']=pictures
        if not pictures and not state.get('desktopWrites'):
            if before.get('desktopPictures')!=pictures and 'desktopPictures' in before:wallpaper.save(state)
            return
        props=properties('xfce4-desktop')
        keys={str(k) for k in props if str(k).endswith(('/last-image','/image-path'))}
        for monitor in context['monitors']:
            keys.add(f'/backdrop/screen0/monitor{monitor}/workspace0/last-image')
        defaults=state.setdefault('desktopShared',{})
        base=shared or state.get('appliedPath')
        if base and not Path(base).is_file():base=None
        for key in keys:
            if shared:defaults[key]=str(shared)
            elif key not in defaults:defaults[key]=str(base or props.get(key,''))
        selected=picture_path(state,context['uid'])
        changes={key:str(selected or base or defaults.get(key,'')) for key in keys}
        changes={key:value for key,value in changes.items() if value and Path(value).is_file()}
        if pictures:
            # Compiz viewports are one EWMH workspace. A controlled workspace-0
            # backdrop gives both WMs the same behavior, and keeps the locker
            # following the active desktop. The original mode is recoverable.
            changes['/backdrop/single-workspace-mode']=True
            changes['/backdrop/single-workspace-number']=0
        else:
            # Last override removed: keep the latest shared wallpaper, and
            # restore the user's native mode without undoing Spotlight updates.
            for key,record in state.get('desktopWrites',{}).items():
                if key.startswith('/backdrop/single-workspace-'):
                    actual=encode(props.get(key))
                    if actual==record['after']:changes[key]=decode(record['before']) if record['before'] else None
        records=state.setdefault('desktopWrites',{})
        pending=[]
        for key,value in changes.items():
            actual=encode(props.get(key));desired=encode(value)
            if actual==desired:continue
            record=records.setdefault(key,{'before':actual,'after':actual})
            record['previous']=record['after'];record['after']=desired;pending.append((key,value))
        if pending or state!=before:wallpaper.save(state)  # Journal before writes.
        for key,value in pending:
            if value is None:
                bus=dbus.SessionBus(private=True)
                try:dbus.Interface(bus.get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf').ResetProperty('xfce4-desktop',key,False)
                finally:bus.close()
            else:set_property('xfce4-desktop',key,decode(encode(value)))
        for record in records.values():record.pop('previous',None)
        # Leave recovery records in place until full wallpaper restore, even
        # after all desktops return to the shared picture.
        state['desktopError']=''
        if pending or state!=before:wallpaper.save(state)


def assign(uid,ident):
    import wallpaper
    with wallpaper.LOCK:
        if not CONTEXT or uid not in CONTEXT['all_ids']:raise ValueError('That desktop no longer exists.')
        if ident is not None:wallpaper.image_path(ident)
        state=wallpaper.load();pictures=state.setdefault('desktopPictures',{})
        if ident is None:pictures.pop(uid,None)
        else:pictures[uid]=ident
        wallpaper.save(state);sync()


class Backgrounds:
    def __init__(self,m):
        self.m=m;self.d=m.desktops;self.stopped=False;self.timer=0;self.running=False;self.dirty=False;self.error=''
        self.handlers=[self.d.screen.connect(name,self.request) for name in
                       ('active-workspace-changed','viewports-changed','window-manager-changed')]
        self.display=Gdk.Display.get_default()
        self.display_handlers=[self.display.connect(name,self.request) for name in ('monitor-added','monitor-removed')]
        self.request()

    def close(self):
        self.stopped=True
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        for handler in self.handlers:self.d.screen.disconnect(handler)
        for handler in self.display_handlers:self.display.disconnect(handler)

    def request(self,*_):
        if self.stopped:return
        self.dirty=True
        if not self.timer:self.timer=GLib.timeout_add(80,self.dispatch)

    def dispatch(self):
        global CONTEXT
        if self.stopped:self.timer=0;return False
        if self.d.busy:return True
        self.timer=0
        items=self.d.items()
        if not items:return False
        current=next(d for d in items if d['current'])
        screen=Gdk.Screen.get_default()
        monitors=[screen.get_monitor_plug_name(i) for i in range(self.display.get_n_monitors())]
        CONTEXT={'uid':current['uid'],'all_ids':[u for ids in self.m.preferences.get('desktop_ids',{}).values() for u in ids],
                 'monitors':[x for x in monitors if x] or ['0']}
        if self.running:return False
        self.running=True;self.dirty=False
        def finish(error=None):
            self.running=False;self.error=str(error or '')
            if self.dirty:self.request()
        self.m.hub.background(sync,lambda _:finish(),finish)
        return False

    def choose(self,uid,ident,done):
        if self.d.busy:done('Wait for the desktop change to finish.');return
        # Refresh the context synchronously; the actual disk/desktop work stays
        # in the worker, so choosing on a newly created desktop is valid.
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        self.dispatch()
        def finish(error=None):self.error=str(error or '');self.request();done(error)
        self.m.hub.background(lambda:assign(uid,ident),lambda _:finish(),finish)

    def import_picture(self,uid,path,done):
        import wallpaper
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        self.dispatch()
        def task():
            p=Path(path)
            if p.stat().st_size>30*1024*1024:raise ValueError('Choose an image smaller than 30 MB.')
            entry=wallpaper.remember(p.read_bytes(),{'source':'local','title':p.name,'credit':''})
            assign(uid,entry['id'])
        def finish(error=None):self.error=str(error or '');self.request();done(error)
        self.m.hub.background(task,lambda _:finish(),finish)
