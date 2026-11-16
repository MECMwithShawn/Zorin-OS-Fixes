"""Create a launch context for applications opened by the desktop companion."""

import os

import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

from gnome_bridge import active as is_gnome


def _forced_xwayland():
    return (is_gnome() and os.environ.get('XDG_SESSION_TYPE') == 'wayland'
            and os.environ.get('GDK_BACKEND') == 'x11')


def launch_context(timestamp=None):
    context = Gdk.Display.get_default().get_app_launch_context()
    if timestamp is not None:
        context.set_timestamp(timestamp)
    if _forced_xwayland():
        # The companion needs XWayland for placement. Let other applications
        # select their own backend unless their launcher explicitly sets one.
        context.unsetenv('GDK_BACKEND')
    return context


def child_environment():
    if not _forced_xwayland():
        return None
    env = os.environ.copy()
    env.pop('GDK_BACKEND', None)
    return env
