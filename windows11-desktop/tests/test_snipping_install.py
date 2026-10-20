"""Shortcut recovery using private keyfile settings; never changes the host."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ShortcutTests(unittest.TestCase):
    def test_install_upgrade_restore_conflict_and_later_user_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            code = r'''
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import snipping_install as install
from gi.repository import Gio
install.BACKUP=Path(sys.argv[2])/'backup.json'
media=Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
settings=Gio.Settings.new_with_path(install.SCHEMA,install.SHORTCUT)
original=list(media.get_strv('custom-keybindings'))
install.shortcut()
backup=install.BACKUP.read_bytes()
install.shortcut()
assert install.BACKUP.read_bytes()==backup
assert media.get_strv('custom-keybindings').count(install.SHORTCUT)==1
install.restore_shortcut()
assert media.get_strv('custom-keybindings')==original
install.shortcut()
settings.set_string('binding','<Super>F9')
install.restore_shortcut()
assert settings.get_string('binding')=='<Super>F9'
assert install.SHORTCUT in media.get_strv('custom-keybindings')
settings.set_string('binding','<Super><Shift>s')
install.restore_shortcut()
other='/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/owned/'
Gio.Settings.new_with_path(install.SCHEMA,other).set_string('binding','<Super><Shift>s')
media.set_strv('custom-keybindings',[other])
install.shortcut()
assert media.get_strv('custom-keybindings')==[other]
install.RECORD_BACKUP=Path(sys.argv[2])/'record-backup.json'
install.record_shortcut()
record=Gio.Settings.new_with_path(install.SCHEMA,install.RECORD_SHORTCUT)
assert record.get_string('binding')=='<Super><Shift>r'
assert record.get_string('command').endswith('--record')
install.record_shortcut()
assert media.get_strv('custom-keybindings').count(install.RECORD_SHORTCUT)==1
record.set_string('binding','<Super>F8')
install.record_shortcut();assert record.get_string('binding')=='<Super>F8'
install.restore_record_shortcut();assert record.get_string('binding')=='<Super>F8'
record.set_string('binding','<Super><Shift>r');install.restore_record_shortcut()
assert install.RECORD_SHORTCUT not in media.get_strv('custom-keybindings')
'''
            result = subprocess.run(
                [sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]),directory],
                env=dict(os.environ,GSETTINGS_BACKEND='keyfile',XDG_CONFIG_HOME=directory),
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
