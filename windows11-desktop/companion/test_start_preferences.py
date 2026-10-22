from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from start_preferences import Preferences, documents, paths


class StartPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root/'Documents'; self.docs.mkdir()
        self.file = self.root/'settings.json'
        self.preferences = Preferences(self.file, [str(self.docs)])

    def test_persist_remove_reset_and_private_permissions(self):
        other = self.root/'other'; other.mkdir()
        self.preferences.change('add', 'roots', str(other))
        self.preferences.change('add', 'exclusions', str(other))
        self.preferences.change('recent', value=False)
        reloaded = Preferences(self.file, [str(self.docs)])
        self.assertEqual(reloaded.snapshot(), self.preferences.snapshot())
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        reloaded.change('remove', 'roots', str(self.docs))
        self.assertEqual(reloaded.snapshot()['roots'], [str(other)])
        reloaded.change('reset')
        self.assertEqual(reloaded.snapshot(), dict(roots=[str(self.docs)], exclusions=[], recentDocuments=False, style='windows11', tiles={},
            layout='default', columns=6, showRecommended=True, tabs=[],
            transparency=0, corners='style', button='windows11'))

    def test_start_style_persists_and_old_files_default_to_windows11(self):
        self.file.write_text('{"roots": [], "exclusions": [], "recentDocuments": true}')
        self.assertEqual(Preferences(self.file, []).snapshot()['style'], 'windows11')
        self.preferences.change('style', value='windows7')
        self.preferences.change('reset')
        self.assertEqual(Preferences(self.file, []).snapshot()['style'], 'windows7')
        for value in ('vista', None, 7):
            with self.assertRaises(ValueError): self.preferences.change('style', value=value)
        self.file.write_text('{"roots": [], "exclusions": [], "recentDocuments": true, "style": "bogus"}')
        self.assertEqual(Preferences(self.file, []).snapshot()['style'], 'windows11')

    def test_tile_sizes_persist_medium_is_default_and_bad_values_are_dropped(self):
        self.preferences.change('style', value='windows10')
        self.preferences.change('tile', 'orion.desktop', 'wide')
        self.preferences.change('tile', 'nova.desktop', 'large')
        self.preferences.change('tile', 'nova.desktop', 'medium')
        reloaded = Preferences(self.file, [])
        self.assertEqual((reloaded.snapshot()['style'], reloaded.snapshot()['tiles']), ('windows10', {'orion.desktop': 'wide'}))
        reloaded.snapshot()['tiles']['x'] = 'small'
        self.assertNotIn('x', reloaded.snapshot()['tiles'])
        for key, value in (('orion.desktop', 'huge'), ('', 'wide'), (None, 'wide')):
            with self.assertRaises(ValueError): reloaded.change('tile', key, value)
        self.file.write_text('{"roots": [], "exclusions": [], "recentDocuments": true, "tiles": {"a": "huge"}}')
        self.assertEqual(Preferences(self.file, []).snapshot()['tiles'], {})

    def test_windows11_layout_columns_and_recommended_persist(self):
        self.preferences.change('layout', value='more-pins')
        self.preferences.change('columns', value=8)
        self.preferences.change('show-recommended', value=False)
        snapshot = Preferences(self.file, []).snapshot()
        self.assertEqual((snapshot['layout'], snapshot['columns'], snapshot['showRecommended']), ('more-pins', 8, False))
        for operation, value in (('layout', 'tiny'), ('columns', 5), ('columns', True), ('show-recommended', 'no')):
            with self.assertRaises(ValueError): self.preferences.change(operation, value=value)
        self.file.write_text('{"roots": [], "exclusions": [], "recentDocuments": true, "columns": 99, "layout": "more-pins"}')
        snapshot = Preferences(self.file, []).snapshot()
        self.assertEqual((snapshot['layout'], snapshot['columns']), ('more-pins', 6))

    def test_tabs_create_rename_fill_reorder_and_delete(self):
        p = self.preferences
        p.change('tab-create', value='Work'); p.change('tab-create', value=' Games ')
        self.assertEqual([(t['id'], t['name']) for t in p.snapshot()['tabs']], [('tab1', 'Work'), ('tab2', 'Games')])
        for app in ('a.desktop', 'b.desktop', 'c.desktop', 'a.desktop'):
            p.change('tab-add', 'tab1', app)
        p.change('tab-move', 'tab1', {'id': 'c.desktop', 'target': 'a.desktop'})
        p.change('tab-remove', 'tab1', 'b.desktop')
        p.change('tab-rename', 'tab2', 'Play')
        p.change('tab-delete', 'tab2')
        p.change('tab-create', value='New')
        self.assertEqual(Preferences(self.file, []).snapshot()['tabs'],
                         [dict(id='tab1', name='Work', apps=['c.desktop', 'a.desktop']), dict(id='tab2', name='New', apps=[])])
        p.snapshot()['tabs'][0]['apps'].append('x')
        self.assertEqual(p.snapshot()['tabs'][0]['apps'], ['c.desktop', 'a.desktop'])
        for operation, key, value in (('tab-create', None, ''), ('tab-create', None, 'x'*41), ('tab-rename', 'missing', 'X'),
                                      ('tab-move', 'tab1', {'id': 'zzz', 'target': 'a.desktop'}), ('tab-bogus', 'tab1', None)):
            with self.assertRaises(ValueError): p.change(operation, key, value)
        for n in range(6): p.change('tab-create', value=f'T{n}')
        with self.assertRaises(ValueError): p.change('tab-create', value='Ninth')
        self.file.write_text('{"roots": [], "exclusions": [], "recentDocuments": true, "tabs": [{"id": "pinned", "name": "x", "apps": []}]}')
        self.assertEqual(Preferences(self.file, []).snapshot()['tabs'], [])

    def test_appearance_persists_and_bad_values_fall_back(self):
        self.preferences.change('transparency', value=40)
        self.preferences.change('corners', value='square')
        self.preferences.change('button', value='orb')
        snapshot = Preferences(self.file, []).snapshot()
        self.assertEqual((snapshot['transparency'], snapshot['corners'], snapshot['button']), (40, 'square', 'orb'))
        for operation, value in (('transparency', 50), ('transparency', True), ('corners', 'round'), ('button', 'logo')):
            with self.assertRaises(ValueError): self.preferences.change(operation, value=value)
        self.file.write_text('{"roots": [], "exclusions": [], "recentDocuments": true, "transparency": 90, "corners": "square", "button": 3}')
        snapshot = Preferences(self.file, []).snapshot()
        self.assertEqual((snapshot['transparency'], snapshot['corners'], snapshot['button']), (0, 'square', 'windows11'))

    def test_invalid_config_and_folders_do_not_replace_good_state(self):
        self.file.write_text('{broken')
        self.assertEqual(Preferences(self.file,[str(self.docs)]).snapshot(),self.preferences.snapshot())
        for value in ('relative', '/tmp/../etc', '/tmp/\0bad'):
            with self.assertRaises(ValueError): paths([value])
        with self.assertRaises(ValueError): paths([str(self.docs)]*33)
        link = self.root/'link'; link.symlink_to(self.docs, target_is_directory=True)
        for value in (str(link),str(self.root/'missing')):
            with self.assertRaises(ValueError): self.preferences.change('add','roots',value)
        self.assertEqual(self.file.read_text(), '{broken')

    def records(self):
        result = []
        for i, name in enumerate(('normal.txt','older.txt','.hidden.txt','secret/private.txt','node_modules/private.txt')):
            path = self.docs/name; path.parent.mkdir(exist_ok=True); path.touch()
            result.append(dict(uri=path.as_uri(),modified=100-i))
        return result

    def test_recent_privacy_exclusions_dedup_and_missing(self):
        records = self.records()
        self.preferences.change('add','exclusions',str(self.docs/'secret'))
        records.extend([dict(uri=(self.docs/'missing').as_uri(),modified=200),
                        dict(uri='https://example.com/private',modified=200),
                        dict(uri='file://other-host/home/private',modified=200),records[0]])
        self.assertEqual([i['name'] for i in documents(records,self.preferences.snapshot())],['normal.txt','older.txt'])
        records[0]['private'] = True
        self.assertEqual([i['name'] for i in documents(records,self.preferences.snapshot())],['older.txt'])
        self.assertEqual(documents(records,self.preferences.snapshot(),desktop_history=False),[])
        self.preferences.change('recent',value=False)
        self.assertEqual(documents(records,self.preferences.snapshot()),[])

    def test_links_and_outside_scope_cannot_be_suggestions(self):
        outside = self.root/'outside.txt'; outside.touch()
        link = self.docs/'link'; link.symlink_to(self.root,target_is_directory=True)
        records = [dict(uri=p.as_uri(),modified=100) for p in (outside,link/'outside.txt')]
        self.assertEqual(documents(records,self.preferences.snapshot()),[])
        self.preferences.change('remove','roots',str(self.docs))
        self.assertEqual(documents(self.records(),self.preferences.snapshot()),[])

    def test_recent_action_revalidates_current_privacy_and_files(self):
        from app import Hub
        records = self.records()
        items = documents(records,self.preferences.snapshot())
        hub = SimpleNamespace(recent_documents=items,start_preferences=self.preferences,recent_generation=1,
            recent_history_allowed=lambda:True,background=Mock())
        with self.assertRaises(ValueError): Hub.open_recent_document(hub,'file:///etc/passwd')
        Hub.open_recent_document(hub,items[0]['id'])
        task = hub.background.call_args.args[0]
        (self.docs/'normal.txt').unlink()
        with self.assertRaises(ValueError): task()
        hub.recent_history_allowed=lambda:False
        with self.assertRaises(ValueError): Hub.open_recent_document(hub,items[1]['id'])

    def test_only_installed_desktop_actions_are_allowed(self):
        from app import Hub
        app = SimpleNamespace(list_actions=lambda:['new-window'],launch_action=Mock())
        hub = SimpleNamespace(apps={'editor.desktop':app},store=SimpleNamespace(used=Mock()),
                              start=SimpleNamespace(hide=Mock()),broadcast=Mock())
        for ident,action in (('missing.desktop','new-window'),('editor.desktop','run-command')):
            with self.assertRaises(ValueError): Hub.launch_app_action(hub,ident,action)
        with patch('app.Gdk.Display.get_default') as display:
            Hub.launch_app_action(hub,'editor.desktop','new-window')
            app.launch_action.assert_called_once_with('new-window',display.return_value.get_app_launch_context.return_value)
        hub.store.used.assert_called_once_with('editor.desktop')


if __name__=='__main__': unittest.main()
