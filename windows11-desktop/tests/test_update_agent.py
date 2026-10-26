import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import update_agent_install

def module(name):
    spec=importlib.util.spec_from_file_location('update_agent_'+name,ROOT/'update_agent'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

s=module('system');model=module('model')

class UpdateAgentTests(unittest.TestCase):
    def test_settings_route_preserves_local_companion_work(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);path=home/'.local/share/zorin11-hub/settings_backend.py'
            path.parent.mkdir(parents=True)
            text="def launch(tool):\n    command=TOOLS[tool]\n    # unrelated local integration\n"
            path.write_text(text)
            new=update_agent_install.route_files(home)[path]
            self.assertIn(b'# unrelated local integration',new)
            self.assertIn(b"tool == 'updates'",new)
            path.write_bytes(new);self.assertEqual(update_agent_install.route_files(home),{})
    def test_rejects_untrusted_schedule_values(self):
        for key,value in [('mode','daily; reboot'),('day','Sun\nExecStart=/bin/false'),('hour',24),('minute',-1),('hour',True),('scope','anything'),('paused_until',int(__import__('time').time())+10*86400)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):s.validate(dict(s.DEFAULT,**{key:value}))
        with self.assertRaises(ValueError):s.validate(dict(s.DEFAULT,command='reboot'))

    def test_calendar_and_missed_run_slots(self):
        config=dict(s.DEFAULT,mode='weekly',day='Sun',hour=3,minute=15)
        self.assertEqual(s.calendar(config),'Sun *-*-* 03:15:00')
        now=datetime.datetime(2026,10,26,12).timestamp()
        self.assertEqual(datetime.datetime.fromtimestamp(s.scheduled_slot(config,now)),datetime.datetime(2026,10,25,3,15))
        config.update(mode='daily',hour=15)
        self.assertEqual(datetime.datetime.fromtimestamp(s.scheduled_slot(config,now)),datetime.datetime(2026,10,25,15,15))
        self.assertIn('OnUnitInactiveSec=30min',s.units(config)[s.TIMER])
        self.assertIn('systemd-inhibit',s.units(config)[s.SERVICE])

    def test_pause_power_metered_fail_closed(self):
        config=dict(s.DEFAULT,mode='daily')
        self.assertEqual(s.skip_reason(config,1000,'no',False),'')
        self.assertEqual(s.skip_reason(config,1000,'guess-no',False),'')
        for network in ('yes','guess-yes','unknown',''):
            self.assertIn('unmetered',s.skip_reason(config,1000,network,False))
        self.assertIn('AC power',s.skip_reason(config,1000,'no',True))
        self.assertIn('paused',s.skip_reason(dict(config,paused_until=2000),1000,'no',False))
        self.assertIn('not managed',s.skip_reason(s.DEFAULT,1000,'no',False))

    def test_notification_dedupe_and_snooze(self):
        report=dict(packages=[dict(name='test',version='2')],reboot=False)
        note=model.notification(report,{},100)
        self.assertIsNotNone(note)
        self.assertIsNone(model.notification(report,dict(notified=note[0]),100))
        self.assertIsNone(model.notification(report,dict(snooze_until=200),100))
        self.assertIsNone(model.notification(report,dict(notifications=False),100))
        report['reboot']=True
        self.assertEqual(model.notification(report,dict(notified=note[0]),100)[1],'Restart required')
        self.assertIsNone(model.notification(dict(packages=[],reboot=False),{},100))

    def test_resolved_restart_rearms_identical_alert(self):
        report=dict(packages=[],reboot=True)
        prefs=dict(notified=model.notification(report,{})[0],notifications=True)
        self.assertIsNone(model.notification(report,prefs))
        self.assertTrue(model.clear_notification(dict(packages=[],reboot=False),prefs))
        self.assertIsNotNone(model.notification(report,prefs))
        self.assertTrue(prefs['notifications'])
        self.assertFalse(model.clear_notification(report,prefs))

    def test_policy_summary_reflects_active_scheduler(self):
        config=dict(s.DEFAULT,mode='daily',scope='all',hour=3,minute=0)
        text=model.policy_summary(config,False,100)
        self.assertIn('Daily at 03:00',text)
        self.assertIn('all repository updates',text)
        self.assertIn('no automatic restart',text)
        self.assertNotIn('disabled',text)
        self.assertIn('Paused until',model.policy_summary(dict(config,paused_until=200),False,100))
        self.assertIn('Manual updates',model.policy_summary(dict(config,mode='manual')))
        self.assertIn('Zorin manages',model.policy_summary(dict(config,mode='system')))

    def test_installer_only_owns_new_files_and_signout_scopes_tray(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);files=update_agent_install.files(home)
            self.assertFalse(any(p.name in ('app.py','settings_backend.py','index.html') for p in files))
            for path,data in files.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            subprocess.run(['desktop-file-validate',str(home/'.local/share/applications/zorin11-update-agent.desktop')],check=True)
            service=home/'.config/systemd/user/zorin11-update-agent.service'
            self.assertIn('PartOf=graphical-session.target',service.read_text())
            self.assertNotIn('pkexec',service.read_text())

    def test_install_preserves_policy_and_never_runs_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);writes=[];commands=[]
            with patch.object(s,'HELPER',root/'helper'),patch.object(s,'CONFIG',root/'config'),patch.object(s,'atomic',side_effect=lambda p,d,mode=0o644:writes.append((str(p),d))),patch.object(s.subprocess,'run',side_effect=lambda cmd,**kw:commands.append(cmd)):
                s.install()
            self.assertEqual(commands,[['systemctl','daemon-reload']])
            self.assertFalse(any(p==str(s.POLICY) for p,d in writes))
            self.assertEqual(json.loads(next(d for p,d in writes if p==str(root/'config')))['mode'],'system')

    def test_completed_slot_does_not_install_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config=dict(s.DEFAULT,mode='daily')
            (root/'history.json').write_text(json.dumps([dict(state='completed',slot=10**11)]))
            with patch.object(s,'STATE',root),patch.object(s,'read_config',return_value=config),patch.object(s.subprocess,'run') as command:
                s.run()
                command.assert_not_called()

    def test_metered_run_does_not_refresh_or_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);commands=[]
            def command(args,**kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args,0,stdout='u 1\n')
            with patch.object(s,'STATE',root),patch.object(s,'read_config',return_value=dict(s.DEFAULT,mode='daily')),patch.object(s.subprocess,'run',side_effect=command):s.run()
            self.assertFalse(any('apt-get' in ' '.join(c) or 'unattended-upgrade' in ' '.join(c) for c in commands))
            self.assertEqual(json.loads((root/'history.json').read_text())[-1]['state'],'deferred')

    def test_scheduled_scopes_preserve_hooks_and_never_reboot(self):
        for scope in ('security','all'):
            with self.subTest(scope=scope),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);hook=root/'hook';hook.write_text('axentra-desktop-update-guard before')
                commands=[];policies=[]
                def command(args,**kw):
                    commands.append(args)
                    if args==['/usr/bin/unattended-upgrade']:policies.append(Path(kw['env']['APT_CONFIG']).read_text())
                    return subprocess.CompletedProcess(args,0,stdout='u 4\n')
                with patch.object(s,'STATE',root),patch.object(s,'HOOK',hook),patch.object(s,'LOG',root/'log'),patch.object(s,'read_config',return_value=dict(s.DEFAULT,mode='daily',scope=scope)),patch.object(s.subprocess,'run',side_effect=command),patch.object(s.subprocess,'check_output',return_value=b'DPkg::Pre-Invoke:: "/usr/local/libexec/axentra-desktop-update-guard before";\n'):
                    s.run()
                    count=len(commands);s.run();self.assertEqual(len(commands),count)
                self.assertEqual(json.loads((root/'history.json').read_text())[-1]['state'],'completed')
                if scope=='security':
                    self.assertIn('axentra-desktop-update-guard before',policies[0])
                    self.assertIn('Unattended-Upgrade::Automatic-Reboot "false";',policies[0])
                    self.assertIn('Dir::Etc::parts "-";',policies[0])
                else:self.assertTrue(any('--no-remove' in cmd and 'upgrade' in cmd for cmd in commands))
                self.assertFalse(any('reboot' in cmd for cmd in commands))

    def test_system_managed_restores_only_our_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);baseline=root/'20auto-upgrades';baseline.write_text('original policy')
            with patch.object(s,'STATE',root),patch.object(s,'CONFIG',root/'config'),patch.object(s,'POLICY',root/'override'),patch.object(s,'UNITS',root/'units'),patch.object(s.subprocess,'run'):
                s.configure(dict(s.DEFAULT,mode='weekly'))
                self.assertIn('Unattended-Upgrade "0"',s.POLICY.read_text())
                s.configure(s.DEFAULT)
                self.assertFalse(s.POLICY.exists())
                self.assertEqual(baseline.read_text(),'original policy')

    def test_missing_backup_hooks_block_installs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(s,'STATE',root),patch.object(s,'HOOK',root/'missing'),patch.object(s,'read_config',return_value=dict(s.DEFAULT,mode='daily')),patch.object(s.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='u 4\n')) as command:
                with self.assertRaisesRegex(RuntimeError,'backup hooks'):s.run()
                self.assertFalse(any('apt-get' in str(c) for c in command.call_args_list))


if __name__=='__main__':unittest.main()
