"""Copy local paths (or remote URIs) from the GNOME Files context menu."""
import gi
gi.require_version('Nautilus','4.0')
gi.require_version('Gdk','4.0')
from gi.repository import Gdk,GObject,Nautilus


def location_text(files):
    locations=[f.get_location() for f in files]
    return '\n'.join(location.get_path() or location.get_uri() for location in locations if location)


class Zorin11CopyPath(GObject.GObject,Nautilus.MenuProvider):
    def _copy(self,item,text):
        display=Gdk.Display.get_default()
        if display:
            provider=Gdk.ContentProvider.new_for_value(GObject.Value(GObject.TYPE_STRING,text))
            display.get_clipboard().set_content(provider)

    def _items(self,files,background=False):
        text=location_text(files)
        if not text:return []
        label='Copy folder path' if background else 'Copy full path' if len(files)==1 else 'Copy full paths'
        item=Nautilus.MenuItem(name='Zorin11::CopyFullPath',label=label,icon='edit-copy-symbolic')
        item.connect('activate',self._copy,text)
        return [item]

    def get_file_items(self,files):return self._items(files)
    def get_background_items(self,folder):return self._items([folder],background=True)
