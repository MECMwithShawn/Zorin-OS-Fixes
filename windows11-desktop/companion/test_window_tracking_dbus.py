"""Delayed real D-Bus replies must leave the main loop responsive."""
import sys,subprocess,json,time
from unittest.mock import patch
if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("Run this private D-Bus integration test directly.")
if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--private'],timeout=12).returncode)
from gi.repository import Gio,GLib
import gnome_bridge as g
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
xml=Gio.DBusNodeInfo.new_for_xml('<node><interface name="local.zorin11.Gnome"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>')
owner=Gio.bus_own_name_on_connection(bus,'local.zorin11.Gnome',0,None,None)
requests=[]
data=dict(windows=[dict(id=2,focused=True)],current=0)
def handle(connection,sender,path,interface,method,params,invocation):
    requests.append(params.unpack()[0])
    def reply():
        invocation.return_value(GLib.Variant('(s)',(json.dumps(data),)));return False
    GLib.timeout_add(300,reply)
registration=bus.register_object('/local/zorin11/Gnome',xml.interfaces[0],handle,None,None)
def until(fn):
    end=time.monotonic()+4
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if fn():return
        time.sleep(.005)
    raise AssertionError('Timed out waiting for async transport')
# Let the bus acquire its name before starting the fixture.
until(lambda:bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',GLib.Variant('(s)',('local.zorin11.Gnome',)),None,0,1000,None).unpack()[0])
with patch.object(g,'call',return_value=dict(windows=[dict(id=1,focused=True)],current=0)):
    screen=g.Screen()
ticks=[];heartbeat=GLib.timeout_add(10,lambda:(ticks.append(1),True)[1]);closed=[]
screen.connect('window-closed',lambda _,w:closed.append(w.get_xid()))
try:
    screen.poll();screen.poll()
    until(lambda:closed==[1])
    assert len(requests)==1 and len(ticks)>=10,(requests,len(ticks))
    screen.poll();pending=screen.pending;screen.close();until(lambda:pending.is_cancelled())
    until(lambda:screen.pending is None)
    assert screen.data==data
    print('PASS: real delayed D-Bus reply, responsive main-loop heartbeat, coalesced requests, close cancellation')
finally:
    screen.close();GLib.source_remove(heartbeat)
    bus.unregister_object(registration);Gio.bus_unown_name(owner)
