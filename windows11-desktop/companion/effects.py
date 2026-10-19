#!/usr/bin/python3
"""Optional Compiz wobble, with a separate profile and timed Xfwm recovery."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

CONFIG=Path(os.environ.get('ZORIN11_CONFIG_DIR',str(Path.home()/'.config/zorin11-hub')))
STATE=CONFIG/'effects.json'
HERE=Path(__file__).resolve()


def load():
    try:return json.loads(STATE.read_text())
    except (FileNotFoundError,ValueError):return {'enabled':False}


def save(state):
    CONFIG.mkdir(parents=True,exist_ok=True)
    temp=STATE.with_suffix('.tmp');temp.write_text(json.dumps(state)+'\n');temp.replace(STATE)


def environment():
    # Zorin exports GTK_CSD=1 for applications. The decorator itself must draw
    # undecorated backing windows, or its pixmaps cannot be used by Compiz.
    return dict(os.environ,XDG_CONFIG_HOME=str(CONFIG/'compiz'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0')


def companion_switcher():
    # Only release the native bindings when Xfce owns the companion shortcuts.
    # Standalone effects previews/tests keep the native switcher.
    import dbus, shlex
    try:
        xf=dbus.Interface(dbus.SessionBus().get_object(
            "org.xfce.Xfconf","/org/xfce/Xfconf"),"org.xfce.Xfconf")
        command=str(xf.GetProperty("xfce4-keyboard-shortcuts","/commands/custom/<Alt>Tab"))
        return shlex.split(command)==["/usr/bin/python3",str(HERE.parent/"app.py"),"--switch-next"]
    except (dbus.DBusException,ValueError):return False


def configure():
    # This subprocess's XDG_CONFIG_HOME is private to the effects profile.
    import compizconfig
    context=compizconfig.Context()
    context.Integration=False
    values={
        'core':{'active_plugins':['core','composite','opengl','compiztoolbox','decor','place',
                 'move','resize','grid','wall','staticswitcher','wobbly'],
                'show_desktop_key':'<Super>d','toggle_window_maximized_key':'<Super>Up'},
        'decor':{'command':'gtk-window-decorator --replace --metacity-theme Zorin11-Dark'},
        'wobbly':{'friction':4.0,'spring_k':8.0,'map_effect':0,'focus_effect':0,
                  'move_window_match':'type=Normal | type=Dialog','snap_inverted':False},
        'grid':{'put_left_key':'<Super>Left','put_right_key':'<Super>Right',
                'put_maximize_key':'Disabled','put_restore_key':'<Super>Down'},
        'staticswitcher':{'next_key':'<Alt>Tab','prev_key':'<Shift><Alt>Tab',
                         'minimized':True,'icon_only':False,'mipmap':True,
                         'popup_delay':0.12,'mouse_select':True,'bring_to_front':False,
                         'use_background_color':True,'background_color':[9252,9252,9252,64250]},
    }
    if companion_switcher():
        values['staticswitcher'].update(next_key='Disabled',prev_key='Disabled')
    for name,options in values.items():
        for option,value in options.items():context.Plugins[name].Screen[option].Value=value
    from desktop_motion import configure_profile
    configure_profile(context)
    context.Write()
    for schema,key,value in [
        ('org.compiz.gwd','use-metacity-theme','true'),
        ('org.gnome.metacity.theme','type',"'metacity'"),
        ('org.gnome.metacity.theme','name',"'Zorin11-Dark'"),
        ('org.gnome.desktop.interface','gtk-theme',"'ZorinBlue-Dark'"),
        ('org.gnome.desktop.wm.preferences','button-layout',"':minimize,maximize,close'"),
        ('org.gnome.desktop.wm.preferences','titlebar-font',"'Segoe UI 10'" if (CONFIG/'reference-fonts/segoeui.ttf').exists() else "'Selawik 10'"),
    ]:
        subprocess.run(['gsettings','set',schema,key,value],check=True)


def spawn(argv,env=None):
    CONFIG.mkdir(parents=True,exist_ok=True)
    with (CONFIG/'effects.log').open('a') as log:
        return subprocess.Popen(argv,env=env,stdout=log,stderr=log,start_new_session=True)


def wm_name():
    import gi
    gi.require_version('Gdk','3.0');gi.require_version('GdkX11','3.0')
    from gi.repository import Gdk,GdkX11
    return Gdk.Screen.get_default().get_window_manager_name().lower()


def disable():
    previous=load()
    save({'enabled':False})
    if 'compiz' in wm_name() or previous.get('preview') or previous.get('enabled'):
        spawn(['xfwm4','--replace'])


def enable(token):
    env=environment()
    (CONFIG/'compiz').mkdir(parents=True,exist_ok=True)
    subprocess.run(['/usr/bin/python3',str(HERE),'--configure'],env=env,check=True)
    save({'enabled':False,'preview':token})
    # A separate process restores Xfwm even if the preview UI or Compiz crashes.
    spawn(['/usr/bin/python3',str(HERE),'--watchdog',token])
    spawn(['compiz','--replace','ccp'],env=env)


def watchdog(token):
    time.sleep(20)
    if load().get('preview')==token:
        disable()


def gui():
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,GLib
    window=Gtk.Window(title='Window Effects')
    window.set_default_size(460,250);window.set_border_width(24)
    window.set_position(Gtk.WindowPosition.CENTER)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);window.add(box)
    title=Gtk.Label();title.set_markup('<span size="large" weight="bold">Wobbly windows</span>');title.set_xalign(0);box.pack_start(title,False,False,0)
    desc=Gtk.Label(label='Make windows flex gently as you drag them.\nUses Compiz in place of the standard Xfce window manager.');desc.set_xalign(0);desc.set_line_wrap(True);box.pack_start(desc,False,False,0)
    status=Gtk.Label();status.set_xalign(0);box.pack_start(status,False,False,0)
    button=Gtk.Button();box.pack_start(button,False,False,0)
    note=Gtk.Label(label='Preview reverts automatically unless you choose Keep.\nTurning this off restores the standard Xfce window manager.');note.set_xalign(0);note.set_line_wrap(True);box.pack_start(note,False,False,0)
    def refresh():
        active='compiz' in wm_name()
        status.set_text('On' if active else 'Off')
        button.set_label('Turn off' if active else 'Preview wobble' if shutil.which('compiz') else 'Install wobble support')
    def clicked(*_):
        if 'compiz' in wm_name():
            disable();GLib.timeout_add(1200,lambda:(refresh(),False)[1]);return
        if not shutil.which('compiz'):
            button.set_sensitive(False)
            proc=spawn(['pkexec','/usr/bin/apt-get','install','-y','--no-install-recommends',
                        'compiz','compiz-plugins','compizconfig-settings-manager'])
            def installed():
                if proc.poll() is None:return True
                button.set_sensitive(True);refresh()
                if proc.returncode:status.set_text('Installation was not completed. You can try again.')
                return False
            GLib.timeout_add(500,installed);return
        token=uuid.uuid4().hex
        try:enable(token)
        except Exception as error:
            disable();status.set_text(str(error));return
        dialog=Gtk.MessageDialog(transient_for=window,modal=False,message_type=Gtk.MessageType.QUESTION,
             text='Keep wobbly windows?')
        dialog.add_button('Revert',Gtk.ResponseType.CANCEL);dialog.add_button('Keep',Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        deadline=time.monotonic()+15
        timer=[None]
        def reply(widget,response):
            if timer[0] is not None:GLib.source_remove(timer[0]);timer[0]=None
            if response==Gtk.ResponseType.OK and 'compiz' in wm_name():save({'enabled':True})
            else:disable()
            widget.destroy();GLib.timeout_add(1200,lambda:(refresh(),False)[1])
        def tick():
            remaining=max(0,int(deadline-time.monotonic()))
            dialog.format_secondary_text(f'Drag a window to try the effect. Restoring Xfce in {remaining} seconds.')
            if remaining==0:
                timer[0]=None;dialog.response(Gtk.ResponseType.CANCEL);return False
            return True
        dialog.connect('response',reply);timer[0]=GLib.timeout_add(250,tick);dialog.show_all()
    button.connect('clicked',clicked)
    window.connect('destroy',Gtk.main_quit);refresh();window.show_all();Gtk.main()


def main():
    args=sys.argv[1:]
    if args==['--configure']:configure()
    elif args==['--refresh']:
        # Updating the frame theme does not replace the running window manager
        # or disturb application windows and the user's enabled effects choice.
        if 'compiz' in wm_name():
            env=environment()
            subprocess.run(['/usr/bin/python3',str(HERE),'--configure'],env=env,check=True)
            spawn(['gtk-window-decorator','--replace','--metacity-theme','Zorin11-Dark'],env=env)
    elif args and args[0]=='--watchdog':watchdog(args[1])
    elif args==['--disable']:disable()
    elif args==['--login']:
        if load().get('enabled') and shutil.which('compiz'):
            # Previously confirmed choice. If startup fails, restore Xfwm.
            env=environment()
            subprocess.run(['/usr/bin/python3',str(HERE),'--configure'],env=env,check=True)
            proc=spawn(['compiz','--replace','ccp'],env=env)
            time.sleep(5)
            if proc.poll() is not None or 'compiz' not in wm_name():disable()
    else:gui()


if __name__=='__main__':main()
