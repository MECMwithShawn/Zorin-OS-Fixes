"""Plan panel changes by plugin type, independently of machine-specific IDs."""


def find_panel(properties, installed=None):
    if installed is not None:
        key = f'/panels/panel-{installed}/plugin-ids'
        if key not in properties:
            raise ValueError('The installed panel no longer exists; restore or repair it first.')
        return installed
    matches = []
    for key, ids in properties.items():
        if key.startswith('/panels/panel-') and key.endswith('/plugin-ids'):
            if any(properties.get(f'/plugins/plugin-{i}') == 'zorinmenulite' for i in ids):
                matches.append(int(key.split('/')[2].split('-')[1]))
    if len(matches) != 1:
        raise ValueError('Expected one panel containing the Zorin Lite menu. Restore that layout first.')
    return matches[0]


def plan(ids, types, start, quick, search, allocate, battery=False):
    def one(kind):
        return next((i for i in ids if types.get(i) == kind), None)
    clock, tray, dock = one('clock'), one('systray'), one('docklike')
    if None in (clock, tray, dock) or start not in ids:
        raise ValueError('The panel must contain Start, Clock, Status Tray, and Docklike Taskbar.')
    notification = one('notification-plugin')
    separators = [i for i in ids if types.get(i) == 'separator']
    new = {}
    while len(separators) < 2:
        plugin = allocate()
        separators.append(plugin)
        new[plugin] = 'separator'
    left, right = separators[:2]
    show = one('showdesktop')
    if show is None:
        show = allocate()
        new[show] = 'showdesktop'
    reserved = {start, quick, search, dock, left, right, clock, tray, show, notification}
    removed = {'indicator', 'pulseaudio'}
    if not battery:
        removed.add('power-manager-plugin')
    extra = [i for i in ids if i not in reserved and types.get(i) not in removed]
    order = [left, start, search, dock, right, *extra, tray, quick, clock]
    if notification is not None:
        order.append(notification)
    order.append(show)
    return dict(order=order, new=new, clock=clock, tray=tray, dock=dock,
                notification=notification, left=left, right=right, show=show)
