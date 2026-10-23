#!/usr/bin/python3
"""Native lock-screen personalization. Preview is never an authentication surface."""
import datetime
import subprocess
import threading
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib
import lockscreen

CSS = b'''
window { background: #202020; color: #f4f4f4; }
.header { font-size: 26px; font-weight: 600; }
.muted { color: #b8b8b8; font-size: 12px; }
.card { background: #292929; border: 1px solid #393939; border-radius: 10px; padding: 16px; }
button, combobox button { border-radius: 6px; padding: 8px 12px; }
button.suggested-action { background: #60cdff; color: #10212b; }
.status { color: #9bdcff; }
'''
NAMES = [('spotlight','Windows Spotlight'), ('bing','Bing image of the day'), ('zorin','Zorin wallpapers'), ('desktop','Use desktop background'), ('picture','Picture')]

class Preferences(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.zorin11.LockScreenSettings', flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect('activate', self.activate_window)

    def activate_window(self, *_):
        if self.get_active_window(): self.get_active_window().present(); return
        self.draft = lockscreen.load(); self.dirty = False; self.busy = False; self.pixbuf = None; self.generation = 0
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        provider = Gtk.CssProvider(); provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title='Lock screen settings', default_width=760, default_height=850)
        scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.window.add(scroll)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24); scroll.add(root)
        title = Gtk.Label(label='Lock screen', xalign=0); title.get_style_context().add_class('header'); root.pack_start(title,False,False,0)
        subtitle = Gtk.Label(label='Personalize your first view. GNOME handles secure unlocking.',xalign=0)
        subtitle.get_style_context().add_class('muted'); root.pack_start(subtitle,False,False,0)
        self.preview = Gtk.DrawingArea(height_request=300); self.preview.connect('draw',self.draw_preview); root.pack_start(self.preview,False,False,0)
        hint = Gtk.Label(label='Preview · Password entry and account photo use the native GNOME unlock screen.', xalign=0, wrap=True)
        hint.get_style_context().add_class('muted'); root.pack_start(hint,False,False,0)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); card.get_style_context().add_class('card'); root.pack_start(card,False,False,0)
        self.source = Gtk.ComboBoxText()
        for ident,name in NAMES:self.source.append(ident,name)
        self.source.set_active_id(self.draft['source']); self.row(card,'Personalize your lock screen',self.source)
        self.source.connect('changed', self.source_changed)
        self.zorin = Gtk.ComboBoxText(); self.collection = lockscreen.gnome_wallpaper.catalog()
        for entry in self.collection:self.zorin.append(entry['path'],entry['title'])
        selected=next((e['path'] for e in self.collection if e['path']==self.draft['path']), self.collection[0]['path'] if self.collection else None)
        for cell in self.zorin.get_cells():
            cell.set_property('ellipsize', 3); cell.set_property('max-width-chars', 28)
        self.zorin.set_active_id(selected); self.zorin.connect('changed',self.zorin_changed)
        self.zorinrow=self.row(card,'Included Zorin wallpapers',self.zorin)
        buttons=Gtk.Box(spacing=8); self.next=Gtk.Button(label='Get another picture'); self.next.connect('clicked',self.fetch_photo); buttons.pack_start(self.next,False,False,0)
        self.browse=Gtk.Button(label='Browse pictures'); self.browse.connect('clicked',self.browse_photo); buttons.pack_start(self.browse,False,False,0)
        card.pack_start(buttons,False,False,0)
        self.daily=Gtk.Switch(active=self.draft['daily']);self.dailyrow=self.row(card,'Refresh online photos daily',self.daily)
        self.enabled=Gtk.Switch(active=self.draft['enabled']);self.row(card,'Windows 11 lock-screen appearance',self.enabled)
        self.credit=Gtk.Switch(active=self.draft['showCredit']);self.row(card,'Show photo title and credit',self.credit)
        self.dimming=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,45,1);self.dimming.set_size_request(200,-1);self.dimming.set_value(self.draft['dimming']);self.dimming.set_digits(0)
        self.row(card,'Background dimming (%)',self.dimming)
        for widget,key in ((self.daily,'daily'),(self.enabled,'enabled'),(self.credit,'showCredit')):
            widget.connect('notify::active',lambda w,_,k=key:self.changed(k,w.get_active()))
        self.dimming.connect('value-changed',lambda w:self.changed('dimming',round(w.get_value())))
        self.status=Gtk.Label(xalign=0,wrap=True);self.status.get_style_context().add_class('status');root.pack_start(self.status,False,False,0)
        actions=Gtk.Box(spacing=8);root.pack_start(actions,False,False,0)
        self.apply_button=Gtk.Button(label='Apply');self.apply_button.get_style_context().add_class('suggested-action');self.apply_button.connect('clicked',self.apply_changes);actions.pack_end(self.apply_button,False,False,0)
        self.revert_button=Gtk.Button(label='Revert');self.revert_button.connect('clicked',self.revert);actions.pack_end(self.revert_button,False,False,0)
        timing=Gtk.Button(label='Native lock timing and privacy');timing.connect('clicked',lambda *_:subprocess.Popen(['gnome-control-center','privacy'],start_new_session=True));actions.pack_start(timing,False,False,0)
        self.window.show_all();self.visibility();self.update_preview();self.activation_status()
        try:
            self.monitor=Gio.File.new_for_path(str(lockscreen.ROOT)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES,None)
            self.monitor.connect('changed',self.external_change)
            self.window.connect('destroy',lambda *_:self.monitor.cancel())
        except GLib.Error:self.monitor=None

    def row(self, parent, text, widget):
        box=Gtk.Box(spacing=16);label=Gtk.Label(label=text,xalign=0,wrap=True);box.pack_start(label,True,True,0);box.pack_end(widget,False,False,0);parent.pack_start(box,False,False,0);return box

    def activation_status(self):
        try:
            result=Gio.bus_get_sync(Gio.BusType.SESSION,None).call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','GetExtensionInfo',GLib.Variant('(s)',(lockscreen.UUID,)),None,0,1500,None).unpack()[0]
            state=result.get('state')
            if state==1:
                message='Applied. The next lock screen uses these settings.' if self.draft['enabled'] else 'Applied. Native GNOME appearance is selected.'
            elif state==2:message='Saved. Enable Axentra Windows 11 Lock Screen in GNOME Extensions to use this appearance.'
            elif state==3:message='Saved, but GNOME could not load the extension: '+str(result.get('error','Check GNOME Extensions.'))[:160]
            else:message='Saved settings take effect after your next normal sign-in. GNOME has not loaded this new extension yet.'
        except Exception:message='Saved. GNOME extension status is unavailable; first activation requires a normal sign-in.'
        self.status.set_text(message)

    def visibility(self):
        source=self.draft['source'];self.zorinrow.set_visible(source=='zorin');self.browse.set_visible(source=='picture');self.next.set_visible(source in ('spotlight','bing'));self.dailyrow.set_visible(source in ('spotlight','bing'))

    def external_change(self,monitor,file,other,event):
        if any(f and f.get_basename()=='state.json' for f in (file,other)):
            GLib.idle_add(self.reload_if_clean)

    def reload_if_clean(self):
        if not self.dirty and not self.busy:self.revert()
        return False

    def changed(self,key,value):
        self.dirty=True
        self.draft[key]=value;self.status.set_text('Preview changes, then choose Apply.');self.preview.queue_draw()

    def source_changed(self,*_):
        self.dirty=True
        self.generation+=1;self.draft['source']=self.source.get_active_id();self.visibility()
        if self.draft['source']=='zorin':self.zorin_changed()
        elif self.draft['source']=='desktop':self.update_preview()
        else:self.update_preview()
        self.status.set_text('Preview changes, then choose Apply.' + (' Get a picture to preview this service.' if self.draft['source'] in ('spotlight','bing') else ''))

    def zorin_changed(self,*_):
        if self.draft['source']!='zorin':return
        path=self.zorin.get_active_id()
        if path:
            self.dirty=True
            self.draft.update(path=path,title=Path(path).stem.replace('-',' '),credit='Included with Zorin OS',assetSource='zorin',lastDay='');self.update_preview();self.status.set_text('Preview changes, then choose Apply.')

    def update_preview(self):
        path=lockscreen.gnome_wallpaper.current_path() if self.draft['source']=='desktop' else Path(self.draft['path'])
        try:self.pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),1200,700,True)
        except Exception:self.pixbuf=None
        self.preview.queue_draw()

    def draw_preview(self,widget,cr):
        w,h=widget.get_allocated_width(),widget.get_allocated_height();cr.set_source_rgb(.08,.10,.13);cr.paint()
        if self.pixbuf:
            scale=max(w/self.pixbuf.get_width(),h/self.pixbuf.get_height());cr.save();cr.translate((w-self.pixbuf.get_width()*scale)/2,(h-self.pixbuf.get_height()*scale)/2);cr.scale(scale,scale);Gdk.cairo_set_source_pixbuf(cr,self.pixbuf,0,0);cr.paint();cr.restore()
        cr.set_source_rgba(0,0,0,self.draft['dimming']/100);cr.paint();cr.set_source_rgb(1,1,1)
        now=datetime.datetime.now()
        for text,size,y in (((now.strftime('%H:%M') if Gio.Settings.new('org.gnome.desktop.interface').get_string('clock-format')=='24h' else now.strftime('%I:%M').lstrip('0')),58,118),(now.strftime('%A, %B %d').replace(' 0',' '),17,149)):
            cr.select_font_face('Sans',0,0);cr.set_font_size(size);ext=cr.text_extents(text);cr.move_to((w-ext.width)/2-ext.x_bearing,y);cr.show_text(text)
        if self.draft['showCredit']:
            title='Your desktop background' if self.draft['source']=='desktop' else self.draft['title']
            cr.set_font_size(13);cr.move_to(20,h-30);cr.show_text(title[:72])

    def fetch_photo(self,*_):
        if self.busy:return
        self.busy=True;self.generation+=1;generation=self.generation;source=self.draft['source'];self.next.set_sensitive(False);self.apply_button.set_sensitive(False);self.status.set_text('Loading a photo… Your current lock screen stays unchanged.')
        def finish(photo,error):
            self.busy=False;self.next.set_sensitive(True);self.apply_button.set_sensitive(True)
            if generation!=self.generation:return False
            if error:self.status.set_text('Could not load a photo. Keeping your current picture. '+str(error)[:180])
            else:self.dirty=True;self.draft.update(photo);self.update_preview();self.status.set_text('Photo ready. Choose Apply to use it on the lock screen.')
            return False
        def worker():
            try:photo,error=lockscreen.prepare(source),None
            except Exception as error_:photo,error=None,str(error_)
            GLib.idle_add(finish,photo,error)
        threading.Thread(target=worker,daemon=True).start()

    def browse_photo(self,*_):
        dialog=Gtk.FileChooserNative.new('Choose a lock-screen picture',self.window,Gtk.FileChooserAction.OPEN,'Choose','Cancel')
        filt=Gtk.FileFilter();filt.set_name('Pictures');filt.add_pixbuf_formats();dialog.add_filter(filt)
        if dialog.run()==Gtk.ResponseType.ACCEPT:
            try:
                self.dirty=True
                path=lockscreen.validate_image(dialog.get_filename());self.draft.update(path=str(path),title=path.stem,credit='',assetSource='picture',lastDay='');self.update_preview();self.status.set_text('Preview changes, then choose Apply.')
            except Exception as error:self.status.set_text(str(error))
        dialog.destroy()

    def apply_changes(self,*_):
        try:self.draft=lockscreen.apply(self.draft);self.dirty=False;self.activation_status()
        except Exception as error:self.status.set_text('Could not apply: '+str(error))

    def revert(self,*_):
        self.generation+=1;state=lockscreen.load();self.source.set_active_id(state['source'])
        self.zorin.set_active_id(state['path'])
        for widget,key in ((self.daily,'daily'),(self.enabled,'enabled'),(self.credit,'showCredit')):widget.set_active(state[key])
        self.dimming.set_value(state['dimming']);self.draft=state;self.dirty=False;self.visibility();self.update_preview();self.activation_status()

if __name__=='__main__':
    Preferences().run(None)
