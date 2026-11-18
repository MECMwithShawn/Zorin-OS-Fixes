"""Resolve supported native maximize/restore controls through AT-SPI."""

from collections import deque
import gettext
import json
import math
import signal
import sys
import time


class LookupExpired(Exception):
    pass


def children(node, limit):
    count = node.get_child_count()
    if count < 0 or count > limit:
        raise LookupExpired
    for index in range(count):
        child = node.get_child_at_index(index)
        if child is not None:
            yield child


def extents(node, atspi):
    component = node.get_component_iface()
    if component is None:
        return None
    rectangle = component.get_extents(atspi.CoordType.WINDOW)
    if rectangle is None:
        return None
    return rectangle.x, rectangle.y, rectangle.width, rectangle.height


def contains(rect, x, y, margin=0):
    left, top, width, height = rect
    return (width > 0 and height > 0 and left - margin <= x < left + width + margin
            and top - margin <= y < top + height + margin)


def button_hit(node, atspi, request):
    state = node.get_state_set()
    enabled = (atspi.StateType.SENSITIVE if request.get('kind') == 'gtk4'
               else atspi.StateType.ENABLED)
    if not all(state.contains(flag) for flag in
               (atspi.StateType.VISIBLE, atspi.StateType.SHOWING, enabled)):
        return None
    rect = extents(node, atspi)
    if rect is None:
        return None
    x, y, w, h = rect
    if (0 <= x and x + w <= request['width'] and 0 <= y < 72
            and 8 <= w <= 128 and 8 <= h <= 72 and y + h <= request['height']
            and contains(rect, request['x'], request['y'])):
        return rect
    return None


def gtk_caption_hit(frame, atspi, request, check_time):
    # GTK4 exports the real window action on its frame. Individual buttons
    # expose only "click", so also require GTK's caption group and labels.
    if (frame.get_attributes() or {}).get('toolkit') != 'GTK':
        return None
    actions = frame.get_action_iface()
    if actions is None:
        return None
    for index in range(min(actions.get_n_actions(), 128)):
        check_time()
        if actions.get_action_name(index) == 'window.toggle-maximized':
            break
    else:
        return None

    translate = gettext.translation('gtk40', fallback=True).gettext
    maximize = (translate('Maximize'), translate('Maximize the window'))
    peers = {(translate('Minimize'), translate('Minimize the window')),
             (translate('Close'), translate('Close the window'))}
    containers = (atspi.Role.PANEL, atspi.Role.GROUPING, atspi.Role.TOOL_BAR)
    queue = deque((child, 0) for child in children(frame, 24))
    matches = []
    checked = 0
    while queue:
        check_time()
        checked += 1
        if checked > 96:
            return None
        node, depth = queue.popleft()
        if node.get_role() not in containers:
            continue
        bounds = extents(node, atspi)
        # GTK CSS boxes may end a few pixels before the caption button's
        # accessible edge. Only the final button test uses exact bounds.
        if not bounds or not contains(bounds, request['x'], request['y'], margin=8):
            continue
        descendants = list(children(node, 32))
        if depth < 20:
            queue.extend((child, depth + 1) for child in descendants)
        if node.get_role() != atspi.Role.PANEL or bounds[2] > 240 or bounds[3] > 72:
            continue
        if (node.get_attributes() or {}).get('toolkit') != 'GTK':
            continue
        controls = [(child, (child.get_name(), child.get_description()))
                    for child in descendants if child.get_role() == atspi.Role.PUSH_BUTTON]
        if not {label for _, label in controls}.intersection(peers):
            continue
        if any(label not in peers and label != maximize for _, label in controls):
            continue
        for button, label in controls:
            if label == maximize and (button.get_attributes() or {}).get('toolkit') == 'GTK':
                rect = button_hit(button, atspi, request)
                if rect is not None:
                    matches.append(rect)
    return matches[0] if len(matches) == 1 else None


def resolve_control(desktop, atspi, request):
    """Return origin-relative bounds only for an unambiguous caption hit."""
    if desktop is None:
        return None
    pid = request['pid']
    proxy_app_matches = None
    if request.get('kind') == 'chrome-flatpak':
        from maximize_chrome import chrome_scope, is_chrome_proxy, chrome_caption_hit
        scope = chrome_scope(pid)
        if scope is None:
            return None
        proxy_app_matches = lambda app_pid: is_chrome_proxy(app_pid, scope)
    title = request['title']
    buffer_width, buffer_height = request['width'], request['height']
    deadline = time.monotonic() + .45

    def check_time():
        if time.monotonic() >= deadline:
            raise LookupExpired

    frames = []
    for app in children(desktop, 128):
        check_time()
        app_pid = app.get_process_id()
        if not (proxy_app_matches(app_pid) if proxy_app_matches else app_pid == pid):
            continue
        for frame in children(app, 48):
            check_time()
            if frame.get_role() != atspi.Role.FRAME or frame.get_name() != title:
                continue
            rect = extents(frame, atspi)
            if rect and rect[:2] == (0, 0) and abs(rect[2] - buffer_width) <= 2 and abs(rect[3] - buffer_height) <= 2:
                frames.append(frame)
    if len(frames) != 1:
        return None
    if request.get('kind') == 'gtk4':
        return gtk_caption_hit(frames[0], atspi, request, check_time)
    if proxy_app_matches:
        return chrome_caption_hit(frames[0], atspi, request, children, button_hit)

    # Chromium defines the native Views IDs in chrome/browser/ui/view_ids.h.
    # Only walk its caption containers, never the browser UI or web content.
    queue = deque((child, 0) for child in children(frames[0], 24))
    matches = []
    examined = 0
    while queue:
        check_time()
        examined += 1
        if examined > 48:
            return None
        node, depth = queue.popleft()
        role = node.get_role()
        if role == atspi.Role.PANEL and depth < 2:
            queue.extend((child, depth + 1) for child in children(node, 24))
        if role != atspi.Role.PUSH_BUTTON or depth != 2:
            continue
        attributes = node.get_attributes() or {}
        if (attributes.get('class') != 'FrameCaptionButton'
                or attributes.get('id') not in ('view_2', 'view_3')
                or attributes.get('hidden') == 'true'):
            continue
        rect = button_hit(node, atspi, request)
        if rect is not None:
            matches.append(rect)
    return matches[0] if len(matches) == 1 else None


def valid(request):
    if not isinstance(request, dict) or type(request.get('pid')) is not int or request['pid'] <= 0:
        return False
    if request.get('kind', 'chromium') not in ('chromium', 'gtk4', 'chrome-flatpak'):
        return False
    if not isinstance(request.get('title'), str) or not 1 <= len(request['title']) <= 4096:
        return False
    if not all(type(request.get(key)) is int and 0 < request[key] <= 16384 for key in ('width', 'height')):
        return False
    if not all(type(request.get(key)) in (int, float) and math.isfinite(request[key]) for key in ('x', 'y')):
        return False
    return 0 <= request['x'] < request['width'] and 0 <= request['y'] < min(144, request['height'])


def main():
    def expire(_signal, _frame):
        raise LookupExpired

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, .75)
    result = None
    try:
        payload = sys.stdin.read(32769)
        if len(payload) <= 32768:
            request = json.loads(payload)
            if valid(request):
                import gi
                gi.require_version('Atspi', '2.0')
                from gi.repository import Atspi, GLib
                Atspi.set_timeout(150, 200)
                Atspi.init()
                try:
                    result = resolve_control(Atspi.get_desktop(0), Atspi, request)
                except GLib.Error:
                    pass
    except (ImportError, LookupExpired, ValueError, OverflowError):
        pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
