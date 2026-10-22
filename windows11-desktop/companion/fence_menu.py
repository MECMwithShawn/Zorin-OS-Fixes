"""Native context menus for fences.

Fence windows can be as small as a rolled-up title bar, so menus are GTK
popups that may extend past the window, like the desktop's own menu.
"""
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, Gtk

import fences

OPACITY = [(0.15, 'Glass (15%)'), (0.35, 'Light (35%)'), (0.55, 'Balanced (55%)'),
           (0.75, 'Solid (75%)'), (1.0, 'Opaque')]
ICON_SIZES = [('small', 'Small icons'), ('medium', 'Medium icons'), ('large', 'Large icons')]
SORTS = [('manual', 'Manual (drag to arrange)'), ('name', 'Name'), ('type', 'Item type'),
         ('modified', 'Date modified')]
TINT_NAMES = {'slate': 'Slate', 'graphite': 'Graphite', 'midnight': 'Midnight', 'ocean': 'Ocean',
              'teal': 'Teal', 'forest': 'Forest', 'plum': 'Plum', 'rose': 'Rose', 'amber': 'Amber',
              'frost': 'Frost (light)'}


def _item(menu, label, action=None, sensitive=True):
    row = Gtk.MenuItem(label=label)
    row.set_sensitive(sensitive)
    if action:
        row.connect('activate', lambda *_: action())
    menu.append(row)
    return row


def _choices(menu, label, options, current, choose):
    parent = Gtk.MenuItem(label=label)
    sub = Gtk.Menu()
    group = None
    for value, text in options:
        row = Gtk.RadioMenuItem(label=text)
        if group:
            row.join_group(group)
        group = group or row
        row.set_active(value == current)
        row.connect('toggled', lambda widget, v=value: widget.get_active() and choose(v))
        sub.append(row)
    parent.set_submenu(sub)
    menu.append(parent)


def _key(item):
    return item.get('id', item.get('path'))


def show(hub, surface, kind, item_id=None, x=None, y=None):
    group = hub.store.group(surface.group_id)
    style = fences.clean_style(group.get('style'))
    menu = Gtk.Menu()
    menu.get_style_context().add_class('axentra-desktop-menu')

    def restyle(**changes):
        hub.store.set_style(group['id'], fences.clean_style({**style, **changes}))
        hub.broadcast()

    if kind == 'item':
        item = next((i for i in group['items'] if _key(i) == item_id), None)
        info = next((i for i in hub.group_info(group)['items'] if i.get('id') == item_id), None)
        if info is None:
            return
        open_item = (lambda: hub.open_path(info['path'])) if info['kind'] == 'path' else (lambda: hub.launch(info['id']))
        _item(menu, 'Open', open_item)
        if info['kind'] == 'path' and not group['folder']:
            parent = Path(info['path']).parent
            _item(menu, 'Open file location', lambda: hub.open_explorer(str(parent)))
        others = [g for g in hub.store.state['groups'] if g is not group and not g['folder']]
        if item is not None and others:
            move = Gtk.MenuItem(label='Move to fence')
            sub = Gtk.Menu()
            for other in others:
                row = Gtk.MenuItem(label=other['title'])
                row.connect('activate', lambda *_, target=other['id']: hub.dispatch(
                    surface, {'action': 'fence-move-item', 'id': item_id, 'target': target}))
                sub.append(row)
            move.set_submenu(sub)
            menu.append(move)
        if item is not None:
            on_desktop = info['kind'] == 'path' and Path(info['path']).parent == fences.desktop_dir()
            menu.append(Gtk.SeparatorMenuItem())
            _item(menu, 'Return to desktop' if on_desktop else 'Remove from fence',
                  lambda: hub.dispatch(surface, {'action': 'remove-item', 'group': group['id'], 'id': item_id}))
    else:
        _item(menu, 'Rename fence', lambda: surface.send({'type': 'rename-fence'}))
        _item(menu, 'Unroll' if group['collapsed'] else 'Roll up',
              lambda: hub.dispatch(surface, {'action': 'collapse', 'group': group['id']}))
        auto = Gtk.CheckMenuItem(label='Expand on hover when rolled up')
        auto.set_active(style['autoRoll'])
        auto.connect('toggled', lambda widget: restyle(autoRoll=widget.get_active()))
        menu.append(auto)
        menu.append(Gtk.SeparatorMenuItem())
        _choices(menu, 'Color', [(k, TINT_NAMES[k]) for k in fences.TINTS], style['tint'],
                 lambda v: restyle(tint=v))
        _choices(menu, 'Transparency', OPACITY,
                 min(OPACITY, key=lambda o: abs(o[0]-style['opacity']))[0], lambda v: restyle(opacity=v))
        _choices(menu, 'Icon size', ICON_SIZES, style['iconSize'], lambda v: restyle(iconSize=v))
        if not group['folder']:
            _choices(menu, 'Sort by', SORTS, style['sort'], lambda v: restyle(sort=v))
        menu.append(Gtk.SeparatorMenuItem())
        _item(menu, 'New fence', lambda: hub.dispatch(surface, {'action': 'new-fence'}))
        _item(menu, 'Hide all fences (double-click the desktop to show)', hub.toggle_fences)
        _item(menu, 'Manage fences…', lambda: hub.show_start('groups'))
        menu.append(Gtk.SeparatorMenuItem())
        _item(menu, 'Delete fence', lambda: _confirm_delete(hub, surface, group))
    menu.show_all()
    menu.attach_to_widget(surface, None)
    if getattr(surface, 'fence_menu', None):
        surface.fence_menu.destroy()
    surface.fence_menu = menu  # keep a reference while it is open
    # Destroy after close; idle lets the chosen item's handler run first.
    menu.connect('deactivate', lambda m: GLib.idle_add(lambda: (m.destroy(), setattr(surface, 'fence_menu', None), False)[2]))
    # Requests arrive from WebKit, not a GDK event, so there is no trigger
    # event: open at the page's click point (or the top corner for keyboard).
    try:
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x or 8), int(y or 36), 1, 1
    except (TypeError, ValueError):
        rect.x, rect.y = 8, 36
    menu.popup_at_rect(surface.get_window(), rect, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.NORTH_WEST, None)


def _confirm_delete(hub, surface, group):
    on_desktop = sum(1 for i in group['items'] if i.get('kind') == 'path'
                     and Path(i['path']).parent == fences.desktop_dir())
    detail = 'The fence is removed. No files are deleted.'
    if on_desktop:
        detail += f' {on_desktop} desktop {"icon returns" if on_desktop == 1 else "icons return"} to the desktop.'
    hub.modal = True
    dialog = Gtk.MessageDialog(transient_for=surface, modal=True, message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.NONE, text=f'Delete the “{group["title"]}” fence?')
    dialog.format_secondary_text(detail)
    dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Delete fence', Gtk.ResponseType.OK)
    response = dialog.run()
    dialog.destroy()
    hub.modal = False
    if response == Gtk.ResponseType.OK:
        hub.dispatch(surface, {'action': 'remove-group', 'group': group['id']})
