"""Explicit session actions; native session dialogs retain their confirmations."""
import shutil
import subprocess


def command(action, gnome):
    if gnome:
        commands = {
            'lock': ['loginctl', 'lock-session'],
            'switch-user': ['gdmflexiserver'],
            'sign-out': ['gnome-session-quit', '--logout'],
            'sleep': ['systemctl', '--no-block', 'suspend'],
            'shutdown': ['gnome-session-quit', '--power-off'],
            'restart': ['gnome-session-quit', '--reboot'],
        }
    else:
        commands = {
            'lock': ['xflock4'],
            'switch-user': ['dm-tool', 'switch-to-greeter'] if shutil.which('dm-tool') else ['gdmflexiserver'],
            'sign-out': ['xfce4-session-logout', '--logout'],
            'sleep': ['xfce4-session-logout', '--suspend'],
            'shutdown': ['xfce4-session-logout', '--halt'],
            'restart': ['xfce4-session-logout', '--reboot'],
        }
    if action not in commands:
        raise ValueError('Unknown session action.')
    return commands[action]


def run(action, gnome):
    argv = command(action, gnome)
    if not shutil.which(argv[0]):
        raise RuntimeError('This session action is unavailable: '+argv[0]+' is not installed.')
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'The desktop could not complete this session action.')
