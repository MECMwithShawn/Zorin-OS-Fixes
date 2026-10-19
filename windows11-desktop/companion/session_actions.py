"""Explicit session actions; native session dialogs retain their confirmations."""
import shutil
import subprocess


def validate(action):
    if action not in ('lock','switch-user','sign-out','sleep','shutdown','restart'):
        raise ValueError('Unknown session action.')


def command(action):
    """Legacy Xfce commands. GNOME uses its session services directly."""
    validate(action)
    commands = {
        'lock': ['xflock4'],
        'switch-user': ['dm-tool', 'switch-to-greeter'] if shutil.which('dm-tool') else ['gdmflexiserver'],
        'sign-out': ['xfce4-session-logout', '--logout'],
        'sleep': ['xfce4-session-logout', '--suspend'],
        'shutdown': ['xfce4-session-logout', '--halt'],
        'restart': ['xfce4-session-logout', '--reboot'],
    }
    return commands[action]


def _call(system, name, path, method, signature=None, args=()):
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM if system else Gio.BusType.SESSION,None)
    interface = name+'.Manager' if name=='org.freedesktop.login1' else name
    return bus.call_sync(name,path,interface,method,
                         GLib.Variant(signature,args) if signature else None,None,
                         Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION,90000,None)


def _switch_user():
    import gi
    gi.require_version('Gdm','1.0')
    from gi.repository import Gdm
    # Lock the existing session before moving to GDM's login screen, as Shell does.
    _call(False,'org.gnome.ScreenSaver','/org/gnome/ScreenSaver','Lock')
    if not Gdm.goto_login_session_sync(None):
        raise RuntimeError('GNOME could not open the user switching screen.')


def run(action, gnome):
    validate(action)
    if gnome:
        if action=='switch-user':return _switch_user()
        if action=='lock':
            return _call(False,'org.gnome.ScreenSaver','/org/gnome/ScreenSaver','Lock')
        if action=='sleep':
            return _call(True,'org.freedesktop.login1','/org/freedesktop/login1','Suspend','(b)',(True,))
        method={'sign-out':'Logout','shutdown':'Shutdown','restart':'Reboot'}[action]
        return _call(False,'org.gnome.SessionManager','/org/gnome/SessionManager',method,
                     '(u)' if action=='sign-out' else None,(0,) if action=='sign-out' else ())
    argv = command(action)
    if not shutil.which(argv[0]):
        raise RuntimeError('This session action is unavailable: '+argv[0]+' is not installed.')
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'The desktop could not complete this session action.')
