"""Desktop menu Next/Previous background: walks local history, downloads only past the newest."""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ['ZORIN11_CONFIG_DIR'] = tempfile.mkdtemp(prefix='zorin11-step-')
import wallpaper
import wallpaper_action


class StepTests(unittest.TestCase):
    def setUp(self):
        self.applied = []
        def apply(ident):
            self.applied.append(ident)
            state = wallpaper.load(); state['current'] = ident; wallpaper.save(state)
        patcher = patch.object(wallpaper, 'apply', side_effect=apply)
        patcher.start(); self.addCleanup(patcher.stop)
        wallpaper.save({'source': 'spotlight', 'current': 'b', 'history': [{'id': i, 'title': i.upper()} for i in 'abc']})

    def test_previous_and_next_walk_history(self):
        self.assertEqual(wallpaper.step('previous')['id'], 'c')
        self.assertIsNone(wallpaper.step('previous'))
        self.assertEqual(wallpaper.step('next')['id'], 'b')
        self.assertEqual(wallpaper.step('next')['id'], 'a')
        self.assertEqual(self.applied, ['c', 'b', 'a'])

    def test_next_on_the_newest_downloads_only_with_a_picture_service(self):
        state = wallpaper.load(); state['current'] = 'a'; wallpaper.save(state)
        with patch.object(wallpaper, 'update', return_value={'id': 'new'}) as update:
            self.assertEqual(wallpaper.step('next'), {'id': 'new'})
            state['source'] = 'current'; wallpaper.save(state)
            self.assertIsNone(wallpaper.step('next'))
        self.assertEqual(update.call_count, 1)

    def test_a_picture_outside_history_steps_back_to_the_newest(self):
        state = wallpaper.load(); state['current'] = 'zorin-mountains'; wallpaper.save(state)
        self.assertEqual(wallpaper.step('previous')['id'], 'a')

    def test_action_never_opens_settings_and_reports_problems(self):
        with patch.object(wallpaper_action.subprocess, 'Popen') as popen, \
             patch.object(wallpaper_action, 'notify') as notify:
            self.assertEqual(wallpaper_action.main('previous'), 0)
            state = wallpaper.load(); state['current'] = 'c'; wallpaper.save(state)
            self.assertEqual(wallpaper_action.main('previous'), 0)
            with patch.object(wallpaper, 'update', side_effect=ValueError('Offline')):
                state['current'] = 'a'; wallpaper.save(state)
                self.assertEqual(wallpaper_action.main('next'), 1)
        popen.assert_not_called()
        self.assertEqual([c.args[0] for c in notify.call_args_list],
                         ['No earlier background', 'Couldn’t change the desktop background'])


if __name__ == '__main__':
    unittest.main()
