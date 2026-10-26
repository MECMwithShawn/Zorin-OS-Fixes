"""Desktop selection, wallpaper lookup and original-recovery preservation."""
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import os
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'companion')]
import setup,gnome_setup,gnome_wallpaper,gnome_install
class GnomeTests(unittest.TestCase):
    def test_explorer_replaces_files_in_place_without_duplicate_pins(self):
        self.assertEqual(gnome_install.explorer_favorites(['browser.desktop','org.gnome.Nautilus.desktop','other.desktop','zorin11-explorer.desktop']),
                         ['browser.desktop','zorin11-explorer.desktop','other.desktop'])
        self.assertEqual(gnome_install.explorer_favorites(['browser.desktop']),['browser.desktop'])
        self.assertEqual(gnome_install.explorer_favorites(['org.gnome.SystemMonitor.desktop','browser.desktop','io.missioncenter.MissionCenter.desktop']),
                         ['io.missioncenter.MissionCenter.desktop','browser.desktop'])
    def test_folder_defaults_preserve_unrelated_associations(self):
        text='[Default Applications]\ninode/directory=org.gnome.Nautilus.desktop;\nx-scheme-handler/codex=chatgpt.desktop;\n'
        result=gnome_install.folder_defaults(text).decode()
        self.assertIn('inode/directory=zorin11-explorer.desktop;',result)
        self.assertIn('x-scheme-handler/codex=chatgpt.desktop;',result)
        self.assertEqual(gnome_install.folder_defaults(result).decode(),result)
    def test_dispatch_requires_matching_session(self):
        self.assertEqual(setup.desktop_backend(desktop='zorin:GNOME'),'gnome')
        self.assertEqual(setup.desktop_backend(desktop='XFCE'),'xfce')
        with self.assertRaises(ValueError):setup.desktop_backend('xfce',desktop='GNOME')
        with self.assertRaises(ValueError):setup.desktop_backend(desktop='KDE')
    def test_upgrade_retains_original_and_obsolete_recovery(self):
        original=[dict(schema='theme',key='name',old="'light'",new="'dark'"),dict(schema='panel',key='size',old='40',new='48')]
        result=gnome_setup.merge_original([dict(schema='theme',key='name',old="'manual'",new="'new-dark'")],original)
        self.assertEqual(result[0]['old'],"'light'");self.assertEqual(result[0]['new'],"'new-dark'")
        self.assertEqual(result[1],original[1])
    def test_private_atomic_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'settings.json';gnome_setup.save([{'old':'before'}],path)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(json.loads(path.read_text()),[{'old':'before'}])
    def test_restore_and_upgrade_in_memory_settings_backend(self):
        code="""
import tempfile
from pathlib import Path
from gi.repository import Gio
import gnome_setup as g
s=Gio.Settings.new('org.gnome.desktop.interface');old=s.get_string('gtk-theme')
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp)/'backup.json'
 g.install(g.plan({'org.gnome.desktop.interface':{'gtk-theme':'ZorinBlue-Dark'}}),p)
 g.install(g.plan({'org.gnome.desktop.interface':{'gtk-theme':'Adwaita-dark'}}),p)
 g.restore(p);assert s.get_string('gtk-theme')==old and not p.exists()
 g.install(g.plan({'org.gnome.desktop.interface':{'gtk-theme':'ZorinBlue-Dark'}}),p)
 s.set_string('gtk-theme','manual-theme');g.restore(p)
 assert s.get_string('gtk-theme')=='manual-theme'
"""
        subprocess.run(['/usr/bin/python3','-c',code],env=dict(os.environ,GSETTINGS_BACKEND='memory',PYTHONPATH=str(ROOT)),check=True,capture_output=True)
    def test_catalog_resolution_rejects_paths(self):
        with patch.object(gnome_wallpaper,'catalog',return_value=[{'id':'zorin-test','path':'/usr/share/backgrounds/Zorin.jpg'}]):
            self.assertEqual(gnome_wallpaper.resolve('zorin-test'),Path('/usr/share/backgrounds/Zorin.jpg'))
            with self.assertRaises(ValueError):gnome_wallpaper.resolve('../../etc/passwd')
    def test_layout_uses_detected_monitors_and_keeps_wallpaper(self):
        changes=gnome_setup.appearance(['panel-a','panel-b'])
        self.assertEqual(set(json.loads(changes[gnome_setup.TASKBAR]['panel-element-positions'])),{'panel-a','panel-b'})
        positions=json.loads(changes[gnome_setup.TASKBAR]['panel-element-positions'])['panel-a']
        self.assertEqual(next(p['position'] for p in positions if p['element']=='taskbar'),'centered')
        self.assertEqual(next(p['position'] for p in positions if p['element']=='rightBox'),'stackedBR')
        self.assertFalse(any('picture-uri' in entries for entries in changes.values()))
if __name__=='__main__':unittest.main()
