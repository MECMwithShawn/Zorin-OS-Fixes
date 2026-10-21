"""Stop this user's Axentra GUI/player processes when the graphical session ends."""
import os
from pathlib import Path
import select
import signal


def executables(home):
    return {str((home / relative).resolve()) for relative in (
        '.local/share/minitube/app/minitube',
        '.local/share/minitube/soloist/bin/soloist',
        '.local/share/axentra/apps/onedrive/AxentraOneDrive',
    )}


def matches(pid, allowed):
    try:
        process = Path('/proc') / str(pid)
        return process.stat().st_uid == os.getuid() and os.readlink(process / 'exe').removesuffix(' (deleted)') in allowed
    except (OSError, ValueError):
        return False


def stop(allowed, grace=3):
    """Pidfds prevent signalling a reused PID. Never match process names/argv."""
    descriptors = []
    try:
        for process in Path('/proc').iterdir():
            if not process.name.isdigit() or not matches(int(process.name), allowed):
                continue
            try:
                fd = os.pidfd_open(int(process.name))
            except ProcessLookupError:
                continue
            if not matches(int(process.name), allowed):
                os.close(fd)
                continue
            descriptors.append(fd)
            try:
                signal.pidfd_send_signal(fd, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if descriptors:
            poll = select.poll()
            for fd in descriptors:
                poll.register(fd, select.POLLIN)
            # One shared deadline, regardless of the number of processes.
            import time
            end = time.monotonic() + grace
            pending = set(descriptors)
            while pending and time.monotonic() < end:
                for fd, _ in poll.poll(max(1, int((end - time.monotonic()) * 1000))):
                    pending.discard(fd)
                    poll.unregister(fd)
            for fd in pending:
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        return len(descriptors)
    finally:
        for fd in descriptors:
            os.close(fd)


def units(destination):
    script = str(Path(destination) / 'session_cleanup.py').replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"')
    return {'zorin11-session-cleanup.service': f'''[Unit]
Description=Close Axentra GUI and music processes at graphical logout
PartOf=graphical-session.target
After=axentra-onedrive.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/true
ExecStop=/usr/bin/python3 "{script}"
TimeoutStopSec=10

[Install]
WantedBy=graphical-session.target
'''}


if __name__ == '__main__':
    print('Stopped session app processes:', stop(executables(Path.home())))
