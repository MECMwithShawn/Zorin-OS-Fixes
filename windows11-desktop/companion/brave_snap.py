"""Launch an opted-in browser with native caption accessibility for hover snapping."""

import os
import sys

from gi.repository import Gio
from gnome_bridge import maximize_hover_settings


def main():
    settings = maximize_hover_settings()
    if settings:
        settings.set_boolean('maximize-hover', True)
        Gio.Settings.sync()
    if sys.argv[1:2] == ['--chrome-flatpak']:
        flags = ['--force-renderer-accessibility=basic']
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
            flags.append('--ozone-platform=wayland')
        os.execvp('flatpak', ['flatpak', 'run', '--env=ACCESSIBILITY_ENABLED=1', 'com.google.Chrome',
                             *flags, *sys.argv[2:]])
    os.execvpe('brave-browser',
               ['brave-browser', '--force-renderer-accessibility=basic', *sys.argv[1:]],
               dict(os.environ, ACCESSIBILITY_ENABLED='1'))


if __name__ == '__main__':
    main()
