"""Fences end to end: real Hub, WebKit and X drag-and-drop on disposable files.

Run under Xvfb with a private D-Bus session, for example:
  GDK_BACKEND=x11 xvfb-run -a -s "-screen 0 1280x800x24" dbus-run-session -- \
      /usr/bin/python3 test_fences_live.py [--output DIR]
HOME and the config directory point at a temporary folder; no user files are used.
"""
import json, os, subprocess, sys, tempfile, threading, time
from pathlib import Path

workspace = tempfile.TemporaryDirectory(prefix='zorin11-fences-')
root = Path(workspace.name)
os.environ['HOME'] = str(root)
os.environ['ZORIN11_CONFIG_DIR'] = str(root/'config')
os.environ['ZORIN11_APP_ID'] = 'local.zorin11.DesktopHub.FenceTest'
os.environ.pop('XDG_CONFIG_HOME', None)
desktop = root/'Desktop'
desktop.mkdir()
for name in ('a.txt', 'b c.pdf'):
    (desktop/name).write_text(name)
output = Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else None

from app import Hub, GLib, Gtk, Gdk, WebKit2
import fences

hub = Hub(); hub.register(None)
fenced_file = root/'config/fenced.json'
failures = []

def on_main(fn):
    done, box = threading.Event(), []
    def run():
        try: box.append(fn())
        except Exception as error: box.append(error)
        done.set(); return False
    GLib.idle_add(run); assert done.wait(10), 'main loop stalled'
    if isinstance(box[0], Exception): raise box[0]
    return box[0]

def js(surface, code):
    done, box = threading.Event(), []
    def finished(view, result, *_):
        try: box.append(json.loads(view.evaluate_javascript_finish(result).to_json(0)))
        except Exception as error: box.append(error)
        done.set()
    GLib.idle_add(lambda: (surface.web.evaluate_javascript(code, -1, None, None, None, finished, None), False)[1])
    assert done.wait(10); return box[0]

def wait(check, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check(): return
        time.sleep(.1)
    raise AssertionError('Timed out: ' + message)

def x(*args): subprocess.run(['xdotool', *map(str, args)], check=True)

def drag(start, end, release=None, cancel=False):
    x('mousemove', *start); time.sleep(.15); x('mousedown', 1)
    path = [end] + ([release] if release else [])
    here = start
    for stop in path:
        for step in range(1, 26):
            x('mousemove', round(here[0] + (stop[0]-here[0])*step/25), round(here[1] + (stop[1]-here[1])*step/25))
            time.sleep(.03)
        here = stop; time.sleep(.35)
    if cancel: x('key', 'Escape'); time.sleep(.2)
    x('mouseup', 1); time.sleep(.8)

def items(group_id): return [i.get('path', i.get('id')) for i in hub.store.group(group_id)['items']]

def snapshot(surface, name):
    if not output: return
    output.mkdir(parents=True, exist_ok=True); done = threading.Event()
    def captured(view, result, *_):
        view.get_snapshot_finish(result).write_to_png(str(output/name)); done.set()
    GLib.idle_add(lambda: (surface.web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.TRANSPARENT_BACKGROUND, None, captured, None), False)[1])
    assert done.wait(5)

def tile_center(surface, path):
    rect = js(surface, '(()=>{const b=[...document.querySelectorAll(".fence-item")].find(b=>b.title.startsWith(%s));'
                       'const r=b.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/3]})()' % json.dumps(Path(path).name))
    wx, wy = on_main(lambda: surface.get_window().get_origin()[1:])
    return round(wx + rect[0]), round(wy + rect[1])

# A stand-in for Zorin's desktop icons: an X11 drag source offering file URIs.
source = Gtk.Window(title='icons'); source.set_default_size(160, 160); source.move(0, 0)
box = Gtk.EventBox(); box.add(Gtk.Label(label='ICONS')); source.add(box)
box.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [Gtk.TargetEntry.new('x-special/gnome-icon-list', 0, 0),
                    Gtk.TargetEntry.new('text/uri-list', 0, 1)], Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
box.connect('drag-data-get', lambda w, ctx, data, info, t: data.set_uris(
    [Gio_uri for Gio_uri in (p.as_uri() for p in (desktop/'a.txt', desktop/'b c.pdf'))]))
# A stand-in desktop drop target, like Zorin's desktop accepting text/uri-list.
received = []
target = Gtk.Window(title='desktop'); target.set_default_size(420, 140); target.move(320, 600)
target.add(Gtk.Label(label='DESKTOP'))
target.drag_dest_set(Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new('text/uri-list', 0, 0)], Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
target.connect('drag-data-received', lambda w, ctx, x_, y_, data, info, t: received.extend(data.get_uris()))

exit_code = 0
def verify():
    global exit_code
    try:
        on_main(lambda: (source.show_all(), target.show_all()))
        on_main(lambda: (hub.store.state.update(groups=[]), hub.sync_groups()))  # drop the default groups
        first = on_main(lambda: hub.store.add_group('Projects', x=300, y=40))
        second = on_main(lambda: hub.store.add_group('Reading', x=740, y=40))
        on_main(lambda: (hub.store.state.update(groups_visible=True), hub.sync_groups()))
        s1, s2 = hub.surfaces[first], hub.surfaces[second]
        wait(lambda: on_main(lambda: s1.ready and s2.ready) and js(s1, '!!document.querySelector(".fence")') is True, 'fences render')
        assert js(s1, 'document.querySelector(".fence-empty strong").textContent') == 'Drag icons here'
        # 0. Passing over a fence, or cancelling there, fences nothing.
        drag((80, 80), (490, 180), release=(1200, 780))
        time.sleep(.5); assert items(first) == [], 'a drag that only passed over a fence fenced files'
        drag((80, 80), (490, 180), cancel=True)
        time.sleep(.5); assert items(first) == [], 'a cancelled drag fenced files'
        print('Fences: passing over or cancelling over a fence changes nothing', flush=True)
        # 1. Drag two desktop icons into a fence: they join the fence and leave the desktop.
        drag((80, 80), (490, 180))
        wait(lambda: items(first) == [str(desktop/'a.txt'), str(desktop/'b c.pdf')], 'icons dropped into fence')
        published = json.loads(fenced_file.read_text())
        assert published['pid'] == os.getpid() and published['paths'] == sorted(items(first)), published
        wait(lambda: js(s1, 'document.querySelectorAll(".fence-item").length') == 2, 'tiles render')
        assert 'mime' in js(s1, 'document.querySelector(".fence-item img").src')
        snapshot(s1, 'fence-dropped.png')
        print('Fences: icons dragged from a desktop drag source joined the fence and the fenced list', flush=True)
        # 2. Drag a tile from one fence into another: it moves.
        drag(tile_center(s1, desktop/'a.txt'), (930, 180))
        wait(lambda: items(second) == [str(desktop/'a.txt')] and items(first) == [str(desktop/'b c.pdf')], 'fence to fence move')
        print('Fences: a tile dragged between fences moved', flush=True)
        # 2b. Dropping a tile where nothing accepts it keeps it in its fence.
        wait(lambda: js(s1, 'document.querySelectorAll(".fence-item").length') == 1, 'first fence tile')
        drag(tile_center(s1, desktop/'b c.pdf'), (1200, 780))
        time.sleep(.6); assert items(first) == [str(desktop/'b c.pdf')], 'a rejected drag removed the item'
        print('Fences: a rejected drag-out keeps the item', flush=True)
        # 3. Drag a tile out onto the desktop: the desktop receives it and it leaves the fence.
        wait(lambda: js(s2, 'document.querySelectorAll(".fence-item").length') == 1, 'second fence tile')
        drag(tile_center(s2, desktop/'a.txt'), (520, 660))
        wait(lambda: not items(second), 'drag out returns the icon')
        assert received == [(desktop/'a.txt').as_uri()], received
        wait(lambda: json.loads(fenced_file.read_text())['paths'] == [str(desktop/'b c.pdf')], 'un-fenced after drag out')
        print('Fences: a tile dragged onto the desktop target left the fence and was un-fenced', flush=True)
        # Menus open from mouse requests, which carry no GDK event.
        on_main(lambda: hub.dispatch(s1, {'action': 'fence-menu', 'x': 40, 'y': 60}))
        assert on_main(lambda: s1.fence_menu.get_visible()), 'fence menu did not open'
        labels = on_main(lambda: [c.get_label() for c in s1.fence_menu.get_children() if isinstance(c, Gtk.MenuItem)])
        assert {'Rename fence', 'Color', 'Transparency', 'Icon size', 'Sort by', 'Delete fence'} <= set(labels), labels
        on_main(lambda: s1.fence_menu.popdown())
        on_main(lambda: hub.dispatch(s1, {'action': 'fence-menu', 'id': str(desktop/'b c.pdf'), 'x': 30, 'y': 70}))
        labels = on_main(lambda: [c.get_label() for c in s1.fence_menu.get_children() if isinstance(c, Gtk.MenuItem)])
        assert 'Return to desktop' in labels and 'Move to fence' in labels, labels
        on_main(lambda: s1.fence_menu.popdown())
        print('Fences: fence and item menus open at the click point', flush=True)
        # 4. Style, roll-up, quick-hide and peek.
        on_main(lambda: hub.dispatch(s1, {'action': 'fence-style', 'changes': {'tint': 'frost', 'opacity': .8, 'iconSize': 'large', 'evil': 1}}))
        assert hub.store.group(first)['style'] == {**fences.DEFAULT_STYLE, 'tint': 'frost', 'opacity': .8, 'iconSize': 'large'}
        wait(lambda: js(s1, 'document.querySelector(".fence").classList.contains("light")') is True, 'light tint')
        snapshot(s1, 'fence-frost.png')
        on_main(lambda: hub.dispatch(s1, {'action': 'collapse', 'group': first}))
        wait(lambda: on_main(s1.get_size)[1] == 44, 'roll up')
        on_main(lambda: hub.dispatch(s1, {'action': 'fence-style', 'changes': {'autoRoll': True}}))
        on_main(lambda: hub.dispatch(s1, {'action': 'fence-hover', 'inside': True}))
        wait(lambda: on_main(s1.get_size)[1] > 150, 'hover expands a rolled-up fence')
        on_main(lambda: hub.dispatch(s1, {'action': 'fence-hover', 'inside': False}))
        wait(lambda: on_main(s1.get_size)[1] == 44, 'leaving rolls it back up')
        on_main(hub.toggle_fences)
        wait(lambda: not on_main(s1.get_visible) and not on_main(s2.get_visible), 'quick-hide')
        assert json.loads(fenced_file.read_text())['paths'] == [str(desktop/'b c.pdf')], 'quick-hide keeps icons tidy'
        on_main(hub.peek); wait(lambda: on_main(s1.get_visible), 'peek shows hidden fences')
        on_main(hub.peek); wait(lambda: not on_main(s1.get_visible), 'peek ends hidden')
        on_main(hub.toggle_fences); wait(lambda: on_main(s1.get_visible) and on_main(s2.get_visible), 'quick-show')
        print('Fences: style, roll-up, hover expand, quick-hide and peek passed', flush=True)
        # 5. New fence at a desktop point; deleting a fence returns its icons.
        on_main(lambda: hub.new_fence(200, 420))
        newest = hub.store.state['groups'][-1]
        assert (newest['title'], newest['x'], newest['y']) == ('New fence', 200, 420)
        wait(lambda: on_main(lambda: hub.surfaces[newest['id']].ready) and js(hub.surfaces[newest['id']], '!!document.querySelector(".fence-rename")') is True, 'new fence opens rename')
        on_main(lambda: hub.dispatch(s1, {'action': 'remove-group', 'group': first}))
        wait(lambda: json.loads(fenced_file.read_text())['paths'] == [], 'delete returns icons')
        assert all((desktop/n).read_text() == n for n in ('a.txt', 'b c.pdf')), 'files untouched'
        print('Fences: new fence at a point, delete returns icons, files untouched', flush=True)
    except Exception:
        import traceback; traceback.print_exc(); exit_code = 1
    finally:
        GLib.idle_add(hub.quit)

threading.Thread(target=verify, daemon=True).start()
hub.run(None)
assert json.loads(fenced_file.read_text())['paths'] == [], 'shutdown returns icons to the desktop'
print('Fences: shutdown cleared the fenced list' if exit_code == 0 else 'Fences live test FAILED', flush=True)
workspace.cleanup()
raise SystemExit(exit_code)
