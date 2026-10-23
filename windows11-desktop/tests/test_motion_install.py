import json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import motion_install as motion
import desktop_backup,update_guard

class MotionInstallTests(unittest.TestCase):
    def test_route_upgrade_preserves_local_changes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);path=home/'.local/share/zorin11-hub/settings_backend.py'
            self.assertEqual(motion.route_files(home),{})
            source=(motion.ROOT/'companion/settings_backend.py').read_text()
            block="""    if tool == 'panel' and is_gnome():
        taskbar = Path.home()/'.local/share/gnome-shell/extensions/zorin11-motion@zorin-os-fixes/taskbar-settings.js'
        if taskbar.is_file():
            command = ['gjs', '-m', str(taskbar)]
"""
            legacy=source.replace(block,'')+'\n# Local companion customization\n'
            self.assertNotEqual(source,legacy)
            path.parent.mkdir(parents=True);path.write_text(legacy)
            result=motion.route_files(home)
            self.assertEqual(result[path].decode(),source+'\n# Local companion customization\n')
            path.write_bytes(result[path]);self.assertEqual(motion.route_files(home),{})
            path.write_text('unknown custom launch structure')
            with self.assertRaises(RuntimeError):motion.route_files(home)

    def test_addon_install_backup_inventory_and_conservative_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            files=motion.files(home)
            extension=home/'.local/share/gnome-shell/extensions'/motion.UUID
            self.assertTrue(all(p.is_relative_to(extension) or p.name in ('zorin11-taskbar-motion.desktop','zorin11-taskbar-settings.desktop') for p in files))
            for path,data in files.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            motion.compile_schema(home)
            launcher=home/'.local/share/applications/zorin11-taskbar-motion.desktop'
            subprocess.run(['desktop-file-validate',str(launcher)],check=True)
            subprocess.run(['desktop-file-validate',str(launcher.with_name('zorin11-taskbar-settings.desktop'))],check=True)
            records=[r for r in desktop_backup.current_settings(home) if r['schema']=='org.gnome.shell.extensions.zorin11-motion']
            self.assertEqual(len(records),6)
            sources=desktop_backup.collect(home)
            self.assertIn('home/'+str(extension.relative_to(home))+'/extension.js',sources)
            self.assertTrue(update_guard.protected_file('home/'+str(extension.relative_to(home))+'/extension.js'))
            self.assertIn(motion.UUID,update_guard.MANAGED_EXTENSIONS)
            motion.cleanup(home) # Retained schema must keep its compiled data.
            self.assertTrue((extension/'schemas/gschemas.compiled').exists())
            for path in files:path.unlink()
            motion.cleanup(home);self.assertFalse(extension.exists())

if __name__=='__main__':unittest.main()
