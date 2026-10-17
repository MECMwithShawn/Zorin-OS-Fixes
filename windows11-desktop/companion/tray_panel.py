#!/usr/bin/python3
"""Small, local Genmon renderer for the full-size Fluent status pair."""
from html import escape
import json
import shlex
from pathlib import Path

BASE=Path(__file__).resolve().parent
try:state=json.loads((Path.home()/'.config/zorin11-hub/tray-status.json').read_text())
except (FileNotFoundError,ValueError):state={}
network=state.get('networkType','offline')
if network not in ('wifi','wired','offline'):network='offline'
muted=int(bool(state.get('muted',False)))
icon=BASE/f'tray-{network}-{muted}.svg'
command=shlex.join(['/usr/bin/python3',str(BASE/'app.py'),'--quick-settings'])
label='Quick settings — '+{'wifi':'Wi-Fi','wired':'Ethernet','offline':'Offline'}[network]
label+=' · Muted' if muted else ' · Volume '+str(state.get('volume','—'))+'%'
print(f'<img>{icon}</img><click>{command}</click><tool>{escape(label)}</tool>')
