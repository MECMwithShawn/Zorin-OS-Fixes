import json
import os
from pathlib import Path
import tempfile
import unittest

import fences
from model import Store


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.desktop = self.root/'Desktop'
        self.desktop.mkdir()
        for name in ('a.txt', 'b c.pdf'):
            (self.desktop/name).write_text(name)
        self.store = Store(self.root/'layout.json', [], self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_style_is_sanitized(self):
        self.assertEqual(fences.clean_style(None), fences.DEFAULT_STYLE)
        style = fences.clean_style({'tint': 'ocean', 'opacity': 7, 'iconSize': 'huge', 'sort': 'name',
                                    'autoRoll': 1, 'script': '<x>'})
        self.assertEqual(style, {'tint': 'ocean', 'opacity': 1.0, 'iconSize': 'medium', 'sort': 'name',
                                 'autoRoll': True})
        self.assertEqual(fences.clean_style({'opacity': 'nope', 'tint': '#fff'})['tint'], 'slate')
        self.assertEqual(fences.clean_style({'opacity': 0})['opacity'], 0.1)

    def test_uri_paths_accept_only_existing_local_files(self):
        uris = ['file://' + str(self.desktop/'b%20c.pdf'), 'file://' + str(self.desktop/'b%20c.pdf'),
                'https://example.com/a.txt', 'file://other-host/etc/passwd',
                'file://' + str(self.desktop/'missing.txt'), 'file://localhost' + str(self.desktop/'a.txt')]
        self.assertEqual(fences.uri_paths(uris), [str(self.desktop/'b c.pdf'), str(self.desktop/'a.txt')])

    def test_a_path_lives_in_one_fence(self):
        first = self.store.add_group('One')
        second = self.store.add_group('Two')
        path = str(self.desktop/'a.txt')
        self.store.add_paths(first, [path])
        self.store.add_paths(second, [path, path])
        self.assertEqual(self.store.group(first)['items'], [])
        self.assertEqual(self.store.group(second)['items'], [{'kind': 'path', 'path': path}])
        portal = self.store.add_group('Portal', folder=str(self.root))
        with self.assertRaises(ValueError):
            self.store.add_paths(portal, [path])

    def test_reorder_and_new_fence_position(self):
        group = self.store.add_group('Fence', x=640, y=200)
        self.assertEqual((self.store.group(group)['x'], self.store.group(group)['y']), (640, 200))
        paths = [str(self.desktop/n) for n in ('a.txt', 'b c.pdf')]
        self.store.add_paths(group, paths)
        self.store.reorder_item(group, paths[1], paths[0])
        self.assertEqual([i['path'] for i in self.store.group(group)['items']], paths[::-1])
        self.store.reorder_item(group, paths[1], None)
        self.assertEqual([i['path'] for i in self.store.group(group)['items']], paths)
        self.store.reorder_item(group, 'unknown', paths[0])
        self.assertEqual([i['path'] for i in self.store.group(group)['items']], paths)

    def test_fenced_list_covers_desktop_files_in_visible_regular_fences(self):
        group = self.store.add_group('Fence')
        outside = self.root/'elsewhere.txt'
        outside.write_text('x')
        self.store.add_paths(group, [str(self.desktop/'a.txt'), str(outside)])
        self.store.add_group('Portal', folder=str(self.desktop))
        state = self.store.state
        self.assertEqual(fences.fenced_paths(state, self.desktop), [str(self.desktop/'a.txt')])
        state['groups_visible'] = False
        self.assertEqual(fences.fenced_paths(state, self.desktop), [])

    def test_fenced_file_is_atomic_and_only_rewritten_on_change(self):
        target = self.root/'config/fenced.json'
        self.assertTrue(fences.write_fenced(target, ['/a'], 42))
        self.assertFalse(fences.write_fenced(target, ['/a'], 42))
        published = json.loads(target.read_text())
        self.assertEqual((published['version'], published['pid'], published['paths']), (1, 42, ['/a']))
        boot, start = fences.process_identity(os.getpid())
        self.assertTrue(boot and start.isdigit())
        self.assertEqual(fences.process_identity(2**30), ('', ''))
        self.assertTrue(fences.write_fenced(target, [], 42))
        self.assertEqual([p.name for p in target.parent.iterdir()], ['fenced.json'])

    def test_untrusted_launchers_never_run(self):
        launcher = self.desktop/'tool.desktop'
        launcher.write_text('[Desktop Entry]\nType=Application\nName=Tool\nExec=true\n')
        self.assertFalse(fences.launcher_trusted(launcher))  # not executable
        launcher.chmod(0o755)
        self.assertFalse(fences.launcher_trusted(launcher))  # executable but never marked trusted
        self.assertFalse(fences.launcher_trusted(self.desktop/'missing.desktop'))

    def test_sorting(self):
        items = [{'kind': 'path', 'name': 'b.txt', 'path': '/b.txt', 'modified': 1},
                 {'kind': 'app', 'name': 'Zed'},
                 {'kind': 'path', 'name': 'A', 'path': '/A', 'isDir': True, 'modified': 3}]
        self.assertEqual([i['name'] for i in fences.sort_items(items, 'name')], ['A', 'b.txt', 'Zed'])
        self.assertEqual([i['name'] for i in fences.sort_items(items, 'type')], ['Zed', 'A', 'b.txt'])
        self.assertEqual([i['name'] for i in fences.sort_items(items, 'modified')], ['A', 'b.txt', 'Zed'])
        self.assertIs(fences.sort_items(items, 'manual'), items)

    def test_snapping_to_edges_and_neighbours(self):
        area = (0, 0, 1920, 1040)
        self.assertEqual(fences.snap(9, 600, 300, 200, area, []), (0, 600))
        self.assertEqual(fences.snap(1612, 835, 300, 200, area, []), (1620, 840))
        neighbour = [(400, 100, 300, 250)]
        self.assertEqual(fences.snap(706, 108, 300, 200, area, neighbour), (700, 100))
        self.assertEqual(fences.snap(500, 500, 300, 200, area, neighbour), (500, 500))


if __name__ == '__main__':
    unittest.main()
