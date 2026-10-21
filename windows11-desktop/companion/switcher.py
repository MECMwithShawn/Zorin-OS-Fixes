"""Keyboard-driven window/Snap Group switcher for GNOME and Xfce Alt+Tab.

Xfce launches the command; only a visible switcher grabs the keyboard. No idle
key listener or global passive grab is installed. Native Ctrl+Alt+Tab remains
available under Compiz, and uninstall restores the previous Alt+Tab shortcuts.
"""
import ctypes as C
import subprocess
import time
from pathlib import Path
import gi
gi.require_version("Gtk","3.0")
gi.require_version("Gdk","3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
from multitasking import label

BASE=Path(__file__).resolve().parent


class AltKeys:
    """Query only the physical Alt keys while the chooser is open."""
    def __init__(self):
        from gnome_bridge import active as is_gnome
        self.gnome=is_gnome();self.display=None
        if self.gnome:return
        self.x=C.CDLL('libX11.so.6')
        for name,restype,args in [
            ('XOpenDisplay',C.c_void_p,[C.c_char_p]),
            ('XKeysymToKeycode',C.c_uint,[C.c_void_p,C.c_ulong]),
            ('XQueryKeymap',C.c_int,[C.c_void_p,C.c_void_p]),
            ('XCloseDisplay',C.c_int,[C.c_void_p]),
        ]:
            fn=getattr(self.x,name);fn.restype=restype;fn.argtypes=args
        self.display=self.x.XOpenDisplay(None)
        if not self.display:raise RuntimeError('The X11 display is unavailable.')
        self.codes=[self.x.XKeysymToKeycode(self.display,key) for key in (Gdk.KEY_Alt_L,Gdk.KEY_Alt_R)]

    def held(self):
        from gnome_bridge import call
        if self.gnome:return bool(call('modifiers') & int(Gdk.ModifierType.MOD1_MASK))
        keys=(C.c_ubyte*32)();self.x.XQueryKeymap(self.display,keys)
        return any(code and keys[code//8] & (1<<(code%8)) for code in self.codes)

    def close(self):
        if self.display:self.x.XCloseDisplay(self.display);self.display=None


class Switcher:
    def __init__(self,m):
        self.m=m;self.window=None;self.history=[];self.current_group=None
        self.awaiting=0;self.timer=0;self.capture_timer=0;self.keys=None;self.grabbed=False
        self.pending_capture=False;self.capture_cursor=0;self.epoch=0
        self.handler=m.windows.screen.connect('active-window-changed',self.active_changed)
        self.active_changed()

    def shutdown(self):
        if self.window:self.m.close(False)
        self.m.windows.screen.disconnect(self.handler)

    def touch(self,key):
        self.history=[key]+[k for k in self.history if k!=key][:127]

    def active_changed(self,*_):
        w=self.m.windows.screen.get_active_window()
        if not self.m.windows.eligible(w):return
        xid=w.get_xid()
        group=next((g for g in self.m.groups if g.token==self.current_group),None)
        if group and xid in {x for x,_ in group}:
            # More than one member can remap. Keep the short restoration
            # grace period across intermediate member/fallback focus changes.
            self.touch(('group',group.token));return
        # Closing the chooser briefly returns focus to its origin before the
        # asynchronous restore maps the group's members. Do not reorder on it.
        if group and self.awaiting>time.monotonic():return
        self.current_group=None;self.awaiting=0;self.touch(('window',xid))

    def group_activated(self,token,restoring=True):
        self.current_group=token;self.awaiting=time.monotonic()+2 if restoring else 0
        self.touch(("group",token))

    def entries(self):
        desktop=self.m.desktops.current()
        windows=[w for w in self.m.windows.windows() if self.m.desktops.on(w,desktop)]
        entries=[dict(key=('window',w.get_xid()),members=[(w.get_xid(),(0,0,1,1))],
                      title=w.get_name(),subtitle='Minimized' if w.is_minimized() else w.get_class_group_name() or 'Window') for w in windows]
        groups=[g for g in self.m.groups if self.m.snap_groups.desktop(g)==desktop]
        for g in groups:
            refs=[self.m.windows.get(x) for x,_ in g]
            if not all(refs):continue
            names=[w.get_name() for w in refs]
            entries.append(dict(key=('group',g.token),members=list(g),title=f'Snap group · {len(g)} windows',subtitle=' · '.join(names)))
        # Previously selected groups participate in MRU alongside individual
        # windows. New groups follow the normal MRU window list until selected.
        order=self.history+[e['key'] for e in entries if e['key'] not in self.history]
        entries.sort(key=lambda e:order.index(e['key']))
        self.history=[key for key in self.history if any(e['key']==key for e in entries)]
        return entries

    def show(self,reverse=False):
        if self.window:self.step(-1 if reverse else 1);return
        if self.m.desktops.busy:return
        self.awaiting=0;self.active_changed();self.items=self.entries()
        if not self.items:return
        origin=self.m.windows.active();self.m.origin=origin.get_xid() if origin else None
        self.selected=(len(self.items)-1 if reverse else 1)%len(self.items)
        try:
            self.keys=AltKeys()
            held=self.keys.held()
        except (GLib.Error,RuntimeError,OSError,ValueError,TypeError):
            if self.keys:self.keys.close();self.keys=None
            return
        # A fast tap may finish before the Xfce command reaches the application.
        # Select directly in that case instead of leaving a stranded popup.
        if not held:
            self.keys.close();self.keys=None;self.commit();return
        area=self.m.area(origin);width=min(1160,area[2]-40,48+270*len(self.items))
        columns=max(1,min(4,(width-48)//250))
        height=min(600,area[3]-40,130+218*((len(self.items)+columns-1)//columns))
        win,box=self.m.shell('Switch windows',width,height,area)
        self.window=win;self.epoch+=1;self.cards=[];self.drawings=[]
        win.get_style_context().add_class('z11-switcher')
        win.connect('destroy',self.destroyed)
        win.connect('key-press-event',self.key)
        win.connect('key-release-event',lambda *_:self.check_release())
        win.connect('grab-broken-event',lambda *_:(self.m.close(False),False)[1])
        heading=Gtk.Box(spacing=20);heading.pack_start(label('Switch windows','z11-heading'),True,True,0)
        heading.pack_end(label('Alt + Tab','z11-muted'),False,False,0);box.pack_start(heading,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scroll,True,True,0);self.scroll=scroll
        self.flow=Gtk.FlowBox();self.columns=columns
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE);self.flow.set_homogeneous(True)
        self.flow.set_min_children_per_line(columns);self.flow.set_max_children_per_line(columns)
        self.flow.set_row_spacing(12);self.flow.set_column_spacing(12);self.flow.set_valign(Gtk.Align.START)
        scroll.add(self.flow)
        self.build_cards()
        box.pack_end(label('Release Alt to switch   ·   Shift + Tab to go back   ·   Esc to cancel','z11-muted'),False,False,0)
        win.show_all();win.present();self.highlight()
        self.grab_deadline=time.monotonic()+.6
        self.timer=GLib.timeout_add(25,self.tick)
        self.capture_timer=GLib.timeout_add(180,self.capture)

    def destroyed(self,*_):
        self.window=None;self.epoch+=1
        for name in ('timer','capture_timer'):
            source=getattr(self,name)
            if source:GLib.source_remove(source);setattr(self,name,0)
        if self.grabbed:Gdk.Display.get_default().get_default_seat().ungrab()
        self.grabbed=False
        if self.keys:self.keys.close();self.keys=None
        self.cards=[];self.drawings=[]

    def alt_held(self):
        try:return self.keys.held()
        except (GLib.Error,RuntimeError,OSError,ValueError,TypeError):
            # Losing the bridge must cancel, not select another window.
            self.m.close(False)
            return None

    def check_release(self):
        if self.window and self.keys and self.alt_held() is False:self.commit()
        return False

    def tick(self):
        if not self.window:return False
        held=self.alt_held()
        if held is None:return False
        if not held:self.timer=0;self.commit();return False
        from gnome_bridge import active as is_gnome
        if is_gnome():return True  # Shell owns Alt+Tab; poll native modifier release.
        if not self.grabbed:
            status=Gdk.Display.get_default().get_default_seat().grab(
                self.window.get_window(),Gdk.SeatCapabilities.KEYBOARD,False,None,None,None,None)
            self.grabbed=status==Gdk.GrabStatus.SUCCESS
            if not self.grabbed and time.monotonic()>self.grab_deadline:
                self.timer=0;self.m.close(False);return False
        return True

    def key(self,win,event):
        key=event.keyval
        if key in (Gdk.KEY_Tab,Gdk.KEY_ISO_Left_Tab):
            self.step(-1 if event.state&Gdk.ModifierType.SHIFT_MASK else 1);return True
        if key in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Up,Gdk.KEY_Down):
            self.step({Gdk.KEY_Left:-1,Gdk.KEY_Right:1,Gdk.KEY_Up:-self.columns,Gdk.KEY_Down:self.columns}[key]);return True
        if key in (Gdk.KEY_Return,Gdk.KEY_KP_Enter):self.commit();return True
        return False

    def step(self,delta):
        self.selected=(self.selected+delta)%len(self.items);self.highlight()

    def highlight(self):
        for i,card in enumerate(self.cards):
            context=card.get_style_context()
            if i==self.selected:context.add_class('z11-switch-selected');card.grab_focus()
            else:context.remove_class('z11-switch-selected')
        # Gtk's focus scrolling keeps every card reachable on smaller screens.

    def commit(self,index=None):
        if index is not None:self.selected=index
        entry=self.items[self.selected];self.m.close(False)
        kind,value=entry['key']
        if kind=='group':
            live=next((g for g in self.m.groups if g.token==value),None)
            if not live:return
            preferred=next((x for x in self.m.windows.mru if any(x==i for i,_ in live)),live[0][0])
            if not self.m.snap_groups.activate(value,preferred):self.current_group=None;self.awaiting=0
        else:
            self.current_group=None;w=self.m.windows.get(value)
            if w:self.touch(entry['key']);self.m.windows.activate(w)

    def build_cards(self):
        for child in self.flow.get_children():child.destroy()
        self.cards=[];self.drawings=[]
        for index,entry in enumerate(self.items):
            card=Gtk.Button();card.get_style_context().add_class('z11-window-card')
            card.set_tooltip_text(entry['title']+'\n'+entry['subtitle'])
            card.get_accessible().set_name(entry['title']+'. '+entry['subtitle'])
            card.connect('clicked',lambda _,i=index:self.commit(i))
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);card.add(content)
            title=label(entry['title']);title.set_ellipsize(Pango.EllipsizeMode.END);title.set_max_width_chars(24)
            content.pack_start(title,False,False,0)
            drawing=Gtk.DrawingArea();drawing.set_size_request(210,136)
            drawing.connect('draw',self.draw,entry);content.pack_start(drawing,True,True,0)
            subtitle=label(entry['subtitle'],'z11-small');subtitle.set_ellipsize(Pango.EllipsizeMode.END);subtitle.set_max_width_chars(26)
            content.pack_start(subtitle,False,False,0)
            self.flow.add(card);self.cards.append(card);self.drawings.append(drawing)
        self.flow.show_all()

    def draw(self,widget,cr,entry):
        width,height=widget.get_allocated_width(),widget.get_allocated_height()
        members=entry['members'];left=min(r[0] for _,r in members);top=min(r[1] for _,r in members)
        total_w=max(r[0]+r[2] for _,r in members)-left;total_h=max(r[1]+r[3] for _,r in members)-top
        # Individual previews use the complete card; group mosaics retain the
        # saved proportions so halves, columns and quarters are recognizable.
        scale=min(width/total_w,height/total_h) if len(members)>1 else 1
        ox=(width-total_w*scale)/2 if len(members)>1 else 0
        oy=(height-total_h*scale)/2 if len(members)>1 else 0
        for xid,r in members:
            x=ox+(r[0]-left)*scale;y=oy+(r[1]-top)*scale
            w=max(1,r[2]*scale-2);h=max(1,r[3]*scale-2)
            if len(members)==1:x=y=0;w=width;h=height
            cr.set_source_rgb(.09,.095,.105);cr.rectangle(x,y,w,h);cr.fill()
            pix=self.m.preview_cache.get(xid)
            if pix is None:
                window=self.m.windows.get(xid)
                if window:pix=window.get_icon()
                limit=40
            else:limit=None
            if pix:
                ratio=min(w/pix.get_width(),h/pix.get_height())
                if limit:ratio=min(ratio,limit/pix.get_width(),limit/pix.get_height())
                pw,ph=max(1,int(pix.get_width()*ratio)),max(1,int(pix.get_height()*ratio))
                scaled=pix.scale_simple(pw,ph,GdkPixbuf.InterpType.BILINEAR)
                Gdk.cairo_set_source_pixbuf(cr,scaled,x+(w-pw)/2,y+(h-ph)/2);cr.paint()
        return False

    def capture(self):
        if not self.window:return False
        # Refresh metadata without changing the order under a held Alt key.
        available={e['key']:e for e in self.entries()}
        selected=self.items[self.selected]['key'];items=[available[e['key']] for e in self.items if e['key'] in available]
        if items!=self.items:
            self.items=items
            if not items:self.m.close();return False
            self.selected=next((i for i,e in enumerate(items) if e['key']==selected),min(self.selected,len(items)-1))
            self.build_cards();self.highlight()
        if self.pending_capture:return True
        adjustment=self.scroll.get_vadjustment();low=adjustment.get_value();high=low+adjustment.get_page_size()
        ids=[]
        for entry,card in zip(self.items,self.cards):
            bounds=card.get_parent().get_allocation()
            if bounds.y+bounds.height<low or bounds.y>high:continue
            ids.extend(x for x,_ in entry['members'] if x not in ids)
        if not ids:return True
        self.capture_cursor%=len(ids);xid=ids[self.capture_cursor];self.capture_cursor+=1
        w=self.m.windows.get(xid)
        if not w or w.is_minimized():return True
        self.pending_capture=True;epoch=self.epoch
        def task():
            return subprocess.run(['/usr/bin/python3',str(BASE/'window_preview.py'),str(xid)],capture_output=True,timeout=2,check=False).stdout
        def done(data):
            self.pending_capture=False
            if epoch!=self.epoch or not data or len(data)>1048576:return
            try:
                loader=GdkPixbuf.PixbufLoader.new_with_type('png');loader.write(data);loader.close()
                self.m.preview_cache[xid]=loader.get_pixbuf()
                while len(self.m.preview_cache)>36:self.m.preview_cache.pop(next(iter(self.m.preview_cache)))
                for widget in self.drawings:widget.queue_draw()
            except GLib.Error:pass
        self.m.hub.background(task,done,lambda _:done(b''))
        return True
