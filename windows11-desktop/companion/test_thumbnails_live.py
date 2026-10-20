"""Real WebKit image requests → Hub resource authorization → image decoder."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

if __name__ != '__main__':
    import unittest
    raise unittest.SkipTest('Run this isolated integration test directly.')
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='thumbnail-session-') as temp:
        root = Path(temp)
        (root/'runtime').mkdir(mode=0o700)
        env = dict(os.environ, GDK_BACKEND='x11', GTK_USE_PORTAL='0', GIO_USE_VFS='local',
                   XDG_RUNTIME_DIR=str(root/'runtime'), XDG_CONFIG_HOME=str(root/'config'),
                   XDG_CACHE_HOME=str(root/'cache'), XDG_DATA_HOME=str(root/'data'),
                   WEBKIT_DISABLE_COMPOSITING_MODE='1')
        raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',
                                         __file__,'--private',*sys.argv[1:]],env=env,timeout=80).returncode)

import gi
gi.require_version('Gtk','3.0')
gi.require_version('WebKit2','4.1')
from gi.repository import Gtk, WebKit2, GLib
from PIL import Image
from app import Hub
import explorer
import file_thumbnails


def pump(seconds=.05):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.003)


def until(condition, timeout=10):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        pump()
        if condition():
            return
    raise AssertionError('Timed out waiting for thumbnails')


with tempfile.TemporaryDirectory(prefix='thumbnail-files-') as temp:
    root = Path(temp)
    photos = root/'OneDrive/Photos'
    photos.mkdir(parents=True)
    other = root/'Other'
    other.mkdir()
    for index in range(120):
        Image.new('RGB',(400,250),('red','green','blue')[index%3]).save(photos/f'Photo {index:03}.jpg')
    (photos/'Broken.jpg').write_bytes(b'not an image')
    (photos/'Vector.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (photos/'Movie.mov').write_bytes(b'not a movie')
    before = {p:p.read_bytes() for p in photos.iterdir()}
    manager = WebKit2.UserContentManager()
    manager.register_script_message_handler('desktop')
    context = WebKit2.WebContext.new_ephemeral()
    web = WebKit2.WebView(web_context=context, user_content_manager=manager)
    context.get_security_manager().register_uri_scheme_as_local('zorin11')
    context.get_security_manager().register_uri_scheme_as_secure('zorin11')
    window = Gtk.Window(title='Thumbnail test')
    window.set_default_size(1120,760)
    window.add(web)
    window.show_all()
    ready = []
    errors = []
    requested = []
    surface = SimpleNamespace(mode='explorer',web=web,location=str(photos),file_state=None)
    hub = SimpleNamespace(surfaces={str(id(surface)):surface},icon_cache={},apps={},connect=lambda *_:None)
    hub.icon_bytes = lambda *args: Hub.icon_bytes(hub,*args)

    def resource(request):
        if '://thumbnail/' in request.get_uri():
            requested.append(request.get_uri())
        Hub.resource(hub,request)
    context.register_uri_scheme('zorin11',resource)

    def send(data):
        web.evaluate_javascript('window.receive('+json.dumps(data)+')',-1,None,None,None,None,None)

    def navigate(path):
        surface.location = str(path)
        surface.file_state = explorer.listing(str(path))
        surface.file_state['clouds'] = [dict(name='OneDrive - Personal',path=str(photos.parent),icon='folder')]
        send(dict(type='state',data=dict(surface.file_state,mode='explorer')))
        file_thumbnails.prefetch(hub, surface)

    def message(_manager,result):
        item = json.loads(result.get_js_value().to_string())
        if item['action']=='ready':
            ready.append(True)
            navigate(photos)
        elif item['action']=='file-navigate':
            navigate(item['path'])
        elif item['action'] not in ('file-preview-cancel','file-loading'):
            errors.append(item['action'])
    manager.connect('script-message-received::desktop',message)

    def js(code):
        result = []
        def done(view,response,*_):
            try:
                result.append(json.loads(view.evaluate_javascript_finish(response).to_json(0)))
            except Exception as error:
                result.append(error)
        web.evaluate_javascript('JSON.stringify(('+code+') ?? null)',-1,None,None,None,done,None)
        until(lambda:bool(result),5)
        if isinstance(result[0],Exception):
            raise result[0]
        return json.loads(result[0])

    web.load_uri('zorin11://ui/index.html')
    try:
        until(lambda:ready)
        until(lambda:js('document.querySelectorAll(".file-item").length')==123)
        js('document.querySelector("button[aria-label=\'Large icons\']").click()')
        until(lambda:js('[...document.querySelectorAll(".photo-thumbnail")].filter(i=>i.naturalWidth>0).length')>=10)
        pump(.5)
        assert len(requested)<90, ('Offscreen files loaded eagerly',len(requested))
        assert js('document.querySelector(".photo-thumbnail").getBoundingClientRect().height')==80
        assert js('document.querySelector(".file-thumbnail").getBoundingClientRect().height')==80
        assert js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Broken.jpg").querySelectorAll(".photo-thumbnail").length')==0
        assert js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Vector.svg").querySelectorAll(".photo-thumbnail").length')==0
        first_count = len(requested)
        js('document.querySelector(".explorer-files").scrollTop=100000')
        until(lambda:len(requested)>first_count)
        until(lambda:js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Photo 119.jpg").querySelector(".photo-thumbnail")?.naturalWidth>0'))
        # Navigating away while work is pending cannot deliver images into another folder.
        navigate(other)
        until(lambda:js('document.querySelectorAll(".file-item").length')==0)
        navigate(photos)
        until(lambda:js('document.querySelectorAll(".file-item").length')==123)
        js('document.querySelector(".explorer-files").scrollTop=0')
        until(lambda:js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Photo 000.jpg").querySelector(".photo-thumbnail")?.naturalWidth>0'))
        old = js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Photo 000.jpg").querySelector(".photo-thumbnail").src')
        Image.new('RGB',(300,200),'purple').save(photos/'Photo 000.jpg')
        navigate(photos)
        until(lambda:js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Photo 000.jpg").querySelector(".photo-thumbnail")?.naturalWidth>0'))
        assert js('[...document.querySelectorAll(".file-item")].find(e=>e.title==="Photo 000.jpg").querySelector(".photo-thumbnail").src') != old
        js('document.querySelector("button[aria-label=\'Details view\']").click()')
        until(lambda:js('document.querySelector(".photo-thumbnail").getBoundingClientRect().height')==20)
        js('document.querySelector("button[aria-label=\'Large icons\']").click()')
        if '--onedrive' in sys.argv:
            assert js('[...document.querySelectorAll(".explorer-sidebar button")].some(b=>b.textContent==="OneDrive - Personal")')
            js('[...document.querySelectorAll(".explorer-sidebar button")].find(b=>b.textContent==="OneDrive - Personal").click()')
            until(lambda:surface.location==str(photos.parent))
            navigate(photos)
        assert js('window.desktopErrors') == []
        assert errors == [], errors
        if os.environ.get('ZORIN11_TEST_OUTPUT'):
            path = Path(os.environ['ZORIN11_TEST_OUTPUT'])
            path.mkdir(parents=True,exist_ok=True)
            finished=[]
            def snap(view,response,*_):
                view.get_snapshot_finish(response).write_to_png(str(path/'explorer-thumbnails-fixture.png'))
                finished.append(True)
            pump(.5)
            web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,WebKit2.SnapshotOptions.NONE,None,snap,None)
            until(lambda:finished)
        assert all(p.read_bytes()==content for p,content in before.items() if p.name!='Photo 000.jpg')
        print('PASS: actual WebKit image decoding, lazy scrolling, 80px/20px layout, fallback, navigation, '
              'file-change invalidation, unchanged source files'+(' and OneDrive navigation' if '--onedrive' in sys.argv else ''))
    finally:
        hub.surfaces.clear()
        if getattr(hub,'thumbnails',None):
            hub.thumbnails.close()
            hub.thumbnails.pool.shutdown(wait=True)
        pump(.2)
        window.destroy()
