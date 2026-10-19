"""GNOME wallpaper journal and the installed Zorin wallpaper collection."""
import hashlib
from pathlib import Path
from urllib.parse import urlparse, unquote
from gi.repository import Gio


def catalog():
    result=[]
    for root in (Path('/usr/share/backgrounds'),Path('/usr/share/wallpapers')):
        if not root.exists():continue
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in ('.jpg','.jpeg','.png','.svg','.webp'):continue
            result.append(dict(id='zorin-'+hashlib.sha256(str(path).encode()).hexdigest()[:20],
                               title=path.stem.replace('-',' '),path=str(path),source='Zorin'))
    return result


def resolve(ident):
    entry=next((e for e in catalog() if e['id']==ident),None)
    if not entry:raise ValueError('This Zorin wallpaper is no longer installed.')
    return Path(entry['path'])


def current_path():
    s=Gio.Settings.new('org.gnome.desktop.background')
    dark=Gio.Settings.new('org.gnome.desktop.interface').get_string('color-scheme')=='prefer-dark'
    uri=s.get_string('picture-uri-dark' if dark else 'picture-uri')
    parsed=urlparse(uri)
    path=Path(unquote(parsed.path)) if parsed.scheme=='file' else None
    return path if path and path.is_file() else None


def apply_path(path):
    import wallpaper
    settings=Gio.Settings.new('org.gnome.desktop.background')
    state=wallpaper.load();records=state.setdefault('gnomeOriginal',{})
    changes={'picture-uri':Path(path).as_uri(),'picture-uri-dark':Path(path).as_uri(),'picture-options':'zoom'}
    for key,new in changes.items():
        record=records.setdefault(key,{'before':settings.get_string(key)})
        record['previous']=record.get('after');record['after']=new
    wallpaper.save(state)
    for key,new in changes.items():
        if not settings.set_string(key,new):raise RuntimeError('GNOME rejected the wallpaper setting: '+key)
    Gio.Settings.sync()


def apply(ident):
    import wallpaper,datetime
    path=wallpaper.image_path(ident)
    if not path or not path.is_file():raise ValueError('This wallpaper is unavailable.')
    import desktop_backgrounds
    if desktop_backgrounds.CONTEXT and wallpaper.load().get('desktopPictures'):sync(shared=str(path))
    else:apply_path(path)
    state=wallpaper.load();state.update(current=ident,appliedPath=str(path),lastDay=datetime.date.today().isoformat(),error='')
    wallpaper.save(state)


def restore():
    import wallpaper
    settings=Gio.Settings.new('org.gnome.desktop.background');state=wallpaper.load()
    for key,record in state.get('gnomeOriginal',{}).items():
        if settings.get_string(key) in (record.get('after'),record.get('previous')):
            if not settings.set_string(key,record['before']):raise RuntimeError('Cannot restore wallpaper: '+key)
    Gio.Settings.sync()
    for key in ('gnomeOriginal','current','appliedPath','desktopPictures','desktopShared','gnomeShared','gnomeDesktopManaged'):state.pop(key,None)
    state.update(source='current',daily=False);wallpaper.save(state)


def sync(shared=None):
    import wallpaper,desktop_backgrounds
    context=desktop_backgrounds.CONTEXT
    if not context:return
    state=wallpaper.load();pictures=state.get('desktopPictures',{})
    if not pictures and not state.get('gnomeDesktopManaged'):return context['uid']
    if shared:state['gnomeShared']=shared
    if not state.get('gnomeShared'):
        current=current_path()
        if current:state['gnomeShared']=str(current)
    state['gnomeDesktopManaged']=bool(pictures);wallpaper.save(state)
    ident=pictures.get(context['uid'])
    path=wallpaper.image_path(ident) if ident else Path(state['gnomeShared']) if state.get('gnomeShared') else None
    if path and path.is_file():apply_path(path)
    return context['uid']
