"""Native Task View: window cards above a Windows-style desktop filmstrip."""
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
from multitasking import label, button

DRAG_TYPE='application/x-zorin11-window'
DESKTOP_DRAG_TYPE='application/x-zorin11-desktop'


class TaskView:
    def __init__(self,m):
        self.m=m;self.d=m.desktops;self.selected=self.d.current();self.pixbufs=m.preview_cache.copy()
        self.menu=None;self.dragging=False;self.editing=False;self.modal=False;self.choosing=False;self.transition=False;self.hover=0;self.error=''
        self.wallpapers={};self.revision=None;self.thumbs=[]
        target=m.windows.active();m.origin=target.get_xid() if target else None
        area=m.area(target);self.width=min(1480,area[2]-48);height=min(920,area[3]-48)
        self.win,self.box=m.shell('Task view',self.width,height,area)
        self.win.stick();self.win.get_style_context().add_class('z11-taskview')
        self.render()
        self.win.show_all();self.filter();self.win.present();self.search.grab_focus()
        GLib.timeout_add(450,self.refresh)

    def alive(self):return self.m.window is self.win

    def hold_focus(self):return self.menu is not None or self.dragging or self.d.busy or self.modal or self.choosing or self.transition

    def resume(self):
        # Workspace activation can restore focus to a normal app after its
        # EWMH acknowledgement. Keep Task View through that transition and use
        # a fresh server timestamp when requesting focus back.
        if not self.alive():return
        self.transition=True;self.win.present_with_time(self.m.windows.timestamp())
        def settled():
            if self.alive():self.win.present_with_time(self.m.windows.timestamp())
            self.transition=False;return False
        from desktop_motion import load
        GLib.timeout_add(max(250,load()['duration']+200),settled)

    def fingerprint(self):
        import wallpaper
        return (tuple((d['uid'],d['name'],d['current']) for d in self.d.items()),
                wallpaper.STATE.stat().st_mtime_ns if wallpaper.STATE.exists() else 0,
                tuple((w.get_xid(),w.get_name(),self.d.desktop_for(w),w.is_minimized()) for w in self.m.windows.windows()))

    def refresh(self):
        if not self.alive():return False
        if self.d.busy or self.editing or self.hold_focus():return True
        revision=self.fingerprint()
        if revision!=self.revision:self.render()
        return True

    def render(self):
        query=self.search.get_text() if hasattr(self,'search') else ''
        focus_search=hasattr(self,'search') and self.search.has_focus()
        focus_desktop=next((self.items[i]['uid'] for i,b in enumerate(getattr(self,'desktop_buttons',[])) if b.has_focus()),None)
        focus_window=next((c.xid for c in self.m.flow.get_children() if c.get_child().has_focus()),None) if hasattr(self.m,'flow') else None
        for widget in self.box.get_children():widget.destroy()
        self.items=self.d.items();self.selected=min(self.selected,len(self.items)-1)
        self.thumbs=[];self.desktop_buttons=[];self.revision=self.fingerprint()
        self.clients=self.m.windows.windows()
        live={w.get_xid() for w in self.clients};self.pixbufs={k:v for k,v in self.pixbufs.items() if k in live}
        self.m.preview_cache={k:v for k,v in self.m.preview_cache.items() if k in live}
        header=Gtk.Box(spacing=16)
        header.pack_start(label('Task view','z11-heading'),False,False,0)
        self.subtitle=label('','z11-muted');header.pack_start(self.subtitle,True,True,0)
        header.pack_end(button('Close',lambda:self.m.close()),False,False,0)
        header.pack_end(label('Win + Tab','z11-muted'),False,False,0);self.box.pack_start(header,False,False,0)
        self.search=Gtk.SearchEntry();self.search.set_placeholder_text('Search windows across your desktops')
        self.search.set_text(query);self.box.pack_start(self.search,False,False,0)
        self.m.snap_groups.prune()
        groups=[g for g in self.m.groups if self.m.snap_groups.desktop(g) is not None]
        self.group_widgets=[];self.groups_box=None
        if groups:
            row=Gtk.Box(spacing=8);self.groups_box=row;row.pack_start(label('Snap groups','z11-muted'),False,False,0)
            for i,g in enumerate(groups[:4]):
                b=button(f'Group {i+1} · {len(g)} windows',lambda group=g:self.m.activate_group(group))
                row.pack_start(b,False,False,0);self.group_widgets.append((b,g))
            self.box.pack_start(row,False,False,0)
        self.m.cards(self.box,self.clients,self.m.choose,self.width,self.search,view=self)
        self.empty=label('No open windows here. Open an app or drag a window onto this desktop.','z11-muted')
        self.box.pack_start(self.empty,False,False,0)
        foot=Gtk.Box(spacing=12)
        self.message=label(self.error or 'Drag desktops to reorder · Right-click a desktop for its background · Drag windows between desktops','z11-muted')
        self.message.set_ellipsize(Pango.EllipsizeMode.END);foot.pack_start(self.message,True,True,0)
        foot.pack_end(button('Desktop settings',lambda:(self.m.close(False),self.m.hub.open_settings('multitasking'))),False,False,0)
        self.box.pack_start(foot,False,False,0)
        separator=Gtk.Separator();self.box.pack_start(separator,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.NEVER)
        scroll.set_min_content_height(194);scroll.set_max_content_height(194)
        row=Gtk.Box(spacing=16);row.set_halign(Gtk.Align.CENTER);scroll.add(row)
        self.box.pack_end(scroll,False,False,0)
        for item in self.items:row.pack_start(self.desktop(item),False,False,0)
        new=button(None,lambda:self.create(),'z11-new-desktop');new.set_size_request(200,150)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18);content.set_valign(Gtk.Align.CENTER)
        content.pack_start(label('＋','z11-desktop-plus'),False,False,0)
        content.pack_start(label('New desktop'),False,False,0)
        for child in content.get_children():child.set_xalign(.5)
        new.add(content);new.set_tooltip_text('New desktop · Win + Ctrl + D');new.get_accessible().set_name('New desktop')
        new.set_sensitive(len(self.items)<32 and not self.d.busy);self.drop_target(new,None)
        row.pack_start(new,False,False,0);self.new_button=new
        self.box.show_all();self.filter();self.search.connect('search-changed',lambda *_:self.filter())
        self.load_wallpapers()
        self.search.connect('key-press-event',self.search_key)
        if focus_search:self.search.grab_focus();self.search.set_position(-1)
        elif focus_desktop:
            for i,item in enumerate(self.items):
                if item['uid']==focus_desktop:self.desktop_buttons[i].grab_focus();break
        elif focus_window:
            for child in self.m.flow.get_children():
                if child.xid==focus_window and child.get_child_visible():child.get_child().grab_focus();break

    def filter(self):
        self.m.flow.invalidate_filter()
        count=sum(c.get_child_visible() for c in self.m.flow.get_children())
        query=self.search.get_text().strip()
        self.subtitle.set_text(f'{"All desktops" if query else self.items[self.selected]["name"]} · {count} window'+('' if count==1 else 's'))
        self.empty.set_text('No matching windows.' if query else 'No open windows here. Open an app or drag a window onto this desktop.')
        self.empty.set_visible(count==0)
        for b,group in self.group_widgets:
            b.set_visible(all(self.m.windows.get(x) and self.d.on(self.m.windows.get(x),self.selected) for x,_ in group))
        if self.groups_box:self.groups_box.set_visible(any(b.get_visible() for b,_ in self.group_widgets))
        for index,b in enumerate(self.desktop_buttons):
            style=b.get_style_context()
            if index==self.selected:style.add_class('z11-desktop-previewed')
            else:style.remove_class('z11-desktop-previewed')

    def accepts(self,child):
        query=self.search.get_text().strip().casefold()
        return query in child.search_text if query else child.desktop in (None,self.selected)

    def search_key(self,widget,event):
        if event.keyval in (Gdk.KEY_Return,Gdk.KEY_Down):
            children=[c for c in self.m.flow.get_children() if c.get_child_visible()]
            if children:
                if event.keyval==Gdk.KEY_Return:children[0].get_child().clicked()
                else:children[0].get_child().grab_focus()
            return True
        return False

    def desktop(self,item):
        index=item['id'];box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        box.set_size_request(216,-1)
        header=Gtk.Box(spacing=6)
        name=Gtk.Entry();name.set_text(item['name']);name.set_width_chars(14);name.set_max_length(40)
        name.get_style_context().add_class('z11-desktop-name');name.get_accessible().set_name('Rename '+item['name'])
        name.set_tooltip_text('Rename desktop · Enter to save');header.pack_start(name,True,True,0)
        name.connect('focus-in-event',lambda *_:setattr(self,'editing',True))
        def rename(*_):
            if not self.alive():return
            self.editing=False
            try:
                if name.get_text()!=item['name']:self.d.rename(index,name.get_text());item['name']=name.get_text()
            except ValueError as error:self.notice(str(error));name.set_text(item['name'])
        name.connect('activate',lambda *_:(rename(),self.search.grab_focus()))
        name.connect('focus-out-event',rename)
        def cancel(_,event):
            if event.keyval==Gdk.KEY_Escape:name.set_text(item['name']);self.search.grab_focus();return True
            return False
        name.connect('key-press-event',cancel)
        close=button('×',lambda:self.remove(index),'z11-desktop-close');close.set_sensitive(len(self.items)>1)
        close.set_tooltip_text('Close desktop; keep its apps open');close.get_accessible().set_name('Close '+item['name'])
        header.pack_end(close,False,False,0);box.pack_start(header,False,False,0)
        b=button(None,lambda:self.switch(index),'z11-desktop-card');b.set_size_request(216,126)
        b.get_accessible().set_name('Switch to '+item['name']);b.set_tooltip_text('Click to switch · Drag to reorder · Right-click for background and desktop actions')
        if item['current']:b.get_style_context().add_class('z11-desktop-current')
        drawing=Gtk.DrawingArea();drawing.set_size_request(200,112);drawing.connect('draw',lambda widget,cr:self.draw_desktop(widget,cr,index))
        b.add(drawing);self.thumbs.append(drawing);self.desktop_buttons.append(b);self.drop_target(b,index)
        b.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,[Gtk.TargetEntry.new(DESKTOP_DRAG_TYPE,Gtk.TargetFlags.SAME_APP,1)],Gdk.DragAction.MOVE)
        b.connect('drag-data-get',lambda _,context,selection,info,stamp:selection.set(selection.get_target(),8,item['uid'].encode('ascii')))
        b.connect('drag-begin',lambda *_:setattr(self,'dragging',True))
        b.connect('drag-end',lambda *_:(setattr(self,'dragging',False),self.win.present() if self.alive() else None))
        b.connect('button-press-event',lambda _,event:self.desktop_menu(b,index,event) if event.button==3 else False)
        b.connect('popup-menu',lambda *_:self.desktop_menu(b,index,None))
        def preview(*_):
            if self.hover:GLib.source_remove(self.hover)
            def select():
                self.hover=0
                if self.alive() and not self.dragging and not self.d.busy:self.selected=index;self.filter()
                return False
            self.hover=GLib.timeout_add(250,select)
        def leave(*_):
            if self.hover:GLib.source_remove(self.hover);self.hover=0
        b.connect('enter-notify-event',preview);b.connect('leave-notify-event',leave)
        b.connect('focus-in-event',lambda *_:(setattr(self,'selected',index),self.filter()))
        box.pack_start(b,False,False,0)
        total=sum(self.d.on(w,index) for w in self.clients)
        status=label(('Current desktop · ' if item['current'] else '')+str(total)+(' window' if total==1 else ' windows'),'z11-small')
        box.pack_start(status,False,False,0)
        return box

    def draw_desktop(self,widget,cr,index):
        width,height=widget.get_allocated_width(),widget.get_allocated_height()
        cr.set_source_rgb(.08,.15,.23);cr.paint()
        picture=self.wallpapers.get(self.items[index]['uid'])
        if picture:
            pix=picture;scale=max(width/pix.get_width(),height/pix.get_height())
            cr.save();cr.translate((width-pix.get_width()*scale)/2,(height-pix.get_height()*scale)/2);cr.scale(scale,scale)
            Gdk.cairo_set_source_pixbuf(cr,pix,0,0);cr.paint();cr.restore()
        sw,sh,nx,_=self.d.dimensions();sx,sy=width/sw,height/sh
        for w in reversed(self.clients):
            try:
                if not self.d.on(w,index) or w.is_minimized():continue
                x,y,ww,wh=w.get_geometry()
                if self.d.compiz and not self.d.shared(w):
                    ws=w.get_workspace();x+=ws.get_viewport_x()-(index%nx)*sw;y+=ws.get_viewport_y()-(index//nx)*sh
                x,y,ww,wh=x*sx,y*sy,ww*sx,wh*sy
                cr.save();cr.rectangle(x,y,ww,wh);cr.clip()
                pix=self.pixbufs.get(w.get_xid())
                if pix:
                    cr.translate(x,y);cr.scale(ww/pix.get_width(),wh/pix.get_height());Gdk.cairo_set_source_pixbuf(cr,pix,0,0);cr.paint()
                else:
                    cr.set_source_rgb(.18,.19,.21);cr.paint();cr.set_source_rgb(.33,.35,.39);cr.rectangle(x,y,ww,min(6,wh));cr.fill()
                    icon=w.get_mini_icon()
                    if icon:
                        icon=icon.scale_simple(16,16,GdkPixbuf.InterpType.BILINEAR);Gdk.cairo_set_source_pixbuf(cr,icon,x+max(0,(ww-16)/2),y+max(0,(wh-16)/2));cr.paint()
                cr.restore();cr.set_source_rgba(1,1,1,.35);cr.set_line_width(.6);cr.rectangle(x+.3,y+.3,max(0,ww-.6),max(0,wh-.6));cr.stroke()
            except ValueError:continue
        cr.set_source_rgba(.10,.11,.13,.9);cr.rectangle(0,height-5,width,5);cr.fill()
        cr.set_source_rgb(.38,.81,1)
        for x in range(int(width/2)-10,int(width/2)+10,5):cr.rectangle(x,height-4,3,3)
        cr.fill();return False

    def preview_ready(self,xid,pix):
        if not self.alive():return
        self.pixbufs[xid]=pix
        while len(self.pixbufs)>36:self.pixbufs.pop(next(iter(self.pixbufs)))
        for widget in self.thumbs:widget.queue_draw()

    def configure_card(self,card,child,w):
        child.desktop=self.d.desktop_for(w)
        card.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,[Gtk.TargetEntry.new(DRAG_TYPE,Gtk.TargetFlags.SAME_APP,0)],Gdk.DragAction.MOVE)
        xid=w.get_xid()
        def drag_data(_,context,selection,info,stamp):selection.set(selection.get_target(),8,str(xid).encode('ascii'))
        card.connect('drag-data-get',drag_data)
        card.connect('drag-begin',lambda *_:setattr(self,'dragging',True))
        card.connect('drag-end',lambda *_:(setattr(self,'dragging',False),self.win.present() if self.alive() else None))
        card.connect('button-press-event',lambda _,event:self.window_menu(card,xid,event) if event.button==3 else False)
        card.connect('popup-menu',lambda *_:self.window_menu(card,xid,None))

    def window_menu(self,card,xid,event):
        if self.d.busy:return True
        menu=Gtk.Menu();self.menu=menu;menu.get_style_context().add_class('z11-desktop-menu')
        w=self.m.windows.get(xid)
        if not w:self.menu=None;return True
        heading=Gtk.MenuItem(label='Move to');heading.set_sensitive(False);menu.append(heading)
        for desktop in self.d.items():
            index=desktop['id'];item=Gtk.MenuItem(label=desktop['name'])
            item.set_sensitive(not self.d.on(w,index));item.connect('activate',lambda _,i=index:self.move(xid,i));menu.append(item)
        new=Gtk.MenuItem(label='New desktop');new.connect('activate',lambda *_:self.create(xid));menu.append(new)
        def dismissed(*_):
            self.menu=None
            if self.alive():self.win.present()
        menu.connect('deactivate',dismissed);menu.show_all()
        if event:menu.popup_at_pointer(event)
        else:menu.popup_at_widget(card,Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,None)
        return True

    def drop_target(self,widget,index):
        targets=[Gtk.TargetEntry.new(DRAG_TYPE,Gtk.TargetFlags.SAME_APP,0)]
        if index is not None:targets.append(Gtk.TargetEntry.new(DESKTOP_DRAG_TYPE,Gtk.TargetFlags.SAME_APP,1))
        widget.drag_dest_set(Gtk.DestDefaults.ALL,targets,Gdk.DragAction.MOVE)
        def received(_,context,x,y,selection,info,stamp):
            accepted=False
            try:
                data=bytes(selection.get_data()).decode('ascii')
                if info==1 and index is not None:
                    source=next((d['id'] for d in self.d.items() if d['uid']==data),None)
                    if source is not None and not self.d.busy:self.reorder(source,index);accepted=True
                else:
                    xid=int(data)
                    if self.m.windows.get(xid) and not self.d.busy:
                        self.create(xid) if index is None else self.move(xid,index);accepted=True
            except (ValueError,TypeError):pass
            Gtk.drag_finish(context,accepted,False,stamp)
        widget.connect('drag-data-received',received)

    def notice(self,error):
        self.error=str(error)
        if self.alive():self.message.set_text(self.error)

    def switch(self,index):
        if self.d.busy:return
        self.m.close(False);self.d.switch(index)

    def move(self,xid,index):
        if self.d.busy:return
        try:self.d.move(xid,index)
        except ValueError as error:self.notice(error);return
        self.d.wait(lambda:not self.m.windows.get(xid) or self.d.on(self.m.windows.get(xid),index),
                    lambda:self.render() if self.alive() else None,self.notice)

    def create(self,xid=None):
        def done(error,index):
            if error:self.notice(error);return
            if not self.alive():return
            self.selected=index;self.render();self.win.present()
            # Match Windows: the New desktop tile creates in place. Click its
            # preview to enter it; Win+Ctrl+D creates and switches immediately.
        self.d.create(done,xid)
        if self.alive():self.message.set_text('Creating desktop…')

    def remove(self,index):
        def done(error,target):
            if error:self.notice(error);return
            if self.alive():self.selected=target;self.render();self.win.present()
        self.d.remove(index,done)
        if self.alive():self.message.set_text('Moving apps and closing desktop…')

    def reorder(self,source,target):
        if self.d.busy or self.choosing or not 0<=target<len(self.items):return
        self.message.set_text('Moving desktop…');self.transition=True
        def done(error,index):
            if error:self.transition=False;self.notice(error);return
            if self.alive():
                self.selected=index;self.render();self.resume();self.desktop_buttons[index].grab_focus()
        self.d.reorder(source,target,done)

    def desktop_menu(self,widget,index,event):
        if self.d.busy or self.choosing:return True
        menu=Gtk.Menu();self.menu=menu;menu.get_style_context().add_class('z11-desktop-menu')
        for title,callback,enabled in [
                ('Move left',lambda:self.reorder(index,index-1),index>0),
                ('Move right',lambda:self.reorder(index,index+1),index<len(self.items)-1),
                ('Choose background…',lambda:self.choose_background(index),True),
                ('Use shared background / Spotlight',lambda:self.set_background(self.items[index]['uid'],None),True),
                ('Close desktop',lambda:self.remove(index),len(self.items)>1)]:
            item=Gtk.MenuItem(label=title);item.set_sensitive(enabled);item.connect('activate',lambda _,fn=callback:fn());menu.append(item)
        def dismissed(*_):
            self.menu=None
            if self.alive() and not self.modal:self.win.present()
        menu.connect('deactivate',dismissed);menu.show_all()
        if event:menu.popup_at_pointer(event)
        else:menu.popup_at_widget(widget,Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,None)
        return True

    def choose_background(self,index):
        self.modal=True;uid=self.items[index]['uid']
        dialog=Gtk.FileChooserDialog(title='Choose background for '+self.items[index]['name'],transient_for=self.win,action=Gtk.FileChooserAction.OPEN)
        dialog.set_destroy_with_parent(True)
        dialog.set_modal(True);dialog.set_keep_above(True);dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Choose picture',Gtk.ResponseType.OK)
        images=Gtk.FileFilter();images.set_name('JPEG and PNG pictures');images.add_mime_type('image/jpeg');images.add_mime_type('image/png');dialog.add_filter(images)
        # A response callback keeps the GTK loop available while the native
        # file picker is open. No borrowed workspace object is retained.
        def response(_,result):
            path=dialog.get_filename() if result==Gtk.ResponseType.OK else None
            dialog.destroy();self.modal=False
            if self.alive():self.win.present()
            if path:self.set_background(uid,path=path)
        dialog.connect('response',response);dialog.show_all();self.picture_dialog=dialog

    def set_background(self,uid,ident=None,path=None):
        if self.choosing or self.d.busy:return
        self.choosing=True;self.message.set_text('Applying desktop background…')
        def done(error):
            self.choosing=False
            if error:self.notice(error)
            elif self.alive():self.error='';self.render();self.win.present()
        if path:self.m.backgrounds.import_picture(uid,path,done)
        else:self.m.backgrounds.choose(uid,ident,done)

    def load_wallpapers(self):
        identities=[d['uid'] for d in self.items]
        def task():
            import wallpaper
            from desktop_backgrounds import picture_path
            with wallpaper.LOCK:
                state=wallpaper.load();base=state.get('appliedPath') or next(iter(state.get('desktopShared',{}).values()),None)
                if not base:base=wallpaper.current_path()
                paths={uid:str(picture_path(state,uid) or base or '') for uid in identities}
            result={}
            for uid,path in paths.items():
                if not path:continue
                try:result[uid]=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,480,270,True)
                except GLib.Error:pass
            return result
        def done(pictures):
            if self.alive():
                self.wallpapers=pictures
                for drawing in self.thumbs:drawing.queue_draw()
        self.m.hub.background(task,done,lambda _:None)
