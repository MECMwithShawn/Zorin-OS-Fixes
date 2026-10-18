"""Native Compiz slides and a temporary, input-transparent desktop crossfade.

The window manager animates live applications. Only Xfdesktop's own backing
pixmap is copied for the wallpaper fade; app windows are never screenshotted.
The snapshot stays in memory and is discarded when the transition finishes.
"""
import json
import os
from pathlib import Path
import subprocess
import struct

CONFIG=Path(os.environ.get('ZORIN11_CONFIG_DIR',str(Path.home()/'.config/zorin11-hub')))
STATE=CONFIG/'desktop-motion.json'
DURATIONS=(180,320,480)


def load():
    try:state=json.loads(STATE.read_text())
    except (OSError,ValueError):state={}
    return {'enabled':state.get('enabled',True) is not False,
            'duration':state.get('duration',320) if state.get('duration',320) in DURATIONS else 320}


def profile_values(preferences,refresh_rates,gtk_motion=True):
    rates=[round(rate/1000) for rate in refresh_rates if 10000<=rate<=1000000]
    # Keep the native budget short: Wall holds an input grab while sliding.
    # Increasing its duration with refresh rate delays unrelated shortcuts.
    duration=preferences['duration']/1000
    values={'wall':{'slide_duration':duration if preferences['enabled'] and gtk_motion else 0.0,
                    'show_switcher':False,'miniscreen':False,'preview_timeout':0.0},
            'opengl':{'sync_to_vblank':True},
            'composite':{'detect_refresh_rate':not bool(rates)}}
    # The Compiz shipped with Zorin caps this setting at 200. Its bindings
    # silently reject larger values, which would otherwise retain the old rate.
    if rates:values['composite']['refresh_rate']=min(200,max(rates))
    return values


def configure_profile(context):
    # Runs in a private-profile subprocess, never in the GTK application's
    # worker threads. RandR's legacy XRRConfigCurrentRate can report 50 Hz for
    # a 240 Hz display; GDK reads each connected output's current mode.
    import gi
    gi.require_version('Gdk','3.0');gi.require_version('Gtk','3.0')
    from gi.repository import Gdk,Gtk
    display=Gdk.Display.get_default();settings=Gtk.Settings.get_default()
    rates=[display.get_monitor(i).get_refresh_rate() for i in range(display.get_n_monitors())] if display else []
    values=profile_values(load(),rates,settings.get_property('gtk-enable-animations') if settings else True)
    for plugin,options in values.items():
        for option,value in options.items():
            setting=context.Plugins[plugin].Screen[option];setting.Value=value
            accepted=abs(setting.Value-value)<.00001 if isinstance(value,float) else setting.Value==value
            if not accepted:raise RuntimeError('The window manager rejected '+plugin+'.'+option)


def refresh_profile():
    import effects
    # No WM replacement or plugin-list changes. Existing wobble and desktop
    # counts are left to their own controls.
    subprocess.run(['/usr/bin/python3',str(Path(__file__).resolve()),'--refresh'],
                   env=effects.environment(),check=True,capture_output=True,timeout=8)


def configure(name,value):
    state=load()
    if name=='desktopAnimations':
        if type(value) is not bool:raise ValueError('Animation effects needs an on/off value.')
        state['enabled']=value
    elif name=='desktopAnimationDuration':
        if type(value) is not int or value not in DURATIONS:raise ValueError('Choose a supported animation speed.')
        state['duration']=value
    else:raise ValueError('Unknown desktop motion setting.')
    CONFIG.mkdir(parents=True,exist_ok=True)
    previous=STATE.read_bytes() if STATE.exists() else None
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(state)+'\n');tmp.replace(STATE)
    try:refresh_profile()
    except Exception:
        if previous is None:STATE.unlink(missing_ok=True)
        else:tmp.write_bytes(previous);tmp.replace(STATE)
        # A failed write does not leave the switch reporting a new preference.
        raise


class BackdropFade:
    def __init__(self,m):
        self.m=m;self.window=None;self.generation=0;self.watchdog=0;self.tick=0;self.stopped=False;self.fading=False

    def enabled(self):
        from gi.repository import Gdk,Gtk
        return (not self.stopped and self.m.desktops.compiz and Gdk.Screen.get_default().is_composited()
                and load()['enabled'] and Gtk.Settings.get_default().get_property('gtk-enable-animations'))

    def clear(self):
        from gi.repository import GLib
        self.generation+=1
        self.fading=False
        if self.watchdog:GLib.source_remove(self.watchdog);self.watchdog=0
        if self.window:
            if self.tick:self.window.remove_tick_callback(self.tick);self.tick=0
            self.window.destroy();self.window=None

    def close(self):self.stopped=True;self.clear()

    def begin(self,ready):
        from gi.repository import Wnck,GdkPixbuf,GLib
        self.clear();generation=self.generation
        # Store primitives only; a native Wnck window can disappear before the
        # capture helper returns. X errors stay isolated in that subprocess.
        desktop=next(((w.get_xid(),tuple(w.get_geometry())) for w in self.m.windows.screen.get_windows()
                      if w.get_window_type()==Wnck.WindowType.DESKTOP and w.get_class_instance_name()=='xfdesktop'),None)
        if not self.enabled() or not desktop:ready();return
        xid,rect=desktop
        def capture():
            result=subprocess.run(['/usr/bin/python3',str(Path(__file__).with_name('window_preview.py')),str(xid),'--desktop'],
                                  capture_output=True,timeout=1)
            data=result.stdout
            if not data.startswith(b'Z11D') or len(data)<12:return None
            width,height=struct.unpack('!II',data[4:12])
            if not 1<=width*height<=18000000 or len(data)!=12+width*height*3:return None
            return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data[12:]),GdkPixbuf.Colorspace.RGB,False,8,width,height,width*3)
        def show(picture):
            if self.stopped:return
            if generation==self.generation and picture is not None and self.enabled():self.show(picture,rect,xid)
            ready()
        self.m.hub.background(capture,show,lambda _:show(None))

    def show(self,picture,rect,xid):
        import cairo
        from gi.repository import Gtk,Gdk,GdkX11,GLib
        x,y,width,height=rect
        win=Gtk.Window(title='Desktop background transition');self.window=win
        visual=win.get_screen().get_rgba_visual()
        if visual:win.set_visual(visual)
        win.set_app_paintable(True);self.opacity=1.0
        def clear(widget,cr):
            cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER);return False
        win.connect('draw',clear)
        win.set_type_hint(Gdk.WindowTypeHint.DESKTOP);win.set_decorated(False)
        win.set_accept_focus(False);win.set_focus_on_map(False);win.set_keep_below(True)
        win.set_skip_taskbar_hint(True);win.set_skip_pager_hint(True);win.stick()
        win.set_default_size(width,height);win.move(x,y)
        area=Gtk.DrawingArea()
        def draw(widget,cr):
            cr.scale(width/picture.get_width(),height/picture.get_height())
            Gdk.cairo_set_source_pixbuf(cr,picture,0,0);cr.paint_with_alpha(self.opacity);return True
        area.connect('draw',draw);win.add(area)
        def mapped(*_):
            window=win.get_window();window.input_shape_combine_region(cairo.Region(),0,0)
            # Stay above Xfdesktop but below other desktop surfaces and apps.
            display=Gdk.Display.get_default();display.error_trap_push()
            other=GdkX11.X11Window.foreign_new_for_display(display,xid)
            if other:window.restack(other,True)
            display.error_trap_pop_ignored()
        win.connect('map-event',mapped);win.show_all()
        # Always release the surface if a service/worker stops responding.
        def expired():self.watchdog=0;self.clear();return False
        self.watchdog=GLib.timeout_add(1500,expired)

    def finish(self):
        from gi.repository import GLib
        if not self.window or self.fading:return
        self.fading=True
        generation=self.generation;started=[None];duration=min(320,load()['duration'])*1000
        # Xfdesktop loads its image asynchronously after the Xfconf response.
        # Two frame intervals avoid exposing its old backing pixmap too early.
        def start():
            if not self.window or generation!=self.generation:return False
            def frame(widget,clock,*_):
                now=clock.get_frame_time()
                if started[0] is None:started[0]=now
                progress=min(1,(now-started[0])/duration)
                self.opacity=(1-progress)**2;widget.queue_draw()
                if progress>=1:
                    self.tick=0;self.clear();return False
                return True
            self.tick=self.window.add_tick_callback(frame);return False
        GLib.timeout_add(50,start)


if __name__=='__main__':
    import effects
    if 'compiz' in effects.wm_name():
        import compizconfig
        context=compizconfig.Context();configure_profile(context);context.Write()
