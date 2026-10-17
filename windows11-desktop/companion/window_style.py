"""Reversible Windows-style captions for GTK apps and native window frames."""
import re

THEME = 'Zorin11-Dark'


def apply(home, source, setting, file):
    import dbus
    for asset in (source/'window-theme').rglob('*'):
        if asset.is_file():
            file(home/'.local/share/themes'/THEME/asset.relative_to(source/'window-theme'), asset.read_bytes())
    setting('xfwm4', '/general/theme', dbus.String(THEME))
    setting('xfwm4', '/general/button_layout', dbus.String('O|HMC'))
    setting('xfwm4', '/general/title_alignment', dbus.String('left'))
    font = 'Segoe UI' if (home/'.config/zorin11-hub/reference-fonts/segoeui.ttf').exists() else 'Selawik'
    setting('xfwm4', '/general/title_font', dbus.String(font+' 10'))
    setting('xsettings', '/Gtk/DecorationLayout', dbus.String('menu:minimize,maximize,close'))


def css(content, source):
    content = re.sub(r'/\* BEGIN Windows 11 captions \*/.*?/\* END Windows 11 captions \*/\n?', '', content, flags=re.S)
    controls = source/'window-theme/controls'
    return content.rstrip()+f'''
/* BEGIN Windows 11 captions */
window.background {{ background-color: #202020; color: #f3f3f3; }}
headerbar.titlebar {{ min-height: 32px; padding: 0 0 0 12px; background: #202020; color: #f5f5f5; border: 0; box-shadow: inset 0 -1px #ffffff08; }}
headerbar.titlebar:backdrop {{ background: #202020; color: #999999; }}
headerbar.titlebar .title {{ font-weight: normal; color: inherit; }}
headerbar.titlebar .subtitle {{ color: #aaaaaa; }}
headerbar.titlebar button.titlebutton {{ min-width: 46px; min-height: 32px; padding: 0; margin: 0; border: 0; border-radius: 0; background-color: transparent; background-image: none; box-shadow: none; color: #f5f5f5; animation: none; transition: background-color 100ms ease; }}
headerbar.titlebar button.titlebutton:hover {{ background-color: #383838; background-image: none; box-shadow: none; }}
headerbar.titlebar button.titlebutton:active {{ background-color: #303030; }}
headerbar.titlebar button.titlebutton.close:hover {{ background-color: #c42b1c; color: white; }}
headerbar.titlebar button.titlebutton.close:active {{ background-color: #a92518; }}
headerbar.titlebar button.titlebutton image {{ -gtk-icon-transform: none; -gtk-icon-shadow: none; color: inherit; }}
headerbar.titlebar button.titlebutton:backdrop image {{ opacity: 0.55; }}
headerbar.titlebar button.titlebutton:backdrop:hover image {{ opacity: 1; }}
headerbar.titlebar button.titlebutton.minimize image {{ -gtk-icon-source: url('{controls/'minimize.svg'}'); }}
headerbar.titlebar button.titlebutton.maximize image {{ -gtk-icon-source: url('{controls/'maximize.svg'}'); }}
window.maximized headerbar.titlebar button.titlebutton.maximize image {{ -gtk-icon-source: url('{controls/'restore.svg'}'); }}
headerbar.titlebar button.titlebutton.close image {{ -gtk-icon-source: url('{controls/'close.svg'}'); }}
headerbar.titlebar separator.titlebutton {{ min-width: 0; margin: 0; opacity: 0; }}
window.background.csd headerbar.titlebar {{ border-top-left-radius: 8px; border-top-right-radius: 8px; }}
window.background.csd.maximized headerbar.titlebar, window.background.csd.tiled headerbar.titlebar {{ border-radius: 0; }}
window.csd decoration {{ border-radius: 8px; box-shadow: 0 8px 28px 4px rgba(0,0,0,0.30), 0 0 0 1px rgba(255,255,255,0.16); }}
window.csd.maximized decoration, window.csd.tiled decoration {{ border-radius: 0; }}
/* END Windows 11 captions */
'''
