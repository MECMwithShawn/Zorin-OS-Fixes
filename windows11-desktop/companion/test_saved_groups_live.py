"""Restart/relaunch real apps from portable recipes in private X11 sessions."""
import os,subprocess,sys,tempfile,time,shutil
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')
BASE=Path(__file__).resolve().parent
if '--session' not in sys.argv and '--fixture' not in sys.argv:
    for wm in os.environ.get('ZORIN11_TEST_WMS','xfwm4 compiz').split():
        with tempfile.TemporaryDirectory(prefix='z11-persist-test-') as temp:
            root=Path(temp);display=next(':'+str(n) for n in range(81,110) if not Path('/tmp/.X11-unix/X'+str(n)).exists())
            with (root/'log').open('w') as log:
                server=subprocess.Popen(['Xephyr',display,'-screen','1400x960','-noreset','-nolisten','tcp'],stdout=log,stderr=log)
                try:
                    time.sleep(.7)
                    env=dict(os.environ,DISPLAY=display,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),ZORIN11_CONFIG_DIR=str(root/'hub'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0',LIBGL_ALWAYS_SOFTWARE='1')
                    shutil.copytree(BASE/'window-theme',root/'data/themes/Zorin11-Dark')
                    subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',wm],env=env,stdout=log,stderr=log,check=True,timeout=100)
                finally:server.terminate();server.wait();log.flush();print((root/'log').read_text()[-9000:])
    sys.exit()
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,Gio,GLib
if '--fixture' in sys.argv:
    cls=sys.argv[-1];w=Gtk.Window(title=cls+' private test');w.set_wmclass(cls.lower(),cls)
    w.set_default_size(500,320);w.set_icon_name('applications-graphics');w.add(Gtk.Label(label='Saved Snap Groups\nDisposable test application'))
    w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main();sys.exit()
from concurrent.futures import ThreadPoolExecutor
from multitasking import Multitasking
from windowing import layouts,zone_rect
from saved_groups import catalog
wm_name=sys.argv[-1]
if wm_name=='compiz':
    import effects
    subprocess.run(['/usr/bin/python3',str(BASE/'effects.py'),'--configure'],env=effects.environment(),check=True)
    wm=subprocess.Popen(['compiz','--replace','ccp'],env=effects.environment())
else:wm=subprocess.Popen(['xfwm4','--replace'])
def pump(seconds=.1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)
def until(fn,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        result=fn()
        if result:return result
        pump(.05)
    raise AssertionError('Timed out: '+str(fn))
class Hub:
    surfaces={}
    def __init__(self):self.workers=ThreadPoolExecutor(max_workers=3)
    def work_area(self,x,y):return Gdk.Display.get_default().get_monitor_at_point(x,y).get_workarea()
    def monitor_geometry(self):return self.work_area(100,100)
    def background(self,task,success,failure):
        def done(future):
            try:value=future.result()
            except Exception as error:GLib.idle_add(lambda e=error:(failure(e),False)[1]);return
            GLib.idle_add(lambda:(success(value),False)[1])
        self.workers.submit(task).add_done_callback(done)
    def open_settings(self,*_):pass
config=Path(os.environ['ZORIN11_CONFIG_DIR']);applications=Path(os.environ['XDG_DATA_HOME'])/'applications';applications.mkdir(parents=True)
for cls in ('RecipeOne','RecipeTwo'):
    (applications/(cls+'.desktop')).write_text('[Desktop Entry]\nType=Application\nName='+cls+'\nExec=/usr/bin/python3 "'+str(Path(__file__).resolve())+'" --fixture '+cls+'\nStartupWMClass='+cls+'\nIcon=applications-graphics\nTerminal=false\n')
hub=Hub();m=Multitasking(hub,config);pump(2)
# A normal Xfce session keeps xfdesktop mapped. Xfwm can leave STACKING
# absent when its very last client exits and X11 immediately recycles that ID.
desktop=Gtk.Window();desktop.set_type_hint(Gdk.WindowTypeHint.DESKTOP);desktop.set_skip_taskbar_hint(True);desktop.set_default_size(1400,960);desktop.show_all();desktop.get_window().lower();pump(.3)
def owned():return [w for w in m.windows.windows() if w.get_class_group_name() in ('RecipeOne','RecipeTwo')]
def close_owned():
    for w in owned():w.close(m.windows.timestamp())
    until(lambda:not owned());pump(.2)
def status(text,done):
    messages.append((text,done))
    if done and text!='Layout restored.':print('RESTORE ERROR:',text,flush=True)
def restored():return m.saved_groups.operation is None and messages and messages[-1][0]=='Layout restored.'
try:
    apps=catalog()
    for cls in ('RecipeOne','RecipeTwo'):apps[cls+'.desktop'].launch([],None)
    until(lambda:len(owned())==2)
    ids=[w.get_xid() for w in owned()];pids={w.get_pid() for w in owned()};placements=[(xid,zone_rect(m.area(),zone)) for xid,zone in zip(ids,layouts()[0][1])]
    for xid,rect in placements:m.windows.place(xid,rect)
    pump(.7);m.remember_group(placements)
    assert len(m.saved_groups.store.groups)==1,m.saved_groups.last_error
    recipe=m.saved_groups.store.groups[0];ident=recipe['id'];old_token=m.groups[0].token
    m.saved_groups.store.rename(ident,'Research desk')
    m.shutdown();m=Multitasking(hub,config);pump(.3)
    assert not m.groups and m.saved_groups.store.groups[0]['name']=='Research desk'
    close_owned();messages=[];m.saved_groups.restore(ident,status);until(restored,15)
    # X11 may recycle numeric XIDs after a client exits. The recipe must launch
    # new processes and issue a fresh live token, not rely on IDs staying unique.
    new_ids={w.get_xid() for w in owned()};assert len(new_ids)==2 and not pids&{w.get_pid() for w in owned()}
    assert len(m.groups)==1 and m.groups[0].saved_id==ident and not m.snap_groups.activate(old_token)
    assert len(m.saved_groups.store.groups)==1
    print('PASS automatic save, restart, reopen two app processes, layout and fresh live token',flush=True)
    messages=[];m.saved_groups.restore(ident,status);until(restored)
    assert {w.get_xid() for w in owned()}==new_ids
    # A new screen gets the same proportions, rather than desktop-PC pixels.
    real_area=m.area;m.area=lambda *args:(0,0,1000,700)
    messages=[];m.saved_groups.restore(ident,status);until(restored)
    for i,(xid,rect) in enumerate(m.groups[0]):
        expected=m.saved_groups.store.groups[0]['members'][i]['rect']
        assert abs(rect[2]-round(expected[2]*1000))<=1
    m.area=real_area
    print('PASS reuse existing apps without duplicates; normalized geometry on smaller work area',flush=True)
    # Save two instances of one app, then close/relaunch them independently.
    close_owned();apps['RecipeOne.desktop'].launch([],None);apps['RecipeOne.desktop'].launch([],None)
    until(lambda:len(owned())==2)
    placements=[(w.get_xid(),zone_rect(m.area(),z)) for w,z in zip(owned(),layouts()[0][1])]
    m.remember_group(placements);same=m.saved_groups.store.groups[0]['id'];close_owned()
    messages=[];m.saved_groups.restore(same,status)
    until(restored,15)
    assert len(owned())==2 and len({x for x,_ in m.groups[0]})==2
    print('PASS distinct slots reopen two windows of one app',flush=True)
    m.show_saved_groups();view=m.saved_view
    assert view.alive() and any(g['name']=='Research desk' for g in view.saved.store.groups)
    assert not view.cancel_button.get_visible()
    # Missing software fails before any launch or move.
    (applications/'RecipeTwo.desktop').unlink();pump(.5)
    original={w.get_xid():tuple(w.get_geometry()) for w in owned()}
    try:m.saved_groups.restore(ident,status);raise AssertionError('missing app accepted')
    except ValueError as error:assert 'Install these apps first' in str(error)
    assert original=={w.get_xid():tuple(w.get_geometry()) for w in owned()}
    m.close(False)
    messages=[];m.saved_groups.restore(same,status);m.saved_groups.cancel();pump(.4)
    assert not m.saved_groups.operation and len(owned())==2
    view.saved.store.remove(same);assert all(g['id']!=same for g in view.saved.store.groups)
    print('PASS saved-groups UI, missing-app preflight, cancellation, removal',flush=True)
finally:
    m.saved_groups.cancel();close_owned();m.shutdown();desktop.destroy();hub.workers.shutdown(wait=True,cancel_futures=True)
    wm.terminate();pump(.2)
