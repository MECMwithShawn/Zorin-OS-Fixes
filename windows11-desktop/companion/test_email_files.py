import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import email_files


class EmailFilesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.doc = self.dir/'Report été.pdf'; self.doc.write_bytes(b'%PDF')
        self.sheet = self.dir/'budget.xlsx'; self.sheet.write_bytes(b'x')
        (self.dir/'folder').mkdir()

    def test_command_attaches_files_only(self):
        args = email_files.command([str(self.doc), str(self.dir/'folder'), str(self.dir/'gone.txt'), str(self.sheet)])
        self.assertEqual(args, ['axentra-outlook', '--compose', '--subject', 'Emailing: Report été.pdf, budget.xlsx',
                                '--attach', str(self.doc), '--attach', str(self.sheet)])
        self.assertIsNone(email_files.command([str(self.dir/'folder')]))

    def test_compose_runs_outlook(self):
        bin_dir = self.dir/'bin'; bin_dir.mkdir()
        log = self.dir/'args.json'
        fake = bin_dir/'axentra-outlook'
        fake.write_text(f'#!/usr/bin/python3\nimport json,sys\nopen({str(log)!r},"w").write(json.dumps(sys.argv[1:]))\n')
        fake.chmod(0o755)
        path = os.environ['PATH']
        os.environ['PATH'] = f'{bin_dir}:{path}'
        try:
            self.assertIsNone(email_files.compose([str(self.doc)]))
            for _ in range(50):
                if log.exists(): break
                time.sleep(.1)
            self.assertEqual(json.loads(log.read_text()),
                             ['--compose', '--subject', 'Emailing: Report été.pdf', '--attach', str(self.doc)])
            self.assertEqual(email_files.compose([str(self.dir/'folder')]), 'Choose one or more files to email.')
            os.environ['PATH'] = str(self.dir/'empty')
            self.assertEqual(email_files.compose([str(self.doc)]), "Axentra Outlook isn't installed.")
        finally:
            os.environ['PATH'] = path


if __name__ == '__main__':
    unittest.main()
