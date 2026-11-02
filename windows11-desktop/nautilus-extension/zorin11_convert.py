"""Convert pictures to PNG or JPG from the GNOME Files context menu.

Copies are saved beside the originals by the companion's image_convert.py.
"""
import subprocess
from pathlib import Path
import gi
gi.require_version('Nautilus','4.0')
from gi.repository import GObject,Nautilus

CONVERTER=Path.home()/'.local/share/zorin11-hub/image_convert.py'
PICTURES={'.jpg','.jpeg','.png','.webp','.gif','.bmp','.tif','.tiff','.heic','.heif'}
FORMATS=(('png','PNG',{'.png'}),('jpg','JPG',{'.jpg','.jpeg'}))


def picture_paths(files):
    """Local picture files only; folders and remote locations are skipped."""
    paths=[f.get_location().get_path() for f in files if not f.is_directory() and f.get_location()]
    return [p for p in paths if p and Path(p).suffix.lower() in PICTURES and Path(p).is_file()]


def command(fmt,paths):
    return ['/usr/bin/python3',str(CONVERTER),fmt,*paths]


class Zorin11Convert(GObject.GObject,Nautilus.MenuProvider):
    def _convert(self,item,fmt,paths):
        subprocess.Popen(command(fmt,paths),start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def get_file_items(self,files):
        paths=picture_paths(files)
        if not paths or not CONVERTER.is_file():return []
        top=Nautilus.MenuItem(name='Zorin11::Convert',label='Convert to',icon='image-x-generic-symbolic',
                              tip='Save a copy in another picture format')
        submenu=Nautilus.Menu();top.set_submenu(submenu)
        for fmt,label,same in FORMATS:
            chosen=[p for p in paths if Path(p).suffix.lower() not in same]
            if not chosen:continue
            item=Nautilus.MenuItem(name=f'Zorin11::Convert::{fmt}',label=label,tip=f'Save a {label} copy beside each picture')
            item.connect('activate',self._convert,fmt,chosen)
            submenu.append_item(item)
        return [top] if submenu.get_items() else []
