#!/usr/bin/python3
"""Exercise the Rust binary through GTK accessibility, pointer input and clipboard on a private X display."""
import os,sys,subprocess,tempfile,time,json
from pathlib import Path
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin11-snip-test-') as folder:
        root=Path(folder);(root/'runtime').mkdir(mode=0o700)
        (root/'config').mkdir();(root/'Pictures').mkdir()
        (root/'config/axentra-snipping').mkdir();(root/'config/axentra-snipping/settings.ini').write_text('[Capture]\nautosave=false\nautocopy=false\n')
        (root/'config/user-dirs.dirs').write_text(f'XDG_PICTURES_DIR="{root}/Pictures"\n')
        env=dict(os.environ,XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),XDG_SESSION_TYPE='x11',GDK_BACKEND='x11',GIO_USE_VFS='local',DCONF_PROFILE='/dev/null',GTK_USE_PORTAL='0',GIO_USE_VOLUME_MONITOR='unix')
        env.pop('AT_SPI_BUS_ADDRESS',None)
        result=subprocess.run(['xvfb-run','-a','-s','-screen 0 1600x900x24','dbus-run-session','--',sys.executable,__file__,'--private'],env=env,timeout=120)
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
# Desktop fixture remains behind the capture editor.
fixture=Gtk.Window(title='Capture fixture');fixture.set_default_size(500,400);fixture.move(80,100)
a=Gtk.DrawingArea();fixture.add(a)
def draw(_,c):c.set_source_rgb(.1,.6,.9);c.paint();c.set_source_rgb(1.,.8,.1);c.rectangle(40,40,120,100);c.fill()
a.connect('draw',draw);fixture.show_all();pump()
log=open(root/'app.log','w')
proc=subprocess.Popen([str(binary)],stdout=log,stderr=log)
try:
    idle=focus();wait(lambda:node('＋ New'));pump(.2)
    geometry=dict(line.split('=',1) for line in x('getwindowgeometry','--shell',idle).splitlines() if '=' in line)
    assert int(geometry['WIDTH'])<=700 and int(geometry['HEIGHT'])<=300,geometry
    assert node('Pen') is None and node('Save as') is None
    output=os.environ.get('ZORIN11_TEST_OUTPUT')
    if output:
        Path(output).mkdir(parents=True,exist_ok=True)
        Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),int(geometry['X']),int(geometry['Y']),int(geometry['WIDTH']),int(geometry['HEIGHT'])).savev(str(Path(output)/'idle.png'),'png',[],[])
    key('alt+m');wait(lambda:node('Window mode'));key('Escape')
    capture('rect');drag([(130,150),(300,230),(400,300)])
    p=copied();assert(p.get_width(),p.get_height())==(270,150)
    before=bytes(p.get_pixels())
    # Draw a pen stroke on the fitted image in the real editor.
    wid=focus();geo=json.loads('{}')
    # The accessible drawing area exposes its actual screen allocation.
    canvas=wait(lambda:next((n for n in walk(Atspi.get_desktop(0)) if n.get_role()==Atspi.Role.DRAWING_AREA and n.get_state_set().contains(Atspi.StateType.SHOWING) and n.get_component_iface().get_extents(Atspi.CoordType.SCREEN).width>900),None))
    rect=canvas.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    cx=rect.x+rect.width//2;cy=rect.y+rect.height//2
    drag([(cx-80,cy),(cx,cy),(cx+80,cy)])
    p=copied();assert bytes(p.get_pixels())!=before
    key('ctrl+z');assert bytes(copied().get_pixels())==before
    key('ctrl+shift+z');assert bytes(copied().get_pixels())!=before
    click('Crop');drag([(cx-80,cy-45),(cx+80,cy+45)]);p=copied();assert p.get_width() in (160,161) and p.get_height() in (90,91), (p.get_width(),p.get_height())
    key('ctrl+z');assert copied().get_width()==270
    # Save through the actual native chooser and verify encoded pixels.
    click('Save as');wait(lambda:node('Save snip'));key('ctrl+l');key('ctrl+a');x('type','--clearmodifiers',str(root/'saved.png'));key('Return');pump(.15)
    if node('Save'):click('Save')
    wait(lambda:(root/'saved.png').exists());from gi.repository import GdkPixbuf
    p=GdkPixbuf.Pixbuf.new_from_file(str(root/'saved.png'));assert p.get_width()==270
    click('Save as');wait(lambda:node('Save snip'));key('ctrl+l');key('ctrl+a');x('type','--clearmodifiers',str(root/'saved.jpg'));key('Return');pump(.15)
    if node('Save'):click('Save')
    wait(lambda:(root/'saved.jpg').exists())
    assert (root/'saved.jpg').read_bytes().startswith(b'\xff\xd8')
    # Appending .png must not bypass overwrite confirmation.
    guard=root/'guard.png';guard.write_bytes(b'keep original')
    click('Save as');wait(lambda:node('Save snip'));key('ctrl+l');key('ctrl+a');x('type','--clearmodifiers',str(root/'guard'));key('Return');pump(.15)
    if node('Save'):click('Save')
    wait(lambda:node('Replace'));key('Escape');pump(.2)
    assert guard.read_bytes()==b'keep original'
    capture('free');drag([(140,170),(300,170),(220,290),(140,170)]);p=copied();assert p.get_has_alpha();pixels=p.get_pixels();assert min(pixels[3::4])==0 and max(pixels[3::4])==255
    capture('window');x('mousemove',200,220);x('click',1);pump(.2);p=copied();assert(p.get_width(),p.get_height())==(500,400)
    capture('full');p=copied();assert(p.get_width(),p.get_height())==(1600,900)
    # Escape cancels without replacing the previous image.
    capture('rect');focus('Snipping selection');key('Escape');assert copied().get_width()==1600
    # Output artifacts contain only the isolated fixture.
    output=os.environ.get('ZORIN11_TEST_OUTPUT')
    if output:
        Path(output).mkdir(parents=True,exist_ok=True);focus();pump(.1)
        win=Gdk.get_default_root_window();p=Gdk.pixbuf_get_from_window(win,0,0,1600,900);p.savev(str(Path(output)/'snipping-tool.png'),'png',[],[])
    print('PASS real Rust rectangle/freeform/window/full-desktop capture, pen, crop, undo/redo, PNG/JPEG save, overwrite cancellation, clipboard and Escape')
    # A cancelled delayed snip must not appear later.
    child=subprocess.Popen([str(binary),'--capture','--delay','3']);pump(.15)
    if node('Discard'):click('Discard')
    wait(lambda:child.poll() is not None);click('Cancel capture');pump(3.3)
    assert node('Snipping selection') is None
    proc.terminate();proc.wait(timeout=3);pump(.1)
    proc=subprocess.Popen([str(binary)],env=dict(os.environ,XDG_SESSION_TYPE='wayland'),stdout=log,stderr=log)
    focus();wait(lambda:node('GNOME picker'))
    child=subprocess.Popen([str(binary),'--capture']);wait(lambda:child.poll() is not None)
    wait(lambda:portal_requests);pump(.4);assert copied().get_width()==123
    portal_result[0]=1
    child=subprocess.Popen([str(binary),'--capture']);pump(.15)
    if node('Discard'):click('Discard')
    wait(lambda:child.poll() is not None);wait(lambda:node('Capture cancelled.'))
    assert copied().get_width()==123
    print('PASS cancelled delay and Wayland portal consent, image response, cancellation and previous-image retention')

finally:
    if sys.exc_info()[0]:
        print('Visible windows:',x('search','--onlyvisible','--name','.*'))
        print('Visible named nodes:',[(n.get_role_name(),n.get_name()) for n in walk(Atspi.get_desktop(0)) if n.get_state_set().contains(Atspi.StateType.SHOWING) and n.get_name()][:100])
        output=os.environ.get('ZORIN11_TEST_OUTPUT')
        if output:
            Path(output).mkdir(parents=True,exist_ok=True)
            Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,1600,900).savev(str(Path(output)/'failure.png'),'png',[],[])
    proc.terminate()
    try:proc.wait(timeout=3)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    fixture.destroy();log.close();text=(root/'app.log').read_text()
    if 'panicked' in text:print(text);raise AssertionError('Rust application panicked')
