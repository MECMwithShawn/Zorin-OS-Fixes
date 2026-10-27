#!/usr/bin/python3
"""Real GTK window and DisplayConfig calls on a private bus and Xvfb display."""
import os,sys,time,tempfile,subprocess,json
from pathlib import Path

def session(output):
    import dbus,dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    import display_details as d
    from test_display_details import fixture
    from gi.repository import Gtk,Gdk
    from unittest.mock import patch
    bus=dbus.SessionBus();name=dbus.service.BusName(d.SERVICE,bus)
    class DisplayService(dbus.service.Object):
        def __init__(self):super().__init__(bus,d.PATH);self.state=fixture();self.fail=False;self.calls=[]
        @dbus.service.method(d.SERVICE,out_signature='ua((ssss)a(siiddada{sv})a{sv})a(iiduba(ssss)a{sv})a{sv}')
        def GetCurrentState(self):
            self.calls.append('GetCurrentState')
            if self.fail:raise dbus.DBusException('Display service temporarily unavailable',name='org.freedesktop.DBus.Error.Failed')
            return self.state
        @dbus.service.method(d.SERVICE)
        def GetResources(self):
            self.calls.append('GetResources')
            raise dbus.DBusException('Legacy dimensions unavailable',name='org.freedesktop.DBus.Error.NotSupported')
        @dbus.service.signal(d.SERVICE,signature='')
        def MonitorsChanged(self):pass
    service=DisplayService()
    def until(fn):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            while Gtk.events_pending():Gtk.main_iteration_do(False)
            if fn():return
            time.sleep(.02)
        raise AssertionError('Timed out waiting for GTK state')
    def tool(args):return 'OpenGL renderer string: Fixture renderer' if args[0]=='glxinfo' else '0000:00:02.0 "VGA compatible controller" "Fixture" "GPU"'
    bindir=output/'bin';bindir.mkdir(exist_ok=True)
    marker=output/'settings-launch.json';marker.unlink(missing_ok=True)
    stub=bindir/'gnome-control-center'
    stub.write_text('#!/usr/bin/python3\nimport sys,json\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text(json.dumps(sys.argv[1:]))\n');stub.chmod(0o755)
    os.environ['PATH']=str(bindir)+':'+os.environ['PATH']
    with patch.object(d,'run',side_effect=tool):
        app=d.Application();app.register(None);app.activate();window=app.get_active_window()
        until(lambda:window.data and not window.pending)
        assert len(window.data['monitors'])==2
        assert window.selector.get_active_id()=='eDP-1'
        assert dict(d.fields(window.data['monitors'][0]))['Scale']=='125%'
        window.selector.set_active_id('DP-1')
        assert '59.95 Hz' in [c.get_text() for grid in window.content.get_children() if isinstance(grid,Gtk.Grid) for c in grid.get_children() if isinstance(c,Gtk.Label)]
        window.refresh_button.clicked();until(lambda:not window.pending)
        assert window.selector.get_active_id()=='DP-1'
        window.copy_button.clicked()
        copied=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        assert '125%' in copied and 'DP-1' in copied and 'eDP-1' in copied
        assert 'diagnostic client' in copied
        # A monitor-change signal invalidates a running collection immediately.
        from concurrent.futures import Future
        old=window.data
        future=Future();future.set_result(dict(old,monitors=[]))
        token=window.generation
        window.schedule()
        assert not window.copy_button.get_sensitive()
        window.received(future,token)
        assert window.data is old
        until(lambda:not window.debounce and not window.pending)

        paint_after=time.monotonic()+.25
        until(lambda:time.monotonic()>paint_after)
        surface=window.get_window();pix=Gdk.pixbuf_get_from_window(surface,0,0,surface.get_width(),surface.get_height())
        pix.savev(str(output/'advanced-display.png'),'png',[],[])
        outer=window.get_child();button=next(b for b in outer.get_children() if isinstance(b,Gtk.Button) and b.get_label()=='Open display settings');button.clicked()
        until(marker.exists);assert json.loads(marker.read_text())==['display']
        state=list(fixture());state[1]=[state[1][1]];state[2]=[state[2][0]];service.state=state;service.MonitorsChanged()
        until(lambda:window.data and len(window.data['monitors'])==1 and not window.pending)
        assert window.selector.get_active_id()=='eDP-1'
        service.fail=True;service.MonitorsChanged()
        until(lambda:window.data is None and 'unavailable' in window.status.get_text())
        assert not window.copy_button.get_sensitive()
        service.fail=False;window.refresh_button.clicked()
        until(lambda:window.data and not window.pending)
        assert all(c in ('GetCurrentState','GetResources') for c in service.calls)
        window.close();until(lambda:window.closed)
        assert window.received(None) is False
        print('Native Advanced display passed: live D-Bus reads, primary selection, monitor switching, refresh retention, screenshot, real settings launch, hotplug fallback, failure/retry and close cleanup.')

if __name__=='__main__':
    if '--session' in sys.argv:session(Path(sys.argv[-1]))
    else:
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-display-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-display-') as temp:
            env=dict(os.environ,XDG_CONFIG_HOME=temp,XDG_CACHE_HOME=temp,GTK_USE_PORTAL='0',GSETTINGS_BACKEND='memory',XDG_CURRENT_DESKTOP='GNOME')
            result=subprocess.run(['dbus-run-session','--','xvfb-run','-a','/usr/bin/python3',__file__,'--session',str(output)],env=env,capture_output=True,text=True,timeout=45)
            print(result.stdout)
            if result.returncode:print(result.stderr)
            raise SystemExit(result.returncode)
