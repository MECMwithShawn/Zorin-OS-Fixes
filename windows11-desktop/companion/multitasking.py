"""Fluent-style Snap Layouts and searchable Task View over native X11 windows."""
import json
import os
from pathlib import Path
import subprocess
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
from windowing import Windows, layouts, zone_rect

BASE=Path(__file__).resolve().parent


def label(text,cls=None):
    widget=Gtk.Label(label=text,xalign=0)
    if cls:widget.get_style_context().add_class(cls)
    return widget


def button(text,callback,cls=None):
    widget=Gtk.Button(label=text) if text is not None else Gtk.Button()
    widget.connect('clicked',lambda *_:callback())
    if cls:widget.get_style_context().add_class(cls)
    return widget


class Multitasking:
    def __init__(self,hub,config):
        self.hub=hub;self.config=config;self.windows=Windows()
        self.window=None;self.overlay=None;self.generation=0;self.groups=[]
        self.origin=None;self.restore_focus=True;self.hover_timer=0;self.preview_cache={}
        self.preview_handler=self.windows.screen.connect('window-closed',lambda _,w:self.preview_cache.pop(w.get_xid(),None))
        try:self.preferences=json.loads((config/'multitasking.json').read_text())
        except (OSError,ValueError):self.preferences={}
        from desktops import Desktops
        self.desktops=Desktops(self)
        self.css=Gtk.CssProvider();self.css.load_from_path(str(BASE/'multitasking.css'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.css,650)

    def shutdown(self):
        self.desktops.stopped=True
        if self.hover_timer:GLib.source_remove(self.hover_timer);self.hover_timer=0
        self.close(False)
        self.windows.screen.disconnect(self.preview_handler)
        self.windows.close()

    def save(self):
        self.config.mkdir(parents=True,exist_ok=True)
        path=self.config/'multitasking.json';tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.preferences)+'\n');tmp.replace(path)

    def close(self,restore=True):
        self.generation+=1;self.clear_preview()
        if self.window:
            window=self.window;self.window=None;window.destroy()
        if restore and self.origin:
            w=self.windows.get(self.origin)
            if w:self.windows.activate(w)

    def shell(self,title,width,height,area,position=None):
        self.close(False)
        for surface in self.hub.surfaces.values():
            if surface.mode in ('start','quick','notifications'):surface.hide()
        win=Gtk.Window(title=title);self.window=win
        win.set_decorated(False);win.set_skip_taskbar_hint(True);win.set_skip_pager_hint(True)
        win.set_type_hint(Gdk.WindowTypeHint.UTILITY);win.set_keep_above(True)
        win.set_resizable(False);win.get_style_context().add_class('z11-multitask')
        visual=win.get_screen().get_rgba_visual()
        if visual:win.set_visual(visual)
        win.set_default_size(width,height)
        win.connect('delete-event',lambda *_:(self.close(),True)[1])
        win.connect('key-press-event',self.key)
        generation=self.generation
        def blur(*_):
            def finish():
                view=getattr(self,'task_view',None)
                held=view and view.alive() and view.hold_focus()
                if generation==self.generation and self.window and not self.window.is_active() and not held:self.close(False)
                return False
            GLib.timeout_add(200,finish)
        win.connect('focus-out-event',blur)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        box.set_border_width(24);win.add(box)
        x,y,w,h=area
        px,py=position or (x+(w-width)//2,y+(h-height)//2)
        px=max(x+8,min(px,x+w-width-8));py=max(y+8,min(py,y+h-height-8))
        win.move(px,py)
        win.connect('map-event',lambda *_:GLib.idle_add(lambda:(win.move(px,py),False)[1]))
        return win,box

    def key(self,win,event):
        if event.keyval==Gdk.KEY_Escape:self.close();return True
        if win.get_title()=='Snap layouts' and Gdk.KEY_1<=event.keyval<=Gdk.KEY_6:
            index=event.keyval-Gdk.KEY_1
            if index<len(self.layout_buttons):self.layout_buttons[index][0].grab_focus()
            return True
        return False

    def area(self,w=None):
        if w:
            x,y,width,height=w.get_geometry()
            area=self.hub.work_area(x+width//2,y+height//2)
        else:area=self.hub.monitor_geometry()
        return area.x,area.y,area.width,area.height

    def clear_preview(self):
        if self.overlay:self.overlay.destroy();self.overlay=None

    def preview(self,rect):
        self.clear_preview()
        overlay=Gtk.Window(type=Gtk.WindowType.POPUP);self.overlay=overlay
        overlay.set_accept_focus(False);overlay.set_skip_taskbar_hint(True)
        overlay.set_app_paintable(True);overlay.set_visual(overlay.get_screen().get_rgba_visual())
        overlay.set_opacity(.7)
        def draw(widget,cr):
            import cairo
            cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(.16,.46,.65,.27);cr.paint()
            cr.set_source_rgba(.38,.81,1,.95);cr.set_line_width(3)
            cr.rectangle(2,2,rect[2]-4,rect[3]-4);cr.stroke();return True
        overlay.connect('draw',draw)
        overlay.move(rect[0],rect[1]);overlay.resize(rect[2],rect[3]);overlay.show_all()
        import cairo
        overlay.get_window().input_shape_combine_region(cairo.Region(),0,0)
        if self.window and self.window.get_window():self.window.get_window().raise_()

    def show_snap(self,xid=None):
        if self.window and self.window.get_title()=='Snap layouts' and xid is None:self.close();return
        target=self.windows.get(xid) if xid else self.windows.active()
        if not target:return
        self.origin=target.get_xid();area=self.area(target)
        if not self.windows.can_snap(target):return
        tx,ty,tw,th=target.get_geometry()
        win,box=self.shell('Snap layouts',456,340,area,(tx+tw-456,ty+36))
        head=Gtk.Box(spacing=12);head.pack_start(label('Snap layouts','z11-heading'),True,True,0)
        head.pack_end(label('Win + Z','z11-muted'),False,False,0);box.pack_start(head,False,False,0)
        subtitle=label(target.get_name(),'z11-muted');subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        subtitle.set_max_width_chars(48);box.pack_start(subtitle,False,False,0)
        grid=Gtk.Grid(column_spacing=16,row_spacing=14);box.pack_start(grid,True,True,0)
        self.layout_buttons=[]
        minimum=self.windows.minimum(target)
        for index,(name,zones) in enumerate(layouts(self.preferences.get('focus_width',50))):
            group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            fixed=Gtk.Fixed();fixed.set_size_request(124,72);group.pack_start(fixed,False,False,0)
            buttons=[]
            for zi,zone in enumerate(zones):
                rect=zone_rect((0,0,124,72),zone,2);actual=zone_rect(area,zone)
                b=button('',lambda zs=zones,z=zi:self.snap(target.get_xid(),area,zs,z),'z11-zone')
                b.set_size_request(rect[2],rect[3]);b.set_tooltip_text(f'{name} · zone {zi+1}')
                if actual[2]<minimum[0] or actual[3]<minimum[1]:
                    b.set_sensitive(False);b.set_tooltip_text('This zone is smaller than the app allows')
                b.get_accessible().set_name(f'{name}, zone {zi+1}')
                b.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
                b.connect('enter-notify-event',lambda *_,r=actual:self.preview(r))
                b.connect('leave-notify-event',lambda *_:self.clear_preview())
                b.connect('focus-in-event',lambda *_,r=actual:self.preview(r))
                fixed.put(b,rect[0],rect[1]);buttons.append(b)
            group.pack_start(label(f'{index+1}  {name}','z11-small'),False,False,0)
            grid.attach(group,index%3,index//3,1,1);self.layout_buttons.append(buttons)
        foot=Gtk.Box(spacing=8)
        restore=button('Restore size',lambda:self.restore(target.get_xid()))
        restore.set_sensitive(target.get_xid() in self.windows.saved);foot.pack_start(restore,False,False,0)
        foot.pack_end(button('Customize…',lambda:self.customize(target.get_xid())),False,False,0)
        box.pack_start(foot,False,False,0);win.show_all();win.present()
        # Do not draw a preview until the user actually hovers or navigates.
        restore.grab_focus();self.clear_preview()

    def restore(self,xid):
        self.close(False);self.windows.restore(xid)

    def customize(self,xid):
        area=self.area(self.windows.get(xid));win,box=self.shell('Snap preferences',430,240,area)
        box.pack_start(label('Make room for your main app','z11-heading'),False,False,0)
        box.pack_start(label('Center width in the Focus columns layout','z11-muted'),False,False,0)
        scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,40,70,5)
        scale.set_value(self.preferences.get('focus_width',50));scale.set_digits(0)
        scale.connect('format-value',lambda _,value:f'{value:.0f}%');box.pack_start(scale,False,False,0)
        assist=Gtk.CheckButton(label='Suggest windows for the remaining spaces')
        assist.set_active(self.preferences.get('assist',True));box.pack_start(assist,False,False,0)
        def save():
            self.preferences.update(focus_width=int(scale.get_value()),assist=assist.get_active());self.save();self.show_snap(xid)
        box.pack_end(button('Save',save,'z11-primary'),False,False,0);win.show_all();win.present()

    def snap(self,xid,area,zones,index):
        self.close(False);rect=zone_rect(area,zones[index])
        placements=[(xid,rect)];remaining=[zone_rect(area,z) for i,z in enumerate(zones) if i!=index]
        self.windows.place(xid,rect,finished=lambda:self.assist(placements,remaining,area))

    def remember_group(self,placements):
        if len(placements)<2:return
        ids={i for i,_ in placements}
        self.groups=[g for g in self.groups if not ids.intersection(i for i,_ in g)]
        self.groups.insert(0,placements[:]);self.groups=self.groups[:8]

    def assist(self,placements,remaining,area):
        self.remember_group(placements)
        choices=[w for w in self.windows.windows() if w.get_xid() not in {i for i,_ in placements}
                 and self.windows.can_snap(w) and self.desktops.on(w,self.desktops.current())]
        if remaining:
            choices=[w for w in choices if all(a<=b for a,b in zip(self.windows.minimum(w),remaining[0][2:]))]
        if not remaining or not choices or not self.preferences.get('assist',True):return
        width=min(980,area[2]-32);height=min(650,area[3]-32)
        win,box=self.shell('Snap assist',width,height,area)
        head=Gtk.Box(spacing=16);head.pack_start(label('Choose a window for the next space','z11-heading'),True,True,0)
        head.pack_end(button('Skip',lambda:self.close()),False,False,0);box.pack_start(head,False,False,0)
        hint=label('The blue outline shows where it will go.  Esc keeps your current layout.','z11-muted')
        box.pack_start(hint,False,False,0)
        def choose(w):
            self.close(False)
            self.windows.place(w.get_xid(),remaining[0],finished=lambda:self.assist(placements+[(w.get_xid(),remaining[0])],remaining[1:],area))
        self.cards(box,choices,choose,width)
        win.show_all();win.present();self.preview(remaining[0])
        # Keep the chooser above its input-transparent target outline.
        win.get_window().raise_()

    def cards(self,box,windows,choose,width,search=None,view=None):
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(220);box.pack_start(scroll,True,True,0)
        flow=Gtk.FlowBox();flow.set_selection_mode(Gtk.SelectionMode.NONE)
        columns=max(1,min(4,(width-48)//250));flow.set_min_children_per_line(columns);flow.set_max_children_per_line(columns)
        flow.set_row_spacing(12);flow.set_column_spacing(12);flow.set_homogeneous(True);flow.set_valign(Gtk.Align.START)
        scroll.add(flow);self.flow=flow
        generation=self.generation
        if view:flow.set_filter_func(view.accepts)
        elif search:
            flow.set_filter_func(lambda child:search.get_text().casefold() in child.search_text)
            search.connect('search-changed',lambda *_:flow.invalidate_filter())
        for index,w in enumerate(windows):
            title=w.get_name();card=Gtk.Button();card.get_style_context().add_class('z11-window-card')
            card.set_tooltip_text(title);card.get_accessible().set_name(title)
            card.connect('clicked',lambda _,window=w:choose(window))
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);card.add(content)
            heading=Gtk.Box(spacing=9);icon=w.get_mini_icon()
            if icon:heading.pack_start(Gtk.Image.new_from_pixbuf(icon.scale_simple(20,20,GdkPixbuf.InterpType.BILINEAR)),False,False,0)
            text=label(title);text.set_ellipsize(Pango.EllipsizeMode.END);text.set_max_width_chars(22)
            heading.pack_start(text,True,True,0);content.pack_start(heading,False,False,0)
            image=Gtk.Image.new_from_pixbuf(w.get_icon());image.set_size_request(210,136)
            cached=self.preview_cache.get(w.get_xid())
            if cached:
                ratio=min(230/cached.get_width(),136/cached.get_height())
                image.set_from_pixbuf(cached.scale_simple(max(1,int(cached.get_width()*ratio)),max(1,int(cached.get_height()*ratio)),GdkPixbuf.InterpType.BILINEAR))
            content.pack_start(image,True,True,0)
            status='Minimized' if w.is_minimized() else w.get_class_group_name() or 'Window'
            if view:
                desktop=self.desktops.desktop_for(w)
                desktop_name=next((d['name'] for d in view.items if d['id']==desktop),'All desktops')
                status=desktop_name+' · '+status
            content.pack_start(label(status,'z11-small'),False,False,0)
            child=Gtk.FlowBoxChild();child.search_text=(title+' '+status).casefold();child.xid=w.get_xid()
            if view:view.configure_card(card,child,w)
            child.add(card);flow.add(child)
            if not w.is_minimized() and index<36:
                def capture(xid=w.get_xid()):
                    return subprocess.run(['/usr/bin/python3',str(BASE/'window_preview.py'),str(xid)],capture_output=True,timeout=3,check=False).stdout
                def done(data,img=image,xid=w.get_xid()):
                    if generation!=self.generation or not data:return
                    loader=GdkPixbuf.PixbufLoader.new_with_type('png');loader.write(data);loader.close()
                    pix=loader.get_pixbuf();ratio=min(230/pix.get_width(),136/pix.get_height())
                    self.preview_cache[xid]=pix
                    while len(self.preview_cache)>36:self.preview_cache.pop(next(iter(self.preview_cache)))
                    img.set_from_pixbuf(pix.scale_simple(max(1,int(pix.get_width()*ratio)),max(1,int(pix.get_height()*ratio)),GdkPixbuf.InterpType.BILINEAR))
                    if view:view.preview_ready(xid,pix)
                # Let the chooser map before capture. Compiz may temporarily
                # unredirect an unobscured full-screen-sized application.
                def begin(task=capture,callback=done):
                    if generation==self.generation:self.hub.background(task,callback,lambda _:None)
                    return False
                GLib.timeout_add(250,begin)
        if not windows and not view:box.pack_start(label('No open windows on this desktop.','z11-muted'),False,False,0)
        return flow

    def show_tasks(self):
        if self.window and self.window.get_title()=='Task view':self.close();return
        from taskview import TaskView
        self.task_view=TaskView(self)

    def desktop_command(self,action):
        if self.desktops.busy:return
        self.close(False)
        def done(error,index):
            if error:
                self.show_tasks();self.task_view.notice(error)
            elif index is not None:self.desktops.switch(index)
        if action=='new':self.desktops.create(done)
        elif action=='close':
            if len(self.desktops.items())>1:self.desktops.remove(self.desktops.current(),done)
        elif action in ('left','right'):
            index=self.desktops.current()+(-1 if action=='left' else 1)
            if 0<=index<len(self.desktops.items()):self.desktops.switch(index)

    def choose(self,w):
        self.close(False)
        if self.windows.get(w.get_xid()):self.windows.activate(w)

    def activate_group(self,group):
        self.close(False)
        for xid,rect in group:
            if self.windows.get(xid):self.windows.place(xid,rect)

    def caption_hover(self,surface,enter):
        if self.hover_timer:GLib.source_remove(self.hover_timer);self.hover_timer=0
        if not enter:return
        def show():
            self.hover_timer=0
            if surface.is_active():self.show_snap(surface.get_window().get_xid())
            return False
        self.hover_timer=GLib.timeout_add(650,show)
