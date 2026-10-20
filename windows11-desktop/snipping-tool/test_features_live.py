#!/usr/bin/python3
"""Exercise the Rust binary through GTK accessibility, pointer input and clipboard on a private X display."""
import os,sys,subprocess,tempfile,time,json
from pathlib import Path
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin11-snip-test-') as folder:
        root=Path(folder);(root/'runtime').mkdir(mode=0o700)
        (root/'config').mkdir();(root/'Pictures').mkdir()
        (root/'config/axentra-snipping').mkdir();(root/'config/axentra-snipping/settings.ini').write_text('[Capture]\nautosave=true\nautocopy=true\n')
        (root/'config/user-dirs.dirs').write_text(f'XDG_PICTURES_DIR="{root}/Pictures"\n')
        env=dict(os.environ,XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),XDG_SESSION_TYPE='x11',GDK_BACKEND='x11',GIO_USE_VFS='local',DCONF_PROFILE='/dev/null',GTK_USE_PORTAL='0',GIO_USE_VOLUME_MONITOR='unix')
        env.pop('AT_SPI_BUS_ADDRESS',None)
        result=subprocess.run(['xvfb-run','-a','-s','-screen 0 1600x900x24','dbus-run-session','--',sys.executable,__file__,'--private'],env=env,timeout=180)
        raise SystemExit(result.returncode)
import gi
gi.require_version('Gtk','3.0');gi.require_version('Atspi','2.0')
from gi.repository import Gtk,Gdk,GLib,Atspi,GdkPixbuf
import dbus,dbus.service
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)
Gtk.init([])
root=Path(os.environ['XDG_RUNTIME_DIR']).parent
binary=Path(os.environ.get('SNIP_BINARY',str(Path(__file__).parent/'target/debug/zorin11-snipping-tool'))).resolve()
def pump(t=.05):
    end=time.monotonic()+t
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.005)
def wait(fn,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=fn()
        if value:return value
        pump(.05)
    raise AssertionError('Condition timed out')
def walk(n):
    yield n
    try:
        for i in range(n.get_child_count()):yield from walk(n.get_child_at_index(i))
    except Exception:pass
def node(name):
    for a in walk(Atspi.get_desktop(0)):
        try:
            if a.get_name()==name and a.get_state_set().contains(Atspi.StateType.SHOWING):return a
        except Exception:pass
def click(name):
    n=wait(lambda:node(name));r=n.get_component_iface().get_extents(Atspi.CoordType.SCREEN);x('mousemove',r.x+r.width//2,r.y+r.height//2);x('click',1);pump()
def x(*args):return subprocess.check_output(['xdotool',*map(str,args)],text=True).strip()
def key(*keys):x('key','--clearmodifiers',*keys);pump()
def focus(title='^Axentra SnippingTool'):
    wid=wait(lambda:x('search','--onlyvisible','--name',title).splitlines()[0] if subprocess.run(['xdotool','search','--onlyvisible','--name',title],capture_output=True).returncode==0 else None)
    x('windowfocus','--sync',wid);return wid
# Serve the permission-mediated screenshot protocol on this private session only.
portal_bus=dbus.SessionBus();portal_name=dbus.service.BusName('org.freedesktop.portal.Desktop',portal_bus)
portal_requests=[];portal_result=[0];request_objects=[]
class Request(dbus.service.Object):
    @dbus.service.signal('org.freedesktop.portal.Request',signature='ua{sv}')
    def Response(self,code,results):pass
class Portal(dbus.service.Object):
    @dbus.service.method('org.freedesktop.portal.Screenshot',in_signature='sa{sv}',out_signature='o',sender_keyword='sender')
    def Screenshot(self,parent,options,sender=None):
        assert options['interactive']
        path='/org/freedesktop/portal/desktop/request/'+sender[1:].replace('.','_')+'/'+str(options['handle_token'])
        request=Request(portal_bus,path);request_objects.append(request);portal_requests.append(dict(options))
        GLib.timeout_add(100,lambda:(request.Response(portal_result[0],{'uri':(root/'portal.png').as_uri()}),False)[1])
        return path
    @dbus.service.method('org.freedesktop.portal.Screenshot',in_signature='sa{sv}',out_signature='o',sender_keyword='sender')
    def PickColor(self,parent,options,sender=None):
        path='/org/freedesktop/portal/desktop/request/'+sender[1:].replace('.','_')+'/'+str(options['handle_token'])
        request=Request(portal_bus,path);request_objects.append(request)
        GLib.timeout_add(100,lambda:(request.Response(0,{'color':dbus.Struct((.2,.4,.8),signature='ddd')}),False)[1]);return path
portal=Portal(portal_bus,'/org/freedesktop/portal/desktop')
portal_picture=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,123,77);portal_picture.fill(0x3399ddff);portal_picture.savev(str(root/'portal.png'),'png',[],[])
clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
def copied():
    focus();key('ctrl+c');return wait(lambda:clipboard.wait_for_image())
def capture(mode):
    if node('Save your snip before continuing?'):click('Discard')
    child=subprocess.Popen([str(binary),'--capture','--mode',mode])
    pump(.1)
    if node('Discard'):click('Discard')
    child.wait(timeout=5)
    if mode!='full':wait(lambda:node('Snipping selection'))
    else:pump(.6)
def drag(points):
    x('mousemove',*points[0]);x('mousedown',1)
    for pt in points[1:]:x('mousemove','--sync',*pt);pump(.025)
    x('mouseup',1);pump(.25)
from PIL import Image,ImageDraw,ImageFont
image=Image.new('RGB',(900,500),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
draw.text((40,40),'Axentra local text recognition',font=font,fill='black')
draw.text((40,130),'Email: user@example.com',font=font,fill='black')
draw.text((40,220),'Phone: 303-555-0142',font=font,fill='black');image.save(root/'fixture.png')
fixture=Gtk.Window(title='Recording fixture');fixture.set_default_size(240,200);fixture.move(10,10)
a=Gtk.DrawingArea();fixture.add(a);a.connect('draw',lambda _,c:(c.set_source_rgb(.1,.6,.9),c.paint(),False)[-1]);fixture.show_all();pump()
log=open(root/'app.log','w');proc=subprocess.Popen([str(binary)],stdout=log,stderr=log)
def command(*args):
    child=subprocess.Popen([str(binary),*args]);wait(lambda:child.poll() is not None)
def canvas_point(px,py,w=900,h=500):
    area=wait(lambda:next((n for n in walk(Atspi.get_desktop(0)) if n.get_role()==Atspi.Role.DRAWING_AREA and n.get_state_set().contains(Atspi.StateType.SHOWING) and n.get_component_iface().get_extents(Atspi.CoordType.SCREEN).width>900),None));r=area.get_component_iface().get_extents(Atspi.CoordType.SCREEN);return(round(r.x+r.width/2-w/2+px),round(r.y+r.height/2-h/2+py))
def pixel(p,x,y):
    b=p.get_pixels();o=y*p.get_rowstride()+x*p.get_n_channels();return tuple(b[o:o+3])
def save_dialog(name,path):
    click('Save as');wait(lambda:node(name));key('ctrl+l');key('ctrl+a');x('type','--clearmodifiers',str(path));key('Return');pump(.2)
    if node('Save'):click('Save')
    wait(path.exists)
try:
    focus();command('--capture','--mode','rect');wait(lambda:node('Snipping selection'));key('Right','shift+Right','Return');pump(.4)
    wait(lambda:list((root/'Pictures/Screenshots').glob('*.png')))
    p=wait(lambda:clipboard.wait_for_image());assert (p.get_width(),p.get_height())==(110,100)
    command('--open',str(root/'fixture.png'));pump(.3)
    click('⋯');click('Pick screen color');wait(lambda:clipboard.wait_for_text()=='#3366CC');pump(.2)
    # Pen and eraser preserve underlying image pixels and undo history.
    click('Pen');drag([canvas_point(50,400),canvas_point(300,400)]);assert pixel(copied(),150,400)!=(255,255,255)
    click('Eraser');x('mousemove',*canvas_point(150,400));x('click',1);pump();assert pixel(copied(),150,400)==(255,255,255)
    key('ctrl+z');assert pixel(copied(),150,400)!=(255,255,255);key('ctrl+z')
    click('Color picker');x('mousemove',*canvas_point(700,400));x('click',1);pump();assert clipboard.wait_for_text()=='#FFFFFF'
    click('Text actions');wait(lambda:node('Copy all text'),timeout=50);click('Copy all text');assert 'user@example.com' in clipboard.wait_for_text();assert '303-555-0142' in clipboard.wait_for_text()
    click('Quick redact');pump(.3);p=copied();assert pixel(p,250,150)==(0,0,0);assert pixel(p,250,240)==(0,0,0)
    save_dialog('Save snip',root/'redacted.png');assert Image.open(root/'redacted.png').getpixel((250,150))[:3]==(0,0,0)
    click('Emoji');x('mousemove',*canvas_point(650,350));x('click',1);wait(lambda:node('Add emoji'));click('✅');click('Add');assert pixel(copied(),660,360)!=(255,255,255);key('ctrl+z')
    # The app chooser is local; cancel without launching or sending anything.
    click('⋯');click('Share / Open with');pump(.3);key('Escape');pump(.2)
    click('Rotate');p=copied();assert(p.get_width(),p.get_height())==(500,900);key('ctrl+z')
    # Native print dialog opens but never submits a real print job.
    key('ctrl+p');wait(lambda:node('Print'));key('Escape');pump(.2)
    click('⋯');click('Settings');wait(lambda:node('Save settings'));click('Automatically save new screenshots');click('Save settings');assert 'autosave=false' in (root/'config/axentra-snipping/settings.ini').read_text()
    if os.environ.get('ZORIN11_TEST_OUTPUT'):
        out=Path(os.environ['ZORIN11_TEST_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
        Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,1600,900).savev(str(out/'editor.png'),'png',[],[])
    # Record an actual private X11 region and validate the resulting video.
    child=subprocess.Popen([str(binary),'--record']);pump(.15)
    if node('Discard'):click('Discard')
    wait(lambda:child.poll() is not None);wait(lambda:node('Snipping selection'));drag([(20,20),(220,170)])
    click('Start recording');pump(5.5);command('--stop');wait(lambda:node('▶ Play recording'),timeout=20)
    guard=root/'keep.mp4';guard.write_bytes(b'keep original')
    click('Save as');wait(lambda:node('Save recording'));key('ctrl+l');key('ctrl+a');x('type','--clearmodifiers',str(root/'keep'));key('Return');pump(.2)
    if node('Save'):click('Save')
    wait(lambda:node('Replace'));key('Escape');pump(.2);assert guard.read_bytes()==b'keep original'
    save_dialog('Save recording',root/'recording.mp4')
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(root/'recording.mp4')],text=True));video=next(s for s in data['streams'] if s['codec_type']=='video')
    assert(video['width'],video['height'])==(200,150);assert float(data['format']['duration'])>1;assert all(s['codec_type']!='audio' for s in data['streams'])
    print('PASS native OCR/copy/redaction, eraser/undo, exact color, rotation, automatic save/copy, settings, keyboard selection, print cancellation and real region recording/save')
finally:
    if sys.exc_info()[0]:
        print('Visible named nodes:',[(n.get_role_name(),n.get_name()) for n in walk(Atspi.get_desktop(0)) if n.get_state_set().contains(Atspi.StateType.SHOWING) and n.get_name()][:100])
        if os.environ.get('ZORIN11_TEST_OUTPUT'):
            out=Path(os.environ['ZORIN11_TEST_OUTPUT']);out.mkdir(parents=True,exist_ok=True);Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,1600,900).savev(str(out/'features-failure.png'),'png',[],[])
    proc.terminate()
    try:proc.wait(timeout=3)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    fixture.destroy();log.close();text=(root/'app.log').read_text()
    if 'panicked' in text:print(text);raise AssertionError('Rust application panicked')
