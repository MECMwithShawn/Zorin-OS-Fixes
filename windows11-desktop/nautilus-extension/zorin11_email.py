"""Email files with Axentra Outlook from the GNOME Files context menu."""
import shutil
import subprocess
from pathlib import Path
import gi
gi.require_version('Nautilus','4.0')
from gi.repository import GObject,Nautilus


def file_paths(files):
    """Local regular files only; folders and remote locations can't be attached."""
    paths=[f.get_location().get_path() for f in files if not f.is_directory() and f.get_location()]
    return [p for p in paths if p and Path(p).is_file()]


def command(paths):
    names=', '.join(Path(p).name for p in paths)
    args=['axentra-outlook','--compose','--subject',f'Emailing: {names}']
    for p in paths:args+=['--attach',p]
    return args


class Zorin11Email(GObject.GObject,Nautilus.MenuProvider):
    def _email(self,item,paths):
        subprocess.Popen(command(paths),start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def get_file_items(self,files):
        paths=file_paths(files)
        if not paths or not shutil.which('axentra-outlook'):return []
        item=Nautilus.MenuItem(name='Zorin11::Email',label='Email',icon='mail-send-symbolic',
                               tip='Attach to a new message in Axentra Outlook')
        item.connect('activate',self._email,paths)
        return [item]
