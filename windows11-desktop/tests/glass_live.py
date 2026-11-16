#!/usr/bin/python3
"""Window glass on a private GNOME 46 Wayland session. Never touches live settings."""
import base64,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11-glass@zorin-os-fixes'
WRAPPER=r'''
import Base from './glass.js';
import Gio from 'gi://Gio';import GLib from 'gi://GLib';import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
const XML='<node><interface name="local.zorin11.GlassTest"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="Capture"><arg type="s" direction="out"/></method></interface></node>';
const find=title=>global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()===title);
export default class Test extends Base {
 enable(){super.enable();this.bus=Gio.DBusExportedObject.wrapJSObject(XML,this);this.bus.export(Gio.DBus.session,'/local/zorin11/GlassTest');this.owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.GlassTest',0,null,null);}
 Call(text){const p=JSON.parse(text);
  if(p.overview===false)Main.overview.hide();
  if(p.focus)find(p.focus)?.activate(global.get_current_time());
  if(p.fullscreen){const w=find(p.fullscreen);w.is_fullscreen()?w.unmake_fullscreen():w.make_fullscreen();}
  if(p.move){const w=find(p.move[0]);w.move_resize_frame(false,...p.move.slice(1));}
  if(p.reload){super.disable();super.enable();}
  if(p.off){super.disable();}
  return JSON.stringify({windows:global.get_window_actors().map(a=>{const w=a.meta_window,kids=a.get_children(),blur=kids.filter(c=>c.name==='zorin11-glass-blur');
   return {title:w.get_title(),focused:w.has_focus(),fullscreen:w.is_fullscreen(),blurs:blur.length,blurVisible:blur[0]?.visible??false,blurSize:blur[0]?[blur[0].width,blur[0].height]:null,frame:[w.get_frame_rect().width,w.get_frame_rect().height],opacity:kids.filter(c=>c.name!=='zorin11-glass-blur').map(c=>c.opacity),radius:blur[0]?.get_effect('blur')?.radius??null};})});}
 async CaptureAsync(args,inv){try{const stream=Gio.MemoryOutputStream.new_resizable();await new Shell.Screenshot().screenshot(false,stream);stream.close(null);inv.return_value(new GLib.Variant('(s)',[GLib.base64_encode(stream.steal_as_bytes().get_data())]));}catch(e){inv.return_dbus_error('local.zorin11.Error',String(e));}}
 disable(){this.bus.unexport();Gio.bus_unown_name(this.owner);super.disable();}
}
'''
CLIENT=r'''
import sys,gi;gi.require_version('Gtk','3.0');from gi.repository import Gtk,Gdk
css=Gtk.CssProvider();css.load_from_data(b".back{background:repeating-linear-gradient(45deg,#e33 0,#e33 24px,#ff0 24px,#ff0 48px);} .front{background:#f3f3f3;color:#111;font-size:28px;}");Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,600)
for title,cls,size in (('Glass back','back',(900,700)),('Glass front','front',(600,400))):
    w=Gtk.Window(title=title);w.set_default_size(*size);l=Gtk.Label(label=title);w.add(l);w.get_style_context().add_class(cls);w.show_all()
Gtk.main()
'''
def session(temp,output):
    from gi.repository import Gio,GLib
    ext=temp/'data/gnome-shell/extensions'/UUID
    shutil.copytree(ROOT/'gnome-glass-extension',ext)
    (ext/'extension.js').rename(ext/'glass.js');(ext/'extension.js').write_text(WRAPPER)
    shellsettings=Gio.Settings.new('org.gnome.shell')
    shellsettings.set_strv('enabled-extensions',[UUID])
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir()])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.new('org.gnome.desktop.interface').set_boolean('enable-animations',False)
    Gio.Settings.sync()
    log=(output/'shell.log').open('w');children=[]
    def start(args,env=None):
        p=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def call(**p):return json.loads(bus.call_sync('local.zorin11.GlassTest','/local/zorin11/GlassTest','local.zorin11.GlassTest','Call',GLib.Variant('(s)',(json.dumps(p),)),None,0,3000,None).unpack()[0])
    def capture(name):
        data=bus.call_sync('local.zorin11.GlassTest','/local/zorin11/GlassTest','local.zorin11.GlassTest','Capture',None,None,0,5000,None).unpack()[0]
        (output/(name+'.png')).write_bytes(base64.b64decode(data))
    def win(state,title):return next(w for w in state['windows'] if w['title']==title)
    config=temp/'config/zorin11-hub/glass.json'
    try:
        start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
        start(['gnome-shell','--headless','--wayland','--no-x11','--virtual-monitor','1280x900','--wayland-display','glass-test'])
        until(lambda:call())
        start(['/usr/bin/python3','-c',CLIENT],env=dict(os.environ,GDK_BACKEND='wayland'))
        until(lambda:sum(w['title'].startswith('Glass') for w in call()['windows'])==2)
        call(overview=False);time.sleep(.5);call(move=['Glass back',40,40,900,700]);call(move=['Glass front',300,250,600,400]);call(focus='Glass front');time.sleep(.5)
        state=call();front,back=win(state,'Glass front'),win(state,'Glass back')
        assert front['focused'] and front['blurs']==1 and front['blurVisible'] and front['blurSize']==front['frame'],front
        assert all(o==round(90*255/100) for o in front['opacity']) and all(o==round(85*255/100) for o in back['opacity']),state
        assert front['radius']==30,front
        capture('glass-default')
        call(focus='Glass back');time.sleep(.3);state=call()
        assert all(o==round(90*255/100) for o in win(state,'Glass back')['opacity']) and all(o==round(85*255/100) for o in win(state,"Glass front")['opacity']),state
        call(focus='Glass front');call(fullscreen='Glass front');time.sleep(.5);front=win(call(),'Glass front')
        assert front['fullscreen'] and all(o==255 for o in front['opacity']) and not front['blurVisible'],front
        call(fullscreen='Glass front');time.sleep(.5)
        config.parent.mkdir(parents=True,exist_ok=True);config.write_text(json.dumps({'enabled':True,'active':80,'inactive':70,'blur':12}))
        front=until(lambda:(f if (f:=win(call(),'Glass front'))['radius']==12 else None))
        assert all(o==round(80*255/100) for o in front['opacity']),front
        capture('glass-stronger')
        config.write_text(json.dumps({'enabled':False}))
        front=until(lambda:(f if not (f:=win(call(),'Glass front'))['blurVisible'] else None))
        assert all(o==255 for o in front['opacity']),front
        config.write_text('not json');call(reload=True);front=win(call(),'Glass front')
        assert front['blurs']==1 and all(o==round(90*255/100) for o in front['opacity']),front
        call(off=True);state=call()
        assert all(w['blurs']==0 and all(o==255 for o in w['opacity']) for w in state['windows']),state
        errors=[l for l in (output/'shell.log').read_text().splitlines() if 'glass' in l.lower() and ('error' in l.lower() or 'exception' in l.lower())]
        assert not errors,errors
        print('PASSED glass: blur under each window, focused/inactive opacity, fullscreen solid, live config, bad config fallback, clean disable',flush=True)
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        log.close()

if __name__=='__main__':
    if '--systemd-fixture' in sys.argv:systemd_fixture()
    elif '--session' in sys.argv:session(Path(sys.argv[-2]),Path(sys.argv[-1]))
    else:
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-glass-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-glass-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='dconf',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='glass-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=160)
            print(result.stdout)
            if result.returncode:print(result.stderr[-4000:]);print((output/'shell.log').read_text()[-6000:])
            raise SystemExit(result.returncode)
