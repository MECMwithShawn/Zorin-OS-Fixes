"""Apply GNOME accessibility preferences to the companion's custom surfaces."""

from pathlib import Path

from gi.repository import Gio

from gnome_bridge import active as is_gnome


_CONTRAST = 'org.gnome.desktop.a11y.interface'
_MOTION = 'org.gnome.desktop.interface'
_REDUCED_MOTION = """
*, *::before, *::after {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
}
"""


def _watch(widget, schema, key, apply):
    settings = Gio.Settings.new(schema)

    def changed(*_):
        apply(settings.get_boolean(key))

    changed()
    handler = settings.connect('changed::' + key, changed)
    widget.connect('destroy', lambda *_: settings.disconnect(handler))


def configure_web(widget, manager):
    if not is_gnome():
        return
    from gi.repository import WebKit2

    def follow(schema, key, css, enabled):
        sheet = WebKit2.UserStyleSheet.new(
            css, WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserStyleLevel.USER, None, None)
        installed = False

        def update(value):
            nonlocal installed
            wanted = value == enabled
            if wanted and not installed:
                manager.add_style_sheet(sheet)
            elif installed and not wanted:
                manager.remove_style_sheet(sheet)
            installed = wanted

        _watch(widget, schema, key, update)

    contrast_css = Path(__file__).with_name('high-contrast.css').read_text()
    follow(_CONTRAST, 'high-contrast', contrast_css, True)
    follow(_MOTION, 'enable-animations', _REDUCED_MOTION, False)


def configure_native(widget):
    if not is_gnome():
        return
    context = widget.get_style_context()

    def update(high_contrast):
        if high_contrast:
            context.add_class('z11-high-contrast')
        else:
            context.remove_class('z11-high-contrast')

    _watch(widget, _CONTRAST, 'high-contrast', update)
