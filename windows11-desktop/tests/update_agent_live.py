#!/usr/bin/python3
"""Private GTK test; no package operations or system policy changes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def session(folder):
    sys.path.insert(0,str(ROOT/'update_agent'))
    import agent
    from gi.repository import GLib
    agent.PREFS=folder/'prefs.json'
    agent.scheduler.CONFIG=folder/'system.json'
    agent.scheduler.STATE=folder
    agent.scheduler.HELPER=folder/'helper';agent.scheduler.HELPER.write_bytes((ROOT/'update_agent/system.py').read_bytes())
    agent.scheduler.CONFIG.write_text(json.dumps(agent.scheduler.DEFAULT))
    app=agent.App();app.register(None);app.poll=lambda:False;app.open()
    assert app.os_logo.get_accessible().get_name()=='Zorin OS logo'
    def until(check):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            if check():return
            time.sleep(.02)
        raise AssertionError('Timed out')
    app.report=dict(packages=[dict(name='test-package',version='2',security=True,held=False)],reboot=True,checked=100,refreshed=90,system_auto=True)
    app.render()
    assert 'Restart required' in app.headline.get_text()
    assert 'test-package' in app.packages.get_text()
    app.mode.set_active_id('daily');assert app.hour.get_sensitive() and not app.day.get_sensitive()
    app.mode.set_active_id('weekly');assert app.day.get_sensitive()
    app.day.set_active_id('Sat');app.hour.set_value(9);app.minute.set_value(25)
    app.scope.set_active_id('all')
    # A background policy refresh must not discard the user's unsaved controls.
    agent.scheduler.CONFIG.write_text(json.dumps(dict(agent.scheduler.DEFAULT,mode='daily',scope='all',hour=3)))
    app.render()
    assert 'Daily at 03:00' in app.details.get_text()
    assert app.mode.get_active_id()=='weekly' and app.hour.get_value_as_int()==9
    commands=[]
    def run(command,**kwargs):
        commands.append(command)
        if 'configure' in command:agent.scheduler.CONFIG.write_text(command[-1])
        return subprocess.CompletedProcess(command,0,stdout='',stderr='')
    with patch.object(agent.subprocess,'run',side_effect=run):
        app.configure(7)
        until(lambda:app.apply.get_sensitive())
    saved=json.loads(agent.scheduler.CONFIG.read_text())
    assert saved['mode']=='weekly' and saved['scope']=='all' and saved['day']=='Sat' and saved['hour']==9 and saved['minute']==25
    assert time.time()+6*86400 < saved['paused_until'] <= time.time()+7*86400
    assert commands[0][:3]==['/usr/bin/pkexec',str(agent.scheduler.HELPER),'configure']
    with patch.object(agent.subprocess,'run',side_effect=run):
        app.configure(0);until(lambda:app.apply.get_sensitive())
    assert json.loads(agent.scheduler.CONFIG.read_text())['paused_until']==0
    app.notify_check.set_active(False);assert not json.loads(agent.PREFS.read_text())['notifications']
    app.mode.set_active_id('system');assert not app.pause.get_sensitive()
    with patch.object(agent.subprocess,'run',side_effect=subprocess.CalledProcessError(126,['pkexec'])):
        app.configure();until(lambda:app.apply.get_sensitive())
    assert 'not saved' in app.feedback.get_text()
    assert json.loads(agent.scheduler.CONFIG.read_text())['mode']=='weekly','Cancelled authentication must preserve system settings'
    with patch.object(agent.subprocess,'Popen') as launch:
        app.install_updates();launch.assert_called_once_with(['/usr/bin/update-manager'],start_new_session=True)
    assert len(app.menu.get_children())>=8
    app.close();assert app.window is None
    app.open();assert app.window is not None
    app.close();app.quit()
    print('PASS GTK: tray menu, update inventory/reboot, schedule controls, authenticated save dispatch, pause/resume, cancellation, notifications, native installer dispatch, close/reopen.')


if __name__=='__main__':
    if '--session' in sys.argv:session(Path(sys.argv[-1]))
    else:
        with tempfile.TemporaryDirectory(prefix='axentra-update-test-') as tmp:
            Path(tmp+'/runtime').mkdir(mode=0o700)
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=tmp+'/config',XDG_CACHE_HOME=tmp+'/cache',XDG_RUNTIME_DIR=tmp+'/runtime',GDK_BACKEND='x11',GTK_USE_PORTAL='0',GIO_USE_VFS='local')
            result=subprocess.run(['dbus-run-session','--','xvfb-run','-a','/usr/bin/python3',__file__,'--session',tmp],env=env,capture_output=True,text=True,timeout=45)
            print(result.stdout)
            if result.returncode:print(result.stderr)
            raise SystemExit(result.returncode)
