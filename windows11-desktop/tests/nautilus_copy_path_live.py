"""Actual Nautilus MenuProvider actions and GTK4 clipboard, isolated display."""
import sys,os,subprocess
from pathlib import Path
if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--private'],env=dict(os.environ,GDK_BACKEND='x11'),timeout=20).returncode)
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nautilus-extension'))
from zorin11_copy_path import Zorin11CopyPath,location_text
from types import SimpleNamespace as NS
Gtk.init();provider=Zorin11CopyPath()
file=lambda p:NS(get_location=lambda:Gio.File.new_for_path(p))
files=[file('/home/example/OneDrive/My photos/été.png'),file('/tmp/second file.pdf')]
assert location_text(files)=='/home/example/OneDrive/My photos/été.png\n/tmp/second file.pdf'
assert not provider.get_file_items([])
remote=NS(get_location=lambda:Gio.File.new_for_uri('smb://server/share/test.pdf'))
assert location_text([remote])=='smb://server/share/test.pdf'
for menu,expected in [(provider.get_file_items(files),location_text(files)),(provider.get_background_items(files[0]),location_text(files[:1]))]:
    menu[0].emit('activate');loop=GLib.MainLoop();result=[]
    def read(clipboard,res):
        result.append(clipboard.read_text_finish(res));loop.quit()
    Gdk.Display.get_default().get_clipboard().read_text_async(None,read)
    timeout=GLib.timeout_add_seconds(3,lambda:(loop.quit(),False)[1]);loop.run();GLib.source_remove(timeout)
    assert result==[expected],result
print('PASS real Nautilus actions and clipboard: multiple paths, spaces, Unicode, folder background, remote URI')
