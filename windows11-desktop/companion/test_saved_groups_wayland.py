"""Restore only disposable native Wayland apps using real desktop identities."""
import os,sys,time,tempfile,subprocess,uuid
from pathlib import Path
if __name__!='__main__':
    import unittest
    raise unittest.SkipTest('Run this live Wayland fixture directly.')
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,Gio,GLib
if '--client' in sys.argv:
    app=Gtk.Application(application_id=sys.argv[-1])
    def activate(a):
        w=Gtk.ApplicationWindow(application=a,title='Disposable saved-group validation')
        w.set_default_size(420,300);w.add(Gtk.Label(label='Native Wayland Snap Group test'));w.show_all()
    app.connect('activate',activate);app.run([sys.argv[0]]);raise SystemExit
base=Path(os.environ.get('ZORIN11_TEST_RUNTIME',Path(__file__).resolve().parent));sys.path.insert(0,str(base))
import gnome_bridge as bridge
from windowing import Windows
from saved_groups import SavedGroups,identify
from window_layouts import monitors,encode,decode
from snap_groups import Group
from unittest.mock import patch
from types import SimpleNamespace as NS
assert os.environ.get('XDG_SESSION_TYPE')=='wayland'
manager=Windows();prior=manager.active();processes=[];entries=[]
appdir=Path.home()/'.local/share/applications';appdir.mkdir(parents=True,exist_ok=True)
ids=['local.zorin11.Recipe'+uuid.uuid4().hex for _ in range(3)]
def wait(fn,seconds=12):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        result=fn()
        if result:return result
        time.sleep(.025)
    raise AssertionError('Timed out restoring native fixture')
try:
    apps={}
    for ident in ids:
        entry=appdir/(ident+'.desktop');entries.append(entry)
        entry.write_text('[Desktop Entry]\nType=Application\nName=Disposable recipe test\nExec=/usr/bin/false\nStartupWMClass='+ident+'\nNoDisplay=true\n')
        apps[entry.name]=Gio.DesktopAppInfo.new_from_filename(str(entry))
        processes.append(subprocess.Popen(['/usr/bin/python3',__file__,'--client',ident],env=dict(os.environ,GDK_BACKEND='wayland'),stdout=subprocess.DEVNULL))
    owned=lambda:[w for w in manager.windows() if w.get_pid() in {p.pid for p in processes}]
    wait(lambda:len(owned())==3 and all(w.get_application_id() in apps for w in owned()))
    byapp={w.get_application_id():w for w in owned()}
    for ident,w in byapp.items():assert identify(w,apps)==ident
    current=manager.screen.get_active_workspace().get_number()
    area=Gdk.Display.get_default().get_monitor(0).get_workarea()
    unrelated=byapp[ids[2]+'.desktop'];before=unrelated.get_geometry()
    # Use the normal window operations but never allow access to user windows.
    class FixtureWindows:
        def windows(self):return owned()
        def get(self,xid):return next((w for w in owned() if w.get_xid()==xid),None)
        def active(self):return byapp[ids[0]+'.desktop']
        def __getattr__(self,name):return getattr(manager,name)
    with tempfile.TemporaryDirectory() as folder:
        m=NS(config=Path(folder),windows=FixtureWindows(),groups=[])
        m.area=lambda *_:(area.x+6,area.y+6,area.width-12,area.height-12)
        m.desktops=NS(busy=False,current=lambda:current,items=lambda:[dict(id=current,uid='fixture')],on=lambda w,d:w.get_workspace().get_number()==d)
        m.snap_groups=NS(remember=lambda placements,persist=False:m.groups.append(Group(placements)))
        saved=SavedGroups(m)
        # Old class strings must not prevent native app-ID matches.
        members=[dict(app=ids[i]+'.desktop',**{'class':'Old shared X11 toolkit class'},rect=[i*.5,0,.5,1]) for i in range(2)]
        recipe=saved.store.put(members,desktop='fixture');messages=[]
        with patch('saved_groups.catalog',return_value=apps):
            saved.restore(recipe,lambda *args:messages.append(args));wait(lambda:saved.operation is None)
        assert messages[-1]==('Layout restored.',True),messages
        assert {x for x,_ in m.groups[0]}=={byapp[i+'.desktop'].get_xid() for i in ids[:2]}
        assert unrelated.get_geometry()==before,'Unrelated fixture was moved'
        assert len(owned())==3,'Duplicate app was launched'
        outputs=monitors();assert len(outputs)>=2,'This live test needs two monitors'
        for i,w in enumerate(owned()):
            a=outputs[i%len(outputs)]['area']
            manager.place(w.get_xid(),(a[0]+60+i*20,a[1]+60+i*20,500,350))
        wait(lambda:all(w.get_geometry()[2:]==(500,350) for w in owned()))
        # Capture all three visible clients, including two apps on one monitor.
        with patch('saved_groups.catalog',return_value=apps):
            snapshot=saved.current_layout();full=saved.save_current('Both monitors',snapshot)
        recipe=next(g for g in saved.store.groups if g['id']==full)
        assert recipe['kind']=='layout' and len(recipe['members'])==3
        assert len({r['monitor']['index'] for r in recipe['members']})==2
        expected={saved.layout_windows[full][i]:decode(r,outputs) for i,r in enumerate(recipe['members'])}
        assert '_window' not in saved.store.path.read_text()
        for w in owned():manager.place(w.get_xid(),(area.x+30,area.y+30,450,320))
        wait(lambda:all(w.get_geometry()[2:]==(450,320) for w in owned()))
        messages=[]
        with patch('saved_groups.catalog',return_value=apps):
            saved.restore(full,lambda *args:messages.append(args));wait(lambda:saved.operation is None)
        assert messages[-1]==('Layout restored.',True),messages
        for w in owned():assert all(abs(a-b)<=12 for a,b in zip(w.get_geometry(),expected[w.get_xid()])),(w.get_geometry(),expected)
        maximized=byapp[ids[0]+'.desktop'];full=byapp[ids[1]+'.desktop']
        maximized.maximize();full.set_fullscreen(True)
        wait(lambda:maximized.is_maximized() and full.is_fullscreen())
        with patch('saved_groups.catalog',return_value=apps):states=saved.save_current('Window states')
        full.set_fullscreen(False);maximized.unmaximize()
        wait(lambda:not maximized.is_maximized() and not full.is_fullscreen())
        messages=[]
        with patch('saved_groups.catalog',return_value=apps):
            saved.restore(states,lambda *args:messages.append(args));wait(lambda:saved.operation is None)
        assert messages[-1]==('Layout restored.',True),messages
        wait(lambda:maximized.is_maximized() and full.is_fullscreen())
        messages=[]
        with patch('saved_groups.catalog',return_value=apps):
            saved.restore(states,lambda *args:messages.append(args));wait(lambda:saved.operation is None)
        assert messages[-1]==('Layout restored.',True),messages
        wait(lambda:maximized.is_maximized() and full.is_fullscreen())
        saved.close()
        print('PASS: maximized and fullscreen states restored')
        print('PASS: Save current layout, private persistence, three windows on both monitors, moved windows restored')
    print('PASS: native app identity, saved restore despite changed classes, reuse without relaunch, unrelated window unchanged')
finally:
    for process in processes:
        process.terminate()
        try:process.wait(timeout=4)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    for entry in entries:entry.unlink(missing_ok=True)
    if prior:
        try:
            w=manager.get(prior.get_xid())
            if w:manager.activate(w)
        except (ValueError,GLib.Error):pass
    manager.close()
