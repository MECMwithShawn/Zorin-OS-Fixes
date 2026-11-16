"""Bind Chrome Flatpak accessibility to the exact compositor window's sandbox."""

import configparser
from pathlib import Path
import re


_PROC = Path('/proc')
_APP_ID = 'com.google.Chrome'
_SCOPE = re.compile(r'0::/.*/app-flatpak-com\.google\.Chrome-[1-9][0-9]*\.scope')


def _instance(pid, executable):
    if type(pid) is not int or pid <= 0:
        return None
    process = _PROC / str(pid)
    try:
        if process.joinpath('exe').readlink() != Path(executable):
            return None
        scope = process.joinpath('cgroup').read_text().strip()
        if not _SCOPE.fullmatch(scope):
            return None
        metadata = configparser.ConfigParser(interpolation=None)
        with process.joinpath('root/.flatpak-info').open(encoding='utf-8') as stream:
            metadata.read_string(stream.read(16384))
        if metadata.get('Application', 'name', fallback='') != _APP_ID:
            return None
        instance = metadata.get('Instance', 'instance-id', fallback='')
        if not re.fullmatch(r'[0-9]+', instance):
            return None
        return scope, instance
    except (OSError, UnicodeError, configparser.Error):
        return None


def chrome_scope(pid):
    return _instance(pid, '/app/extra/chrome')


def is_chrome_proxy(pid, scope):
    # Host AT-SPI identifies the Flatpak D-Bus proxy, while Mutter identifies
    # the browser. Tie both PIDs to one sandbox before inspecting its windows.
    return scope is not None and _instance(pid, '/usr/bin/xdg-dbus-proxy') == scope


def chrome_caption_hit(frame, atspi, request, children, button_hit):
    if (frame.get_attributes() or {}).get('class') != 'BrowserRootView':
        return None
    parent = frame
    for name in ('NonClientView', 'BrowserFrameViewLinuxNative'):
        panels = [node for node in children(parent, 24)
                  if node.get_role() == atspi.Role.PANEL
                  and (node.get_attributes() or {}).get('class') == name]
        if len(panels) != 1:
            return None
        parent = panels[0]

    hits = []
    for node in children(parent, 24):
        if node.get_role() != atspi.Role.PUSH_BUTTON:
            continue
        attributes = node.get_attributes() or {}
        if (attributes.get('class') != 'ImageButton'
                or attributes.get('id') not in ('view_2', 'view_3')
                or attributes.get('hidden') == 'true'):
            continue
        hit = button_hit(node, atspi, request)
        if hit is not None:
            hits.append(hit)
    return hits[0] if len(hits) == 1 else None
