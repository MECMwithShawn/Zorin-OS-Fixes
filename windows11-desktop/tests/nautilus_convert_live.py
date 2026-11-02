"""Actual Nautilus MenuProvider Convert to submenu with the real converter, isolated display."""
import sys,os,subprocess,tempfile,time
from pathlib import Path
if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--private'],env=dict(os.environ,GDK_BACKEND='x11'),timeout=60).returncode)
import gi
from gi.repository import Gio
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'nautilus-extension'))
import zorin11_convert
from zorin11_convert import Zorin11Convert
from types import SimpleNamespace as NS
temp=Path(tempfile.mkdtemp());(temp/'docs').mkdir()
heic=temp/'docs/IMG 0001.HEIC';heic.write_bytes((root/'companion/test-fixtures/portrait.heic').read_bytes())
png=temp/'docs/été.png'
from PIL import Image;Image.new('RGB',(2,2),'red').save(png)
doc=temp/'docs/notes.txt';doc.write_text('x')
file=lambda p:NS(get_location=lambda:Gio.File.new_for_path(str(p)),is_directory=lambda:Path(p).is_dir())
remote=NS(get_location=lambda:Gio.File.new_for_uri('smb://server/share/a.heic'),is_directory=lambda:False)
provider=Zorin11Convert()
zorin11_convert.CONVERTER=temp/'missing.py'
assert provider.get_file_items([file(heic)])==[], 'hidden without the companion converter'
zorin11_convert.CONVERTER=root/'companion/image_convert.py'
assert provider.get_file_items([file(temp/'docs'),file(doc),remote])==[], 'folders, other files and remote locations are skipped'
labels=lambda items:[i.props.label for i in items[0].props.menu.get_items()]
assert labels(provider.get_file_items([file(png)]))==['JPG'], 'no PNG choice for a PNG'
items=provider.get_file_items([file(heic),file(doc),file(png)])
assert [i.props.label for i in items]==['Convert to'] and labels(items)==['PNG','JPG'],items
png_item,jpg_item=items[0].props.menu.get_items()
png_item.emit('activate');jpg_item.emit('activate')
expected=[temp/'docs/IMG 0001.png',temp/'docs/IMG 0001.jpg',temp/'docs/été.jpg']
for _ in range(100):
    if all(p.exists() and p.stat().st_size for p in expected):break
    time.sleep(.1)
time.sleep(.3)
assert Image.open(expected[0]).size==(160,320) and Image.open(expected[1]).format=='JPEG' and Image.open(expected[2]).format=='JPEG'
assert not (temp/'docs/été (2).png').exists(), 'a PNG is not converted to PNG again'
print('PASS real Nautilus Convert to submenu: pictures only, PNG/JPG choices per selection, hidden without converter, copies saved beside originals')
