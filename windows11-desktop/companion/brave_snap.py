"""Launch Brave with the native caption accessibility needed for hover snapping."""

import os
from pathlib import Path
import sys

from gi.repository import Gio


def main():
    schemas = Path.home() / '.local/share/gnome-shell/extensions/zorin11@zorin-os-fixes/schemas'
    if (schemas / 'gschemas.compiled').is_file():
        source = Gio.SettingsSchemaSource.new_from_directory(
            str(schemas), Gio.SettingsSchemaSource.get_default(), False)
        schema = source.lookup('org.gnome.shell.extensions.zorin11', True)
        if schema and schema.has_key('maximize-hover'):
            settings = Gio.Settings.new_full(schema, None, None)
            settings.set_boolean('maximize-hover', True)
            Gio.Settings.sync()
    os.execvpe('brave-browser',
               ['brave-browser', '--force-renderer-accessibility=basic', *sys.argv[1:]],
               dict(os.environ, ACCESSIBILITY_ENABLED='1'))


if __name__ == '__main__':
    main()
