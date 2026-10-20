"""Bounded, read-only systemd journal queries for Event Viewer."""
from concurrent.futures import CancelledError
from datetime import datetime
import hashlib
import json
import os
import selectors
import subprocess
import time

LIMIT = 250
MAX_BYTES = 4 * 1024 * 1024
SCOPES = {'application': ['--user'], 'system': ['--system'], 'kernel': ['--system', '_TRANSPORT=kernel']}
PERIODS = {'boot': ['--boot=0'], 'previous': ['--boot=-1'],
           'hour': ['--since=-1 hour'], 'day': ['--since=-24 hours']}
LEVELS = {'all': [], 'errors': ['--priority=0..3'], 'warnings': ['--priority=0..4'],
          'information': ['--priority=5..6']}
NAMES = ['Emergency', 'Alert', 'Critical', 'Error', 'Warning', 'Notice', 'Information', 'Debug']
FIELDS = '__REALTIME_TIMESTAMP,PRIORITY,SYSLOG_IDENTIFIER,MESSAGE,_SYSTEMD_UNIT,_SYSTEMD_USER_UNIT,_PID,_BOOT_ID'


def command(scope, period, level):
    if scope not in SCOPES or period not in PERIODS or level not in LEVELS:
        raise ValueError('Unknown journal filter')
    return ['journalctl', '--no-pager', '--output=json', '--all', '--reverse', f'--lines={LIMIT}',
            '--output-fields=' + FIELDS, *SCOPES[scope], *PERIODS[period], *LEVELS[level]]


def capture(argv, cancel=None, timeout=4, limit=MAX_BYTES):
    """Drain both pipes with byte/time limits; terminate only our query process."""
    output, errors = bytearray(), bytearray()
    truncated = False
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=dict(os.environ, LC_ALL='C'))
    except FileNotFoundError as error:
        raise RuntimeError('journalctl is not installed.') from error
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, output)
            selector.register(process.stderr, selectors.EVENT_READ, errors)
            deadline = time.monotonic() + timeout
            while selector.get_map():
                if cancel and cancel.is_set():
                    raise CancelledError()
                if time.monotonic() >= deadline:
                    raise RuntimeError('Reading the journal timed out. Choose Refresh to retry.')
                for key, _ in selector.select(.1):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    target = key.data
                    maximum = limit if target is output else 65536
                    room = maximum - len(target)
                    target.extend(data[:room])
                    if len(data) > room:
                        truncated = True
                        break
                if truncated:
                    break
            if not truncated:
                process.wait(timeout=max(.05, deadline - time.monotonic()))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()
    warning = errors.decode('utf-8', 'replace').strip()[:1000]
    if not truncated and process.returncode:
        raise RuntimeError(warning or 'The journal is unavailable for this account.')
    if truncated:
        # A boundary may split a JSON record. Keep only complete records.
        output = output.rsplit(b'\n', 1)[0] if b'\n' in output else b''
        warning = 'Output limit reached; only complete events are shown.' + ('\n' + warning if warning else '')
    return bytes(output), warning


def text(value, limit=16000):
    if isinstance(value, list):
        if value and all(isinstance(v, int) and 0 <= v <= 255 for v in value):
            value = bytes(value).decode('utf-8', 'replace')
        else:
            value = '\n'.join(text(v, limit) for v in value[:8])
    if value is None:
        return 'Unavailable (omitted or oversized journal field)'
    result = str(value)
    result = ''.join(c if c.isprintable() or c in '\n\t' else '\uFFFD' for c in result)
    return result[:limit] + ('\n[Field truncated]' if len(result) > limit else '')


def parse(raw):
    rows, seen, skipped = [], set(), 0
    for line in raw.splitlines():
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            skipped += 1
            continue
        ident = text(record.get('__CURSOR') or hashlib.sha256(line).hexdigest(), 4096)
        if ident in seen:
            continue
        seen.add(ident)
        try:
            priority = int(record.get('PRIORITY', -1))
        except (ValueError, TypeError):
            priority = -1
        level = NAMES[priority] if 0 <= priority < len(NAMES) else 'Unknown'
        try:
            stamp = datetime.fromtimestamp(int(record.get('__REALTIME_TIMESTAMP', '')) / 1_000_000).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
        except (ValueError, TypeError, OverflowError, OSError):
            stamp = 'Unavailable'
        source = text(record.get('SYSLOG_IDENTIFIER') or record.get('_SYSTEMD_USER_UNIT') or record.get('_SYSTEMD_UNIT') or 'Unknown', 512)
        rows.append(dict(id=ident, time=stamp, priority=priority, level=level, source=source,
                         message=text(record.get('MESSAGE')), pid=text(record.get('_PID', 'Unavailable'), 64),
                         unit=text(record.get('_SYSTEMD_USER_UNIT') or record.get('_SYSTEMD_UNIT') or 'Unavailable', 512),
                         boot=text(record.get('_BOOT_ID', 'Unavailable'), 128)))
        if len(rows) >= LIMIT:
            break
    return rows, skipped


def load(scope='system', period='boot', level='all', cancel=None):
    raw, warning = capture(command(scope, period, level), cancel)
    rows, skipped = parse(raw)
    if skipped:
        warning += f'\n{skipped} unreadable journal records were omitted.'
    return {'rows': rows, 'warning': warning.strip()}


def matches(row, query):
    haystack = ' '.join(row[k] for k in ('source', 'message', 'unit', 'level', 'pid')).casefold()
    return all(term in haystack for term in query.casefold().split())


def details(row):
    return (f"Date and time: {row['time']}\nLevel: {row['level']}\nSource: {row['source']}\n"
            f"Unit: {row['unit']}\nProcess ID: {row['pid']}\nBoot ID: {row['boot']}\n\n{row['message']}")
