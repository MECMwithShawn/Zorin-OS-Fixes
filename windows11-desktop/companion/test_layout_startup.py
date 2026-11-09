import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch,Mock
from saved_groups import Recipes
from test_window_layouts import member
from layout_startup import StartupRestore,claim_session

class StartupTests(unittest.TestCase):
    def test_selection_persistence_and_removal(self):
        with tempfile.TemporaryDirectory() as root:
            store=Recipes(Path(root)/'recipes.json')
            first=store.put([member()],kind='layout',name='First')
            second=store.put([member()],desktop='other',kind='layout',name='Second')
            store.set_startup(first);store.set_startup(second)
            self.assertEqual(Recipes(store.path).data['startup_layout'],second)
            store.rename(second,'Renamed');self.assertEqual(store.data['startup_layout'],second)
            with self.assertRaises(ValueError):store.set_startup('missing')
            store.remove(second);self.assertNotIn('startup_layout',Recipes(store.path).data)
    def test_session_guard(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(claim_session(root,'login-one'))
            self.assertFalse(claim_session(root,'login-one'))
            self.assertTrue(claim_session(root,'login-two'))
    def test_delayed_restore_and_restart_no_repeat(self):
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'XDG_RUNTIME_DIR':root}),patch('layout_startup.session_key',return_value='login'),patch('layout_startup.GLib.timeout_add_seconds',return_value=42) as schedule,patch('layout_startup.locked',return_value=False):
            saved=NS(store=NS(data={'startup_layout':'chosen'}),operation=None,m=NS(desktops=NS(busy=False),hub=Mock()),restore=Mock())
            auto=StartupRestore(saved);schedule.assert_called_once_with(20,auto.run)
            self.assertFalse(auto.run());saved.restore.assert_called_once_with('chosen',auto.notify)
            StartupRestore(saved);self.assertEqual(schedule.call_count,1)
    def test_disabled_busy_locked_and_cancel(self):
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'XDG_RUNTIME_DIR':root}),patch('layout_startup.session_key',return_value='login'),patch('layout_startup.GLib.timeout_add_seconds') as schedule,patch('layout_startup.locked',return_value=True):
            saved=NS(store=NS(data={}),operation=None,m=NS(desktops=NS(busy=False),hub=Mock()),restore=Mock())
            auto=StartupRestore(saved);schedule.assert_not_called()
            saved.store.data['startup_layout']='chosen'
            self.assertTrue(auto.run());saved.restore.assert_not_called()
            auto.deadline=0;self.assertFalse(auto.run());saved.restore.assert_not_called()
            self.assertIn('skipped',saved.last_error)
            saved.store.data['startup_layout']='';self.assertFalse(auto.run())

if __name__=='__main__':unittest.main()
