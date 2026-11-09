import os,shutil,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import session_cleanup as cleanup

class CleanupTests(unittest.TestCase):
    def test_only_exact_allowed_executable_stops(self):
        with tempfile.TemporaryDirectory() as root:
            exe=Path(root)/'disposable-player';shutil.copy('/bin/sleep',exe)
            target=subprocess.Popen([str(exe),'30']);unrelated=subprocess.Popen(['/bin/sleep','30'])
            try:
                time.sleep(.05)
                self.assertEqual(cleanup.stop({str(exe)},grace=.1),1)
                target.wait(timeout=2);self.assertIsNone(unrelated.poll())
            finally:
                for p in (target,unrelated):
                    if p.poll() is None:p.terminate()
                    p.wait(timeout=2)
    def test_live_session_and_unknown_state_skip_cleanup(self):
        for state,code in [('active',0),('activating',0),('',1)]:
            with patch('session_cleanup.subprocess.run',return_value=Mock(returncode=code,stdout=state)),patch('session_cleanup.stop') as stop:
                cleanup.main();stop.assert_not_called()
        for state in ['deactivating','inactive']:
            with patch('session_cleanup.subprocess.run',return_value=Mock(returncode=0,stdout=state)):
                self.assertTrue(cleanup.logout_in_progress())
    def test_sync_daemon_is_excluded_and_unit_follows_graphical_session(self):
        home=Path('/example')
        self.assertNotIn(str(home/'.local/share/axentra/apps/onedrive/axentra-onedrive'),cleanup.executables(home))
        unit=cleanup.units(home)['zorin11-session-cleanup.service']
        self.assertIn('PartOf=graphical-session.target',unit)
        self.assertIn('WantedBy=graphical-session.target',unit)
        self.assertIn('TimeoutStopSec=10',unit)

if __name__=='__main__':unittest.main()
