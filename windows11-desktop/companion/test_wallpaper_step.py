"""Desktop menu Next/Previous background: walks local history, downloads only past the newest."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import wallpaper
import wallpaper_action


class StepTests(unittest.TestCase):
    def setUp(self):
        # Patched here, not through the environment: another test may have imported wallpaper first.
        self.temp = tempfile.TemporaryDirectory(prefix='zorin11-step-'); self.addCleanup(self.temp.cleanup)
        for name, value in (('CONFIG', Path(self.temp.name)), ('STATE', Path(self.temp.name, 'wallpapers.json')),
                            ('ROOT', Path(self.temp.name, 'wallpapers'))):
            patcher = patch.object(wallpaper, name, value); patcher.start(); self.addCleanup(patcher.stop)
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

    def picture(self, name, data=b'\xff\xd8\xffpicture'):
        path = Path(self.temp.name, name); path.write_bytes(data)
        return path

    def save_current(self, path):
        with patch.object(wallpaper, 'current_path', return_value=path), \
                patch.object(wallpaper, 'saved_folder', return_value=Path(self.temp.name, 'saved')):
            return wallpaper.keep()

    def test_save_copies_the_picture_and_stops_rotation(self):
        state = wallpaper.load(); state.update(daily=True, history=[{'id': 'abc', 'title': 'Go: with/the gusts'}]); wallpaper.save(state)
        target = self.save_current(self.picture('abc.image'))
        self.assertEqual(target.name, 'Go with the gusts.jpg')
        self.assertEqual(target.read_bytes(), b'\xff\xd8\xffpicture')
        self.assertFalse(wallpaper.load()['daily'])
        self.assertFalse(wallpaper.due())
        self.assertEqual(wallpaper.load()['history'][0]['id'], 'abc')

    def test_saving_twice_keeps_one_copy_but_a_new_picture_gets_its_own(self):
        first = self.save_current(self.picture('abc.image'))
        self.assertEqual(self.save_current(self.picture('abc.image')), first)
        second = self.save_current(self.picture('abc.image', b'\x89PNG\r\n\x1a\nother'))
        self.assertEqual(second.name, 'Desktop background abc.png')
        third = self.save_current(self.picture('abc.image', b'\xff\xd8\xffother'))
        self.assertEqual(third.name, 'Desktop background abc (2).jpg')
        self.assertEqual(len(list(first.parent.iterdir())), 3)

    def test_a_failed_save_leaves_rotation_alone(self):
        state = wallpaper.load(); state['daily'] = True; wallpaper.save(state)
        with patch.object(wallpaper, 'current_path', return_value=None):
            self.assertRaises(ValueError, wallpaper.keep)
        self.assertTrue(wallpaper.load()['daily'])

    def test_menu_save_reports_where_the_picture_went(self):
        with patch.object(wallpaper, 'keep', return_value=Path('/saved/x.jpg')), patch.object(wallpaper_action, 'notify') as notify:
            self.assertEqual(wallpaper_action.main('save'), 0)
        self.assertIn('/saved/x.jpg', notify.call_args[0][1])


if __name__ == '__main__':
    unittest.main()
