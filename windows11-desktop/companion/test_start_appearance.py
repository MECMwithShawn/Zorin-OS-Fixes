import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ['GSETTINGS_BACKEND'] = 'memory'
import app
from gi.repository import GdkPixbuf, Gio
from start_preferences import Preferences


class StartAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        schemas = self.root/'schemas'
        shutil.copytree(Path(__file__).parents[1]/'gnome-extension/schemas', schemas)
        subprocess.run(['glib-compile-schemas', str(schemas)], check=True)
        for name, value in (('EXTENSION_SCHEMAS', schemas), ('CONFIG', self.root/'config'),
                            ('CUSTOM_START_BUTTON', self.root/'config/start-button-custom.png')):
            patcher = patch.object(app, name, value); patcher.start(); self.addCleanup(patcher.stop)
        self.hub = SimpleNamespace(start_preferences=Preferences(self.root/'prefs.json', []))
        self.hub.start_button_file = lambda: app.Hub.start_button_file(self.hub)
        self.settings = Gio.Settings.new_full(Gio.SettingsSchemaSource.new_from_directory(
            str(schemas), Gio.SettingsSchemaSource.get_default(), False).lookup('org.gnome.shell.extensions.zorin11', False), None, None)
        # The memory backend is shared by every test in this process.
        self.settings.reset('start-button')

    def choose(self, button):
        self.hub.start_preferences.change('button', value=button)
        with patch.object(app, 'is_gnome', return_value=True):
            app.Hub.apply_start_button(self.hub)
        return self.settings.get_string('start-button')

    def test_buttons_map_to_bundled_files_and_default_is_empty(self):
        self.assertEqual(self.choose('orb'), str(app.BASE/'start-buttons/orb.svg'))
        self.assertTrue(Path(self.choose('windows10')).is_file())
        self.assertEqual(self.choose('windows11'), '')
        self.assertEqual(self.choose('custom'), '', 'Custom without a saved picture keeps the default')

    def test_custom_picture_is_converted_and_bad_files_are_rejected(self):
        app.Hub.save_custom_start_button(self.hub, app.BASE/'start-buttons/orb.svg')
        _, width, height = GdkPixbuf.Pixbuf.get_file_info(str(app.CUSTOM_START_BUTTON))
        self.assertEqual(max(width, height), 64)
        self.assertEqual(self.choose('custom'), str(app.CUSTOM_START_BUTTON))
        text = self.root/'notes.txt'; text.write_text('not an image')
        for path in (text, self.root/'missing.png'):
            with self.assertRaises(ValueError): app.Hub.save_custom_start_button(self.hub, path)
        self.assertEqual(max(GdkPixbuf.Pixbuf.get_file_info(str(app.CUSTOM_START_BUTTON))[1:]), 64, 'A failed choice keeps the old picture')

    def test_xfce_and_old_schemas_are_left_alone(self):
        self.hub.start_preferences.change('button', value='orb')
        with patch.object(app, 'is_gnome', return_value=False):
            app.Hub.apply_start_button(self.hub)
        self.assertEqual(self.settings.get_string('start-button'), '')
        with patch.object(app, 'EXTENSION_SCHEMAS', self.root/'missing'), patch.object(app, 'is_gnome', return_value=True):
            app.Hub.apply_start_button(self.hub)

    def test_preview_resource_serves_only_known_buttons(self):
        served = []
        def fetch(name):
            request = SimpleNamespace(get_uri=lambda: 'zorin11://start-button/'+name,
                                      finish=lambda stream, length, mime: served.append((length, mime)))
            app.Hub.resource(self.hub, request)
            return served[-1]
        self.assertEqual(fetch('orb')[1], 'image/svg+xml')
        self.assertEqual(fetch('windows11')[1], 'image/svg+xml')
        self.assertEqual(fetch('../start_preferences.py'), (0, 'text/plain'))
        self.assertEqual(fetch('custom'), (0, 'text/plain'), 'No custom picture saved yet')
        app.Hub.save_custom_start_button(self.hub, app.BASE/'start-buttons/orb.svg')
        self.assertEqual(fetch('custom')[1], 'image/png')


if __name__ == '__main__':
    unittest.main()
