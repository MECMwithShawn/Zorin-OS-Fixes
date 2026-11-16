#!/usr/bin/python3
"""Exercise the Multitasking switch in WebKit with private GNOME settings."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run_session(runtime):
    if os.environ.get('GSETTINGS_BACKEND') != 'memory':
        raise RuntimeError('This fixture requires an in-memory GSettings backend')

    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.1')
    from gi.repository import Gio, Gtk, WebKit2

    from gnome_live import until
    sys.path.insert(0, str(runtime))
    import settings_backend as settings

    shell = Gio.Settings.new('org.gnome.shell')
    shell.set_boolean('disable-user-extensions', False)
    shell.set_strv('enabled-extensions', [settings.TILING_EXTENSION])
    shell.set_strv('disabled-extensions', [])
    native = settings.top_edge_snap_settings()
    assert native is not None, 'Install the Zorin Tiling Shell schema to run this fixture'
    assert native.set_boolean(settings.TOP_EDGE_SNAP, False)

    messages = []
    manager = WebKit2.UserContentManager()
    manager.register_script_message_handler('desktop')
    view = WebKit2.WebView.new_with_user_content_manager(manager)
    window = Gtk.Window()
    window.set_default_size(1000, 680)
    window.add(view)

    def send(message):
        view.evaluate_javascript(f'window.receive({json.dumps(message)})',
                                 -1, None, None, None, None, None)

    def publish():
        data = {'mode': 'settings', 'facts': {'desktop': 'GNOME'}}
        snap = settings.top_edge_snap_settings()
        if snap is not None:
            data['topEdgeSnap'] = snap.get_boolean(settings.TOP_EDGE_SNAP)
            data['topEdgeSnapWritable'] = snap.is_writable(settings.TOP_EDGE_SNAP)
        send({'type': 'state', 'data': data})

    def received(_manager, result):
        message = json.loads(result.get_js_value().to_string())
        if message['action'] == 'ready':
            send({'type': 'show', 'page': 'multitasking'})
            publish()
        elif message['action'] == 'settings-set':
            messages.append(message)
            settings.apply(message['name'], message['value'])
            publish()

    def javascript(code):
        results = []

        def finished(web, operation, _data):
            try:
                results.append(web.evaluate_javascript_finish(operation).to_string())
            except Exception as error:
                results.append(error)

        view.evaluate_javascript(code, -1, None, None, None, finished, None)

        def settled():
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            return results

        result = until(settled)[0]
        if isinstance(result, Exception):
            raise result
        return result

    selector = 'document.querySelector(\'[role="switch"][aria-label="Show Snap Layouts at the top edge"]\')'

    def switch_state():
        return javascript(f'String({selector}?.getAttribute("aria-checked"))')

    manager.connect('script-message-received::desktop', received)
    try:
        window.show_all()
        view.load_uri((runtime / 'dist/index.html').as_uri())
        until(lambda: switch_state() == 'false')
        assert javascript(f'String({selector}.disabled)') == 'false'

        for expected in (True, False):
            javascript(f'{selector}.click(); "clicked"')
            until(lambda: switch_state() == str(expected).lower())
            assert messages[-1] == {'action': 'settings-set', 'name': 'topEdgeSnap', 'value': expected}
            assert native.get_boolean(settings.TOP_EDGE_SNAP) is expected
        assert len(messages) == 2

        shell.set_strv('disabled-extensions', [settings.TILING_EXTENSION])
        publish()
        until(lambda: switch_state() == 'undefined')
        assert javascript('String(document.body.innerText.includes("Multitasking"))') == 'true'
    finally:
        window.destroy()

    print('PASS: WebKit toggle updates the native top-edge setting and hides when tiling is disabled')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=Path(__file__).resolve().parents[1] / 'companion')
    parser.add_argument('--private', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.private:
        run_session(args.runtime.resolve())
        return

    with tempfile.TemporaryDirectory(prefix='zorin11-snap-settings-') as directory:
        env = dict(os.environ, GSETTINGS_BACKEND='memory', GDK_BACKEND='x11',
                   XDG_CURRENT_DESKTOP='GNOME', GTK_USE_PORTAL='0', GIO_USE_VFS='local',
                   XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory, XDG_DATA_HOME=directory)
        subprocess.run(['xvfb-run', '-a', 'dbus-run-session', '--', sys.executable, __file__,
                        '--private', '--runtime', str(args.runtime)], env=env, timeout=35, check=True)


if __name__ == '__main__':
    main()
