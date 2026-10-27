import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'companion'),str(ROOT)]
import lockscreen,lockscreen_install,wallpaper,update_guard

class LockScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patches=[patch.object(lockscreen,'ROOT',self.root/'state'),patch.object(lockscreen,'sync')]
        self.sync=None
        for p in self.patches:self.sync=p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_apply_validates_and_never_changes_desktop(self):
        with patch.object(wallpaper,'apply') as desktop:
            state=lockscreen.apply({'source':'zorin','title':'Zorin','dimming':20})
            self.assertEqual(lockscreen.load()['source'],'zorin');self.sync.assert_called_once();desktop.assert_not_called()
            self.assertTrue(state['revision'])
            for changes in ({'dimming':101},{'source':'invalid'},{'enabled':'true'},{'path':'/missing-photo'}):
                with self.assertRaises(ValueError):lockscreen.apply(changes)
            self.assertEqual(lockscreen.load(),state)
    def test_custom_photo_survives_original_disappearing(self):
        original=self.root/'OneDrive photo.jpg'
        original.write_bytes(Path('/usr/share/backgrounds/Zorin.jpg').read_bytes())
        state=lockscreen.apply({'source':'picture','path':str(original)})
        self.assertNotEqual(state['path'],str(original));original.unlink()
        self.assertTrue(Path(state['path']).is_file())
    def test_offline_keeps_selected_image(self):
        state=lockscreen.apply({})
        with patch.object(lockscreen,'prepare',side_effect=OSError('Offline')):
            with self.assertRaises(OSError):lockscreen.refresh()
        self.assertEqual(lockscreen.load()['path'],state['path']);self.assertEqual(self.sync.call_count,1)
        self.assertIn('Offline',lockscreen.load()['error'])
    def test_refresh_does_not_overwrite_user_changes(self):
        lockscreen.apply({})
        def prepare(source):
            lockscreen.apply({'source':'zorin'})
            return {'path':'/not-selected','title':'Stale photo'}
        with patch.object(lockscreen,'prepare',side_effect=prepare):self.assertFalse(lockscreen.refresh())
        self.assertEqual(lockscreen.load()['source'],'zorin')
    def test_disabled_and_local_sources_do_not_fetch(self):
        with patch.object(lockscreen,'prepare') as prepare:
            for options in ({'source':'zorin'},{'source':'picture'},{'source':'desktop'},{'source':'bing','daily':False},{'source':'spotlight','daily':True,'enabled':False}):
                lockscreen.apply(options);self.assertFalse(lockscreen.refresh(force=True))
            prepare.assert_not_called()
    def test_image_rejects_non_image_response(self):
        with patch.object(wallpaper,'candidates',return_value=[{'url':'https://www.bing.com/photo'}]),patch.object(wallpaper,'fetch',return_value=b'<html>bad</html>'):
            with self.assertRaises(ValueError):lockscreen.prepare('bing')
        self.assertFalse((lockscreen.ROOT/'state.json').exists())
    def test_install_and_route_preserve_other_code(self):
        files=lockscreen_install.files(self.root)
        for path,data in files.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        lockscreen_install.compile_schema(self.root)
        path=self.root/'.local/share/zorin11-hub/settings_backend.py'
        text="# Claude OneDrive code\ndef launch(tool):\n    command=TOOLS[tool]\n    existing_custom_behavior()\n"
        path.write_text(text);changes=lockscreen_install.route_files(self.root);path.write_bytes(changes[path])
        self.assertIn('# Claude OneDrive code',path.read_text());self.assertIn('existing_custom_behavior()',path.read_text())
        self.assertFalse(lockscreen_install.route_files(self.root))
        self.assertIn(lockscreen_install.UUID,update_guard.MANAGED_EXTENSIONS)
        self.assertTrue(update_guard.protected_file('home/.local/share/gnome-shell/extensions/'+lockscreen_install.UUID+'/extension.js'))

if __name__=='__main__':unittest.main()
