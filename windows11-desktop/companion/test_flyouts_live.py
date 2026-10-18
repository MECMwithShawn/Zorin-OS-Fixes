"""Real WebKit + Xfce log round trip in a private Xephyr/D-Bus/cache session."""
import json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin-flyout-test-') as temp:
        root=Path(temp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
        with (root/'session.log').open('w') as log:
            server=subprocess.Popen(['Xephyr',display,'-screen','1100x950','-noreset','-nolisten','tcp'],stdout=log,stderr=log)
            try:
                time.sleep(.7)
                env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),ZORIN11_APP_ID='local.zorin11.FlyoutTest',GSETTINGS_BACKEND='keyfile')
                subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session'],env=env,stdout=log,stderr=log,check=True,timeout=45)
            finally:
                server.terminate();server.wait();log.flush();print((root/'session.log').read_text()[-4500:])
    sys.exit()
import dbus
import settings_backend,notifications
from app import Hub,GLib,WebKit2,Gdk
wm=subprocess.Popen(['xfwm4','--replace'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def pump(seconds=.08):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.01)
def until(fn,timeout=10):
    stop=time.monotonic()+timeout
    while time.monotonic()<stop:
        if fn():return
        pump()
    raise AssertionError('Timed out waiting for the live flyout')
def js(surface,expression):
    result=[]
    def done(web,value,*args):
        try:result.append(json.loads(web.evaluate_javascript_finish(value).to_string()))
        except Exception as e:result.append(e)
    surface.js('JSON.stringify('+expression+')',done);until(lambda:result)
    if isinstance(result[0],Exception):raise result[0]
    return result[0]
def snapshot(surface,name):
    if not os.environ.get('ZORIN11_TEST_OUTPUT'):return
    folder=Path(os.environ['ZORIN11_TEST_OUTPUT']);folder.mkdir(parents=True,exist_ok=True);done=[]
    def ready(web,result,*args):web.get_snapshot_finish(result).write_to_png(str(folder/name));done.append(True)
    surface.web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,ready,None);until(lambda:done)
for key,value in [('/notification-log',dbus.Boolean(True)),('/log-level',dbus.String('always')),('/theme',dbus.String('Zorin11-Notifications')),('/notify-location',dbus.String('bottom-right'))]:settings_backend.set_property('xfce4-notifyd',key,value)
theme=Path(os.environ['XDG_DATA_HOME'])/'themes/Zorin11-Notifications/xfce-notify-4.0/gtk.css';theme.parent.mkdir(parents=True);shutil.copy(BASE/'notification-theme.css',theme)
service=dbus.Interface(dbus.SessionBus().get_object('org.freedesktop.Notifications','/org/freedesktop/Notifications'),'org.freedesktop.Notifications')
toast_id=service.Notify('Zorin flyout test',0,'dialog-information','Notification center is ready','A test message from the isolated desktop session.',[],{},10000)
until(lambda:len(notifications.snapshot()['entries'])==1)
ident=notifications.snapshot()['entries'][0]['id']
if os.environ.get('ZORIN11_TEST_OUTPUT'):
    pump(.4);folder=Path(os.environ['ZORIN11_TEST_OUTPUT']);folder.mkdir(parents=True,exist_ok=True)
    Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),0,0,1100,950).savev(str(folder/'native-toast.png'),'png',[],[])
service.CloseNotification(toast_id)
hub=Hub();hub.register(None);hub.store.state['groups_visible']=False;hub.sync_groups()
try:
    hub.show_notifications();surface=hub.notifications
    until(lambda:surface.ready and not hub.notification_data.get('loading',True));pump(.4)
    assert js(surface,"document.querySelectorAll('.notification-card').length")==1
    assert js(surface,"document.querySelectorAll('.calendar-grid button').length")==42
    assert js(surface,'window.desktopErrors')==[]
    snapshot(surface,'windows11-notification-center.png')
    js(surface,"([...document.querySelectorAll('button')].find(b=>b.textContent==='Mark as read').click(),true)")
    until(lambda:notifications.snapshot()['entries'][0]['read']);assert not notifications.has_unread()
    js(surface,"(document.querySelector('[aria-label=\"Dismiss Notification center is ready\"]').click(),true)")
    until(lambda:not notifications.snapshot()['entries']);assert notifications.snapshot()['available']
    hub.show_quick();quick=hub.quick;until(lambda:quick.ready and 'outputs' in hub.status);pump(.4)
    # Real audio and radio state is read, never changed by this test.
    assert js(quick,"document.querySelectorAll('.flyout-tile-wrap').length")==6
    js(quick,"(document.querySelector('[aria-label=\"Select sound output\"]').click(),true)");pump(.1)
    assert js(quick,"document.querySelector('.flyout-subheading h2').textContent")=='Sound output'
    js(quick,"(document.querySelector('[aria-label=\"Back to Quick Settings\"]').click(),true)");pump(.1)
    assert js(quick,'window.desktopErrors')==[]
    snapshot(quick,'windows11-quick-settings.png')
    js(quick,"(document.querySelector('[aria-label=\"Edit quick settings\"]').click(),true)");pump(.1)
    js(quick,"(document.querySelector('[aria-label=\"Show Screenshot\"]').click(),true)");pump(.1)
    js(quick,"([...document.querySelectorAll('button')].find(b=>b.textContent==='Done').click(),true)")
    until(lambda:'screenshot' not in hub.store.state.get('quick_tiles',[]))
    saved=json.loads(hub.store.path.read_text());assert 'screenshot' not in saved['quick_tiles']
    print('LIVE PASSED: real Xfce log ingest/read/delete; calendar; Quick Settings resources, output page and persistent tile edit; no user history or hardware settings changed.',flush=True)
finally:
    for surface in list(hub.surfaces.values()):surface.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    wm.terminate();wm.wait()
