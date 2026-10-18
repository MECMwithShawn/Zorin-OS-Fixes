"""Motion settings boundaries, frame pacing and failure recovery."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import desktop_motion as motion
import settings_backend


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patches=[patch.object(motion,'CONFIG',self.root),patch.object(motion,'STATE',self.root/'motion.json')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_frame_pacing_uses_connected_output_rates_and_keeps_vsync(self):
        values=motion.profile_values(motion.load(),[239988,60000,0])
        self.assertEqual(values['composite'],{'refresh_rate':200,'detect_refresh_rate':False})
        self.assertTrue(values['opengl']['sync_to_vblank'])
        self.assertEqual(values['wall']['slide_duration'],.32)
        self.assertEqual(motion.profile_values(motion.load(),[60000])['wall']['slide_duration'],.32)
        self.assertFalse(values['wall']['show_switcher'])
        self.assertNotIn('core',values);self.assertNotIn('wobbly',values)
    def test_unknown_display_rate_retains_native_detection(self):
        self.assertEqual(motion.profile_values(motion.load(),[0])['composite'],{'detect_refresh_rate':True})
    def test_both_accessibility_controls_disable_the_native_slide(self):
        self.assertEqual(motion.profile_values({'enabled':False,'duration':480},[60000])['wall']['slide_duration'],0)
        self.assertEqual(motion.profile_values(motion.load(),[60000],False)['wall']['slide_duration'],0)
    def test_untrusted_settings_never_write_or_launch(self):
        with patch.object(motion,'refresh_profile') as refresh:
            for name,value in [('desktopAnimations',1),('desktopAnimations','false'),('desktopAnimationDuration',True),
                               ('desktopAnimationDuration',0),('desktopAnimationDuration',320.0),('shell','anything')]:
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):motion.configure(name,value)
            refresh.assert_not_called();self.assertFalse(motion.STATE.exists())
    def test_backend_routes_setting_and_persists_without_changing_effects_choice(self):
        with patch.object(motion,'refresh_profile') as refresh:
            settings_backend.apply('desktopAnimationDuration',180)
            settings_backend.apply('desktopAnimations',False)
        self.assertEqual(motion.load(),{'enabled':False,'duration':180})
        self.assertEqual(refresh.call_count,2)
        self.assertFalse((self.root/'effects.json').exists())
    def test_failed_profile_change_restores_previous_preference_exactly(self):
        previous=b'{"enabled": false, "duration": 480}\n';motion.STATE.write_bytes(previous)
        with patch.object(motion,'refresh_profile',side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):motion.configure('desktopAnimations',True)
        self.assertEqual(motion.STATE.read_bytes(),previous)


if __name__=='__main__':unittest.main()
