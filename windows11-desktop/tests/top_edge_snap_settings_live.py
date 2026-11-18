#!/usr/bin/python3
"""Exercise both top-edge Snap Layouts switches in WebKit with private GNOME settings."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch


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
    ready = False

    shell = Gio.Settings.new('org.gnome.shell')
    shell.set_boolean('disable-user-extensions', False)
    shell.set_strv('enabled-extensions', [settings.TILING_EXTENSION])
    shell.set_strv('disabled-extensions', [])
    native = settings.top_edge_snap_settings()
    assert native is not None, 'Install the Zorin Tiling Shell schema to run this fixture'
    assert native.set_boolean(settings.TOP_EDGE_SNAP, False)
    assert native.set_boolean(settings.SNAP_SUGGESTIONS, False)

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
            for name, key in settings.SNAP_SETTINGS.items():
                data[name] = snap.get_boolean(key)
                data[name + 'Writable'] = snap.is_writable(key)
            data['snapSuggestionsReady'] = settings.snap_suggestions_ready()
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

    def control(label):
        return f'document.querySelector(\'[role="switch"][aria-label="{label}"]\')'

    drag = control('Show Snap Layouts at the top edge')
    suggestions = control('Suggest windows after dragging to snap')

    def switch_state(selector):
        return javascript(f'String({selector}?.getAttribute("aria-checked"))')

    def click(selector, name, key, value):
        javascript(f'{selector}.click(); "clicked"')
        until(lambda: switch_state(selector) == str(value).lower())
        assert messages[-1] == {'action': 'settings-set', 'name': name, 'value': value}
        assert native.get_boolean(key) is value

    manager.connect('script-message-received::desktop', received)
    with patch.object(settings, 'shell_call', lambda op: ready if op == 'snap-suggestions-ready' else None):
        window.show_all()
        view.load_uri((runtime / 'dist/index.html').as_uri())
        until(lambda: switch_state(drag) == 'false' and switch_state(suggestions) == 'false')
        assert javascript(f'String({drag}.disabled)') == 'false'
        assert javascript(f'String({suggestions}.disabled)') == 'true'
        click(drag, 'topEdgeSnap', settings.TOP_EDGE_SNAP, True)
        assert javascript(f'String({suggestions}.disabled)') == 'true'
        ready = True
        publish()
        until(lambda: javascript(f'String({suggestions}.disabled)') == 'false')
        for expected in (True, False, True):
            click(suggestions, 'snapSuggestions', settings.SNAP_SUGGESTIONS, expected)
            assert native.get_boolean(settings.TOP_EDGE_SNAP)
        click(drag, 'topEdgeSnap', settings.TOP_EDGE_SNAP, False)
        assert javascript(f'String({suggestions}.disabled)') == 'true'
        assert native.get_boolean(settings.SNAP_SUGGESTIONS)
        assert len(messages) == 5

        shell.set_strv('disabled-extensions', [settings.TILING_EXTENSION])
        publish()
        until(lambda: switch_state(drag) == 'undefined' and switch_state(suggestions) == 'undefined')
        assert javascript('String(document.body.innerText.includes("Multitasking"))') == 'true'
        window.destroy()

    print('PASS: WebKit switches update the native top-edge settings and preserve the suggestions preference')


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
