import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'companion'))
import task_manager


class TaskManagerTests(unittest.TestCase):
    def test_chatgpt_passthrough_wrapper_maps_binary_without_losing_metadata(self):
        source='[Desktop Entry]\nName=ChatGPT\nName[fr]=ChatGPT\nExec=chatgpt %U\nIcon=chatgpt\nMimeType=x-scheme-handler/codex;\n'
        wrapper='#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/ChatGPT" "$@"\n'
        entry=task_manager.chatgpt_entry(source,wrapper,Path('/usr/lib/chatgpt/ChatGPT')).decode()
        self.assertIn('Exec="/usr/lib/chatgpt/ChatGPT" %U',entry)
        self.assertIn('Icon=chatgpt',entry)
        self.assertIn('Name[fr]=ChatGPT',entry)
        self.assertNotIn('MimeType=',entry)
        self.assertIn('OnlyShowIn=X-Zorin11-ProcessMonitor;',entry)
        self.assertIsNone(task_manager.chatgpt_entry(source,wrapper+'setup-something\n',Path('/bin/other')))
        self.assertIsNone(task_manager.chatgpt_entry(source.replace('chatgpt %U','chatgpt --custom %U'),wrapper,Path('/bin/other')))

    def test_upgrade_retains_original_settings_and_restore_preserves_later_edits(self):
        values={key:'original-'+key for key in task_manager.DEFAULTS}
        def setting(action,key,value=None):
            if action=='get':return values[key]
            values[key]=value
        with tempfile.TemporaryDirectory() as directory,patch.object(task_manager,'available',return_value=True),patch.object(task_manager,'setting',side_effect=setting):
            backup=Path(directory)/'backup.json'
            task_manager.configure(backup);task_manager.configure(backup)
            self.assertEqual(json.loads(backup.read_text())['window-width']['before'],'original-window-width')
            self.assertEqual(values['apps-page-merged-process-stats'],'true')
            self.assertEqual(values['performance-show-gpus'],'true')
            values['window-width']='1440'
            task_manager.restore(backup)
            self.assertEqual(values['window-width'],'1440')
            self.assertEqual(values['performance-show-gpus'],'original-performance-show-gpus')
            self.assertFalse(backup.exists())

    def test_missing_flatpak_app_does_not_write_settings(self):
        with patch.object(task_manager,'available',return_value=False),patch.object(task_manager,'setting') as setting:
            with self.assertRaisesRegex(RuntimeError,'install-system-deps'):task_manager.configure()
            setting.assert_not_called()
