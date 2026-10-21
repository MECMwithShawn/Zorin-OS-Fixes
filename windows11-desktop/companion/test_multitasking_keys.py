"""Task View edits must consume Escape before the containing window closes."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
import gi
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
from gi.repository import Gdk
from multitasking import Multitasking
from taskview import TaskView

class KeyboardPolishTests(unittest.TestCase):
    def setUp(self):
        self.text='';self.name='Draft';self.saved=[];self.focus=None
        self.entry=NS(set_text=lambda value:setattr(self,'name',value))
        self.search=NS(get_text=lambda:self.text,set_text=lambda value:setattr(self,'text',value),
                       grab_focus=self.focus_search,select_region=Mock())
        self.view=TaskView.__new__(TaskView)
        self.view.search=self.search;self.view.menu=None;self.view.editing=True
        self.view.rename_entries=[(self.entry,{'name':'Desktop 1'})];self.view.filter=Mock()
        self.win=NS(get_focus=lambda:self.focus,get_title=lambda:'Task view')
        self.view.win=self.win;self.view.alive=lambda:True
        self.m=NS(task_view=self.view,close=Mock())
    def focus_search(self):
        # Simulate the existing focus-out rename callback.
        if self.focus is self.entry and self.name!='Desktop 1':self.saved.append(self.name)
        self.focus=self.search
    def key(self,key,state=0):return Multitasking.key(self.m,self.win,NS(keyval=key,state=state))
    def test_escape_cancels_rename_before_focus_out(self):
        self.focus=self.entry
        self.assertTrue(self.key(Gdk.KEY_Escape))
        self.assertEqual(self.name,'Desktop 1');self.assertEqual(self.saved,[])
        self.assertIs(self.focus,self.search);self.assertFalse(self.view.editing)
        self.m.close.assert_not_called()
    def test_search_escape_clears_then_closes(self):
        self.text='Browser';self.focus=self.search
        self.assertTrue(self.key(Gdk.KEY_Escape));self.assertEqual(self.text,'')
        self.m.close.assert_not_called();self.view.filter.assert_called_once()
        self.assertTrue(self.key(Gdk.KEY_Escape));self.m.close.assert_called_once()
    def test_ctrl_f_focuses_and_selects_search(self):
        self.assertTrue(self.key(Gdk.KEY_f,Gdk.ModifierType.CONTROL_MASK))
        self.assertIs(self.focus,self.search);self.search.select_region.assert_called_once_with(0,-1)
        self.assertFalse(self.key(Gdk.KEY_f));self.m.close.assert_not_called()
    def test_escape_dismisses_menu_before_search_or_panel(self):
        self.view.menu=Mock();self.text='Browser'
        self.assertTrue(self.key(Gdk.KEY_Escape));self.view.menu.popdown.assert_called_once()
        self.assertEqual(self.text,'Browser');self.m.close.assert_not_called()
    def test_layout_number_skips_disabled_zones(self):
        first=Mock();first.get_sensitive.return_value=False
        second=Mock();second.get_sensitive.return_value=True
        self.m.task_view=None;self.m.layout_buttons=[[first,second]];self.win.get_title=lambda:'Snap layouts'
        self.assertTrue(self.key(Gdk.KEY_1));first.grab_focus.assert_not_called();second.grab_focus.assert_called_once()
        second.get_sensitive.return_value=False;second.grab_focus.reset_mock()
        self.assertTrue(self.key(Gdk.KEY_1));second.grab_focus.assert_not_called()

if __name__=='__main__':unittest.main()
