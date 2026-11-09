"""Opt-in, once-per-GNOME-login layout restore; never a sync service."""
import hashlib
import os
from pathlib import Path
import time
from gi.repository import Gio, GLib


def session_key():
    # The session manager's unique bus owner changes on sign-out, but not when
    # the companion restarts. A missing session manager fails closed.
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    owner=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
        'GetNameOwner',GLib.Variant('(s)',('org.gnome.SessionManager',)),None,
        Gio.DBusCallFlags.NONE,1500,None).unpack()[0]
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()+owner


def claim_session(root,key):
    folder=Path(root)/'zorin11-layout-startup';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    marker=folder/hashlib.sha256(key.encode()).hexdigest()
    try:fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:return False
    os.close(fd);return True


def locked():
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    return bus.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver','org.gnome.ScreenSaver',
        'GetActive',None,None,Gio.DBusCallFlags.NONE,1500,None).unpack()[0]


class StartupRestore:
    def __init__(self,saved):
        self.saved=saved;self.timer=0;self.deadline=time.monotonic()+120
        try:
            root=os.environ.get('XDG_RUNTIME_DIR')
            if not root or not claim_session(root,session_key()):return
            if not saved.store.data.get('startup_layout'):return
            self.timer=GLib.timeout_add_seconds(20,self.run)
        except (OSError,GLib.Error) as error:saved.last_error='Sign-in layout restore unavailable: '+str(error)

    def close(self):
        if self.timer:GLib.source_remove(self.timer);self.timer=0

    def notify(self,text,finished):
        if not finished:return
        self.saved.last_error='' if text=='Layout restored.' else text
        notification=Gio.Notification.new('Saved window layout')
        notification.set_body(text)
        self.saved.m.hub.send_notification('layout-startup',notification)

    def run(self):
        ident=self.saved.store.data.get('startup_layout')
        if not ident:self.timer=0;return False
        try:
            if self.saved.operation or self.saved.m.desktops.busy or locked():
                if time.monotonic()<self.deadline:return True
                self.notify('Sign-in restore skipped while the desktop was busy or locked. Restore it from Saved groups.',True)
            else:self.saved.restore(ident,self.notify)
        except (ValueError,OSError,RuntimeError,GLib.Error) as error:self.notify(str(error),True)
        self.timer=0;return False
