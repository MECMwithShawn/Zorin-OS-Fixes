"""Hardware-backed flyout controls, with no gamma or root-shell fallback."""
import os
from pathlib import Path
import dbus
import settings_backend

BACKLIGHT=Path('/sys/class/backlight')
TILES=('wifi','bluetooth','dnd','accessibility','screenshot','display')

def validate_tiles(value):
    if not isinstance(value,list) or not value or len(value)>len(TILES) or any(type(i) is not str or i not in TILES for i in value) or len(set(value))!=len(value):
        raise ValueError('Choose at least one unique supported tile.')
    return value

def backlights():
    result=[]
    for device in sorted(BACKLIGHT.glob('*')):
        try:
            maximum=int((device/'max_brightness').read_text());current=int((device/'brightness').read_text())
            if maximum>0:result.append({'id':device.name,'value':max(1,min(100,round(current/maximum*100))),'maximum':maximum})
        except (OSError,ValueError):continue
    return result

def login_session(bus):
    manager=dbus.Interface(bus.get_object('org.freedesktop.login1','/org/freedesktop/login1'),'org.freedesktop.login1.Manager')
    try:path=manager.GetSessionByPID(os.getpid(),timeout=3)
    except dbus.DBusException:
        session=os.environ.get('XDG_SESSION_ID')
        if not session:raise ValueError('Brightness requires an active local desktop session.')
        path=manager.GetSession(session,timeout=3)
    obj=bus.get_object('org.freedesktop.login1',path)
    info=dbus.Interface(obj,'org.freedesktop.DBus.Properties').GetAll('org.freedesktop.login1.Session',timeout=3)
    if int(info['User'][0])!=os.getuid() or not info['Active'] or info['Remote']:
        raise ValueError('Brightness requires your active local desktop session.')
    return obj

def brightness(ident,value):
    if type(value) is not int or not 1<=value<=100:raise ValueError('Brightness must be between 1 and 100 percent.')
    device=next((d for d in backlights() if d['id']==ident),None)
    if not device:raise ValueError('This display no longer supports brightness control.')
    bus=dbus.SystemBus(private=True)
    try:
        session=login_session(bus)
        dbus.Interface(session,'org.freedesktop.login1.Session').SetBrightness('backlight',ident,dbus.UInt32(max(1,round(device['maximum']*value/100))),timeout=4)
    finally:bus.close()

def snapshot():
    data=settings_backend.snapshot()
    data['backlights']=[{'id':d['id'],'value':d['value']} for d in backlights()]
    return data
