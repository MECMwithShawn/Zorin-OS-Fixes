"""Caption routing must never treat an XID as a Mutter window ID."""
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import windowing
from multitasking import Multitasking
from app import Hub

@unittest.skipUnless(hasattr(windowing,'GnomeWindows'),'GNOME backend required')
class CaptionTargetTests(unittest.TestCase):
    def setUp(self):
        self.manager=windowing.GnomeWindows.__new__(windowing.GnomeWindows)
        frame=NS(x=10,y=20,width=900,height=600)
        self.surface=NS(mode='explorer',get_mapped=lambda:True,get_title=lambda:'Photos',
                        get_window=lambda:NS(get_xid=lambda:999,get_frame_extents=lambda:frame))
        self.manager.windows=Mock(return_value=[])
    def client(self,ident=12,title='Photos',pid=None,rect=(10,20,900,600)):
        return NS(get_pid=lambda:os.getpid() if pid is None else pid,get_name=lambda:title,
                  get_geometry=lambda:rect,get_xid=lambda:ident)
    def test_native_id_and_foreign_process(self):
        self.manager.windows.return_value=[self.client(pid=os.getpid()+1),self.client(44)]
        self.assertEqual(self.manager.for_surface(self.surface).get_xid(),44)
    def test_duplicate_titles_use_frame(self):
        self.manager.windows.return_value=[self.client(rect=(30,50,900,600)),self.client(44)]
        self.assertEqual(self.manager.for_surface(self.surface).get_xid(),44)
    def test_ambiguous_closed_or_unmapped_never_fall_back(self):
        for windows in ([],[self.client(),self.client(44)], [self.client(title='Different app')]):
            self.manager.windows.return_value=windows
            self.assertIsNone(self.manager.for_surface(self.surface))
        self.surface.get_mapped=lambda:False
        self.manager.windows.return_value=[self.client()]
        self.assertIsNone(self.manager.for_surface(self.surface))
        self.surface.get_mapped=lambda:True;self.surface.get_window=lambda:None
        self.assertIsNone(self.manager.for_surface(self.surface))
    def test_dispatch_uses_surface_not_xid(self):
        hub=NS(multitasking=Mock())
        Hub.dispatch(hub,self.surface,{'action':'snap-layouts'})
        hub.multitasking.show_surface_snap.assert_called_once_with(self.surface)
        hub.multitasking.show_snap.assert_not_called()
    def test_resolved_request_cancels_hover_without_active_fallback(self):
        m=NS(caption_hover=Mock(),windows=NS(for_surface=Mock(return_value=self.client(44))),show_snap=Mock())
        Multitasking.show_surface_snap(m,self.surface)
        m.caption_hover.assert_called_once_with(self.surface,False)
        m.show_snap.assert_called_once_with(44)
        m.show_snap.reset_mock();m.windows.for_surface.return_value=None
        Multitasking.show_surface_snap(m,self.surface)
        m.show_snap.assert_not_called()

if __name__=='__main__':unittest.main()
