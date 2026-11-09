"""Display-only restoration must not borrow same-app windows from the laptop."""
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from saved_groups import SavedGroups
from window_layouts import encode
from test_window_layouts import OUTPUTS

class Window:
    def __init__(self,ident,rect):self.ident=ident;self.rect=rect
    def get_xid(self):return self.ident
    def get_geometry(self):return self.rect
    def get_application_id(self):return 'browser.desktop'
    def get_class_group_name(self):return 'browser'
    def is_minimized(self):return False
    def is_fullscreen(self):return False

class DisplayRestoreTests(unittest.TestCase):
    def test_same_app_windows_on_laptop_are_not_borrowed(self):
        with tempfile.TemporaryDirectory() as root:
            laptop=Window(1,(500,1000,700,500));dell=Window(2,(30,30,800,700))
            windows=NS(windows=lambda:[laptop,dell],get=lambda ident:{1:laptop,2:dell}[ident],active=lambda:laptop,minimum=lambda w:(1,1),can_snap=lambda w:True,place=Mock())
            m=NS(config=Path(root),windows=windows,desktops=NS(busy=False,current=lambda:0,items=lambda:[dict(id=0,uid='desk')],on=lambda w,d:True),area=lambda *_:OUTPUTS[0]['area'])
            saved=SavedGroups(m)
            member=dict(app='browser.desktop',**{'class':'browser'},state='normal',**encode((30,30,800,700),OUTPUTS))
            ident=saved.store.put([member],desktop='desk',kind='layout',display_only=True)
            ticks=[]
            with patch('window_layouts.monitors',return_value=OUTPUTS),patch('saved_groups.catalog',return_value={'browser.desktop':Mock()}),patch('saved_groups.GLib.timeout_add',side_effect=lambda _,fn:ticks.append(fn) or 1):
                saved.restore(ident,Mock());ticks[0]()
            windows.place.assert_called_once_with(2,(30,30,800,700))
            saved.operation=None
            with patch('window_layouts.monitors',return_value=OUTPUTS[:1]),patch('saved_groups.catalog',return_value={'browser.desktop':Mock()}):
                with self.assertRaisesRegex(ValueError,'Connect the saved display'):saved.restore(ident,Mock())

if __name__=='__main__':unittest.main()
