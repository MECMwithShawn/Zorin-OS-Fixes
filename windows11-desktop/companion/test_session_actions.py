"""Verify session routing without locking, suspending or ending a real session."""
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import session_actions


class SessionActionTests(unittest.TestCase):
    def test_gnome_end_session_actions_keep_native_confirmation(self):
        for action,flag in [('sign-out','--logout'),('restart','--reboot'),('shutdown','--power-off')]:
            with self.subTest(action=action), patch.object(session_actions.shutil,'which',return_value='/bin/tool'), patch.object(session_actions.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
                session_actions.run(action,True)
                run.assert_called_once_with(['gnome-session-quit',flag],capture_output=True,text=True)

    def test_switch_user_and_sleep_use_distinct_native_operations(self):
        self.assertEqual(session_actions.command('switch-user',True),['gdmflexiserver'])
        self.assertEqual(session_actions.command('lock',True),['loginctl','lock-session'])
        self.assertEqual(session_actions.command('sleep',True),['systemctl','--no-block','suspend'])
        with patch.object(session_actions.shutil,'which',return_value='/usr/bin/dm-tool'):
            self.assertEqual(session_actions.command('switch-user',False),['dm-tool','switch-to-greeter'])
        for action in ('sign-out','restart','shutdown','sleep'):
            self.assertEqual(session_actions.command(action,False)[0],'xfce4-session-logout')

    def test_invalid_or_unavailable_actions_cannot_start_processes(self):
        with patch.object(session_actions.subprocess,'run') as run:
            with self.assertRaises(ValueError):session_actions.run('restart --force',True)
            with patch.object(session_actions.shutil,'which',return_value=None):
                with self.assertRaisesRegex(RuntimeError,'not installed'):session_actions.run('switch-user',True)
            run.assert_not_called()

    def test_native_failures_are_reported(self):
        with patch.object(session_actions.shutil,'which',return_value='/bin/tool'), patch.object(session_actions.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stderr='Session action inhibited')):
            with self.assertRaisesRegex(RuntimeError,'inhibited'):session_actions.run('sleep',True)

    def test_start_dispatch_uses_requested_action_and_restores_errors(self):
        import app
        start=Mock()
        hub=SimpleNamespace(start=start,background=Mock(),show_start=Mock())
        with patch.object(app,'is_gnome',return_value=True),patch.object(session_actions,'run') as run:
            app.Hub.dispatch(hub,SimpleNamespace(mode='start'),{'action':'session-action','command':'restart'})
            start.hide.assert_called_once()
            task,success,failure=hub.background.call_args.args
            task();run.assert_called_once_with('restart',True)
            failure('Inhibited')
            hub.show_start.assert_called_once()
            start.send.assert_called_once_with({'type':'error','message':'Inhibited'})
            with self.assertRaises(ValueError):
                app.Hub.dispatch(hub,SimpleNamespace(mode='explorer'),{'action':'session-action','command':'restart'})


if __name__=='__main__':unittest.main()
