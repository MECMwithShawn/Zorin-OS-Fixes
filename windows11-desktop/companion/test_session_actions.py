"""Verify session routing without locking, suspending or ending a real session."""
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import session_actions


class SessionActionTests(unittest.TestCase):
    def test_gnome_end_session_actions_keep_native_confirmation(self):
        for action,method in [('sign-out','Logout'),('restart','Reboot'),('shutdown','Shutdown')]:
            with self.subTest(action=action), patch.object(session_actions,'_call') as call:
                session_actions.run(action,True)
                call.assert_called_once_with(False,'org.gnome.SessionManager','/org/gnome/SessionManager',method,
                                             '(u)' if action=='sign-out' else None,(0,) if action=='sign-out' else ())

    def test_switch_user_and_sleep_use_distinct_native_operations(self):
        with patch.object(session_actions,'_call') as call:
            session_actions.run('lock',True)
            call.assert_called_once_with(False,'org.gnome.ScreenSaver','/org/gnome/ScreenSaver','Lock')
            call.reset_mock()
            session_actions.run('sleep',True)
            call.assert_called_once_with(True,'org.freedesktop.login1','/org/freedesktop/login1','Suspend','(b)',(True,))
        with patch.object(session_actions.shutil,'which',return_value='/usr/bin/dm-tool'):
            self.assertEqual(session_actions.command('switch-user'),['dm-tool','switch-to-greeter'])
        for action in ('sign-out','restart','shutdown','sleep'):
            self.assertEqual(session_actions.command(action)[0],'xfce4-session-logout')

    def test_switch_user_locks_before_gdm_and_checks_result(self):
        import gi
        gi.require_version('Gdm','1.0')
        from gi.repository import Gdm
        events=[]
        with patch.object(session_actions,'_call',side_effect=lambda *args:events.append(args[3])),patch.object(Gdm,'goto_login_session_sync',side_effect=lambda _:events.append('GDM') or True):
            session_actions.run('switch-user',True)
        self.assertEqual(events,['Lock','GDM'])
        with patch.object(session_actions,'_call'),patch.object(Gdm,'goto_login_session_sync',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'switching'):session_actions.run('switch-user',True)

    def test_invalid_or_unavailable_actions_cannot_start_processes(self):
        with patch.object(session_actions.subprocess,'run') as run:
            with self.assertRaises(ValueError):session_actions.run('restart --force',True)
            with patch.object(session_actions.shutil,'which',return_value=None):
                with self.assertRaisesRegex(RuntimeError,'not installed'):session_actions.run('switch-user',False)
            run.assert_not_called()

    def test_native_failures_are_reported(self):
        with patch.object(session_actions,'_call',side_effect=RuntimeError('Session action inhibited')):
            with self.assertRaisesRegex(RuntimeError,'inhibited'):session_actions.run('sleep',True)
        with patch.object(session_actions.shutil,'which',return_value='/bin/tool'), patch.object(session_actions.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stderr='Session action inhibited')):
            with self.assertRaisesRegex(RuntimeError,'inhibited'):session_actions.run('sleep',False)

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
