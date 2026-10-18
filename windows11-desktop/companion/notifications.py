"""Use Xfce's existing notification log; never run actions from logged text."""
from html.parser import HTMLParser
import dbus
import json
from settings_backend import properties

SERVICE='org.xfce.Notifyd'
PATH='/org/xfce/Notifyd'
INTERFACE='org.xfce.Notifyd.Log'

class PlainText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):self.parts.append(data)
    def handle_starttag(self,tag,attrs):
        if tag in ('br','p','div'):self.parts.append('\n')

def plain(value):
    parser=PlainText()
    parser.feed(str(value)[:20000]);parser.close()
    return ''.join(parser.parts).strip()

def call(method,*args):
    bus=dbus.SessionBus(private=True)
    try:
        proxy=dbus.Interface(bus.get_object(SERVICE,PATH),INTERFACE)
        return getattr(proxy,method)(*args,timeout=4)
    finally:bus.close()

def snapshot():
    config=properties('xfce4-notifyd')
    result={'loading':False,'entries':[],'available':False,'logging':bool(config.get('/notification-log',False)),
            'dnd':bool(config.get('/do-not-disturb',False)),'hasMore':False}
    try:
        rows=call('List','',dbus.UInt32(201),False)
        result['available']=True;result['hasMore']=len(rows)>200
        for row in rows[:200]:
            if len(row)!=11:continue
            ident,timestamp,zone,app_id,app_name,icon,summary,body,actions,timeout,read=row
            result['entries'].append({'id':str(ident),'time':int(timestamp)//1000,'appId':str(app_id),
                'app':plain(app_name or app_id or 'Notification'),'title':plain(summary),
                'body':plain(body),'read':bool(read)})
    except dbus.DBusException:pass
    return result

def change(action,ids=None):
    if action=='clear':return call('Clear')
    if action not in ('dismiss','read'):raise ValueError('Unknown notification action.')
    if not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(i,str) or not i or len(i)>200 for i in ids):
        raise ValueError('Select valid notifications.')
    # Validate against the daemon, not paths or commands in a notification body.
    for ident in ids:call('Get',ident)
    return call('Delete' if action=='dismiss' else 'MarkRead',dbus.Array(ids,signature='s'))


def has_unread():
    try:return bool(call('HasUnread'))
    except dbus.DBusException:return False


def write_badge(config,status):
    path=config/'notification-status.json'
    text=json.dumps({'unread':bool(status.get('unread',False)),'dnd':bool(status.get('dnd',False))})
    try:
        if path.read_text()==text:return
    except OSError:pass
    config.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(text);temporary.replace(path)
