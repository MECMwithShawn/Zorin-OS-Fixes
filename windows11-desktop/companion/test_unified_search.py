from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
import unified_search


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.apps=[dict(id='editor.desktop',name='Notes',description='Text editor',icon='notes.svg')]

    def search(self,query,**kwargs):
        return unified_search.search(query,self.apps,[self.root],threading.Event(),**kwargs)

    def test_apps_files_folders_and_settings_share_search(self):
        (self.root/'Notes.txt').write_text('This content is not indexed')
        (self.root/'Notes folder').mkdir()
        result=self.search('notes')['results']
        self.assertEqual({r['kind'] for r in result},{'app','file','folder'})
        self.assertEqual(result[0]['kind'],'app')
        self.assertEqual(self.search('volume')['results'][0]['id'],'sound')
        self.assertEqual(self.search('monitor')['results'][0]['id'],'display')
        self.assertEqual(self.search('indexed')['results'],[])

    def test_excludes_hidden_dependencies_links_and_special_files(self):
        for name in ('.private','node_modules','build'):
            p=self.root/name;p.mkdir();(p/'secret.txt').touch()
        outside=self.root/'.outside';outside.mkdir();(outside/'secret.txt').touch()
        (self.root/'secret-link').symlink_to(outside,target_is_directory=True)
        import os
        os.mkfifo(self.root/'secret-pipe')
        self.assertEqual(self.search('secret')['results'],[])

    def test_unicode_tokens_limits_and_short_queries(self):
        (self.root/'Café meeting notes.txt').touch()
        self.assertEqual(len(self.search('cafe notes')['results']),1)
        self.assertTrue(self.search('c')['filesNeedMore'])
        self.assertFalse(any(r['kind'] in ('file','folder') for r in self.search('c')['results']))
        self.assertTrue(self.search('notes',max_entries=0)['limited'])
        self.assertTrue(self.search('notes',seconds=-1)['limited'])

    def test_cancellation_and_duplicate_roots(self):
        (self.root/'test.txt').touch();cancel=threading.Event();cancel.set()
        self.assertEqual(unified_search.search('test',[],[self.root],cancel)['results'],[])
        result=unified_search.search('test',[],[self.root,self.root],threading.Event())
        self.assertEqual(len(result['results']),1)

    def test_latest_query_wins_and_open_requires_returned_result(self):
        from app import Hub
        pending=[];messages=[]
        surface=SimpleNamespace(location='::home',send=messages.append)
        hub=SimpleNamespace(apps={},background=lambda task,done,fail:pending.append(done))
        hub.start_search=lambda s:Hub.start_search(hub,s)
        for i in (1,2,3):Hub.search_action(hub,surface,dict(action='search-query',query=str(i),id=i))
        self.assertEqual(len(pending),1)
        messages.clear()
        pending.pop(0)(dict(results=[],limited=False));self.assertTrue(all(m['id']==3 for m in messages))
        self.assertEqual(len(pending),1)
        pending.pop(0)(dict(results=[],limited=False));self.assertEqual(messages[-1]['id'],3)
        with self.assertRaises(ValueError):Hub.search_action(hub,surface,dict(action='search-open',key='path:/etc/passwd'))
        Hub.search_action(hub,surface,dict(action='search-cancel'))
        self.assertEqual(surface.search_results,{})


if __name__=='__main__':unittest.main()
