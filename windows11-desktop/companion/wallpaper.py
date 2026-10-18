"""Opt-in Bing/Spotlight backgrounds, local history, and Xfce integration.

Spotlight v4 protocol reference: ORelio/Spotlight-Downloader, SpotlightAPI.md.
Only image metadata and image assets are requested, never tracking/action URLs.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import urlparse
import dbus
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf
from settings_backend import properties, set_property

CONFIG=Path(os.environ.get('ZORIN11_CONFIG_DIR',str(Path.home()/'.config/zorin11-hub')))
ROOT=CONFIG/'wallpapers'
STATE=CONFIG/'wallpapers.json'
FEEDS={
 'bing':'https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1&mkt=en-US',
 'spotlight':'https://fd.api.iris.microsoft.com/v4/api/selection?placement=88000820&bcnt=4&country=US&locale=en-US&fmt=json',
}


def load():
    default={'source':'current','daily':False,'preferUhd':True,'history':[]}
    try:return dict(default,**json.loads(STATE.read_text()))
    except (OSError,ValueError):return default


def save(state):
    CONFIG.mkdir(parents=True,exist_ok=True)
    temp=STATE.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(STATE)


def configure(key,value):
    if key=='source':
        if value not in ('current','bing','spotlight'):raise ValueError('Choose a supported wallpaper source.')
    elif key in ('daily','preferUhd'):
        if type(value) is not bool:raise ValueError('Expected an on/off value.')
    else:raise ValueError('Unknown wallpaper option.')
    state=load();state[key]=value
    if key=='source':state.pop('lastDay',None)
    save(state)


def allowed_url(url):
    parsed=urlparse(url);host=parsed.hostname or ''
    return parsed.scheme=='https' and parsed.port in (None,443) and not parsed.username and any(host==d or host.endswith('.'+d) for d in ('bing.com','bing.net','microsoft.com','static.microsoft','msn.com','s-msn.com'))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        if not allowed_url(newurl):raise ValueError('The image service redirected to an unsupported host.')
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def fetch(url,limit):
    if not allowed_url(url):raise ValueError('Unsupported image service URL.')
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,image/jpeg,image/png'})
    with urllib.request.build_opener(SafeRedirect).open(request,timeout=18) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('This image exceeds the download limit.')
        return data


def candidates(source,prefer_uhd=True):
    if source not in FEEDS:raise ValueError('Choose Bing or Windows Spotlight first.')
    feed=json.loads(fetch(FEEDS[source],2*1024*1024))
    if source=='bing':
        return [{'url':'https://www.bing.com'+i['urlbase']+('_UHD.jpg' if prefer_uhd else '_1920x1080.jpg'),
                 'fallback':'https://www.bing.com'+i['urlbase']+'_1920x1080.jpg',
                 'title':i.get('title','Bing image of the day'),'credit':i.get('copyright','')}
                 for i in feed.get('images',[]) if i.get('urlbase','').startswith('/th?')]
    result=[]
    for item in feed.get('batchrsp',{}).get('items',[]):
        ad=json.loads(item.get('item','{}')).get('ad',{})
        url=ad.get('landscapeImage',{}).get('asset')
        if url:result.append({'url':url,'title':ad.get('title','Windows Spotlight'),'credit':ad.get('copyright','')})
    return result


def remember(data,metadata):
    if not data.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')):raise ValueError('The service did not return a JPEG or PNG image.')
    loader=GdkPixbuf.PixbufLoader();loader.write(data);loader.close();pixbuf=loader.get_pixbuf()
    width,height=pixbuf.get_width(),pixbuf.get_height()
    if width<800 or height<450 or width*height>80000000:raise ValueError('This image has unsupported dimensions.')
    ident=hashlib.sha256(data).hexdigest()[:24]
    ROOT.mkdir(parents=True,exist_ok=True)
    path=ROOT/(ident+'.image');temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
    entry=dict(metadata,id=ident,width=width,height=height,date=datetime.date.today().isoformat())
    state=load();state['history']=[entry]+[i for i in state['history'] if i['id']!=ident]
    # Bounded local history; do not remove a currently selected background.
    removed=state['history'][60:];state['history']=state['history'][:60]
    save(state)
    for old in removed:
        if old['id']!=state.get('current'): (ROOT/(old['id']+'.image')).unlink(missing_ok=True)
    return entry


def download(source=None):
    state=load();source=source or state['source'];options=candidates(source,state['preferUhd'])
    if not options:raise ValueError('The image service has no picture available right now.')
    seen={i.get('url') for i in state['history']}
    entry=next((i for i in options if i['url'] not in seen),options[0])
    try:data=fetch(entry['url'],30*1024*1024)
    except Exception:
        if not entry.get('fallback') or entry['fallback']==entry['url']:raise
        data=fetch(entry['fallback'],30*1024*1024)
    return remember(data,dict(entry,source=source))


def current_path():
    props=properties('xfce4-desktop')
    values=[str(v) for k,v in props.items() if str(k).endswith('/last-image')]
    values += [str(v) for k,v in props.items() if str(k).endswith('/image-path')]
    return next((Path(p) for p in values if Path(p).is_file()),None)


def image_path(ident):
    if ident=='current':return current_path()
    if not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Unknown wallpaper.')
    if not any(i['id']==ident for i in load()['history']):raise ValueError('This picture is no longer in history.')
    return ROOT/(ident+'.image')


def thumbnail(ident):
    path=image_path(ident)
    if not path:raise ValueError('No background image is configured.')
    picture=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),720,405,True)
    return bytes(picture.save_to_bufferv('jpeg',['quality'],['85'])[1])


def apply(ident):
    path=image_path(ident)
    if not path or not path.is_file():raise ValueError('This wallpaper is unavailable.')
    props=properties('xfce4-desktop')
    keys={str(k) for k in props if str(k).endswith(('/last-image','/image-path'))}
    # Xfdesktop and xfce4-screensaver share these monitor/workspace backgrounds.
    monitors=[]
    try:
        output=subprocess.check_output(['xrandr','--current'],text=True,timeout=4)
        monitors=re.findall(r'^(\S+) connected',output,re.M)
    except (OSError,subprocess.SubprocessError):pass
    count=int(properties('xfwm4').get('/general/workspace_count',1))
    for monitor in monitors or ['0']:
        for workspace in range(min(32,max(1,count))):
            keys.add(f'/backdrop/screen0/monitor{monitor}/workspace{workspace}/last-image')
    state=load();backup=state.setdefault('original',{})
    for key in sorted(keys):
        if key not in backup:backup[key]=str(props[key]) if key in props else None
    # Keep both paths recoverable if the desktop service fails partway through.
    state['appliedPaths']=list({str(path),state.get('appliedPath','')} - {''})
    save(state)  # Persist recovery before changing the desktop.
    for key in sorted(keys):set_property('xfce4-desktop',key,dbus.String(str(path)))
    state.pop('appliedPaths',None)
    state['current']=ident;state['appliedPath']=str(path);state['lastDay']=datetime.date.today().isoformat();state['error']='';save(state)


def restore():
    state=load()
    if not state.get('original'):
        state.update(source='current',daily=False);save(state);return
    props=properties('xfce4-desktop');bus=dbus.SessionBus(private=True)
    managed=set(state.get('appliedPaths',[]))|{state.get('appliedPath')}
    try:
        xf=dbus.Interface(bus.get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
        for key,value in state.get('original',{}).items():
            if str(props.get(key,'')) not in managed:continue
            if value is None:xf.ResetProperty('xfce4-desktop',key,False)
            else:xf.SetProperty('xfce4-desktop',key,dbus.String(value))
    finally:bus.close()
    state.update(source='current',daily=False);state.pop('current',None);state.pop('appliedPath',None);state.pop('original',None);state.pop('appliedPaths',None);save(state)


def due():
    state=load()
    return state['daily'] and state['source'] in FEEDS and state.get('lastDay')!=datetime.date.today().isoformat() and time.time()-state.get('lastAttempt',0)>3600


def update():
    state=load();state['lastAttempt']=time.time();save(state)
    try:
        entry=download();apply(entry['id']);return entry
    except Exception as error:
        state=load();state['error']=str(error);save(state);raise


def status():
    state=load();state.pop('original',None);state.pop('appliedPath',None);state.pop('appliedPaths',None)
    state['hasPreview']=current_path() is not None
    state['lockFollowsDesktop']=bool(shutil.which('xfce4-screensaver'))
    return state

