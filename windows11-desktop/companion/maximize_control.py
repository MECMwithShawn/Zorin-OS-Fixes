"""Resolve Brave's real maximize/restore control through AT-SPI."""

from collections import deque
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


def resolve_control(desktop, atspi, request):
    """Return buffer-relative bounds only for an unambiguous caption hit."""
    if desktop is None:
        return None
    pid = request['pid']
    title = request['title']
    buffer_width, buffer_height = request['width'], request['height']
    pointer_x, pointer_y = request['x'], request['y']
    deadline = time.monotonic() + .45

    def check_time():
        if time.monotonic() >= deadline:
            raise LookupExpired

    frames = []
    for app in children(desktop, 128):
        check_time()
        if app.get_process_id() != pid:
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
        state = node.get_state_set()
        if not all(state.contains(flag) for flag in
                   (atspi.StateType.VISIBLE, atspi.StateType.SHOWING, atspi.StateType.ENABLED)):
            continue
        rect = extents(node, atspi)
        if rect is None:
            continue
        x, y, w, h = rect
        if (0 <= x and x + w <= buffer_width and 0 <= y < 72
                and 8 <= w <= 128 and 8 <= h <= 72 and y + h <= buffer_height
                and x <= pointer_x < x + w and y <= pointer_y < y + h):
            matches.append(rect)
    return matches[0] if len(matches) == 1 else None


def valid(request):
    if not isinstance(request, dict) or type(request.get('pid')) is not int or request['pid'] <= 0:
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
