"""On-demand local filename search; no document index or content collection."""
from collections import deque
import json
import os
from pathlib import Path
import time
import unicodedata

CATALOG = json.loads(Path(__file__).with_name('settings_catalog.json').read_text())
EXCLUDED = {'node_modules','__pycache__','venv','env','target','build','dist','$RECYCLE.BIN','System Volume Information'}


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))


def score(name, terms, query):
    name, terms = normalized(name), normalized(terms)
    if not all(t in name+' '+terms for t in query.split()):return None
    return 0 if name == query else 1 if name.startswith(query) else 2 if query in name else 3


def search(query, apps, roots, cancelled, *, max_entries=25000, seconds=1.5, limit=80):
    query = normalized(query.strip()[:160])
    matches=[]
    def add(item, terms=''):
        rank=score(item['name'],terms,query)
        if rank is not None:matches.append((rank,item))
    if not query:return dict(results=[],limited=False,scope=[str(p) for p in roots])
    for app in apps:
        add(dict(app,kind='app',key='app:'+app['id']),app.get('description',''))
    for ident,title,*_ in CATALOG['sections']+CATALOG['subpages']:
        add(dict(kind='setting',key='setting:'+ident,id=ident,name=title,description='Settings'),CATALOG['terms'].get(ident,''))
    deadline=time.monotonic()+seconds;seen=set();count=0;limited=False
    queue=deque((Path(root),0) for root in roots)
    # A one-character query still searches apps/settings, but avoids a broad file scan.
    while queue and len(query)>=2 and not cancelled.is_set():
        directory,depth=queue.popleft()
        try:
            real=directory.resolve()
            if real in seen:continue
            seen.add(real)
            with os.scandir(directory) as entries:
                for entry in entries:
                    if cancelled.is_set():return dict(results=[],limited=False,scope=[])
                    count+=1
                    if count>max_entries or time.monotonic()>deadline:
                        limited=True;queue.clear();break
                    if entry.name.startswith('.') or entry.name in EXCLUDED or entry.is_symlink():continue
                    folder=entry.is_dir(follow_symlinks=False)
                    if not folder and not entry.is_file(follow_symlinks=False):continue
                    if score(entry.name,'',query) is not None:
                        info=entry.stat(follow_symlinks=False)
                        add(dict(kind='folder' if folder else 'file',key='path:'+entry.path,path=entry.path,
                                 name=entry.name,description=str(directory),folder=folder,size=info.st_size,
                                 modified=info.st_mtime))
                    if folder:
                        if depth<16:queue.append((Path(entry.path),depth+1))
                        else:limited=True
        except (OSError,ValueError):continue
    matches.sort(key=lambda pair:(pair[0],{'app':0,'setting':1,'folder':2,'file':3}[pair[1]['kind']],pair[1]['name'].casefold(),pair[1]['key']))
    # Limit each category separately so many files cannot displace apps/settings.
    results=[];counts={}
    for _,item in matches:
        kind=item['kind'];counts[kind]=counts.get(kind,0)+1
        if counts[kind]<=limit:results.append(item)
        else:limited=True
    return dict(results=results,limited=limited,scope=[str(p) for p in roots],filesNeedMore=len(query)<2)
