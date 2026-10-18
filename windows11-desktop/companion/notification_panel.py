#!/usr/bin/python3
"""Small notification-center launcher with a real unread/DND indicator."""
from html import escape
import json
import os
from pathlib import Path
import shlex
BASE=Path(__file__).resolve().parent
CONFIG=Path(os.environ.get('ZORIN11_CONFIG_DIR',str(Path.home()/'.config/zorin11-hub')))
try:state=json.loads((CONFIG/'notification-status.json').read_text())
except (OSError,ValueError):state={}
icon=BASE/('fluent/alert-off.svg' if state.get('dnd') else 'notification-unread.svg' if state.get('unread') else 'fluent/alert.svg')
command=shlex.join(['/usr/bin/python3',str(BASE/'app.py'),'--notifications'])
label='Notification center'+(' — Do not disturb on' if state.get('dnd') else ' — Unread notifications' if state.get('unread') else '')
print(f'<img>{icon}</img><click>{command}</click><tool>{escape(label)}</tool>')
