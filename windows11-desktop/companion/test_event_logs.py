import json
import sys
import threading
import time
import unittest
from concurrent.futures import CancelledError
from unittest.mock import patch
import event_logs as e


def fixture():
    return [
        dict(__CURSOR='event-1', __REALTIME_TIMESTAMP='1792497600000000',
             PRIORITY='3', SYSLOG_IDENTIFIER='Fixture service', _SYSTEMD_UNIT='fixture.service',
             _PID='123', _BOOT_ID='fixture-boot', MESSAGE='Disk <error> & retry\nSecond line'),
        dict(__CURSOR='event-2', __REALTIME_TIMESTAMP='1792497601000000',
             PRIORITY='6', SYSLOG_IDENTIFIER='Fixture app', MESSAGE='Started successfully'),
        dict(__CURSOR='event-3', __REALTIME_TIMESTAMP='1792497602000000',
             PRIORITY='4', SYSLOG_IDENTIFIER='Fixture kernel', MESSAGE='Temperature warning')
    ]


class EventLogTests(unittest.TestCase):
    def test_command_is_read_only_and_validates_filters(self):
        for scope in e.SCOPES:
            for period in e.PERIODS:
                for level in e.LEVELS:
                    argv = e.command(scope, period, level)
                    self.assertIn('--lines=250', argv)
                    self.assertIn('--no-pager', argv)
                    self.assertFalse(any(arg.startswith(('--vacuum', '--rotate', '--flush', '--sync')) for arg in argv))
        self.assertIn('--boot=-1', e.command('kernel', 'previous', 'all'))
        self.assertNotIn('--dmesg', e.command('kernel', 'day', 'all'))
        with self.assertRaises(ValueError):
            e.command('system; rm', 'boot', 'all')

    def test_parse_metadata_duplicates_and_untrusted_text(self):
        rows, skipped = e.parse('\n'.join(json.dumps(r) for r in fixture() + fixture()).encode())
        self.assertEqual(len(rows), 3)
        self.assertEqual(skipped, 0)
        self.assertEqual(rows[0]['level'], 'Error')
        self.assertEqual(rows[0]['unit'], 'fixture.service')
        self.assertIn('Disk <error> & retry\nSecond line', e.details(rows[0]))
        self.assertIn('2026-', rows[0]['time'])
        self.assertTrue(e.matches(rows[0], 'DISK fixture.service'))
        self.assertFalse(e.matches(rows[0], 'disk nonexistent'))

    def test_missing_binary_multiple_and_invalid_values(self):
        payload = dict(PRIORITY=['3', '4'], __REALTIME_TIMESTAMP='invalid',
                       MESSAGE=[65, 0, 66], SYSLOG_IDENTIFIER=['one', 'two'])
        rows, skipped = e.parse(b'null\nmalformed\n' + json.dumps(payload).encode())
        self.assertEqual(skipped, 2)
        self.assertEqual(rows[0]['level'], 'Unknown')
        self.assertEqual(rows[0]['time'], 'Unavailable')
        self.assertEqual(rows[0]['message'], 'A\uFFFDB')
        self.assertEqual(rows[0]['source'], 'one\ntwo')
        self.assertIn('Unavailable', e.text(None))
        self.assertTrue(e.text('a' * 20000).endswith('[Field truncated]'))

    def test_record_limit_and_omission_warning(self):
        payload = b'\n'.join(json.dumps(dict(__CURSOR=str(i), MESSAGE='test')).encode() for i in range(300))
        self.assertEqual(len(e.parse(payload)[0]), e.LIMIT)
        with patch.object(e, 'capture', return_value=(b'invalid\n', 'Partial journal access')):
            result = e.load()
        self.assertIn('Partial journal access', result['warning'])
        self.assertIn('1 unreadable', result['warning'])

    def test_real_subprocess_output_failure_and_missing_tool(self):
        raw, warning = e.capture([sys.executable, '-c', "import sys;print('{}');sys.stderr.write('partial access')"])
        self.assertEqual(raw.strip(), b'{}')
        self.assertEqual(warning, 'partial access')
        with self.assertRaisesRegex(RuntimeError, 'denied'):
            e.capture([sys.executable, '-c', "import sys;sys.stderr.write('denied');sys.exit(1)"])
        with self.assertRaisesRegex(RuntimeError, 'not installed'):
            e.capture(['/nonexistent-zorin11-journal-command'])

    def test_output_limit_timeout_and_cancellation(self):
        raw, warning = e.capture([sys.executable, '-c', "import sys;sys.stdout.write('{}\\n'*10000)"], limit=1024)
        self.assertLessEqual(len(raw), 1024)
        self.assertIn('limit reached', warning)
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            e.capture([sys.executable, '-c', 'import time;time.sleep(10)'], timeout=.2)
        cancel = threading.Event()
        timer = threading.Timer(.1, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            with self.assertRaises(CancelledError):
                e.capture([sys.executable, '-c', 'import time;time.sleep(10)'], cancel=cancel)
        finally:
            timer.join()
        self.assertLess(time.monotonic() - start, 2)


if __name__ == '__main__':
    unittest.main()
