"""Window visibility and safe panel fallback, without modifying the session."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from gnome_bridge import Window

class WaylandBridgeTests(unittest.TestCase):
    def test_unmapped_helpers_are_not_task_windows(self):
        row={'id':9,'rect':[0,0,0,0],'skip':False,'title':'OneDrive helper'}
        screen=SimpleNamespace(data={'windows':[row]})
        window=Window(screen,9)
        self.assertTrue(window.is_skip_tasklist())
        row['rect']=[0,0,640,480]
        self.assertFalse(window.is_skip_tasklist())
        row['skip']=True
        self.assertTrue(window.is_skip_tasklist())

    def test_wayland_does_not_capture_xwayland_root(self):
        from app import Hub
        surface=SimpleNamespace(mode='start',backdrop='stale',get_visible=lambda:False)
        hub=SimpleNamespace(backdrops={'start':b'stale'})
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'wayland'}),patch('app.Gdk.pixbuf_get_from_window') as capture:
            Hub.capture_backdrop(hub,surface,0,0,100,100)
        capture.assert_not_called()
        self.assertIsNone(surface.backdrop)
        self.assertNotIn('start',hub.backdrops)

if __name__=='__main__':unittest.main()
