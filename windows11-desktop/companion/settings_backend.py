"""Local, allowlisted Settings controls. No web services or arbitrary commands."""
import getpass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import dbus
from platform_ui import desktop_status

TOOLS = {
    'display': ['xfce4-display-settings'], 'sound': ['pavucontrol'],
    'network': ['nm-connection-editor'], 'bluetooth': ['blueman-manager'],
    'printers': ['system-config-printer'], 'mouse': ['xfce4-mouse-settings'],
    'keyboard': ['xfce4-keyboard-settings'], 'background': ['xfdesktop-settings'],
    'appearance': ['xfce4-appearance-settings'], 'panel': ['xfce4-panel','--preferences'],
    'notifications': ['xfce4-notifyd-config'], 'power': ['xfce4-power-manager-settings'],
    'apps': ['gnome-software'], 'defaults': ['xfce4-mime-settings'],
    'startup': ['xfce4-session-settings'], 'accounts': ['users-admin'],
    'time': ['time-admin'], 'language': ['gnome-language-selector'],
    'accessibility': ['xfce4-accessibility-settings'], 'lock': ['xfce4-screensaver-preferences'],
    'firewall': ['gufw'], 'updates': ['update-manager'],
    'repositories': ['software-properties-gtk'], 'drivers': ['software-properties-gtk','--open-tab=4'],
    'advanced': ['xfce4-settings-manager'], 'about': ['xfce4-about'],
    'screenshot': ['xfce4-screenshooter'],
}
BOOL_SETTINGS = {
    'dnd': ('xfce4-notifyd','/do-not-disturb'),
    'notificationHistory': ('xfce4-notifyd','/notification-log'),
    'stickyKeys': ('accessibility','/StickyKeys'),
    'slowKeys': ('accessibility','/SlowKeys'),
    'bounceKeys': ('accessibility','/BounceKeys'),
    'mouseKeys': ('accessibility','/MouseKeys'),
    'eventSounds': ('xsettings','/Net/EnableEventSounds'),
}
TIMEOUTS = (0,1,2,3,5,10,15,20,30,45,60,90,120)


def run(args):
    return subprocess.check_output(args,text=True,timeout=4,stderr=subprocess.PIPE).strip()


def properties(channel):
    bus=dbus.SessionBus(private=True)
    try:
        xf=dbus.Interface(bus.get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
        return dict(xf.GetAllProperties(channel,'/'))
    except dbus.DBusException:return {}
    finally:bus.close()


def set_property(channel,key,value):
    bus=dbus.SessionBus(private=True)
    try:
        xf=dbus.Interface(bus.get_object('org.xfce.Xfconf','/org/xfce/Xfconf'),'org.xfce.Xfconf')
        xf.SetProperty(channel,key,value)
    finally:bus.close()


def bluetooth_objects():
    bus=dbus.SystemBus(private=True)
    try:
        manager=dbus.Interface(bus.get_object('org.bluez','/'),'org.freedesktop.DBus.ObjectManager')
        return manager.GetManagedObjects()
    except dbus.DBusException:return {}
    finally:bus.close()


def sound_outputs():
    try:
        sinks=json.loads(run(['pactl','--format=json','list','sinks']))
        return [{'id':s['name'],'name':s['description']} for s in sinks]
    except (OSError,ValueError,subprocess.SubprocessError):return []


def facts():
    def text(path,fallback=''):
        try:return Path(path).read_text().strip()
        except OSError:return fallback
    os_info=platform.freedesktop_os_release()
    memory=next((line.split()[1] for line in text('/proc/meminfo').splitlines() if line.startswith('MemTotal:')),None)
    cpu=next((line.split(':',1)[1].strip() for line in text('/proc/cpuinfo').splitlines() if line.startswith('model name')),platform.machine())
    model=text('/sys/class/dmi/id/product_name')
    if model in ('System Product Name','To Be Filled By O.E.M.','Default string'):model='Desktop PC'
    return {'hostname':platform.node(),'model':model or 'This PC','os':os_info.get('PRETTY_NAME','Linux'),
            'kernel':platform.release(),'architecture':platform.machine(),'cpu':cpu,
            'memory':int(memory)*1024 if memory else None,'account':getpass.getuser(),
            'timezone':text('/etc/timezone', 'Local time'),
            'tools':{key:bool(shutil.which(cmd[0])) for key,cmd in TOOLS.items()}}


def snapshot():
    result=desktop_status()
    from desktop_motion import load
    motion=load();result.update(desktopAnimations=motion['enabled'],desktopAnimationDuration=motion['duration'])
    result['outputs']=sound_outputs()
    try:result['output']=run(['pactl','get-default-sink'])
    except (OSError,subprocess.SubprocessError):result['output']=None
    for channel in {v[0] for v in BOOL_SETTINGS.values()}:
        props=properties(channel)
        for name,(target,key) in BOOL_SETTINGS.items():
            if target==channel:result[name]=bool(props.get(key,False))
    power=properties('xfce4-power-manager')
    result['screenTimeout']=int(power.get('/xfce4-power-manager/blank-on-ac',0))
    result['batteryTimeout']=int(power.get('/xfce4-power-manager/blank-on-battery',0))
    result['batteries']=[]
    for battery in Path('/sys/class/power_supply').glob('*'):
        try:
            if (battery/'type').read_text().strip()=='Battery':
                result['batteries'].append({'percent':int((battery/'capacity').read_text()),'status':(battery/'status').read_text().strip()})
        except (OSError,ValueError):pass
    objects=bluetooth_objects()
    adapters=[v['org.bluez.Adapter1'] for v in objects.values() if 'org.bluez.Adapter1' in v]
    result['bluetoothAvailable']=bool(adapters)
    result['bluetooth']=any(bool(a.get('Powered',False)) for a in adapters)
    result['devices']=[{'name':str(v['org.bluez.Device1'].get('Alias','Bluetooth device')),
                        'connected':bool(v['org.bluez.Device1'].get('Connected',False))}
                       for v in objects.values() if 'org.bluez.Device1' in v and v['org.bluez.Device1'].get('Paired')]
    try:result['wifiAvailable']='wifi' in run(['nmcli','-t','-f','TYPE','device']).splitlines()
    except (OSError,subprocess.SubprocessError):result['wifiAvailable']=False
    usage=shutil.disk_usage('/')
    result['storage']={'total':usage.total,'free':usage.free}
    return result


def apply(name,value):
    if name in ('desktopAnimations','desktopAnimationDuration'):
        from desktop_motion import configure
        configure(name,value)
    elif name in BOOL_SETTINGS:
        if type(value) is not bool:raise ValueError('This control needs an on/off value.')
        set_property(*BOOL_SETTINGS[name],dbus.Boolean(value))
    elif name in ('screenTimeout','batteryTimeout'):
        if type(value) is not int or value not in TIMEOUTS:raise ValueError('Choose a supported timeout.')
        key='/xfce4-power-manager/blank-on-'+('ac' if name=='screenTimeout' else 'battery')
        set_property('xfce4-power-manager',key,dbus.UInt32(value))
    elif name=='volume':
        if type(value) is not int or not 0<=value<=100:raise ValueError('Volume must be between 0 and 100.')
        run(['pactl','set-sink-volume','@DEFAULT_SINK@',str(value)+'%'])
    elif name=='muted':
        if type(value) is not bool:raise ValueError('This control needs an on/off value.')
        run(['pactl','set-sink-mute','@DEFAULT_SINK@','1' if value else '0'])
    elif name=='output':
        if value not in [s['id'] for s in sound_outputs()]:raise ValueError('That sound device is no longer available.')
        previous=run(['pactl','get-default-sink'])
        sinks=json.loads(run(['pactl','--format=json','list','sinks']))
        previous_index=next((s['index'] for s in sinks if s['name']==previous),None)
        streams=json.loads(run(['pactl','--format=json','list','sink-inputs']))
        run(['pactl','set-default-sink',value])
        for stream in streams:
            if previous_index is not None and stream['sink']==previous_index:
                run(['pactl','move-sink-input',str(stream['index']),value])
    elif name=='wifi':
        if type(value) is not bool:raise ValueError('This control needs an on/off value.')
        run(['nmcli','radio','wifi','on' if value else 'off'])
    elif name=='bluetooth':
        if type(value) is not bool:raise ValueError('This control needs an on/off value.')
        adapters=[path for path,v in bluetooth_objects().items() if 'org.bluez.Adapter1' in v]
        if not adapters:raise ValueError('No Bluetooth adapter is available.')
        bus=dbus.SystemBus(private=True)
        try:
            for path in adapters:
                dbus.Interface(bus.get_object('org.bluez',path),'org.freedesktop.DBus.Properties').Set('org.bluez.Adapter1','Powered',dbus.Boolean(value))
        finally:bus.close()
    else:raise ValueError('Unknown setting.')


def launch(tool):
    if tool not in TOOLS:raise ValueError('Unknown settings tool.')
    command=TOOLS[tool]
    if not shutil.which(command[0]):raise ValueError('This settings tool is not installed.')
    subprocess.Popen(command,start_new_session=True)
