#!/usr/bin/python3
"""Isolated GNOME 46/Wayland smoke test. Run directly; never uses live settings.

Requires gnome-shell, Xwayland and the normal companion dependencies. A private
session-manager fixture permits XWayland startup without the real user systemd.
Set ZORIN11_TEST_FEEDS=1 to additionally test the live Bing/Spotlight services.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
COMPANION=ROOT/'companion'
UUID='zorin11@zorin-os-fixes'


def until(fn,seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            value=fn()
            if value:return value
        except Exception:pass
        time.sleep(.1)
    raise AssertionError('Timed out waiting for the test session')


def systemd_fixture():
    import dbus,dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus=dbus.SessionBus();name=dbus.service.BusName('org.freedesktop.systemd1',bus)
    class Manager(dbus.service.Object):
        @dbus.service.method('org.freedesktop.systemd1.Manager',in_signature='ss',out_signature='o')
        def StartUnit(self,unit,mode):
            path='/org/freedesktop/systemd1/job/1'
            GLib.timeout_add(100,lambda:(self.JobRemoved(1,path,unit,'done'),False)[1])
            return path
        @dbus.service.method('org.freedesktop.systemd1.Manager',in_signature='s',out_signature='o')
        def GetUnit(self,unit):return '/org/freedesktop/systemd1/unit/test'
        @dbus.service.method('org.freedesktop.systemd1.Manager',in_signature='',out_signature='')
        def Subscribe(self):pass
        @dbus.service.method('org.freedesktop.systemd1.Manager',in_signature='as',out_signature='')
        def SetEnvironment(self,values):pass
        @dbus.service.signal('org.freedesktop.systemd1.Manager',signature='uoss')
        def JobRemoved(self,ident,path,unit,result):pass
    manager=Manager(bus,'/org/freedesktop/systemd1')
    GLib.MainLoop().run()


def session(temp):
    import re,base64
    from gi.repository import Gio,GLib
    sys.path[:0]=[str(COMPANION),str(ROOT)]
    from gnome_bridge import call
    import wallpaper,gnome_wallpaper
    extension=temp/'data/gnome-shell/extensions'/UUID
    shutil.copytree(ROOT/'gnome-extension',extension)
    for icon in ('start.svg','search.svg','taskview.svg'):shutil.copy(COMPANION/icon,extension/icon)
    subprocess.run(['glib-compile-schemas',str(extension/'schemas')],check=True)
    Gio.Settings.new('org.gnome.shell').set_strv('enabled-extensions',[
        'user-theme@gnome-shell-extensions.gcampax.github.com','zorin-taskbar@zorinos.com','zorin-menu@zorinos.com',UUID])
    Gio.Settings.new('org.gnome.mutter').set_boolean('dynamic-workspaces',False)
    Gio.Settings.new('org.gnome.shell').set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.sync()
    children=[]
    def start(args,env=None,log=None):
        p=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    stub=start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
    shell_log=(temp/'shell.log').open('w')
    shell=start(['gnome-shell','--headless','--wayland','--virtual-monitor','1600x1000','--wayland-display','zorin11-test'],log=shell_log)
    try:
        until(lambda:call('snapshot'))
        until(lambda:re.search(r'public X11 display (:\d+)',(temp/'shell.log').read_text()))
        display=re.search(r'public X11 display (:\d+)',(temp/'shell.log').read_text()).group(1)
        env=dict(os.environ,DISPLAY=display,XAUTHORITY=str(next((temp/'runtime').glob('.mutter-Xwaylandauth.*'))),
                 WAYLAND_DISPLAY='zorin11-test',GDK_BACKEND='x11',GTK_USE_PORTAL='0')
        subprocess.run(['dbus-update-activation-environment','DISPLAY='+env['DISPLAY'],'XAUTHORITY='+env['XAUTHORITY'],'WAYLAND_DISPLAY=zorin11-test'],env=env,check=True)
        # The desktop icon surface must stay transparent under the user theme.
        css_test='''import gi
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
import window_style
w=Gtk.Window();context=w.get_style_context();context.add_class('desktopwindow')
base=Gtk.CssProvider();base.load_from_data(b'window.desktopwindow { background-color: transparent; }')
context.add_provider(base,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
user=Gtk.CssProvider();user.load_from_data(window_style.css('',Path('.')).encode())
context.add_provider(user,Gtk.STYLE_PROVIDER_PRIORITY_USER)
assert context.get_background_color(Gtk.StateFlags.NORMAL).alpha==0
w.destroy()
'''
        subprocess.run(['/usr/bin/python3','-c',css_test],env=env,check=True)
        panels=call('panels');assert panels and all(p['windowsStartVisible'] and not p['zorinStartVisible'] for p in panels),panels
        print('Single Start button and transparent desktop theme: passed',flush=True)
        app_log=(temp/'app.log').open('w')
        app=start(['/usr/bin/python3',str(COMPANION/'app.py'),'--settings','background'],env,app_log)
        def command(*args):
            subprocess.run(['/usr/bin/python3',str(COMPANION/'app.py'),*args],env=env,stdout=app_log,stderr=app_log,check=True,timeout=50)
        time.sleep(3)
        command('--explorer','::computer');time.sleep(2)
        for mode in ('--toggle-start','--quick-settings','--notifications','--task-view'):
            command(mode);time.sleep(.6)
        command('--diagnostics',str(temp/'diagnostics.json'))
        report=until(lambda:json.loads((temp/'diagnostics.json').read_text()))
        for surface in report['surfaces'].values():
            assert surface['ready'] and not surface['errors'] and not surface['brokenImages'],surface
        print('Start, Explorer, Settings, flyouts, groups and Task View: passed',flush=True)
        fixture="import gi;gi.require_version('Gtk','3.0');from gi.repository import Gtk;w=Gtk.Window(title='Zorin11 Wayland test');w.set_default_size(600,400);w.add(Gtk.Label(label='Native Wayland window'));w.show_all();Gtk.main()"
        native=start(['/usr/bin/python3','-c',fixture],dict(env,GDK_BACKEND='wayland'),app_log)
        row=until(lambda:next((w for w in call('snapshot')['windows'] if w['title']=='Zorin11 Wayland test' and w['rect'][2]>100),None))
        ident=row['id'];time.sleep(.6)
        call('window',id=ident,action='move',rect=[100,120,700,450])
        until(lambda:next((w for w in call('snapshot')['windows'] if w['id']==ident and abs(w['rect'][2]-700)<20),None))
        call('window',id=ident,action='workspace',index=1)
        assert next(w for w in call('snapshot')['windows'] if w['id']==ident)['workspace']==1
        call('workspace',index=1);assert call('snapshot')['current']==1
        call('rename',index=1,name='Native test');assert call('snapshot')['names'][1]=='Native test'
        count=call('snapshot')['count'];call('count',count=count+1);assert call('snapshot')['count']==count+1
        call('count',count=count);print('Native Wayland resizing and desktop operations: passed',flush=True)
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        image=bus.call_sync('local.zorin11.Gnome','/local/zorin11/Gnome','local.zorin11.Gnome','Capture',GLib.Variant('(t)',(ident,)),None,Gio.DBusCallFlags.NONE,5000,None).unpack()[0]
        assert base64.b64decode(image).startswith(b'\x89PNG')
        bus.call_sync('org.freedesktop.Notifications','/org/freedesktop/Notifications','org.freedesktop.Notifications','Notify',GLib.Variant('(susssasa{sv}i)',('Zorin11 test',0,'','GNOME bridge test','Disposable test notification',[],{},0)),None,Gio.DBusCallFlags.NONE,3000,None)
        rows=until(lambda:[n for n in call('notifications') if n['title']=='GNOME bridge test']);nid=rows[0]['id']
        call('notification',action='read',ids=[nid]);assert next(n for n in call('notifications') if n['id']==nid)['read']
        call('notification',action='dismiss',ids=[nid]);assert not any(n['id']==nid for n in call('notifications'))
        print('Native thumbnail and notification read/dismiss: passed',flush=True)
        settings=Gio.Settings.new('org.gnome.desktop.background');keys=('picture-uri','picture-uri-dark','picture-options')
        before=[settings.get_string(k) for k in keys];collection=gnome_wallpaper.catalog();assert collection
        for entry in collection:assert wallpaper.thumbnail(entry['id']).startswith(b'\xff\xd8')
        wallpaper.apply(collection[0]['id']);assert settings.get_string('picture-uri')==Path(collection[0]['path']).as_uri()
        wallpaper.restore();assert [settings.get_string(k) for k in keys]==before
        print(f'{len(collection)} Zorin thumbnails, wallpaper apply and restore: passed',flush=True)
        if os.environ.get('ZORIN11_TEST_FEEDS')=='1':
            for source in ('bing','spotlight'):
                try:
                    entry=wallpaper.download(source);wallpaper.apply(entry['id'])
                    assert settings.get_string('picture-uri')==wallpaper.image_path(entry['id']).as_uri()
                    print(source,entry['width'],entry['height'],'download/apply: passed',flush=True)
                finally:
                    wallpaper.restore();assert [settings.get_string(k) for k in keys]==before
        app_log.flush()
        assert 'Traceback (most recent call last)' not in (temp/'app.log').read_text() and 'Desktop action failed:' not in (temp/'app.log').read_text(),(temp/'app.log').read_text()
        assert 'JS ERROR' not in (temp/'shell.log').read_text(),(temp/'shell.log').read_text()
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        shell_log.close()


if __name__=='__main__':
    if '--systemd-fixture' in sys.argv:systemd_fixture()
    elif '--session' in sys.argv:session(Path(sys.argv[-1]))
    else:
        with tempfile.TemporaryDirectory(prefix='zorin11-gnome-test-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),
                     XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',
                     XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',ZORIN11_CONFIG_DIR=str(temp/'hub'),
                     ZORIN11_RUNTIME_DIR=str(COMPANION),PYTHONPATH=str(COMPANION),WAYLAND_DISPLAY='zorin11-test',GTK_USE_PORTAL='0')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp)],env=env,capture_output=True,text=True,timeout=150)
            print(result.stdout if result.returncode else "\n".join(line for line in result.stdout.splitlines() if "passed" in line))
            if result.returncode:
                print(result.stderr[-6000:])
                for name in ('shell.log','app.log'):
                    if (temp/name).exists():print(name,(temp/name).read_text()[-6000:])
            raise SystemExit(result.returncode)
