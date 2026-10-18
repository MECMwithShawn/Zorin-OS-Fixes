"""Boundary and recovery tests; never change the live desktop."""
import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import settings_backend as settings
import wallpaper

class SettingsTests(unittest.TestCase):
    def test_rejects_untrusted_commands_and_wrong_types(self):
        with patch.object(settings,'run') as run,patch.object(settings,'set_property') as set_property:
            for name,value in [('volume',True),('volume',101),('muted','false'),('screenTimeout',True),('screenTimeout',999),('wifi',1),('bluetooth','on'),('dnd',0),('shell','touch /tmp/unwanted')]:
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):settings.apply(name,value)
            run.assert_not_called();set_property.assert_not_called()
        with self.assertRaises(ValueError):settings.launch('sh -c anything')
    def test_missing_sound_output_is_not_applied(self):
        with patch.object(settings,'sound_outputs',return_value=[{'id':'speaker','name':'Speakers'}]),patch.object(settings,'run') as run:
            with self.assertRaises(ValueError):settings.apply('output','removed-device')
            run.assert_not_called()
    def test_boolean_preserves_dbus_type(self):
        with patch.object(settings,'set_property') as setter:
            settings.apply('bounceKeys',True)
            self.assertEqual(setter.call_args.args[:2],('accessibility','/BounceKeys'))
            self.assertIsInstance(setter.call_args.args[2],settings.dbus.Boolean)

class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.patches=[patch.object(wallpaper,'CONFIG',root),patch.object(wallpaper,'ROOT',root/'images'),patch.object(wallpaper,'STATE',root/'state.json')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_allowlist_rejects_insecure_and_lookalike_hosts(self):
        for url in ['http://www.bing.com/a','https://bing.com.example.com/a','https://user@bing.com/a','https://bing.com:444/a','file:///etc/passwd','https://127.0.0.1/a']:
            self.assertFalse(wallpaper.allowed_url(url),url)
        self.assertTrue(wallpaper.allowed_url('https://res.public.onecdn.static.microsoft/creativeservice/a.jpg'))
    def test_spotlight_extracts_only_image_metadata(self):
        ad={'title':'Landscape','copyright':'Photographer','landscapeImage':{'asset':'https://example.microsoft.com/image.jpg'},'trackingUrl':'https://example.microsoft.com/tracking'}
        payload={'batchrsp':{'items':[{'item':json.dumps({'ad':ad})}]}}
        with patch.object(wallpaper,'fetch',return_value=json.dumps(payload)) as fetch:
            result=wallpaper.candidates('spotlight')
            self.assertEqual(result,[{'url':ad['landscapeImage']['asset'],'title':'Landscape','credit':'Photographer'}])
            self.assertEqual(fetch.call_count,1)
    def test_daily_retry_and_success_guard(self):
        wallpaper.save({'source':'spotlight','daily':True,'lastDay':'2000-01-01','lastAttempt':0})
        self.assertTrue(wallpaper.due())
        state=wallpaper.load();state['lastAttempt']=wallpaper.time.time();wallpaper.save(state)
        self.assertFalse(wallpaper.due())
        state['lastAttempt']=0;state['lastDay']=datetime.date.today().isoformat();wallpaper.save(state)
        self.assertFalse(wallpaper.due())
        wallpaper.configure('source','current');self.assertFalse(wallpaper.due())
    def test_update_failure_keeps_previous_selection(self):
        wallpaper.save({'source':'spotlight','daily':True,'current':'existing','lastDay':'2000-01-01'})
        with patch.object(wallpaper,'download',side_effect=OSError('offline')):
            with self.assertRaises(OSError):wallpaper.update()
        state=wallpaper.load();self.assertEqual(state['current'],'existing');self.assertEqual(state['error'],'offline');self.assertFalse(wallpaper.due())
    def test_restore_preserves_later_manual_changes(self):
        wallpaper.save({'source':'spotlight','daily':True,'appliedPath':'managed.jpg','original':{'/a':'old.jpg','/b':None,'/c':'previous.jpg'}})
        xf=Mock();bus=Mock()
        with patch.object(wallpaper,'properties',return_value={'/a':'managed.jpg','/b':'managed.jpg','/c':'manual.jpg'}),patch.object(wallpaper.dbus,'SessionBus',return_value=bus),patch.object(wallpaper.dbus,'Interface',return_value=xf):
            wallpaper.restore()
        xf.SetProperty.assert_called_once_with('xfce4-desktop','/a','old.jpg');xf.ResetProperty.assert_called_once_with('xfce4-desktop','/b',False)
        self.assertFalse(wallpaper.load()['daily']);self.assertNotIn('original',wallpaper.load())
    def test_partial_apply_retains_recovery_paths(self):
        picture=Path(self.temp.name)/'image.jpg';picture.write_bytes(b'placeholder')
        wallpaper.save({'history':[],'appliedPath':'previous-managed.jpg','original':{'/a/last-image':'original.jpg'}})
        with patch.object(wallpaper,'image_path',return_value=picture),patch.object(wallpaper,'properties',side_effect=[{'/a/last-image':'previous-managed.jpg'},{}]),patch.object(wallpaper.subprocess,'check_output',return_value='DP-2 connected'),patch.object(wallpaper,'set_property',side_effect=RuntimeError('desktop service stopped')):
            with self.assertRaises(RuntimeError):wallpaper.apply('id')
        state=wallpaper.load();self.assertEqual(state['original']['/a/last-image'],'original.jpg');self.assertEqual(set(state['appliedPaths']),{str(picture),'previous-managed.jpg'})
    def test_history_path_cannot_escape_cache(self):
        for ident in ['../../etc/passwd','foo','a'*24]:
            with self.assertRaises(ValueError):wallpaper.image_path(ident)

if __name__=='__main__':unittest.main()
