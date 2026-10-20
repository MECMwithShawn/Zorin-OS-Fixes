import json
import tempfile
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

import audio_effects as eq
import settings_backend as settings


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for key, value in [('ROOT', root), ('STATE', root/'state.json'), ('STATUS', root/'status.json')]:
            change = patch.object(eq, key, value)
            change.start()
            self.addCleanup(change.stop)

    def test_presets_are_bounded_and_only_build_playback_filters(self):
        for choice in eq.PRESETS:
            self.assertEqual(len(choice['gains']), len(eq.FREQUENCIES))
            self.assertTrue(all(-12 <= gain <= 12 for gain in choice['gains']))
            self.assertLessEqual(eq.headroom(choice['gains'])+sum(max(0,g) for g in choice['gains']), 0)
            graph = eq.graph(choice['id'], 'speakers"\\test')
            parsed = json.loads(json.dumps(graph))
            args = parsed['context.modules'][-1]['args']
            self.assertEqual(args['capture.props']['media.class'], 'Audio/Sink')
            self.assertEqual(args['playback.props']['target.object'], 'speakers"\\test')
            self.assertEqual(args['audio.position'], ['FL','FR'])

    def test_invalid_presets_and_unavailable_backend_never_run_commands(self):
        with patch.object(eq, 'run') as command:
            for invalid in ('shell command', None, {}, True, 5):
                with self.assertRaises(ValueError):
                    eq.configure(invalid)
            command.assert_not_called()
        with patch.object(eq, 'available', return_value=False), patch.object(eq, 'run') as command:
            with self.assertRaises(ValueError):
                eq.configure('bass')
            command.assert_not_called()
            self.assertFalse(eq.STATE.exists())

    def test_failed_start_restores_prior_selection_and_disables_new_service(self):
        eq.save(eq.STATE, dict(preset='off'))
        with patch.object(eq, 'available', return_value=True), \
                patch.object(eq, 'run', side_effect=RuntimeError('service rejected')), \
                patch.object(eq.subprocess, 'run') as cleanup:
            with self.assertRaises(RuntimeError):
                eq.configure('voice')
            self.assertEqual(eq.selection(), 'off')
            cleanup.assert_called_once()

    def test_selection_persists_and_status_expires(self):
        with patch.object(eq, 'available', return_value=True), patch.object(eq, 'run') as command:
            def applied(*_args, **_kwargs):
                eq.save(eq.STATUS, dict(active=True,preset='bass',updated=time.time()))
                return ''
            command.side_effect = applied
            eq.configure('bass')
            self.assertEqual(eq.selection(), 'bass')
            self.assertTrue(eq.snapshot()['active'])
            eq.save(eq.STATUS, dict(active=True,preset='bass',updated=0))
            self.assertFalse(eq.snapshot()['active'])
            eq.configure('off')
            self.assertEqual(eq.selection(), 'off')
            self.assertIn('disable', command.call_args.args[0])

    def test_routing_excludes_filter_output_and_other_devices(self):
        inputs = [
            dict(index=1,sink=5,properties={'application.name':'Browser'}),
            dict(index=2,sink=5,properties={'node.name':eq.PLAYBACK}),
            dict(index=3,sink=8,properties={'application.name':'Music'}),
        ]
        with patch.object(eq, 'streams', return_value=inputs), patch.object(eq, 'run') as command:
            eq.move(5, eq.SINK)
            command.assert_called_once_with(['pactl','move-sink-input','1',eq.SINK])

    def test_upgrade_restarts_old_daemon_before_waiting_for_new_preset(self):
        eq.save(eq.STATE, dict(preset='voice'))
        eq.save(eq.STATUS, dict(active=True, preset='voice', updated=time.time()))
        def service(args, **_kwargs):
            if 'restart' in args:
                eq.save(eq.STATUS, dict(active=True, preset='music',
                                       updated=time.time(), version=eq.ENGINE_VERSION))
            return ''
        with patch.object(eq, 'available', return_value=True), patch.object(eq, 'run', side_effect=service) as command:
            eq.configure('music')
            self.assertEqual(eq.selection(), 'music')
            self.assertTrue(eq.snapshot()['active'])
            self.assertTrue(any('restart' in c.args[0] for c in command.call_args_list))
            command.reset_mock()
            eq.configure('music')
            self.assertFalse(any('restart' in c.args[0] for c in command.call_args_list))

    def test_settings_delegates_presets_and_hides_processing_sink(self):
        with patch.object(eq, 'configure') as configure:
            settings.apply('audioPreset', 'night')
            configure.assert_called_once_with('night')
        sinks = [dict(name='speakers',description='Speakers'),dict(name=eq.SINK,description='Processing')]
        with patch.object(settings, 'run', return_value=json.dumps(sinks)):
            self.assertEqual(settings.sound_outputs(),[dict(id='speakers',name='Speakers')])


if __name__ == '__main__':
    unittest.main()
