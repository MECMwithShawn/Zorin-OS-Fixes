"""Exercise real GTK menus and Zorin settings on a disposable display/session."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import desktop_menu_install
import gnome_install


class DesktopMenuTests(unittest.TestCase):
    def test_launchers_use_companion_without_file_association_changes(self):
        entries=gnome_install.personalization_entries(Path('/example/apps'))
        self.assertEqual(len(entries),3)
        for panel in ('gnome-display-panel','gnome-background-panel'):
            self.assertIn(b'X-GNOME-Settings-Panel;',entries[Path('/example/apps')/(panel+'.desktop')])
            self.assertIn(b'X-GNOME-DevicesSettings;',entries[Path('/example/apps')/(panel+'.desktop')])
        for path,data in entries.items():
            self.assertIn(b'app.py" --settings ',data)
            self.assertNotIn(b'DBusActivatable=true',data)
            self.assertNotIn(b'MimeType=',data)
        self.assertIn(b'--settings background',entries[Path('/example/apps/gnome-background-panel.desktop')])

    def test_actual_gtk_actions_and_vendor_preservation(self):
        original=desktop_menu_install.VENDOR/'app/desktopManager.js'
        before=original.read_bytes()
        with tempfile.TemporaryDirectory(prefix='axentra-desktop-test-') as directory:
            root=Path(directory); extension=root/'extension'
            for path,data in desktop_menu_install.prepare(extension).items():
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            subprocess.run(['glib-compile-schemas',str(extension/'schemas')],check=True)
            runtime=root/'hub';runtime.mkdir()
            (root/'run').mkdir(mode=0o700)
            (runtime/'app.py').write_text("import sys\nfrom pathlib import Path\nwith Path(__file__).with_name('actions').open('a') as f:f.write(' '.join(sys.argv[1:])+'\\n')\n")
            (runtime/'wallpaper_action.py').write_text("from pathlib import Path\nwith Path(__file__).with_name('actions').open('a') as f:f.write('next wallpaper\\n')\n")
            env=dict(os.environ,GSETTINGS_BACKEND='memory',XDG_CONFIG_HOME=str(root/'config'),
                     XDG_CACHE_HOME=str(root/'cache'),XDG_RUNTIME_DIR=str(root/'run'),
                     GIO_USE_VFS='local',GIO_USE_VOLUME_MONITOR='unix',
                     ZORIN11_RUNTIME_DIR=str(runtime),GTK_USE_PORTAL='0')
            result=subprocess.run(['xvfb-run','-a','dbus-run-session','--','gjs',str(ROOT/'tests/desktop_menu_live.js'),
                                   str(extension),os.environ.get('ZORIN11_TEST_OUTPUT','')],
                                  env=env,capture_output=True,text=True,timeout=25)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS',result.stdout)
            self.assertEqual((runtime/'actions').read_text().splitlines(),
                             ['--settings display','--settings personalization','next wallpaper'])
            self.assertEqual(original.read_bytes(),before)


if __name__=='__main__':
    unittest.main()
