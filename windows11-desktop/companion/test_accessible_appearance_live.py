"""Check live GNOME appearance changes in a disposable GTK/WebKit session."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

if __name__ != '__main__':
    import unittest
    raise unittest.SkipTest('Run this private GTK fixture directly.')

if '--private' not in sys.argv:
    env = dict(os.environ, GSETTINGS_BACKEND='memory', XDG_CURRENT_DESKTOP='GNOME',
               GDK_BACKEND='x11', GIO_USE_VFS='local')
    subprocess.run(['xvfb-run', '-a', 'dbus-run-session', '--', sys.executable,
                    __file__, '--private'], env=env, timeout=35, check=True)
    raise SystemExit
assert os.environ.get('GSETTINGS_BACKEND') == 'memory'

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, Gdk, GdkX11, Gio, WebKit2

base = Path(os.environ.get('ZORIN11_TEST_RUNTIME', Path(__file__).parent))
sys.path.insert(0, str(base))
import accessible_appearance


def until(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError('Timed out waiting for the appearance to update')


contrast = Gio.Settings.new('org.gnome.desktop.a11y.interface')
desktop = Gio.Settings.new('org.gnome.desktop.interface')
contrast.set_boolean('high-contrast', False)
desktop.set_boolean('enable-animations', True)
window = Gtk.Window()
window.set_default_size(420, 240)
window.get_style_context().add_class('z11-multitask')
provider = Gtk.CssProvider()
provider.load_from_path(str(base / 'multitasking.css'))
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, 650)
accessible_appearance.configure_native(window)
manager = WebKit2.UserContentManager()
accessible_appearance.configure_web(window, manager)
web = WebKit2.WebView(user_content_manager=manager)
window.add(web)
window.show_all()
web.grab_focus()
loaded = []
web.connect('load-changed', lambda _view, event: loaded.append(event))
web.load_html("""
<style>
.start-shell { background: #282828; }
.start-shell::before { content: 'decoration'; }
button { transition: background 1s; }
</style>
<main class="start-shell"><button>Start</button><input aria-label="Search"></main>
""", None)
until(lambda: WebKit2.LoadEvent.FINISHED in loaded)
window_id = GdkX11.X11Window.get_xid(window.get_window())
subprocess.run(['xdotool', 'windowfocus', '--sync', str(window_id)], check=True)
until(window.is_active)


def styles():
    result = []

    def finished(view, operation, _):
        result.append(json.loads(view.evaluate_javascript_finish(operation).to_json(0)))

    web.evaluate_javascript("""
document.querySelector('input').focus();
JSON.stringify([
    getComputedStyle(document.querySelector('main')).backgroundColor,
    getComputedStyle(document.querySelector('main'), '::before').display,
    getComputedStyle(document.querySelector('button')).transitionDuration,
    getComputedStyle(document.querySelector('input')).outlineColor
])
""", -1, None, None, None, finished, None)
    return json.loads(until(lambda: result)[0])


try:
    assert styles()[:3] == ['rgb(40, 40, 40)', 'inline', '1s']
    contrast.set_boolean('high-contrast', True)
    until(lambda: styles()[:3] == ['rgb(0, 0, 0)', 'none', '1s'])
    contrast_styles = styles()
    assert contrast_styles[3] == 'rgb(255, 223, 117)', contrast_styles
    desktop.set_boolean('enable-animations', False)
    until(lambda: styles() == ['rgb(0, 0, 0)', 'none', '0s', 'rgb(255, 223, 117)'])
    assert window.get_style_context().has_class('z11-high-contrast')
    # Standard appearance and motion return without reloading the WebView.
    contrast.set_boolean('high-contrast', False)
    until(lambda: styles()[:3] == ['rgb(40, 40, 40)', 'inline', '0s'])
    desktop.set_boolean('enable-animations', True)
    until(lambda: styles()[:3] == ['rgb(40, 40, 40)', 'inline', '1s'])
    assert not window.get_style_context().has_class('z11-high-contrast')
    assert loaded.count(WebKit2.LoadEvent.FINISHED) == 1
    print('PASS: running GTK and WebKit surfaces follow both GNOME preferences live')
finally:
    window.destroy()
