"""Saved Snap Group management and on-demand application/layout restoration."""
from gi.repository import Gtk, Gdk, Pango
from multitasking import label,button
from saved_groups import catalog,identify


class SavedGroupsView:
    def __init__(self,m):
        self.m=m;self.saved=m.saved_groups;self.editing=False;self.modal=False;self.query=''
        target=m.windows.active();m.origin=target.get_xid() if target else None
        area=m.area(target);height=min(650,max(360,240+110*len(self.saved.store.groups)),area[3]-40)
        self.win,self.box=m.shell('Saved groups',min(860,area[2]-40),height,area)
        self.win.get_style_context().add_class('z11-saved-layouts')
        self.win.connect('destroy',lambda *_:self.saved.cancel())
        self.render();self.win.show_all();self.win.present()

    def alive(self):return self.m.window is self.win
    def hold_focus(self):return self.modal or self.editing or self.saved.operation is not None

    def render(self):
        for child in self.box.get_children():child.destroy()
        head=Gtk.Box(spacing=16);head.pack_start(label('Saved groups','z11-heading'),True,True,0)
        self.capture_button=button('Save current layout…',self.save_current_dialog,'z11-primary')
        head.pack_start(self.capture_button,False,False,0)
        head.pack_end(button('Close',lambda:self.m.close()),False,False,0);self.box.pack_start(head,False,False,0)
        intro=label('Reopen your apps together, with their saved layout.','z11-muted');self.box.pack_start(intro,False,False,0)
        hint=label('Documents, browser tabs and terminal sessions follow each app’s own restore settings.','z11-small');hint.set_line_wrap(True);self.box.pack_start(hint,False,False,0)
        self.search=Gtk.SearchEntry(placeholder_text='Search saved layouts and apps')
        self.search.get_accessible().set_name('Search saved layouts and apps');self.search.set_text(self.query)
        self.search.connect('changed',lambda entry:self.filter_rows(entry.get_text()))
        self.box.pack_start(self.search,False,False,0);self.rows=[]
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);self.box.pack_start(scroll,True,True,0)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);scroll.add(content);self.controls=content
        apps=catalog()
        for recipe in self.saved.store.groups:
            row=Gtk.Box(spacing=16);row.set_border_width(12);row.get_style_context().add_class('z11-saved-card');content.pack_start(row,False,False,0)
            canvas=Gtk.DrawingArea();canvas.set_size_request(124,78);canvas.connect('draw',self.draw,recipe);row.pack_start(canvas,False,False,0)
            details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);row.pack_start(details,True,True,0)
            name=Gtk.Entry();name.set_text(recipe['name']);name.set_max_length(80);name.set_width_chars(18)
            name.recipe_id=recipe['id'];name.get_accessible().set_name('Rename saved group '+recipe['name']);details.pack_start(name,False,False,0)
            name.connect('focus-in-event',lambda *_:setattr(self,'editing',True))
            def rename(entry,*_,ident=recipe['id'],card=row):
                self.editing=False
                current=next((g for g in self.saved.store.groups if g['id']==ident),None)
                if not self.alive() or not current or current['name']==entry.get_text().strip():return
                try:
                    self.saved.store.rename(ident,entry.get_text())
                    self.rows=[(r,(entry.get_text()+' '+card.search_apps).casefold() if r is card else terms) for r,terms in self.rows]
                    self.filter_rows(self.query)
                except (OSError,ValueError) as error:self.notice(str(error))
            name.connect('activate',rename);name.connect('focus-out-event',lambda entry,event,f=rename:(f(entry),False)[1])
            names=[apps[r['app']].get_display_name() if r['app'] in apps else (r['app']+' (not installed)' if r['app'] else r['class']+' (must be open)') for r in recipe['members']]
            row.search_apps=' '.join(names)
            self.rows.append((row,(recipe['name']+' '+' '.join(names)).casefold()))
            text=label(' · '.join(names),'z11-small');text.set_ellipsize(Pango.EllipsizeMode.END);text.set_max_width_chars(38);text.set_tooltip_text(' · '.join(names));details.pack_start(text,False,False,0)
            if recipe.get('kind')=='layout':
                startup=Gtk.CheckButton(label='Restore automatically when I sign in')
                startup.set_active(self.saved.store.data.get('startup_layout')==recipe['id'])
                startup.set_tooltip_text('Restore this layout once after sign-in. Only one layout can be selected. Apps may open; documents follow each app’s settings.')
                def toggle(widget,ident=recipe['id']):
                    try:self.saved.store.set_startup(ident if widget.get_active() else '');self.render()
                    except (OSError,ValueError) as error:self.notice(str(error))
                startup.connect('toggled',toggle);details.pack_start(startup,False,False,0)
            actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);row.pack_end(actions,False,False,0)
            restore=button('Restore layout' if recipe.get('kind')=='layout' else 'Reopen group',lambda ident=recipe['id']:self.restore(ident),'z11-primary');restore.get_accessible().set_name('Reopen saved group '+recipe['name']);actions.pack_start(restore,False,False,0)
            remove=button('Remove',lambda ident=recipe['id']:self.remove(ident));remove.get_accessible().set_name('Remove saved group '+recipe['name']);actions.pack_start(remove,False,False,0)
        for group in self.m.groups:
            if getattr(group,'saved_id',None) in {g['id'] for g in self.saved.store.groups}:continue
            row=Gtk.Box(spacing=12);row.pack_start(label(f'Open group · {len(group)} windows','z11-muted'),True,True,0)
            row.pack_end(button('Choose apps and save…',lambda g=group:self.save_dialog(g)),False,False,0);content.pack_start(row,False,False,0)
        if not self.saved.store.groups:
            empty=label('Use Save current layout to remember your open windows.\nSnap Assist groups also appear here.','z11-muted');empty.set_line_wrap(True);content.pack_start(empty,False,False,8)
        self.no_matches=label('No saved layouts match your search.','z11-muted');content.pack_start(self.no_matches,False,False,8)
        self.status=label(self.saved.store.error or self.saved.last_error,'z11-muted');self.status.set_line_wrap(True);self.status.set_max_width_chars(85);self.box.pack_start(self.status,False,False,0)
        self.cancel_button=button('Cancel restore',self.cancel);self.cancel_button.set_no_show_all(True)
        self.box.pack_end(self.cancel_button,False,False,0)
        self.box.show_all();self.cancel_button.hide();self.filter_rows(self.query)

    def filter_rows(self,text):
        self.query=text
        if not hasattr(self,'no_matches'):return
        query=text.strip().casefold();count=0
        for row,terms in self.rows:
            matched=all(term in terms for term in query.split());row.set_visible(matched);count+=int(matched)
        self.no_matches.set_visible(bool(query) and not count)

    def key(self,event):
        if self.modal:return False
        if event.keyval in (Gdk.KEY_f,Gdk.KEY_F) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus();self.search.select_region(0,-1);return True
        if event.keyval!=Gdk.KEY_Escape:return False
        focus=self.win.get_focus();ident=getattr(focus,'recipe_id',None)
        recipe=next((g for g in self.saved.store.groups if g['id']==ident),None)
        if recipe and focus.get_text()!=recipe['name']:
            focus.set_text(recipe['name']);self.editing=False;self.search.grab_focus();return True
        if self.query:self.search.set_text('');self.search.grab_focus();return True
        return False

    def notice(self,text):
        if self.alive():self.status.set_text(text)

    def restore(self,ident):
        self.editing=False
        def status(text,finished):
            if not self.alive():return
            self.notice(text);self.controls.set_sensitive(finished);self.capture_button.set_sensitive(finished);self.search.set_sensitive(finished);self.cancel_button.set_visible(not finished)
            if finished:
                if text=='Layout restored.':
                    self.m.close(False)
                    group=next((g for g in self.m.groups if getattr(g,'saved_id',None)==ident),None)
                    if group:self.m.activate_group(group)
                else:self.win.present_with_time(self.m.windows.timestamp())
        try:self.saved.restore(ident,status)
        except (ValueError,OSError) as error:self.notice(str(error))

    def cancel(self):
        self.saved.cancel();self.controls.set_sensitive(True);self.capture_button.set_sensitive(True);self.search.set_sensitive(True);self.cancel_button.hide();self.notice('Restore cancelled. Apps already opened stay open.')

    def remove(self,ident):
        try:self.saved.store.remove(ident);self.render()
        except (ValueError,OSError) as error:self.notice(str(error))

    def save_current_dialog(self):
        if self.saved.operation:self.notice('Wait for the current restore to finish.');return
        try:snapshot=self.saved.current_layout()
        except (ValueError,OSError) as error:self.notice(str(error));return
        self.modal=True
        dialog=Gtk.Dialog(title='Save current layout',transient_for=self.win,modal=True,destroy_with_parent=True)
        dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Save layout',Gtk.ResponseType.OK)
        box=dialog.get_content_area();box.set_border_width(20);box.set_spacing(12)
        count=len(snapshot[0]);screens=len({r['monitor']['index'] for r in snapshot[0]})
        box.pack_start(label(f'{count} windows across {screens} displays on this desktop.'),False,False,0)
        name=Gtk.Entry(text='My desktop layout',activates_default=True);name.get_accessible().set_name('Layout name')
        box.pack_start(name,False,False,0)
        note=label('Saves positions and window states. Documents and tabs follow each app’s restore settings.');note.set_line_wrap(True);note.set_max_width_chars(55);box.pack_start(note,False,False,0)
        error=label('');box.pack_start(error,False,False,0)
        def respond(widget,response):
            if response==Gtk.ResponseType.OK:
                try:
                    if not name.get_text().strip():raise ValueError('Enter a layout name.')
                    self.saved.save_current(name.get_text(),snapshot)
                except (ValueError,OSError) as problem:error.set_text(str(problem));return
            self.modal=False;widget.destroy()
            if self.alive():self.render();self.win.present()
        dialog.connect('response',respond);dialog.set_default_response(Gtk.ResponseType.OK);dialog.show_all();name.grab_focus();name.select_region(0,-1)

    def save_dialog(self,group):
        self.modal=True;dialog=Gtk.Dialog(title='Save Snap Group',transient_for=self.win,modal=True)
        dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Save group',Gtk.ResponseType.OK)
        dialog.set_default_size(520,280);box=dialog.get_content_area();box.set_border_width(20);box.set_spacing(12)
        name=Gtk.Entry();name.set_placeholder_text('Group name');name.set_text('My group');box.pack_start(name,False,False,0)
        apps=catalog();choices={}
        for xid,_ in group:
            w=self.m.windows.get(xid)
            if not w:continue
            text=label(w.get_name());text.set_ellipsize(Pango.EllipsizeMode.END);text.set_max_width_chars(50);box.pack_start(text,False,False,0)
            combo=Gtk.ComboBoxText();combo.append('','Choose the app that opens this window')
            for ident,app in sorted(apps.items(),key=lambda p:p[1].get_display_name().casefold()):combo.append(ident,app.get_display_name())
            combo.set_active_id(identify(w,apps) or '');box.pack_start(combo,False,False,0);choices[xid]=combo
        error=label('','z11-muted');box.pack_start(error,False,False,0)
        def respond(widget,response):
            if response==Gtk.ResponseType.OK:
                try:
                    if len(choices)!=len(group) or not all(c.get_active_id() for c in choices.values()):raise ValueError('Choose an app for every window.')
                    self.saved.capture(group,overrides={x:c.get_active_id() for x,c in choices.items()},name=name.get_text())
                except (ValueError,OSError) as problem:error.set_text(str(problem));return
            self.modal=False;widget.destroy()
            if self.alive():self.render();self.win.present()
        dialog.connect('response',respond);dialog.show_all()

    def draw(self,widget,cr,recipe):
        width,height=widget.get_allocated_width(),widget.get_allocated_height()
        cr.set_source_rgb(.10,.11,.13);cr.paint()
        rects=[]
        for member in recipe['members']:
            x,y,w,h=member['rect']
            if recipe.get('kind')=='layout':
                a,b,c,d=member['monitor']['area'];x,y,w,h=a+x*c,b+y*d,w*c,h*d
            rects.append((x,y,w,h))
        left=min(r[0] for r in rects);top=min(r[1] for r in rects)
        right=max(r[0]+r[2] for r in rects);bottom=max(r[1]+r[3] for r in rects)
        for x,y,w,h in rects:
            if recipe.get('kind')=='layout':x,y,w,h=(x-left)/max(1,right-left),(y-top)/max(1,bottom-top),w/max(1,right-left),h/max(1,bottom-top)
            cr.set_source_rgba(.38,.81,1,.7)
            cr.rectangle(x*width+1,y*height+1,max(1,w*width-2),max(1,h*height-2));cr.fill()
        return False
