"""Real WebKit -> Hub -> native D-Bus/GDM, on private display and buses.

The receiving session, login and GDM services record requests; they cannot
lock, suspend, switch or end the host session. GDM uses the host's read-only
seat metadata, so run this integration check from a graphical GDM session.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

if '--private' not in sys.argv:
    env=dict(os.environ,GDK_BACKEND='x11',GTK_USE_PORTAL='0',XDG_CURRENT_DESKTOP='GNOME')
    env['ZORIN11_HOST_BUS']=env.get('DBUS_SESSION_BUS_ADDRESS','')
    result=subprocess.run(['xvfb-run','-a','dbus-run-session','--','/usr/bin/python3',__file__,'--private'],env=env,timeout=40)
    raise SystemExit(result.returncode)

address=os.environ['DBUS_SESSION_BUS_ADDRESS']
assert address and address!=os.environ.get('ZORIN11_HOST_BUS')
os.environ['DBUS_SYSTEM_BUS_ADDRESS']=address

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)
import gi
gi.require_version('Gtk','3.0')
gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,WebKit2,GLib
import app

records=[];errors=[];denied=False
bus=dbus.SessionBus()
names=[dbus.service.BusName(name,bus) for name in ['org.gnome.ScreenSaver','org.gnome.SessionManager','org.freedesktop.login1','org.gnome.DisplayManager']]

class ScreenSaver(dbus.service.Object):
    @dbus.service.method('org.gnome.ScreenSaver',in_signature='',out_signature='')
    def Lock(self):records.append(('Lock',[]))

class Session(dbus.service.Object):
    @dbus.service.method('org.gnome.SessionManager',in_signature='u',out_signature='')
    def Logout(self,mode):records.append(('Logout',[int(mode)]))
    @dbus.service.method('org.gnome.SessionManager',in_signature='',out_signature='')
    def Shutdown(self):records.append(('Shutdown',[]))
    @dbus.service.method('org.gnome.SessionManager',in_signature='',out_signature='')
    def Reboot(self):records.append(('Reboot',[]))

class Login(dbus.service.Object):
    @dbus.service.method('org.freedesktop.login1.Manager',in_signature='b',out_signature='')
    def Suspend(self,interactive):
        records.append(('Suspend',[bool(interactive)]))
        if denied:raise dbus.exceptions.DBusException('Test sleep inhibitor',name='org.freedesktop.login1.OperationInhibited')
    @dbus.service.method('org.freedesktop.login1.Manager',in_signature='ss',out_signature='')
    def ActivateSessionOnSeat(self,session,seat):records.append(('GDM',[str(session),str(seat)]))

class DisplayFactory(dbus.service.Object):
    @dbus.service.method('org.gnome.DisplayManager.LocalDisplayFactory',in_signature='',out_signature='o')
    def CreateTransientDisplay(self):
        records.append(('GDM',[]))
        return '/org/gnome/DisplayManager/Displays/Test'

services=[ScreenSaver(bus,'/org/gnome/ScreenSaver'),Session(bus,'/org/gnome/SessionManager'),
          Login(bus,'/org/freedesktop/login1'),DisplayFactory(bus,'/org/gnome/DisplayManager/LocalDisplayFactory')]
pool=ThreadPoolExecutor(2)
content=WebKit2.UserContentManager()
content.register_script_message_handler('desktop')
web=WebKit2.WebView.new_with_user_content_manager(content)
window=Gtk.Window();window.set_default_size(832,864);window.add(web);window.show_all()
ready=threading.Event();completed=threading.Event();outcome=[]

def js(code):
    GLib.idle_add(lambda:(web.evaluate_javascript(code,-1,None,None,None,None,None),False)[1])

def send(message):js('window.receive('+json.dumps(message)+')')

def background(task,success,failure):
    def work():
        try:task();GLib.idle_add(lambda:(success(None),False)[1])
        except Exception as error:
            errors.append(str(error))
            GLib.idle_add(lambda value=str(error):(failure(value),False)[1])
        finally:completed.set()
    pool.submit(work)

hub=SimpleNamespace(start=SimpleNamespace(hide=lambda:None,send=send),background=background,
                    show_start=lambda:None,open_settings=lambda page:records.append(('Settings',[page])))
surface=SimpleNamespace(mode='start')

def message(_manager,result):
    data=json.loads(result.get_js_value().to_string())
    if data['action']=='ready':
        send({'type':'state','data':{'mode':'start','user':'Test','apps':[],'pins':[],'recent':[],'places':[],'groups':[],'groupsVisible':False}})
        ready.set()
    else:app.Hub.dispatch(hub,surface,data)

content.connect('script-message-received::desktop',message)
web.load_uri((Path(__file__).parent/'dist/index.html').resolve().as_uri())

def click(menu,label):
    js('document.querySelector('+json.dumps('[aria-label="'+menu+' options"]')+').click()')
    time.sleep(.2)
    js('[...document.querySelectorAll(".session-menu button")].find(b=>b.textContent==='+json.dumps(label)+').click()')

def verify():
    global denied
    try:
        assert ready.wait(8),'WebKit did not load'
        time.sleep(.4)
        for menu,label,expected in [('Account','Lock',[('Lock',[])]),('Account','Switch user',None),
                                    ('Account','Sign out',[('Logout',[0])]),('Power','Sleep',[('Suspend',[True])]),
                                    ('Power','Shut down',[('Shutdown',[])]),('Power','Restart',[('Reboot',[])])]:
            records.clear();completed.clear();click(menu,label)
            assert completed.wait(6),(label,'No backend completion')
            assert not errors,(label,errors)
            if expected is None:
                assert [r[0] for r in records]==['Lock','GDM'],records
            else:assert records==expected,(label,records)
            print(label+': real WebKit request reached native service',flush=True)
        denied=True;completed.clear();click('Power','Sleep')
        assert completed.wait(6)
        assert len(errors)==1 and 'Test sleep inhibitor' in errors[0],errors
        print('Native rejection: propagated back to Start',flush=True)
        click('Account','Account settings');time.sleep(.3)
        assert records[-1]==('Settings',['accounts']),records
        print('Account settings: Accounts page selected',flush=True)
    except BaseException as error:outcome.append(error)
    finally:GLib.idle_add(Gtk.main_quit)

threading.Thread(target=verify,daemon=True).start()
Gtk.main();pool.shutdown(wait=True);window.destroy()
if outcome:raise outcome[0]
