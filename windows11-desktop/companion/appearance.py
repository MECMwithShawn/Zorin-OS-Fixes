"""Queue reversible base appearance in the companion's integration manifest."""
import dbus
import re
import subprocess


def apply(home, panel, layout, setting, file, gsetting):
    prefix = f'/panels/panel-{panel}'
    for key, value in {'size': 48, 'icon-size': 24, 'mode': 0,
                       'nrows': 1, 'length': 100, 'autohide-behavior': 0}.items():
        setting('xfce4-panel', prefix+'/'+key, dbus.UInt32(value))
    # p=8 is Xfce's bottom-center anchor; output selection stays device-local.
    setting('xfce4-panel', prefix+'/position', dbus.String('p=8;x=0;y=0'))
    setting('xfce4-panel', prefix+'/position-locked', dbus.Boolean(True))
    for plugin in (layout['left'], layout['right']):
        setting('xfce4-panel', f'/plugins/plugin-{plugin}/expand', dbus.Boolean(True))
        setting('xfce4-panel', f'/plugins/plugin-{plugin}/style', dbus.UInt32(0))
    setting('xsettings', '/Gtk/FontName', dbus.String('Selawik 10'))
    setting('xsettings', '/Net/IconThemeName', dbus.String('CodexWindows11'))
    setting('xsettings', '/Net/ThemeName', dbus.String('ZorinBlue-Dark'))
    setting('xfwm4', '/general/theme', dbus.String('ZorinBlue-Dark'))
    setting('xfwm4', '/general/title_font', dbus.String('Selawik Semibold 10'))
    setting('xfwm4', '/general/title_alignment', dbus.String('left'))
    setting('xfwm4', '/general/use_compositing', dbus.Boolean(True))
    setting('xfce4-keyboard-shortcuts', '/commands/custom/<Super>i', dbus.String('xfce4-settings-manager'))
    available = set(subprocess.check_output(['gsettings', 'list-schemas'], text=True).splitlines())
    for schema, key, value in [
        ('org.gnome.desktop.interface', 'gtk-theme', "'ZorinBlue-Dark'"),
        ('org.gnome.desktop.interface', 'color-scheme', "'prefer-dark'"),
        ('com.zorin.desktop.auto-theme', 'enabled', 'false'),
    ]:
        if schema in available:
            gsetting(schema, key, value)


def css(content, show):
    content = re.sub(r'/\* BEGIN Windows 11-inspired desktop \*/.*?/\* END Windows 11-inspired desktop \*/\n?', '', content, flags=re.S)
    return content.rstrip()+f'''
/* BEGIN Windows 11-inspired desktop */
.xfce4-panel.background {{ background-color: #202020; background-image: none; border: none; border-top: 1px solid #3b3b3b; color: #f3f3f3; font-family: Selawik; }}
.xfce4-panel.background button {{ border-radius: 5px; margin: 4px 2px; font-weight: normal; }}
.xfce4-panel.background button:hover {{ background-color: #303030; }}
.xfce4-panel.background button:checked {{ background-color: #383838; color: #60cdff; }}
#showdesktop-{show} button {{ min-width: 7px; padding: 0; border-radius: 0; border-left: 1px solid #444444; }}
#showdesktop-{show} image {{ opacity: 0; }}
/* END Windows 11-inspired desktop */
'''
