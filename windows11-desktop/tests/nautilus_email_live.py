"""Actual Nautilus MenuProvider Email item with a stand-in axentra-outlook, isolated display."""
import sys,os,subprocess,json,tempfile,time
from pathlib import Path
if '--private' not in sys.argv:
    raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--private'],env=dict(os.environ,GDK_BACKEND='x11'),timeout=20).returncode)
import gi
from gi.repository import Gio
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nautilus-extension'))
from zorin11_email import Zorin11Email
from types import SimpleNamespace as NS
temp=Path(tempfile.mkdtemp());(temp/'bin').mkdir();(temp/'docs').mkdir()
doc=temp/'docs/Quarterly report.docx';doc.write_bytes(b'x');pic=temp/'docs/été.png';pic.write_bytes(b'x')
log=temp/'args.json';fake=temp/'bin/axentra-outlook'
fake.write_text(f'#!/usr/bin/python3\nimport json,sys\nopen({str(log)!r},"w").write(json.dumps(sys.argv[1:]))\n');fake.chmod(0o755)
file=lambda p:NS(get_location=lambda:Gio.File.new_for_path(str(p)),is_directory=lambda:Path(p).is_dir())
remote=NS(get_location=lambda:Gio.File.new_for_uri('smb://server/share/a.pdf'),is_directory=lambda:False)
provider=Zorin11Email()
os.environ['PATH']=str(temp/'empty')
assert provider.get_file_items([file(doc)])==[], 'hidden without Axentra Outlook'
os.environ['PATH']=f"{temp/'bin'}:/usr/bin:/bin"
assert provider.get_file_items([file(temp/'docs'),remote])==[], 'folders and remote files cannot be attached'
items=provider.get_file_items([file(doc),file(temp/'docs'),file(pic)])
assert [i.props.label for i in items]==['Email'],items
items[0].emit('activate')
for _ in range(50):
    if log.exists():break
    time.sleep(.1)
assert json.loads(log.read_text())==['--compose','--subject','Emailing: Quarterly report.docx, été.png','--attach',str(doc),'--attach',str(pic)]
print('PASS real Nautilus Email item: files only, folder/remote skipped, hidden without Outlook, compose args')
