import json
from pathlib import Path
import tempfile
import unittest

from model import Store


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.path = self.home/'config/layout.json'
        self.ids = ['brave-browser.desktop', 'zorin11-explorer.desktop', 'zorin11-terminal.desktop', 'extra.desktop']
        self.store = Store(self.path, self.ids, self.home)

    def test_pins_reorder_and_reload(self):
        self.store.pin('extra.desktop', True)
        self.store.pin('extra.desktop', True)
        self.store.reorder('extra.desktop', 'brave-browser.desktop')
        self.store.pin('zorin11-explorer.desktop', False)
        self.assertEqual(Store(self.path, self.ids, self.home).state['pins'],
            ['extra.desktop', 'brave-browser.desktop', 'zorin11-terminal.desktop'])

    def test_recent_unique_and_bounded(self):
        for i in range(10):
            self.store.used(str(i))
        self.store.used('8')
        self.assertEqual(self.store.state['recent'], ['8', '9', '7', '6', '5', '4'])

    def test_shortcuts_do_not_move_files(self):
        target = self.home/'important.txt'
        target.write_text('keep this file')
        group = self.store.add_group('Test')
        item = {'kind': 'path', 'path': str(target)}
        self.store.add_item(group, item)
        self.store.add_item(group, item)
        self.assertEqual(len(self.store.group(group)['items']), 1)
        self.store.state['groups'] = [g for g in self.store.state['groups'] if g['id'] != group]
        self.store.save()
        self.assertEqual(target.read_text(), 'keep this file')

    def test_folder_group_does_not_accept_shortcuts(self):
        group = self.store.add_group('Folder', str(self.home))
        with self.assertRaises(ValueError):
            self.store.add_item(group, {'kind': 'app', 'id': self.ids[0]})

    def test_corrupt_state_preserved(self):
        self.path.write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            Store(self.path, self.ids, self.home)
        self.assertEqual(self.path.read_text(), '{broken')

    def test_geometry_persists(self):
        group = self.store.group('everyday')
        group.update(x=401, y=222, width=450, height=310, collapsed=True)
        self.store.save()
        reloaded = Store(self.path, self.ids, self.home).group('everyday')
        self.assertEqual([reloaded[k] for k in ['x','y','width','height','collapsed']], [401,222,450,310,True])


if __name__ == '__main__':
    unittest.main()
