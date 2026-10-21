"""Modifier tracking must not require X11 or commit on a lost Shell bridge."""
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version("Gtk","3.0")
gi.require_version("Gdk","3.0")
from gi.repository import GLib, Gdk
from switcher import AltKeys, Switcher

class ModifierTests(unittest.TestCase):
    def test_gnome_never_loads_x11(self):
        with patch('gnome_bridge.active',return_value=True), patch('switcher.C.CDLL') as dll, patch('gnome_bridge.call',return_value=int(Gdk.ModifierType.MOD1_MASK)) as call:
            keys=AltKeys()
            self.assertTrue(keys.held())
            call.return_value=0
            self.assertFalse(keys.held())
            keys.close();keys.close()
            dll.assert_not_called()

    def chooser(self):
        chooser=Switcher.__new__(Switcher)
        chooser.m=Mock();chooser.keys=Mock();chooser.window=object()
        chooser.timer=1;chooser.commit=Mock()
        return chooser

    def test_bridge_failure_cancels_without_activation(self):
        for callback in ('tick','check_release'):
            chooser=self.chooser()
            chooser.keys.held.side_effect=GLib.Error('bridge unavailable')
            self.assertFalse(getattr(chooser,callback)())
            chooser.m.close.assert_called_once_with(False)
            chooser.commit.assert_not_called()

    def test_release_commits(self):
        chooser=self.chooser();chooser.keys.held.return_value=False
        self.assertFalse(chooser.tick())
        chooser.commit.assert_called_once_with()
        self.assertEqual(chooser.timer,0)

    def test_held_gnome_modifier_keeps_chooser_open(self):
        chooser=self.chooser();chooser.keys.held.return_value=True
        with patch('gnome_bridge.active',return_value=True):
            self.assertTrue(chooser.tick())
        chooser.commit.assert_not_called();chooser.m.close.assert_not_called()

if __name__=='__main__':unittest.main()
