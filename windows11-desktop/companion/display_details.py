"""Read-only GNOME display diagnostics and a standalone Advanced display window."""
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gio,GLib,Gtk,Gdk

SERVICE='org.gnome.Mutter.DisplayConfig'
PATH='/org/gnome/Mutter/DisplayConfig'
ROTATIONS=['Landscape','Portrait (90°)','Landscape (180°)','Portrait (270°)',
           'Landscape, flipped','Portrait (90°), flipped','Landscape (180°), flipped','Portrait (270°), flipped']


def finite(value,default=None):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else default


def parse_state(state,resources=None):
    """Match logical groups by full monitor identity; primary appears first."""
    physical={}
    if resources:
        for output in resources[2]:
            props=output[-1]
            physical[(output[4],props.get('vendor',''),props.get('product',''),props.get('serial',''))]=props
    groups={tuple(spec):(index,logical) for index,logical in enumerate(state[2]) for spec in logical[5]}
    rows=[]
    for spec,modes,props in state[1]:
        spec=tuple(spec);group,logical=groups.get(spec,(None,None))
        current=next((m for m in modes if m[-1].get('is-current')),None)
        preferred=next((m for m in modes if m[-1].get('is-preferred')),None)
        size=physical.get(spec,{})
        width,height=finite(size.get('width-mm')),finite(size.get('height-mm'))
        valid_size=width and height and width>0 and height>0
        dpi=(current[1]*25.4/width,current[2]*25.4/height) if current and valid_size else None
        rows.append(dict(connector=spec[0],name=str(props.get('display-name') or spec[0]),
            builtin=bool(props.get('is-builtin')),active=logical is not None and current is not None,
            primary=bool(logical and logical[4]),group=group,
            mirrored=bool(logical and len(logical[5])>1),
            resolution=(int(current[1]),int(current[2])) if current else None,
            refresh=finite(current[3]) if current else None,
            preferred=(int(preferred[1]),int(preferred[2])) if preferred else None,
            scale=finite(logical[2]) if logical else None,
            rotation=ROTATIONS[logical[3]] if logical and 0<=logical[3]<len(ROTATIONS) else 'Unavailable',
            position=(int(logical[0]),int(logical[1])) if logical else None,
            size=(width,height) if valid_size else None,dpi=dpi,
            modes=sorted(set((int(m[1]),int(m[2]),round(m[3],3)) for m in modes if finite(m[3]) is not None),reverse=True)))
    return sorted(rows,key=lambda r:(not r['primary'],not r['active'],r['connector']))


def run(argv):
    if not shutil.which(argv[0]):return ''
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=3,env=dict(os.environ,LC_ALL='C'))
        return p.stdout if p.returncode==0 else ''
    except (OSError,subprocess.TimeoutExpired):return ''


def parse_gpus(text):
    result=[]
    for line in text.splitlines():
        try:fields=shlex.split(line)
        except ValueError:continue
        if len(fields)>=4 and fields[1] in ('VGA compatible controller','3D controller','Display controller'):
            result.append({'slot':fields[0],'name':fields[2]+' '+fields[3]})
    return result


def collect():
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def read(method):return bus.call_sync(SERVICE,PATH,SERVICE,method,None,None,Gio.DBusCallFlags.NONE,3000,None).unpack()
    state=read('GetCurrentState')
    try:resources=read('GetResources')
    except GLib.Error:resources=None
    # GetResources can race a display hotplug. Discard it if its serial differs.
    if resources and resources[0]!=state[0]:resources=None
    renderer=next((line.split(':',1)[1].strip() for line in run(['glxinfo','-B']).splitlines() if line.startswith('OpenGL renderer string:')),None)
    return dict(monitors=parse_state(state,resources),gpus=parse_gpus(run(['lspci','-Dmm'])),
                renderer=renderer,backend=str(state[3].get('renderer','Unavailable')),
                session=os.environ.get('XDG_SESSION_TYPE','Unavailable'))


def resolution(value):return f'{value[0]} × {value[1]}' if value else 'Unavailable'


def fields(row):
    size=row['size'];dpi=row['dpi']
    return [
        ('Connection',row['connector']+(' · Built-in' if row['builtin'] else '')),
        ('Status',('Active'+(' · Main display' if row['primary'] else '')+(' · Mirrored' if row['mirrored'] else '')) if row['active'] else 'Inactive'),
        ('Current resolution',resolution(row['resolution'])),
        ('Preferred resolution',resolution(row['preferred'])),
        ('Refresh rate',f"{row['refresh']:.2f} Hz" if row['refresh'] is not None else 'Unavailable'),
        ('Scale',f"{row['scale']*100:g}%" if row['scale'] is not None else 'Unavailable'),
        ('Orientation',row['rotation']),
        ('Desktop position',f"{row['position'][0]}, {row['position'][1]}" if row['position'] else 'Unavailable'),
        ('Reported panel size',f'{size[0]:g} × {size[1]:g} mm · {math.hypot(*size)/25.4:.1f} inches' if size else 'Unavailable'),
        ('Pixel density at current mode',f'{dpi[0]:.1f} × {dpi[1]:.1f} DPI' if dpi else 'Unavailable')]


def report(data):
    lines = ['Advanced display report', 'Desktop session: '+data['session']]
    for row in data['monitors']:
        lines += ['', row['name']] + [name+': '+value for name,value in fields(row)]
    lines += ['', 'Graphics adapters:'] + [g['name'] for g in data['gpus']]
    lines += ['OpenGL renderer (diagnostic client): '+(data['renderer'] or 'Unavailable'),
              'This renderer describes the diagnostic client, not necessarily the compositor.']
    return '\n'.join(lines)


class DisplayWindow(Gtk.ApplicationWindow):
    def __init__(self,app):
        super().__init__(application=app,title='Advanced display')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',True)
        self.set_default_size(700,720);self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name('video-display');self.set_wmclass('Zorin11-display-details','Zorin11-display-details')
        self.closed=False;self.pending=False;self.again=False;self.data=None;self.debounce=0;self.watch=0
        self.generation=0
        self.pool=ThreadPoolExecutor(max_workers=1)
        header=Gtk.HeaderBar(title='Advanced display',show_close_button=True);self.set_titlebar(header)
        self.refresh_button=Gtk.Button.new_from_icon_name('view-refresh-symbolic',Gtk.IconSize.BUTTON)
        self.refresh_button.set_tooltip_text('Refresh display information');self.refresh_button.get_accessible().set_name('Refresh display information')
        self.refresh_button.connect('clicked',lambda *_:self.refresh());header.pack_end(self.refresh_button)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,margin=24);self.add(outer)
        label=Gtk.Label(label='Select a display to view its current configuration.',xalign=0);outer.pack_start(label,False,False,0)
        self.selector=Gtk.ComboBoxText();self.selector.get_accessible().set_name('Choose display')
        self.selector.connect('changed',lambda *_:self.render());outer.pack_start(self.selector,False,False,0)
        self.status=Gtk.Label(xalign=0);self.status.set_line_wrap(True);outer.pack_start(self.status,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);outer.pack_start(scroll,True,True,0)
        self.content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);scroll.add(self.content)
        self.copy_button=Gtk.Button(label='Copy display report');self.copy_button.set_sensitive(False)
        self.copy_button.connect('clicked',self.copy_report);outer.pack_end(self.copy_button,False,False,0)
        button=Gtk.Button(label='Open display settings');button.connect('clicked',self.open_settings);outer.pack_end(button,False,False,0)
        self.connect('key-press-event',self.key);self.connect('destroy',self.close_worker)
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.watch=self.bus.signal_subscribe(SERVICE,SERVICE,'MonitorsChanged',PATH,None,0,lambda *_:self.schedule())
        self.show_all();self.refresh()

    def key(self,_widget,event):
        if event.keyval==Gdk.KEY_Escape:self.close();return True
        if event.keyval==Gdk.KEY_F5:self.refresh();return True
        return False

    def copy_report(self,*_):
        if self.data and not self.pending and not self.debounce:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(report(self.data),-1)

    def schedule(self):
        self.generation+=1
        self.copy_button.set_sensitive(False)
        if not self.closed and not self.debounce:self.debounce=GLib.timeout_add(300,self.scheduled)

    def scheduled(self):
        self.debounce=0;self.refresh();return False

    def refresh(self):
        if self.closed:return
        self.generation+=1
        self.copy_button.set_sensitive(False)
        if self.pending:self.again=True;return
        self.pending=True;self.refresh_button.set_sensitive(False);self.status.set_text('Reading display information…')
        token=self.generation
        self.pool.submit(collect).add_done_callback(lambda future:GLib.idle_add(self.received,future,token))

    def received(self,future,token=None):
        if self.closed:return False
        self.pending=False;self.refresh_button.set_sensitive(True)
        if token is not None and token!=self.generation:
            if self.again:self.again=False;self.refresh()
            return False
        try:
            data=future.result();selected=self.selector.get_active_id();self.data=None;self.selector.remove_all();self.data=data
            for row in data['monitors']:self.selector.append(row['connector'],row['name']+' · '+row['connector']+(' · Main display' if row['primary'] else ''))
            if not selected or not self.selector.set_active_id(selected):self.selector.set_active(0)
            self.status.set_text('Current configuration · updates when displays change' if data['monitors'] else 'No displays reported by GNOME.')
            self.render();self.copy_button.set_sensitive(bool(data['monitors']))
        except Exception as error:
            self.data=None;self.render();self.selector.remove_all()
            self.status.set_text('Display information is unavailable. Choose Refresh to try again.\n'+str(error).split('\n')[0][:240])
        if self.again:self.again=False;self.refresh()
        return False

    def render(self):
        for child in self.content.get_children():child.destroy()
        if not self.data:return
        row=next((r for r in self.data['monitors'] if r['connector']==self.selector.get_active_id()),None)
        if row:
            grid=Gtk.Grid(column_spacing=24,row_spacing=12)
            for i,(name,value) in enumerate(fields(row)):
                key=Gtk.Label(label=name,xalign=0);val=Gtk.Label(label=value,xalign=0,selectable=True);val.set_line_wrap(True)
                grid.attach(key,0,i,1,1);grid.attach(val,1,i,1,1)
            self.content.pack_start(grid,False,False,0)
            expander=Gtk.Expander(label='Supported display modes')
            modes=Gtk.Label(label='\n'.join(f'{w} × {h} · {hz:g} Hz' for w,h,hz in row['modes']),xalign=0,selectable=True)
            expander.add(modes);self.content.pack_start(expander,False,False,0)
        gpu='Graphics adapters\n'+ ('\n'.join(g['name'] for g in self.data['gpus']) or 'Unavailable')
        renderer='OpenGL renderer (diagnostic client)\n'+(self.data['renderer'] or 'Unavailable')
        for text in (gpu,renderer,'Desktop session: '+self.data['session']+' · '+self.data['backend']):
            label=Gtk.Label(label=text,xalign=0,selectable=True);label.set_line_wrap(True);self.content.pack_start(label,False,False,0)
        note=Gtk.Label(label='Panel size comes from the display. The OpenGL result describes this diagnostic client; applications may use a different GPU.',xalign=0)
        note.set_line_wrap(True);self.content.pack_start(note,False,False,0)
        self.content.show_all()

    def open_settings(self,*_):
        try:subprocess.Popen(['gnome-control-center','display'],start_new_session=True)
        except OSError as error:self.status.set_text('Could not open display settings: '+str(error))

    def close_worker(self,*_):
        self.closed=True
        if self.debounce:GLib.source_remove(self.debounce)
        if self.watch:self.bus.signal_unsubscribe(self.watch)
        self.pool.shutdown(wait=False,cancel_futures=True)


class Application(Gtk.Application):
    def __init__(self):super().__init__(application_id='local.zorin11.DisplayDetails')
    def do_activate(self):
        window=self.get_active_window() or DisplayWindow(self)
        window.present()

if __name__=='__main__':
    Application().run()
