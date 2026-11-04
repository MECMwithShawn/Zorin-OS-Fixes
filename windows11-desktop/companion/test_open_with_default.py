#!/usr/bin/python3
"""Open with: the Always tick changes the app a file type opens with."""
import os
import tempfile
from pathlib import Path

home = tempfile.TemporaryDirectory(prefix='zorin11-open-with-')
root = Path(home.name)
os.environ.update(XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'), HOME=str(root))
apps = root/'data/applications'
apps.mkdir(parents=True)
(root/'config').mkdir()
for name in ('first', 'second'):
    (apps/f'{name}.desktop').write_text(f'[Desktop Entry]\nType=Application\nName={name}\nExec=/bin/true %F\nMimeType=text/plain;\n')

from gi.repository import Gio  # noqa: E402
import explorer  # noqa: E402

text = root/'notes.txt'
text.write_text('hello\n')
bare = root/'README'
bare.write_text('hello\n')

assert explorer.always_label(text) == 'Always use this app for .txt files'
assert explorer.always_label(root/'NOTES.TXT'.lower()) == 'Always use this app for .txt files'
assert explorer.always_label(bare).endswith(' files') and '.' not in explorer.always_label(bare)
for name in ('first', 'second'):
    explorer.make_default(Gio.DesktopAppInfo.new(f'{name}.desktop'), text)
    assert Gio.AppInfo.get_default_for_type('text/plain', False).get_id() == f'{name}.desktop'
assert 'text/plain=second.desktop' in (root/'config/mimeapps.list').read_text()
print('PASS Always changes the default and leaves a saved file association')
