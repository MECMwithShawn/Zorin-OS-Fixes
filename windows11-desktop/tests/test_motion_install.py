import json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import motion_install as motion
import desktop_backup,update_guard

class MotionInstallTests(unittest.TestCase):
    def test_addon_install_backup_inventory_and_conservative_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            files=motion.files(home)
            extension=home/'.local/share/gnome-shell/extensions'/motion.UUID
            self.assertTrue(all(p.is_relative_to(extension) or p.name=='zorin11-taskbar-motion.desktop' for p in files))
            for path,data in files.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            motion.compile_schema(home)
            launcher=home/'.local/share/applications/zorin11-taskbar-motion.desktop'
            subprocess.run(['desktop-file-validate',str(launcher)],check=True)
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
