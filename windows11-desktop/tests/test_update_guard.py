"""No live settings, package installs or personal files are modified."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_guard as guard
import update_guard_root as root_hook
import desktop_backup as backup


class GuardTests(unittest.TestCase):
    def test_only_missing_desktop_files_restore_and_onedrive_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root/'home'; home.mkdir()
            source = root/'source'; source.write_bytes(b'preserved')
            names = [
                'home/.local/share/gnome-shell/extensions/zorin11@zorin-os-fixes/extension.js',
                'home/.local/share/applications/zorin11-explorer.desktop',
                'home/.local/share/zorin11-hub/explorer.py',
                'home/.config/zorin11-hub/audio-effects.json',
                'home/OneDrive/photo.jpg',
                'home/.config/gtk-3.0/gtk.css',
                'reference/vendor/extension.js',
            ]
            css = home/'.config/gtk-3.0/gtk.css'
            css.parent.mkdir(parents=True); css.write_bytes(b'newer user edit')
            archive = root/'snapshot.tar.gz'
            backup.build_archive(archive, {name:source for name in names}, {}, {})
            repaired, skipped = guard.restore_missing(archive, home)
            self.assertEqual(set(repaired), set(names[:2]))
            self.assertEqual(skipped, [])
            self.assertEqual(css.read_bytes(), b'newer user edit')
            self.assertFalse((home/'OneDrive').exists())
            self.assertFalse((home/'.local/share/zorin11-hub').exists())

    def test_symlink_parent_cannot_redirect_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root/'home';home.mkdir()
            outside=root/'outside';outside.mkdir()
            (home/'.local').symlink_to(outside, target_is_directory=True)
            source=root/'source';source.write_text('desktop')
            archive=root/'snapshot.tar.gz'
            backup.build_archive(archive, {'home/.local/share/applications/zorin11-start.desktop':source}, {}, {})
            repaired, skipped=guard.restore_missing(archive,home)
            self.assertFalse(repaired);self.assertTrue(skipped)
            self.assertEqual(list(outside.iterdir()),[])

    def test_backup_failure_keeps_prior_baseline_and_blocks_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state.json'
            previous={'pending':False,'status':'checked'}
            guard.save(state,previous)
            with patch.multiple(guard, ROOT=root, STATE=state), \
                 patch.object(backup,'configured_destination',return_value=root/'OneDrive'), \
                 patch.object(guard,'capture_profile',return_value={}), \
                 patch.object(backup,'create_snapshot',side_effect=RuntimeError('OneDrive unavailable')):
                with self.assertRaisesRegex(RuntimeError,'OneDrive unavailable'):
                    guard.before('test')
                self.assertEqual(guard.load(),previous)
                self.assertEqual(list(root.glob('baseline-*')),[])

    def test_same_transaction_reuses_but_new_transaction_backs_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); archive=root/'saved.tar.gz';archive.write_bytes(b'archive')
            (root/'desktop-snapshot.tar.gz').write_bytes(b'archive')
            state=root/'state.json'
            guard.save(state,{'pending':True,'transaction':'123-456','created':time.time(),
                'archive':str(archive),'destination':str(root)})
            with patch.multiple(guard,ROOT=root,STATE=state), \
                 patch.object(backup,'configured_destination',return_value=root), \
                 patch.object(backup,'create_snapshot',side_effect=RuntimeError('new transaction')), \
                 patch.object(guard,'capture_profile',return_value={}):
                guard.before('123-456')
                with self.assertRaisesRegex(RuntimeError,'new transaction'):
                    guard.before('999-000')

    def test_repair_defers_busy_packages_and_incompatible_gnome(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state.json'
            guard.save(state,{'pending':True,'last_event':0})
            with patch.multiple(guard,ROOT=root,STATE=state), \
                 patch.object(guard,'session_active',return_value=True), \
                 patch.object(guard,'package_busy',return_value=True), \
                 patch.object(guard,'restore_missing') as restore:
                guard.repair();self.assertTrue(guard.load()['pending']);restore.assert_not_called()
            with patch.multiple(guard,ROOT=root,STATE=state), \
                 patch.object(guard,'session_active',return_value=True), \
                 patch.object(guard,'package_busy',return_value=False), \
                 patch.object(guard,'compatible',return_value='New GNOME major'), \
                 patch.object(guard.subprocess,'run'), \
                 patch.object(guard,'restore_missing') as restore:
                guard.repair();self.assertEqual(guard.load()['status'],'needs-review');restore.assert_not_called()

    def test_root_bridge_drops_privileges_before_user_code(self):
        user = __import__('pwd').getpwuid(os.getuid()).pw_name
        command=root_hook.command(user,'before')
        self.assertEqual(command[:6],['/usr/sbin/runuser','-u',user,'--','/usr/bin/env','-i'])
        self.assertIn('/usr/bin/python3',command)
        self.assertIn('before',command)

    def test_root_hook_blocks_pre_failure_but_post_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'config.json';config.write_text('{"user":"desktop"}')
            with patch.object(root_hook,'CONFIG',config), patch.object(root_hook.os,'geteuid',return_value=0), \
                 patch.object(root_hook,'command',return_value=['false']), \
                 patch.object(root_hook.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'false')):
                with patch.object(sys,'argv',['hook','before']):
                    with self.assertRaises(SystemExit) as error:root_hook.main()
                    self.assertEqual(error.exception.code,1)
                with patch.object(sys,'argv',['hook','after']):root_hook.main()

    def test_kernel_package_lock_detection(self):
        info=type('Stat',(),dict(st_dev=os.makedev(8,2),st_ino=123))()
        with patch.object(Path,'stat',return_value=info), \
             patch.object(Path,'read_text',return_value='1: POSIX ADVISORY WRITE 42 08:02:123 0 EOF\n'):
            self.assertTrue(guard.package_busy())
        with patch.object(Path,'stat',return_value=info), patch.object(Path,'read_text',return_value=''):
            self.assertFalse(guard.package_busy())

    def test_settings_reset_repaired_but_customization_retained(self):
        # A subprocess selects the memory backend before importing Gio.
        script = """
import json,tempfile
from pathlib import Path
from gi.repository import Gio
import update_guard as g
with tempfile.TemporaryDirectory() as directory:
 g.HOME=Path(directory)
 s=Gio.Settings.new('org.gnome.desktop.interface')
 s.reset('icon-theme')
 before=s.get_string('icon-theme')
 record={'schema':'org.gnome.desktop.interface','key':'icon-theme','wanted':"'Win11-dark'",'original':repr(before)}
 profile={'settings':[record],'enabled':[],'disabled':[],'extensions_paused':True,'wallpaper':{'picture-uri':'','picture-uri-dark':''}}
 repaired,skipped=g.settings_repair(profile)
 assert s.get_string('icon-theme')=='Win11-dark' and len(repaired)==1 and not skipped
 s.set_string('icon-theme','My-New-Theme')
 repaired,skipped=g.settings_repair(profile)
 assert s.get_string('icon-theme')=='My-New-Theme' and not repaired and skipped
"""
        subprocess.run([sys.executable,'-c',script],check=True,
            env=dict(os.environ,GSETTINGS_BACKEND='memory',PYTHONPATH=str(Path(guard.__file__).parent)),
            capture_output=True)


if __name__ == '__main__':
    unittest.main()
