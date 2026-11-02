"""Hand files to Axentra Outlook as attachments on a new, unsent message."""
import shutil
import subprocess
from pathlib import Path

OUTLOOK = 'axentra-outlook'


def attachments(paths):
    """Regular files among paths, in order; folders and missing paths are left out."""
    return [str(Path(p).absolute()) for p in paths if isinstance(p, str) and Path(p).is_file()]


def command(paths):
    """The axentra-outlook --compose command for paths, or None if nothing can be attached."""
    files = attachments(paths)
    if not files:
        return None
    names = ', '.join(Path(f).name for f in files)
    args = [OUTLOOK, '--compose', '--subject', f'Emailing: {names}']
    for f in files:
        args += ['--attach', f]
    return args


def available():
    return shutil.which(OUTLOOK) is not None


def compose(paths):
    """Open the draft; returns a message for the user when it can't."""
    args = command(paths)
    if args is None:
        return 'Choose one or more files to email.'
    if not available():
        return 'Axentra Outlook isn\'t installed.'
    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None
