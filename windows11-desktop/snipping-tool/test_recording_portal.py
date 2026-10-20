#!/usr/bin/python3
"""Exercise the Rust binary through GTK accessibility, pointer input and clipboard on a private X display."""
import os,sys,subprocess,tempfile,time,json,shutil,socket
from pathlib import Path
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin11-snip-test-') as folder:
        root=Path(folder);(root/'runtime').mkdir(mode=0o700)
        (root/'config').mkdir();(root/'Pictures').mkdir()
        (root/'config/axentra-snipping').mkdir();(root/'config/axentra-snipping/settings.ini').write_text('[Capture]\nautosave=true\nautocopy=true\n')
        (root/'config/user-dirs.dirs').write_text(f'XDG_PICTURES_DIR="{root}/Pictures"\n')
        env=dict(os.environ,XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),XDG_SESSION_TYPE='x11',GDK_BACKEND='x11',GIO_USE_VFS='local',DCONF_PROFILE='/dev/null',GTK_USE_PORTAL='0',GIO_USE_VOLUME_MONITOR='unix')
        wp=root/'wireplumber';shutil.copytree('/usr/share/wireplumber',wp)
        for path in wp.rglob('*.lua'):
            text=path.read_text()
            for monitor in ('alsa_monitor','bluez_monitor','v4l2_monitor','libcamera_monitor'):text=text.replace('\n'+monitor+'.enable()','\n-- disabled for private test: '+monitor)
            path.write_text(text)
        env.update(PIPEWIRE_REMOTE='pipewire-0',PULSE_SERVER='unix:'+str(root/'runtime/pulse/native'),WIREPLUMBER_CONFIG_DIR=str(wp))
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
processes=[];sockets=[];calls=[];closed=[];response_code=[0]
portal.remove_from_connection()
class Session(dbus.service.Object):
    @dbus.service.signal('org.freedesktop.portal.Session',signature='a{sv}')
    def Closed(self,details):pass
    @dbus.service.method('org.freedesktop.portal.Session',in_signature='',out_signature='')
    def Close(self):closed.append(True)
session=Session(portal_bus,'/org/freedesktop/portal/desktop/session/test')
class CastRequest(Request):
    @dbus.service.method('org.freedesktop.portal.Request',in_signature='',out_signature='')
    def Close(self):self.Response(1,{})
class Cast(dbus.service.Object):
    def response(self,sender,opts,values):
        path='/org/freedesktop/portal/desktop/request/'+sender[1:].replace('.','_')+'/'+str(opts['handle_token'])
        r=CastRequest(portal_bus,path);request_objects.append(r);GLib.timeout_add(100,lambda:(r.Response(response_code[0] if calls[-1]=='start' else 0,values),False)[1]);return dbus.ObjectPath(path)
    @dbus.service.method('org.freedesktop.portal.ScreenCast',in_signature='a{sv}',out_signature='o',sender_keyword='sender')
    def CreateSession(self,options,sender=None):calls.append('create');return self.response(sender,options,{'session_handle':dbus.ObjectPath('/org/freedesktop/portal/desktop/session/test')})
    @dbus.service.method('org.freedesktop.portal.ScreenCast',in_signature='oa{sv}',out_signature='o',sender_keyword='sender')
    def SelectSources(self,session,options,sender=None):
        assert options['types']==3 and not options['multiple'];assert 'restore_token' not in options;calls.append('select');return self.response(sender,options,{})
    @dbus.service.method('org.freedesktop.portal.ScreenCast',in_signature='osa{sv}',out_signature='o',sender_keyword='sender')
    def Start(self,session,parent,options,sender=None):calls.append('start');return self.response(sender,options,{'streams':dbus.Array([(dbus.UInt32(node_id),dbus.Dictionary({},signature='sv'))],signature='(ua{sv})')})
    @dbus.service.method('org.freedesktop.portal.ScreenCast',in_signature='oa{sv}',out_signature='h')
    def OpenPipeWireRemote(self,session,options):
        calls.append('remote');sock=socket.socket(socket.AF_UNIX);sock.connect(str(Path(os.environ['XDG_RUNTIME_DIR'])/'pipewire-0'));sockets.append(sock);return dbus.types.UnixFd(sock.fileno())
portal=Cast(portal_bus,'/org/freedesktop/portal/desktop')
log=open(root/'app.log','w');proc=None
try:
    for name in ('pipewire','pipewire-pulse','wireplumber'):
        processes.append(subprocess.Popen([name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        if name=='pipewire':wait(lambda:(Path(os.environ['XDG_RUNTIME_DIR'])/'pipewire-0').exists())
    wait(lambda:subprocess.run(['pactl','info'],capture_output=True).returncode==0)
    subprocess.run(['pactl','load-module','module-null-sink','sink_name=snip_output'],check=True,capture_output=True)
    subprocess.run(['pactl','set-default-sink','snip_output'],check=True);subprocess.run(['pactl','set-default-source','snip_output.monitor'],check=True)
    processes.append(subprocess.Popen(['gst-launch-1.0','-q','videotestsrc','is-live=true','pattern=ball','!','video/x-raw,format=BGRx,width=320,height=240,framerate=30/1','!','pipewiresink','mode=provide','stream-properties=props,node.name=snip_test_video,media.class=Video/Source'],stdout=subprocess.DEVNULL,stderr=open(root/'video-source.log','w')))
    def node():
        data=json.loads(subprocess.check_output(['pw-dump'],text=True));return next((n['id'] for n in data if n.get('info',{}).get('props',{}).get('node.name')=='snip_test_video'),None)
    node_id=wait(node);del node
    # Restore the accessibility helper shadowed by node discovery.
    def node(name):
        for a in walk(Atspi.get_desktop(0)):
            try:
                if a.get_name()==name and a.get_state_set().contains(Atspi.StateType.SHOWING):return a
            except Exception:pass
    proc=subprocess.Popen([str(binary),'--record'],env=dict(os.environ,XDG_SESSION_TYPE='wayland'),stdout=log,stderr=log)
    click('Include playback audio');click('Include microphone');click('Choose screen');wait(lambda:len(calls)==4);pump(4)
    session.Closed({});wait(lambda:node('▶ Play recording'),timeout=25);wait(lambda:closed)
    click('Save as');wait(lambda:node('Save recording'));key('ctrl+l');key('ctrl+a');x('type','--clearmodifiers',str(root/'portal.webm'));key('Return');pump(.2)
    if node('Save'):click('Save')
    wait(lambda:(root/'portal.webm').exists())
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(root/'portal.webm')],text=True));v=next(s for s in data['streams'] if s['codec_type']=='video');assert(v['width'],v['height'])==(320,240);assert any(s['codec_type']=='audio' for s in data['streams']);assert float(data['format']['duration'])>1
    # Denial must not spawn a new recorder or destroy the saved clip.
    response_code[0]=1
    child=subprocess.Popen([str(binary),'--record']);pump(.15);wait(lambda:node('Choose screen'));click('Choose screen');wait(lambda:node('Recording cancelled.'));assert len(calls)==7;wait(lambda:len(closed)==2);assert node('▶ Play recording')
    print('PASS ScreenCast consent protocol, real PipeWire video and optional audio recording, FD transfer, WebM save, session cleanup and denial')
finally:
    if sys.exc_info()[0]:
        print('Calls',calls,'closed',len(closed));print((root/'app.log').read_text());print((root/'video-source.log').read_text())
        print('Visible nodes:',[(n.get_role_name(),n.get_name()) for n in walk(Atspi.get_desktop(0)) if n.get_name() and n.get_state_set().contains(Atspi.StateType.SHOWING)][:80])
    if proc:proc.terminate();proc.wait(timeout=3)
    for p in reversed(processes):
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    for s in sockets:s.close()
    log.close()
