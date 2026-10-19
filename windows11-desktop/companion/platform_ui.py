"""Native panel geometry and live desktop status, independent of UI rendering."""
import json
import subprocess
import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi


def panel_button(name):
    """Read the launcher's real allocation; it changes with apps and displays."""
    Atspi.set_timeout(150, 300)
    desktop = Atspi.get_desktop(0)
    def find(node, depth=0):
        if depth > 6:
            return None
        if node.get_name() == name and node.get_role() == Atspi.Role.PUSH_BUTTON:
            r = node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            if r.width > 1 and r.x > -100000:
                return (r.x, r.y, r.width, r.height)
        for i in range(node.get_child_count()):
            result = find(node.get_child_at_index(i), depth+1)
            if result:
                return result
    try:
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app.get_name() == 'xfce4-panel':
                return find(app)
    except Exception:
        return None


def run(args):
    return subprocess.check_output(args, text=True, timeout=3, stderr=subprocess.DEVNULL).strip()


def desktop_status():
    result = {'network': 'Unavailable', 'networkType': 'offline', 'wifi': False,
              'volume': None, 'muted': False, 'sink': '', 'bluetooth': False, 'dnd': False}
    try:
        import dbus
        xf = dbus.Interface(dbus.SessionBus().get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
        result['dnd'] = bool(xf.GetProperty('xfce4-notifyd','/do-not-disturb'))
    except Exception:
        pass
    from gnome_bridge import active as is_gnome
    if is_gnome():
        from gi.repository import Gio
        result['dnd']=not Gio.Settings.new('org.gnome.desktop.notifications').get_boolean('show-banners')
    try:
        result['wifi'] = run(['nmcli', 'radio', 'wifi']) == 'enabled'
        devices = run(['nmcli', '-t', '-f', 'TYPE,STATE,CONNECTION', 'device']).splitlines()
        active = [line.split(':', 2) for line in devices if ':connected:' in line and not line.startswith(('loopback:', 'bridge:', 'tun:'))]
        if active:
            kind, _, label = active[0]
            result.update(network=label.replace('\\:', ':'), networkType='wifi' if kind=='wifi' else 'wired')
        else:
            result['network'] = 'Not connected'
    except Exception:
        pass
    try:
        default = run(['pactl', 'get-default-sink'])
        sinks = json.loads(run(['pactl', '--format=json', 'list', 'sinks']))
        sink = next(s for s in sinks if s['name'] == default)
        volumes = [int(v['value_percent'].rstrip('%')) for v in sink['volume'].values()]
        result.update(volume=min(100,round(sum(volumes)/len(volumes))), muted=sink['mute'], sink=sink['description'])
    except Exception:
        pass
    try:
        result['bluetooth'] = 'Powered: yes' in run(['bluetoothctl', 'show'])
    except Exception:
        pass
    return result
