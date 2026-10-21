import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import session_cleanup as cleanup


class CleanupTests(unittest.TestCase):
    def test_exact_executable_cleanup_preserves_unrelated_process(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'fixture-player'
            shutil.copy2('/usr/bin/sleep', binary)
            target = subprocess.Popen([str(binary), '60'])
            unrelated = subprocess.Popen(['/usr/bin/sleep', '60'])
            try:
                self.assertEqual(cleanup.stop({str(binary)}, grace=.2), 1)
                target.wait(timeout=3)
                self.assertIsNone(unrelated.poll())
            finally:
                for process in (target, unrelated):
                    if process.poll() is None:
                        process.kill()
                    process.wait()

    def test_background_sync_daemon_is_not_a_gui_target(self):
        paths = cleanup.executables(Path('/home/example'))
        self.assertNotIn('/home/example/.local/share/axentra/apps/onedrive/axentra-onedrive', paths)
        self.assertIn('/home/example/.local/share/axentra/apps/onedrive/AxentraOneDrive', paths)

    def test_unit_stops_with_graphical_session_and_before_daemon(self):
        unit = cleanup.units('/tmp/my folder')['zorin11-session-cleanup.service']
        self.assertIn('PartOf=graphical-session.target', unit)
        self.assertIn('After=axentra-onedrive.service', unit)
        self.assertIn('WantedBy=graphical-session.target', unit)
        self.assertIn('ExecStop=', unit)


if __name__ == '__main__':
    unittest.main()
