"""Exercise GTK and real query subprocesses on a private display/session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if __name__ != '__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly with python3.')

if '--session' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='zorin11-events-') as temp:
        root = Path(temp)
        (root/'runtime').mkdir(mode=0o700)
        env = dict(os.environ, XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
                   XDG_CACHE_HOME=str(root/'cache'), GSETTINGS_BACKEND='memory',
                   XDG_CURRENT_DESKTOP='GNOME', GIO_USE_VFS='local', GTK_USE_PORTAL='0',
                   NO_AT_BRIDGE='1', GDK_BACKEND='x11', EVENT_TEST_ROOT=temp,
                   XDG_RUNTIME_DIR=str(root/'runtime'))
        subprocess.run(['dbus-run-session', '--', 'xvfb-run', '-a', '-s', '-screen 0 1400x1000x24',
                        '/usr/bin/python3', __file__, '--session'], env=env, check=True, timeout=45)
    sys.exit()

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import event_viewer
from test_event_logs import fixture

root = Path(os.environ['EVENT_TEST_ROOT'])
(root/'bin').mkdir()
config = root/'journal.json'
trace = root/'queries.jsonl'
query = root/'bin/journalctl'
query.write_text('''#!/usr/bin/python3
import json, os, sys, time
from pathlib import Path
root = Path(os.environ['EVENT_TEST_ROOT'])
settings = json.loads((root/'journal.json').read_text())
with (root/'queries.jsonl').open('a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'pid': os.getpid()}) + '\\n')
time.sleep(settings.get('delay', 0))
if settings.get('error'):
    sys.stderr.write(settings['error'])
    sys.exit(1)
rows = settings['rows']
if '--user' in sys.argv:
    rows = [r for r in rows if r['__CURSOR'] == 'event-2']
elif '_TRANSPORT=kernel' in sys.argv:
    rows = [r for r in rows if r['__CURSOR'] == 'event-3']
for arg in sys.argv:
    if arg.startswith('--priority='):
        lo, hi = map(int, arg.split('=')[1].split('..'))
        rows = [r for r in rows if lo <= int(r['PRIORITY']) <= hi]
for row in rows:
    print(json.dumps(row))
''')
query.chmod(0o755)
os.environ['PATH'] = str(root/'bin') + os.pathsep + os.environ['PATH']


def configure(**extra):
    config.write_text(json.dumps(dict(rows=fixture(), **extra)))


def pump(seconds=.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.005)


def until(condition, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pump(.02)
        if condition():
            return
    raise AssertionError('Timed out waiting for GTK/query state')


def queries():
    return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []


def ready():
    until(lambda: not window.pending and not window.again)


def detail_text():
    buffer = window.detail.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


def refresh():
    window.refresh_button.clicked()
    ready()


configure()
app = event_viewer.Application()
app.register(None)
app.activate()
window = app.get_active_window()
try:
    ready()
    assert len(window.store) == 3 and '--system' in queries()[-1]['args']
    window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    assert 'Disk <error> & retry\nSecond line' in detail_text()
    assert window.copy.get_sensitive()
    window.copy.clicked()
    assert Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() == detail_text()
    refresh()
    assert window.selected()['id'] == 'event-1', 'Refresh lost the selection'
    window.search.set_text('DISK fixture.service')
    until(lambda: len(window.store) == 1)
    assert window.selected()['id'] == 'event-1'
    window.search.set_text('no matching event')
    until(lambda: len(window.store) == 0)
    assert not window.copy.get_sensitive() and 'Select an event' in detail_text()
    window.search.set_text('')
    until(lambda: len(window.store) == 3)

    window.level.set_active_id('errors')
    ready()
    assert len(window.store) == 1 and '--priority=0..3' in queries()[-1]['args']
    window.level.set_active_id('warnings')
    ready()
    assert len(window.store) == 2
    window.level.set_active_id('information')
    ready()
    assert len(window.store) == 1 and window.store[0][5] == 'event-2'
    window.level.set_active_id('all')
    ready()
    window.scopes.select_row(window.scopes.get_row_at_index(0))
    ready()
    assert len(window.store) == 1 and '--user' in queries()[-1]['args']
    window.scopes.select_row(window.scopes.get_row_at_index(2))
    ready()
    assert len(window.store) == 1 and '_TRANSPORT=kernel' in queries()[-1]['args']
    for value, arg in [('previous', '--boot=-1'), ('hour', '--since=-1 hour'),
                       ('day', '--since=-24 hours'), ('boot', '--boot=0')]:
        window.period.set_active_id(value)
        ready()
        assert arg in queries()[-1]['args']
        assert '--dmesg' not in queries()[-1]['args']

    # Cancel a slow query, change filters twice, and accept only the latest result.
    configure(delay=2)
    count = len(queries())
    window.refresh_button.clicked()
    until(lambda: len(queries()) > count)
    configure()
    window.scopes.select_row(window.scopes.get_row_at_index(0))
    window.scopes.select_row(window.scopes.get_row_at_index(1))
    ready()
    assert len(window.store) == 3 and '--system' in queries()[-1]['args']

    window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    configure(error='Access denied to fixture journal')
    refresh()
    assert not window.rows and not window.copy.get_sensitive()
    assert 'Access denied' in window.status.get_text() and 'Select an event' in detail_text()
    config.write_text(json.dumps({'rows': []}))
    refresh()
    assert '0 of 0 loaded' in window.status.get_text() and not window.error
    configure()
    refresh()
    assert len(window.store) == 3

    window.auto.set_active(True)
    count = len(queries())
    until(lambda: len(queries()) > count, 7)
    ready()
    window.auto.set_active(False)
    assert window.timer == 0
    count = len(queries())
    pump(.3)
    assert len(queries()) == count
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval, event.state = Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK
    assert window.key(window, event)
    assert window.get_focus() == window.search
    event.keyval, event.state = Gdk.KEY_F5, Gdk.ModifierType(0)
    assert window.key(window, event)
    ready()
    assert len(queries()) == count + 1
    window.search.set_text('Fixture')
    event.keyval = Gdk.KEY_Escape
    assert window.key(window, event) and not window.search.get_text()

    window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    pump(.3)
    output = os.environ.get('ZORIN11_TEST_OUTPUT')
    if output:
        destination = Path(output)
        destination.mkdir(parents=True, exist_ok=True)
        surface = window.get_window()
        Gdk.pixbuf_get_from_window(surface, 0, 0, surface.get_width(), surface.get_height()).savev(
            str(destination/'event-viewer-fixture.png'), 'png', [], [])

    # Closing during I/O cancels the owned query and removes the refresh timer.
    configure(delay=10)
    count = len(queries())
    window.auto.set_active(True)
    window.refresh_button.clicked()
    until(lambda: len(queries()) > count)
    start = time.monotonic()
    window.destroy()
    window.pool.shutdown(wait=True)
    pump(.2)
    assert window.closed and window.timer == 0
    assert time.monotonic() - start < 2
    print('PASS: GTK scope/time/severity filters; literal details/copy; search; refresh selection; '
          'latest-query cancellation; failure/retry/empty state; timed auto-refresh; keyboard; close cleanup.')
finally:
    if not window.closed:
        window.destroy()
    window.pool.shutdown(wait=True)
