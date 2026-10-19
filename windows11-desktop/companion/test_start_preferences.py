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
        self.assertEqual(reloaded.snapshot(), dict(roots=[str(self.docs)], exclusions=[], recentDocuments=False))

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
