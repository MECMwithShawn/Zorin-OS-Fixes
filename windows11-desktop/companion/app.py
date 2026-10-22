#!/usr/bin/python3
"""React desktop UI hosted by GTK/WebKit, with native Xfce integration."""
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urlparse, parse_qs

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, WebKit2
from model import Store
from platform_ui import panel_button, desktop_status
import explorer
import file_preview
import file_thumbnails
import unified_search
import app_details
import start_preferences
import file_transfer
import threading
import settings_backend
import wallpaper
import notifications
import quick_controls
import session_actions
from gnome_bridge import active as is_gnome

BASE = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('ZORIN11_CONFIG_DIR', str(Path.home()/'.config/zorin11-hub')))
APP_ID = os.environ.get('ZORIN11_APP_ID', 'local.zorin11.DesktopHub')
LABELS = {'thunar.desktop': 'Thunar', 'zorin11-explorer.desktop': 'File Explorer', 'brave-browser.desktop': 'Brave',
          'xfce-settings-manager.desktop': 'Advanced Settings', 'zorin11-settings.desktop': 'Settings', 'org.gnome.Evince.desktop': 'PDF Viewer',
          'libreoffice-writer.desktop': 'Writer', 'libreoffice-calc.desktop': 'Calc',
          'org.gnome.Software.desktop': 'Software', 'xfce4-terminal.desktop': 'Xfce Terminal',
          'xfce4-screenshooter.desktop': 'Screenshot', 'org.xfce.ristretto.desktop': 'Photos'}


class Surface(Gtk.ApplicationWindow):
    def __init__(self, hub, group_id=None, mode='start'):
        super().__init__(application=hub)
        self.hub, self.group_id, self.ready = hub, group_id, False
        self.mode = 'group' if group_id else mode
        self.location = '::home'
        self.request_id = 0
        self.file_state = None
        self.file_monitor = None
        self.geometry_timer = 0
        self.pending_page = None
        self.backdrop = None
        self.maximized = False
        self.drag_timer = 0
        self.set_title({'start':'Zorin 11 Start','quick':'Quick settings','notifications':'Notifications and calendar','explorer':'File Explorer','settings':'Settings','group':'Desktop group'}[self.mode])
        self.set_wmclass("zorin11-hub", "Zorin11-hub")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(self.mode not in ('explorer','settings'))
        self.set_skip_pager_hint(self.mode not in ('explorer','settings'))
        if self.mode == 'settings':
            self.set_wmclass('zorin11-settings','Zorin11-settings')
            self.set_icon_name('preferences-system')
        if self.mode == 'explorer':
            self.set_wmclass('zorin11-explorer', 'Zorin11-explorer')
            self.set_icon_from_file(str(BASE/'explorer.svg'))
            if (CONFIG/'reference-icons/48/system-file-manager.png').exists():
                self.set_icon_name('system-file-manager')
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.connect('draw', self.clear_background)
        self.connect('delete-event', self.on_delete)
        self.connect('key-press-event', self.on_key)
        self.connect('configure-event', self.on_configure)
        self.connect('window-state-event', self.on_window_state)
        self.connect('notify::is-active', lambda *args: self.update() if self.mode in ('explorer','settings') else None)
        if self.mode in ('explorer','settings'):
            self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
            self.set_default_size(1120, 760)
            self.set_size_request(740, 440)
            if self.mode=='settings':self.set_size_request(800,540)
        elif group_id is None:
            self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            self.set_keep_above(True)
            self.set_resizable(False)
            self.connect('focus-out-event', self.on_blur)
        else:
            self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            self.set_keep_below(True)
            self.stick()
            geometry = Gdk.Geometry()
            geometry.min_width, geometry.min_height = 260, 44
            self.set_geometry_hints(None, geometry, Gdk.WindowHints.MIN_SIZE)
        manager = WebKit2.UserContentManager()
        manager.register_script_message_handler('desktop')
        manager.connect('script-message-received::desktop', self.on_message)
        self.web = WebKit2.WebView(web_context=hub.context, user_content_manager=manager)
        settings = self.web.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_html5_database(False)
        settings.set_enable_html5_local_storage(False)
        self.web.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        self.web.connect('context-menu', lambda *args: True)
        self.web.connect('decide-policy', self.on_navigation)
        self.web.connect('web-process-terminated', self.on_web_crash)
        self.add(self.web)
        self.web.load_uri('zorin11://ui/index.html')

    def clear_background(self, widget, cr):
        import cairo
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        return False

    def on_navigation(self, web, decision, kind):
        if kind in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            uri = decision.get_navigation_action().get_request().get_uri()
            if uri != 'zorin11://ui/index.html':
                decision.ignore()
                return True
        return False

    def on_web_crash(self, *args):
        self.ready = False
        GLib.timeout_add(400, self.reload)

    def reload(self):
        self.web.load_uri('zorin11://ui/index.html')
        return False

    def js(self, code, callback=None):
        self.web.evaluate_javascript(code, -1, None, None, None, callback, None)

    def send(self, data):
        self.js('window.receive(' + json.dumps(data, ensure_ascii=True) + ')')

    def update(self):
        if self.ready:
            if self.mode == 'quick':
                data = dict(self.hub.status, mode='quick', busy=self.hub.quick_busy,
                            quickTiles=self.hub.store.state.get('quick_tiles',list(quick_controls.TILES)))
            elif self.mode == 'notifications':
                data = dict(self.hub.notification_data,mode='notifications',busy=self.hub.notification_busy)
            elif self.mode == 'explorer':
                data = dict(self.file_state or {'path':self.location,'title':'Home','entries':[], 'places':explorer.place_paths(), 'clouds':explorer.cloud_places()}, mode='explorer')
                data.update(maximized=self.maximized,focused=self.is_active())
            elif self.mode == 'settings':
                data = dict(self.hub.settings_data,mode='settings',maximized=self.maximized,
                            focused=self.is_active(),busy=self.hub.settings_busy)
                profile=self.hub.payload()
                data.update(user=profile['user'],avatar=profile['avatar'],
                            apps=sorted([self.hub.app_info(i) for i in self.hub.apps],key=lambda a:a['name'].casefold()),
                            groupsVisible=self.hub.store.state['groups_visible'])
            else:
                data = self.hub.payload(self.group_id)
            if self.backdrop:
                data['backdrop'] = self.backdrop
            self.send({'type': 'state', 'data': data})

    def on_message(self, manager, result):
        try:
            payload = json.loads(result.get_js_value().to_string())
            if not isinstance(payload, dict):
                return
            self.hub.dispatch(self, payload)
        except Exception as error:
            print('Desktop action:', error, file=sys.stderr, flush=True)
            self.send({'type': 'error', 'message': str(error)})

    def on_key(self, window, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.mode in ('start','notifications') and self.ready:
                self.send({'type':'escape'})
            elif self.mode in ('start','quick', 'notifications'):
                self.hide()
            elif self.hub.peeking:
                self.hub.peek()
            else:
                return False
            return True
        return False

    def on_delete(self, *args):
        if self.mode == 'settings':
            self.hub.surfaces.pop('settings',None)
            self.destroy()
            return True
        if self.mode == 'explorer':
            if getattr(self,'transfer',None):self.transfer.cancel()
            self.request_id += 1
            if getattr(self,'monitor_refresh',0):
                GLib.source_remove(self.monitor_refresh)
            if self.file_monitor:
                self.file_monitor.cancel()
            self.hub.surfaces.pop(str(id(self)), None)
            self.destroy()
            return True
        self.hide()
        return True

    def on_blur(self, *args):
        def hide_unfocused():
            if not self.is_active() and not self.hub.modal:
                self.hide()
            return False
        GLib.timeout_add(180, hide_unfocused)
        return False

    def on_configure(self, *args):
        if self.group_id and self.get_visible():
            if self.geometry_timer:
                GLib.source_remove(self.geometry_timer)
            self.geometry_timer = GLib.timeout_add(350, self.save_geometry)
        return False

    def on_window_state(self, window, event):
        self.maximized=bool(event.new_window_state & Gdk.WindowState.MAXIMIZED)
        if self.mode in ('explorer','settings'):self.update()
        return False

    def save_geometry(self):
        self.geometry_timer = 0
        try:
            group = self.hub.store.group(self.group_id)
        except StopIteration:
            return False
        x, y = self.get_position()
        width, height = self.get_size()
        group.update(x=x, y=y, width=width)
        if not group['collapsed']:
            group['height'] = height
        self.hub.store.save()
        return False

    def drag_group(self, resize=False):
        # Xfwm intentionally disallows its interactive moveresize on DESKTOP
        # windows. Track the pointer while pressed and request geometry directly.
        if self.drag_timer:
            return
        pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
        _, start_x, start_y = pointer.get_position()
        x, y = self.get_position()
        width, height = self.get_size()
        def tick():
            _, now_x, now_y = pointer.get_position()
            _, _, _, modifiers = Gdk.get_default_root_window().get_device_position(pointer)
            if not modifiers & Gdk.ModifierType.BUTTON1_MASK:
                self.drag_timer = 0
                self.save_geometry()
                self.hub.place_group(self, self.hub.store.group(self.group_id))
                return False
            dx, dy = now_x-start_x, now_y-start_y
            if resize:
                self.resize(max(260,width+dx),max(160,height+dy))
            else:
                self.move(x+dx,y+dy)
            return True
        self.drag_timer = GLib.timeout_add(16, tick)


class Hub(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.surfaces = {}
        self.modal = False
        self.peeking = False
        self.context = None
        self.icon_cache = {}
        self.file_monitors = []
        self.refresh_timer = 0
        self.workers = ThreadPoolExecutor(max_workers=3)
        self.status = {}
        self.settings_data = {'loading':True}
        self.settings_busy = False
        self.settings_pending = False
        self.settings_generation = 0
        self.quick_busy=False
        self.status_generation=0
        self.notification_data={'entries':[],'loading':True}
        self.notification_pending=False
        self.notification_busy=False
        self.notification_generation=0
        try:
            self.presentation = json.loads((CONFIG/'presentation.json').read_text())
        except (OSError, ValueError):
            self.presentation = {}
        self.status_pending = False
        self.backdrops = {}
        self.copied_files = ([], False, '')
        self.recent_documents = []
        self.recent_generation = 0
        self.recent_timer = 0

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self.clipboard_owner = Gtk.Invisible()
        targets = [Gtk.TargetEntry.new(name, 0, index) for index,name in enumerate(
            ['x-special/gnome-copied-files','text/uri-list','UTF8_STRING','TEXT','STRING'])]
        Gtk.selection_add_targets(self.clipboard_owner,Gdk.SELECTION_CLIPBOARD,targets)
        self.clipboard_owner.connect('selection-get',self.clipboard_get)
        self.apps = {}
        self.refresh_apps()
        self.store = Store(CONFIG/'layout.json', self.apps, Path.home())
        self.start_preferences = start_preferences.Preferences(CONFIG/'search-start.json', [p['path'] for p in explorer.place_paths()])
        self.recent_manager = Gtk.RecentManager.get_default()
        self.recent_manager.connect('changed', lambda *_: self.refresh_recent_documents())
        self.privacy = Gio.Settings.new('org.gnome.desktop.privacy')
        self.privacy.connect('changed::remember-recent-files', lambda *_: self.refresh_recent_documents())
        Gtk.Settings.get_default().connect('notify::gtk-recent-files-enabled', lambda *_: self.refresh_recent_documents())
        self.context = WebKit2.WebContext.new_ephemeral()
        self.context.register_uri_scheme('zorin11', self.resource)
        self.context.get_security_manager().register_uri_scheme_as_local('zorin11')
        self.context.get_security_manager().register_uri_scheme_as_secure('zorin11')
        self.start = Surface(self)
        self.surfaces['start'] = self.start
        self.quick = Surface(self, mode='quick')
        self.surfaces['quick'] = self.quick
        self.notifications=Surface(self,mode='notifications')
        self.surfaces['notifications']=self.notifications
        self.refresh_status()
        GLib.timeout_add_seconds(4, self.refresh_status)
        GLib.timeout_add_seconds(5, self.refresh_settings)
        GLib.timeout_add_seconds(4,self.refresh_notifications)
        if APP_ID=='local.zorin11.DesktopHub':
            GLib.timeout_add_seconds(60,self.wallpaper_tick)
            GLib.timeout_add_seconds(8,lambda:(self.wallpaper_tick(),False)[1])
        self.app_monitor = Gio.AppInfoMonitor.get()
        self.app_monitor.connect('changed', lambda *args: self.on_apps_changed())
        Gtk.IconTheme.get_default().connect('changed', lambda *args: self.on_apps_changed())
        Gdk.Display.get_default().connect('monitor-added', lambda *args: self.reposition_groups())
        Gdk.Display.get_default().connect('monitor-removed', lambda *args: self.reposition_groups())
        self.sync_groups()
        from multitasking import Multitasking
        self.multitasking=Multitasking(self,CONFIG)
        self.connect('shutdown',lambda *_:self.multitasking.shutdown())
        self.connect('shutdown',lambda *_:[s.transfer.cancel() for s in self.surfaces.values() if getattr(s,'transfer',None)])

    def refresh_apps(self):
        self.apps = {a.get_id(): a for a in Gio.AppInfo.get_all() if a.get_id() and a.should_show()}
        if hasattr(self,'store'):self.store.app_ids=set(self.apps)

    def clipboard_get(self, widget, selection, info, timestamp):
        paths, cut, text = self.copied_files
        if info == 0:
            selection.set(selection.get_target(),8,((('cut' if cut else 'copy')+'\n'+text)).encode())
        elif info == 1:
            selection.set_uris([Path(p).as_uri() for p in paths])
        else:
            selection.set_text(text,-1)

    def on_apps_changed(self):
        self.refresh_apps()
        self.icon_cache.clear()
        self.broadcast()

    def do_activate(self):
        self.toggle_start()

    def do_command_line(self, command):
        try:return self.handle_command_line(command)
        except Exception as error:
            print('Desktop action failed:',error,file=sys.stderr,flush=True)
            return 1

    def handle_command_line(self, command):
        args = command.get_arguments()[1:]
        if '--quit' in args:
            self.quit()
        elif '--switch-next' in args or '--switch-previous' in args:
            self.multitasking.switcher.show('--switch-previous' in args)
        elif '--snap-layouts' in args:
            self.multitasking.show_snap()
        elif '--saved-groups' in args:
            self.multitasking.show_saved_groups()
        elif '--task-view' in args:
            self.multitasking.show_tasks()
        elif '--desktop' in args:
            offset=args.index('--desktop')+1
            if offset<len(args):self.multitasking.desktop_command(args[offset])
        elif '--peek' in args:
            self.peek()
        elif '--search' in args:
            self.show_start()
        elif '--groups' in args:
            self.show_start('groups')
        elif '--notifications' in args:
            self.show_notifications()
        elif '--quick-settings' in args:
            self.show_quick()
        elif '--settings' in args:
            offset=args.index('--settings')+1
            self.open_settings(args[offset] if offset<len(args) else 'home')
        elif '--explorer' in args:
            offset = args.index('--explorer')+1
            for location in args[offset:] or ['::home']:self.open_explorer(location)
        elif '--diagnostics' in args:
            path = args[args.index('--diagnostics') + 1]
            GLib.timeout_add(400, self.diagnostics, path)
        elif '--export-previews' in args:
            path = args[args.index('--export-previews') + 1]
            GLib.timeout_add(600, self.export_previews, path)
        elif '--background' not in args:
            self.toggle_start()
        return 0

    def resource(self, request):
        try:
            uri = urlparse(request.get_uri())
            if uri.netloc == 'ui':
                path = (BASE/'dist'/unquote(uri.path.lstrip('/'))).resolve()
                if not path.is_relative_to((BASE/'dist').resolve()) or not path.is_file():
                    raise ValueError('Unknown local resource')
                content = path.read_bytes()
                mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            elif uri.netloc == 'profile' and uri.path == '/avatar':
                path = self.account_avatar()
                if path is None:
                    raise ValueError('No account photo configured')
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 256, 256, True)
                content = pixbuf.save_to_bufferv('png', [], [])[1]
                mime = 'image/png'
            elif uri.netloc == 'backdrop':
                content = self.backdrops.get(uri.path.lstrip('/'), b'')
                mime = 'image/png'
            elif uri.netloc == 'wallpaper':
                content = wallpaper.thumbnail(uri.path.lstrip('/'))
                mime = 'image/jpeg'
            elif uri.netloc == 'thumbnail':
                file_thumbnails.serve(self, request, uri)
                return
            elif uri.netloc == 'icon':
                key = unquote(uri.path.lstrip('/'))
                content = self.icon_bytes(key)
                mime = 'image/png'
            elif uri.netloc == 'theme-icon':
                key = unquote(uri.path.lstrip('/'))
                if not key or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in key):
                    raise ValueError('Unknown theme icon')
                size=int(parse_qs(uri.query).get('size',['64'])[0])
                if size not in (16,24,32,48,64,256):raise ValueError('Unknown icon size')
                content = self.icon_bytes('theme:'+key,size)
                mime = 'image/png'
            else:
                raise ValueError('Unknown resource')
            request.finish(Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(content)), len(content), mime)
        except Exception as error:
            print('Local resource:', request.get_uri(), error, file=sys.stderr, flush=True)
            request.finish(Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(b'')), 0, 'text/plain')

    def icon_bytes(self, key, size=64):
        cache_key=(key,size)
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]
        if key.startswith('theme:'):
            icon = Gio.ThemedIcon.new(key[6:])
        elif key.startswith('mime:'):
            icon = Gio.content_type_get_icon(key[5:])
        elif key in ('thunar.desktop', 'zorin11-explorer.desktop'):
            icon = Gio.ThemedIcon.new('system-file-manager') if (CONFIG/'reference-icons/48/system-file-manager.png').exists() else Gio.FileIcon.new(Gio.File.new_for_path(str(BASE/'explorer.svg')))
        elif key in self.apps:
            icon = self.apps[key].get_icon()
        elif key == 'folder':
            icon = Gio.ThemedIcon.new('folder')
        elif key == 'file':
            icon = Gio.ThemedIcon.new('text-x-generic')
        else:
            icon = Gio.ThemedIcon.new('application-x-executable')
        theme = Gtk.IconTheme.get_default()
        info = theme.lookup_by_gicon(icon or Gio.ThemedIcon.new('application-x-executable'), size, Gtk.IconLookupFlags.FORCE_SIZE)
        if not info:
            info = theme.lookup_icon('application-x-executable', size, Gtk.IconLookupFlags.FORCE_SIZE)
        image = info.load_icon()
        success, data = image.save_to_bufferv('png', [], [])
        self.icon_cache[cache_key] = bytes(data)
        return bytes(data)

    def app_info(self, app_id):
        app = self.apps.get(app_id)
        if not app:
            return None
        return {'id': app_id, 'name': LABELS.get(app_id, app.get_display_name()),
            'description': app.get_description() or '',
            'actions': [{'id': action, 'name': app.get_action_name(action)} for action in app.list_actions()] if hasattr(app,'list_actions') else [],
            'categories': (app.get_categories() or '').split(';') if hasattr(app, 'get_categories') else [], 'icon': 'zorin11://icon/' + quote(app_id, safe='')}

    def path_info(self, path):
        p = Path(path)
        return {'kind': 'path', 'path': str(p), 'id': str(p),
            'name': 'Home' if p == Path.home() else p.name,
            'icon': 'zorin11://icon/' + ('folder' if p.is_dir() else 'file'), 'missing': not p.exists()}

    def group_info(self, group):
        result = dict(group)
        if group['folder']:
            try:
                children = sorted((p for p in Path(group['folder']).iterdir() if not p.name.startswith('.')),
                    key=lambda p: (not p.is_dir(), p.name.casefold()))
                result['items'] = [self.path_info(p) for p in children[:200]]
                result['overflow'] = len(children) > 200
            except OSError as error:
                result['items'], result['error'] = [], str(error)
        else:
            items = []
            for item in group['items']:
                if item['kind'] == 'app':
                    app = self.app_info(item['id'])
                    if app:
                        items.append(dict(app, kind='app'))
                else:
                    items.append(self.path_info(item['path']))
            result['items'] = items
        return result

    def account_avatar(self):
        """Resolve the system account photo; periodically recheck account changes."""
        now = time.monotonic()
        if now >= getattr(self, '_avatar_checked_until', 0):
            self._avatar_checked_until = now + 5
            candidates = []
            try:
                bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
                user_path = bus.call_sync('org.freedesktop.Accounts',
                    '/org/freedesktop/Accounts', 'org.freedesktop.Accounts',
                    'FindUserById', GLib.Variant('(x)', (os.getuid(),)),
                    GLib.VariantType.new('(o)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
                icon = bus.call_sync('org.freedesktop.Accounts', user_path,
                    'org.freedesktop.DBus.Properties', 'Get',
                    GLib.Variant('(ss)', ('org.freedesktop.Accounts.User', 'IconFile')),
                    GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
                if icon:
                    candidates.append(Path(icon))
            except GLib.Error:
                pass
            candidates.extend([Path.home()/'.face', Path.home()/'.face.icon', CONFIG/'reference-avatar.jpg'])
            self._account_avatar_path = None
            for path in candidates:
                try:
                    if path.is_file() and os.access(path, os.R_OK):
                        self._account_avatar_path = path
                        break
                except OSError:
                    continue
        return self._account_avatar_path

    def account_avatar_uri(self):
        path = self.account_avatar()
        try:
            return 'zorin11://profile/avatar?v=' + str(path.stat().st_mtime_ns) if path else None
        except OSError:
            return None

    def payload(self, group_id=None):
        state = self.store.state
        if group_id:
            return {'mode': 'group', 'group': self.group_info(self.store.group(group_id)), 'peeking': self.peeking}
        return {'mode': 'start', 'apps': sorted([self.app_info(i) for i in self.apps], key=lambda a: a['name'].casefold()),
            'pins': [i for i in state['pins'] if i in self.apps or i in state['start_folders']],
            'startFolders': [dict(folder,id=ident) for ident,folder in state['start_folders'].items()],
            'recent': [i for i in state['recent'] if i in self.apps],
            'documents': self.recent_documents,
            'groups': [self.group_info(g) for g in state['groups']], 'groupsVisible': state['groups_visible'],
            'user': self.presentation.get('displayName') or (GLib.get_real_name() if GLib.get_real_name() not in ('Unknown', '') else GLib.get_user_name()),
            'avatar': self.account_avatar_uri(),
            'places': [self.path_info(p) for p in [Path.home(), Path.home()/'Documents', Path.home()/'Downloads'] if p.exists()],
            'startStyle': self.start_preferences.snapshot()['style'],
            'startTiles': self.start_preferences.snapshot()['tiles'],
            'startOptions': self.start_options(),
            'startPlaces': [self.path_info(p) for p in self.start_place_paths()]}

    def start_options(self):
        """Windows 11 layout options; tabs only list apps that are still installed."""
        preferences = self.start_preferences.snapshot()
        return dict(layout=preferences['layout'], columns=preferences['columns'], showRecommended=preferences['showRecommended'],
                    tabs=[dict(tab, apps=[a for a in tab['apps'] if a in self.apps]) for tab in preferences['tabs']])

    def start_place_paths(self):
        """Right-hand folders of the classic Start layouts, in Windows 7 order."""
        special = [GLib.get_user_special_dir(d) for d in (GLib.UserDirectory.DIRECTORY_DOCUMENTS,
            GLib.UserDirectory.DIRECTORY_PICTURES, GLib.UserDirectory.DIRECTORY_MUSIC,
            GLib.UserDirectory.DIRECTORY_VIDEOS, GLib.UserDirectory.DIRECTORY_DOWNLOAD)]
        result = []
        for path in [Path.home(), *(Path(d) for d in special if d)]:
            if path not in result and path.is_dir():
                result.append(path)
        return result

    def broadcast(self):
        for surface in list(self.surfaces.values()):
            surface.update()

    def monitor_geometry(self, primary=False):
        display = Gdk.Display.get_default()
        if primary:
            # Mutter is authoritative on Wayland; XWayland may report a
            # different primary output and pointer coordinates.
            bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            state=bus.call_sync('org.gnome.Mutter.DisplayConfig','/org/gnome/Mutter/DisplayConfig',
                'org.gnome.Mutter.DisplayConfig','GetCurrentState',None,None,Gio.DBusCallFlags.NONE,3000,None).unpack()
            logical=next((m for m in state[2] if m[4]),state[2][0])
            return self.work_area(logical[0]+1,logical[1]+1)
        pointer = display.get_default_seat().get_pointer()
        _, x, y = pointer.get_position()
        return self.work_area(x, y)

    def work_area(self, x, y):
        display=Gdk.Display.get_default()
        monitor=display.get_monitor_at_point(x,y)
        if monitor:
            return monitor.get_workarea()
        # DisplayPort monitors can temporarily disappear while waking from DPMS.
        root=Gdk.get_default_root_window()
        area=Gdk.Rectangle()
        area.x=area.y=0
        area.width,area.height=root.get_width(),root.get_height()
        return area

    def toggle_start(self):
        if self.start.get_visible():
            self.start.hide()
        else:
            self.show_start()

    def show_start(self, page='home'):
        self.refresh_recent_documents()
        self.notifications.hide()
        self.quick.hide()
        anchor = None if is_gnome() else panel_button('Start')
        display = Gdk.Display.get_default()
        geometry = self.work_area(anchor[0], anchor[1]) if anchor else self.monitor_geometry(primary=is_gnome())
        size = {'windows7': (456, 620), 'modern': (520, 640), 'windows10': (780, 680)}.get(self.start_preferences.snapshot()['style'], (832, 864))
        width, height = min(size[0], geometry.width - 24), min(size[1], geometry.height - 24)
        self.start.set_size_request(width, height)
        self.start.resize(width, height)
        center = anchor[0]+anchor[2]//2 if anchor else geometry.x+geometry.width//2
        x = max(geometry.x+12, min(center-width//2, geometry.x+geometry.width-width-12))
        bottom = min(anchor[1], geometry.y+geometry.height) if anchor else geometry.y+geometry.height
        y = max(geometry.y+12, bottom-height-12)
        self.capture_backdrop(self.start, x, y, width, height)
        self.start.move(x, y)
        self.start.show_all()
        self.start.present_with_time(Gdk.CURRENT_TIME)
        # Xfwm may apply its initial placement when a utility window maps.
        # Reapply the measured anchor after the initial configure event.
        GLib.timeout_add(60, lambda: (self.start.move(x,y), False)[1])
        self.start.update()
        if self.start.ready:
            self.start.send({'type': 'show', 'page': page})
        else:
            self.start.pending_page = page

    def capture_backdrop(self, surface, x, y, width, height):
        """Keep a tiny, blurred-on-render snapshot in memory for acrylic panels."""
        if surface.get_visible():
            return
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
            # XWayland's root is not the composited desktop. Use the normal
            # panel background instead of a black/incomplete root capture.
            self.backdrops.pop(surface.mode, None)
            surface.backdrop = None
            return
        try:
            root = Gdk.get_default_root_window()
            pixels = Gdk.pixbuf_get_from_window(root, x, y, width, height)
            if pixels:
                small = pixels.scale_simple(max(1, width//16), max(1, height//16), GdkPixbuf.InterpType.BILINEAR)
                _, content = small.save_to_bufferv('png', [], [])
                self.backdrops[surface.mode] = bytes(content)
                surface.backdrop = 'zorin11://backdrop/' + surface.mode + '?v=' + str(time.monotonic_ns())
        except Exception as error:
            print('Panel backdrop:', error, file=sys.stderr, flush=True)

    def place_group(self, surface, group):
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_point(group['x'], group['y'])
        if monitor is None:
            return
        area = monitor.get_workarea()
        width = min(max(260, group['width']), area.width)
        height = 44 if group['collapsed'] else min(max(160, group['height']), area.height)
        x = min(max(area.x, group['x']), area.x + area.width-width)
        y = min(max(area.y, group['y']), area.y + area.height-height)
        surface.resize(width, height)
        surface.move(x, y)

    def reposition_groups(self):
        for group in self.store.state['groups']:
            if group['id'] in self.surfaces:
                self.place_group(self.surfaces[group['id']], group)

    def sync_groups(self):
        ids = {g['id'] for g in self.store.state['groups']}
        for key in list(self.surfaces):
            if self.surfaces[key].group_id and key not in ids:
                surface = self.surfaces.pop(key)
                if surface.geometry_timer:
                    GLib.source_remove(surface.geometry_timer)
                if surface.drag_timer:
                    GLib.source_remove(surface.drag_timer)
                surface.destroy()
        for monitor in self.file_monitors:
            monitor.cancel()
        self.file_monitors = []
        for group in self.store.state['groups']:
            key = group['id']
            if key not in self.surfaces:
                self.surfaces[key] = Surface(self, key)
            surface = self.surfaces[key]
            self.place_group(surface, group)
            if self.store.state['groups_visible']:
                surface.show_all()
            else:
                surface.hide()
            if group['folder'] and Path(group['folder']).is_dir():
                monitor = Gio.File.new_for_path(group['folder']).monitor_directory(Gio.FileMonitorFlags.NONE, None)
                monitor.connect('changed', lambda *args: self.schedule_refresh())
                self.file_monitors.append(monitor)
        self.broadcast()

    def schedule_refresh(self):
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
        self.refresh_timer = GLib.timeout_add(200, self.refresh)

    def refresh(self):
        self.refresh_timer = 0
        self.broadcast()
        return False

    def peek(self):
        self.start.hide()
        self.peeking = not self.peeking
        for key, surface in self.surfaces.items():
            if not surface.group_id:
                continue
            surface.set_keep_below(not self.peeking)
            surface.set_keep_above(self.peeking)
            if self.peeking:
                surface.show_all()
                surface.present()
            elif not self.store.state['groups_visible']:
                surface.hide()
        self.broadcast()

    def pick(self, surface, folder=False, multiple=False):
        self.modal = True
        dialog = Gtk.FileChooserDialog(title='Choose a folder' if folder else 'Add file or folder shortcuts',
            transient_for=surface, action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose', Gtk.ResponseType.OK)
        dialog.set_select_multiple(multiple)
        dialog.set_current_folder(str(Path.home()))
        response = dialog.run()
        paths = dialog.get_filenames() if response == Gtk.ResponseType.OK else []
        dialog.destroy()
        self.modal = False
        surface.present()
        return paths

    def launch(self, app_id):
        if app_id not in self.apps:
            raise ValueError('This application is no longer installed.')
        if app_id in ('thunar.desktop','org.gnome.Nautilus.desktop','zorin11-explorer.desktop'):
            self.open_explorer()
        elif app_id=='zorin11-settings.desktop':
            self.open_settings()
        else:
            context = Gdk.Display.get_default().get_app_launch_context()
            context.set_timestamp(Gdk.CURRENT_TIME)
            if not self.apps[app_id].launch([], context):
                raise RuntimeError('The application could not be started.')
        self.store.used(app_id)
        self.start.hide()
        self.broadcast()

    def launch_app_action(self, app_id, action):
        app = self.apps.get(app_id)
        if not app or not hasattr(app, 'list_actions') or action not in app.list_actions():
            raise ValueError('This application shortcut is no longer available.')
        context = Gdk.Display.get_default().get_app_launch_context()
        context.set_timestamp(Gdk.CURRENT_TIME)
        app.launch_action(action, context)
        self.store.used(app_id)
        self.start.hide()
        self.broadcast()

    def recent_history_allowed(self):
        return self.privacy.get_boolean('remember-recent-files') and Gtk.Settings.get_default().get_property('gtk-recent-files-enabled')

    def refresh_recent_documents(self, invalidate=False):
        self.recent_generation += 1
        generation = self.recent_generation
        if self.recent_timer: GLib.source_remove(self.recent_timer)
        self.recent_timer = 0
        preferences = self.start_preferences.snapshot()
        allowed = preferences['recentDocuments'] and self.recent_history_allowed()
        if invalidate or not allowed:
            self.recent_documents = []
            if hasattr(self, 'start'): self.start.update()
        if not allowed: return
        def collect():
            self.recent_timer = 0
            items = sorted(self.recent_manager.get_items(), key=lambda i:i.get_modified(), reverse=True)[:512]
            records = [dict(uri=i.get_uri(), private=i.get_private_hint(), modified=i.get_modified(), mime=i.get_mime_type() or 'application/octet-stream') for i in items if i.is_local()]
            def done(documents):
                if generation == self.recent_generation:
                    self.recent_documents = documents
                    self.start.update()
            self.background(lambda:start_preferences.documents(records,preferences), done, lambda _:done([]))
            return False
        self.recent_timer = GLib.timeout_add(120, collect)

    def open_recent_document(self, ident, location=False):
        item = next((i for i in self.recent_documents if i['id'] == ident), None)
        if not item or not self.recent_history_allowed():
            raise ValueError('This recent document is no longer available.')
        preferences = self.start_preferences.snapshot()
        def validate():
            if not start_preferences.documents([dict(uri=ident,modified=item['modified'])],preferences):
                raise ValueError('This recent document is no longer available.')
            return item
        def opened(item):
            if preferences != self.start_preferences.snapshot() or not self.recent_history_allowed(): return
            try:
                if location: self.open_explorer(str(Path(item['path']).parent))
                else: Gio.AppInfo.launch_default_for_uri(ident, Gdk.Display.get_default().get_app_launch_context())
                self.start.hide()
            except Exception as error:
                self.start.send(dict(type='error',message=str(error)))
        self.background(validate, opened, lambda error:self.start.send(dict(type='error',message=error)))

    def open_path(self, path):
        payload = self.payload()
        allowed = {p['path'] for p in payload['places'] + payload['startPlaces']}
        for group in self.store.state['groups']:
            if group['folder']:
                allowed.add(group['folder'])
            allowed.update(i['path'] for i in self.group_info(group)['items'] if i['kind'] == 'path')
        if path not in allowed or not Path(path).exists():
            raise ValueError('This shortcut is no longer available.')
        if Path(path).is_dir():
            self.open_explorer(path)
        else:
            Gio.AppInfo.launch_default_for_uri(Path(path).as_uri(), Gdk.Display.get_default().get_app_launch_context())
        self.start.hide()

    def spectrum_tick(self):
        now=time.monotonic()
        visible=[s for s in self.surfaces.values()
                 if getattr(s,'spectrum_until',0)>now and s.get_visible()
                 and s.get_window() and not s.get_window().get_state() & Gdk.WindowState.ICONIFIED]
        self.spectrum.enable(bool(visible))
        for surface in visible:surface.send(dict(type='audio-spectrum',**self.spectrum.data))
        return True

    def dispatch(self, surface, message):
        action = message.get('action')
        if not isinstance(action,str):raise ValueError('Missing action.')
        if action=='audio-spectrum' and surface.mode in ('settings','quick'):
            surface.spectrum_until=time.monotonic()+5 if message.get('enabled') is True else 0
            if not hasattr(self,'spectrum'):
                from audio_spectrum import Monitor
                self.spectrum=Monitor()
                self.connect('shutdown',lambda *_:self.spectrum.close())
                GLib.timeout_add(100,self.spectrum_tick)
        elif action=='snap-hover' and surface.mode in ('explorer','settings'):
            self.multitasking.caption_hover(surface,bool(message.get('enter')))
        elif action=='snap-layouts' and surface.mode in ('explorer','settings'):
            self.multitasking.show_surface_snap(surface)
        elif action=='window-resize' and surface.mode in ('explorer','settings'):
            edges={name.lower().replace('_','-'):getattr(Gdk.WindowEdge,name) for name in
                   ('NORTH','SOUTH','EAST','WEST','NORTH_WEST','NORTH_EAST','SOUTH_WEST','SOUTH_EAST')}
            edge=edges.get(message.get('edge'))
            if edge is None:raise ValueError('Unknown window edge.')
            if not surface.is_maximized():
                pointer=Gdk.Display.get_default().get_default_seat().get_pointer()
                _,x,y=pointer.get_position()
                surface.begin_resize_drag(edge,1,x,y,Gdk.CURRENT_TIME)
        elif action=='task-view':
            self.multitasking.show_tasks()
        elif action.startswith('settings-') and surface.mode=='settings':
            self.settings_action(surface,message)
        elif action.startswith('search-') and surface.mode=='start':
            self.search_action(surface,message)
        elif action.startswith('file-') and surface.mode=='explorer':
            self.file_action(surface, message)
        elif action.startswith('notification-') and surface.mode=='notifications':
            self.notification_action(surface,message)
        elif action.startswith('quick-') and surface.mode=='quick':
            self.quick_action(surface, message)
        elif action == 'ready':
            surface.ready = True
            surface.update()
            if surface.pending_page is not None:
                surface.send({'type': 'show', 'page': surface.pending_page})
                surface.pending_page = None
        elif action == 'launch':
            self.launch(message['id'])
        elif action == 'app-action':
            self.launch_app_action(message.get('id'), message.get('shortcut'))
        elif action in ('recent-open', 'recent-location') and surface.mode == 'start':
            self.open_recent_document(message.get('id'), action == 'recent-location')
        elif action == 'pin':
            if message['id'] not in self.apps:
                raise ValueError('Unknown application')
            self.store.pin(message['id'], bool(message['value']))
            self.broadcast()
        elif action == 'reorder':
            self.store.reorder(message['id'], message['target'])
            self.broadcast()
        elif action.startswith('start-folder-') and surface.mode=='start':
            operation=action.removeprefix('start-folder-')
            if operation=='create':self.store.create_start_folder(message['apps'],message.get('name','Folder'))
            elif operation=='rename':self.store.rename_start_folder(message['folder'],message['name'])
            elif operation=='add':self.store.move_to_start_folder(message['id'],message['folder'])
            elif operation=='remove':self.store.remove_start_folder(message['folder'])
            elif operation=='reorder':self.store.reorder_start_folder(message['folder'],message['id'],message['target'])
            else:raise ValueError('Unknown Start folder action.')
            self.broadcast()
        elif action == 'open-path':
            self.open_path(message['path'])
        elif action == 'open-computer' and surface.mode == 'start':
            self.open_explorer('::computer')
        elif action == 'start-tab' and surface.mode == 'start':
            operation = message.get('operation')
            if operation not in ('create', 'rename', 'delete', 'add', 'remove', 'move'):
                raise ValueError('Unknown tab change.')
            if operation == 'add' and message.get('value') not in self.apps:
                raise ValueError('Only installed apps can be added to a tab.')
            self.start_preferences.change('tab-' + operation, message.get('tab'), message.get('value'))
            self.start.update()
        elif action == 'start-tile-size' and surface.mode == 'start':
            self.start_preferences.change('tile', message.get('id'), message.get('size'))
            self.start.update()
        elif action == 'close':
            surface.on_delete()
        elif action == 'settings':
            self.open_settings(message.get('page','home'))
        elif action in ('session-action','lock','power') and surface.mode=='start':
            command = {'lock':'lock','power':'shutdown'}.get(action,message.get('command'))
            gnome = is_gnome()
            session_actions.validate(command)
            self.start.hide()
            def failed(error):
                self.show_start()
                self.start.send({'type':'error','message':error})
            self.background(lambda:session_actions.run(command,gnome),lambda _:None,failed)
        elif action == 'peek':
            self.peek()
        elif action == 'groups-visible':
            self.store.state['groups_visible'] = bool(message['value'])
            self.store.save()
            self.sync_groups()
        elif action == 'new-group':
            folder = None
            if message.get('folder'):
                paths = self.pick(surface, folder=True)
                if not paths:
                    return
                folder = paths[0]
            self.store.add_group(message.get('title', 'New group') if not folder else Path(folder).name, folder)
            self.sync_groups()
        elif action == 'rename-group':
            self.store.group(message['group'])['title'] = str(message['title']).strip()[:60] or 'Untitled group'
            self.store.save()
            self.broadcast()
        elif action == 'remove-group':
            # This removes a shortcut container, never files from the disk.
            self.store.state['groups'] = [g for g in self.store.state['groups'] if g['id'] != message['group']]
            self.store.save()
            self.sync_groups()
        elif action == 'add-app':
            if message['id'] not in self.apps:
                raise ValueError('Unknown application')
            self.store.add_item(message['group'], {'kind': 'app', 'id': message['id']})
            self.broadcast()
        elif action == 'add-path':
            paths = self.pick(surface, folder=bool(message.get('folder')), multiple=not message.get('folder'))
            for path in paths:
                self.store.add_item(message['group'], {'kind': 'path', 'path': path})
            self.broadcast()
        elif action == 'remove-item':
            group = self.store.group(message['group'])
            if group['folder']:
                raise ValueError('Folder contents are managed in File Explorer.')
            group['items'] = [i for i in group['items'] if i.get('id', i.get('path')) != message['id']]
            self.store.save()
            self.broadcast()
        elif action == 'collapse':
            group = self.store.group(message['group'])
            group['collapsed'] = not group['collapsed']
            self.store.save()
            self.place_group(surface, group)
            self.broadcast()
        elif action in ('move', 'resize') and surface.group_id:
            surface.drag_group(resize=action=='resize')
        elif action == 'manage':
            self.show_start('groups')
        else:
            raise ValueError('Unknown desktop action')

    def background(self, task, success, failure=None):
        future = self.workers.submit(task)
        def finished(f):
            try:
                value = f.result()
                GLib.idle_add(lambda: (success(value), False)[1])
            except Exception as error:
                if failure:
                    GLib.idle_add(lambda e=str(error): (failure(e), False)[1])
        future.add_done_callback(finished)

    def tray_snapshot(self):
        value=quick_controls.snapshot() if self.quick.get_visible() else desktop_status()
        value['unread']=notifications.has_unread()
        return value

    def refresh_status(self):
        if not self.status_pending and not self.quick_busy:
            self.status_pending=True;generation=self.status_generation
            def done(value):
                self.status_pending=False
                if generation==self.status_generation:self.accept_status(value)
            self.background(self.tray_snapshot,
                            done,lambda e:setattr(self,'status_pending',False))
        return True

    def accept_status(self,value):
        self.status=value;self.quick.update()
        if APP_ID=='local.zorin11.DesktopHub':
            from tray_icon import update_icon
            update_icon(BASE,CONFIG,value)
            notifications.write_badge(CONFIG,value)

    def show_flyout(self,surface,width,height,anchor_name='Quick settings'):
        anchor=panel_button(anchor_name)
        area=self.work_area(anchor[0],anchor[1]) if anchor else self.monitor_geometry()
        height=min(height,area.height-24)
        surface.set_size_request(width,height);surface.resize(width,height)
        x,y=area.x+area.width-width-12,area.y+area.height-height-12
        self.capture_backdrop(surface,x,y,width,height)
        surface.move(x,y);surface.show_all();surface.present()
        GLib.timeout_add(60,lambda:(surface.move(x,y),False)[1])
        surface.update()

    def show_quick(self):
        self.start.hide();self.notifications.hide()
        if self.quick.get_visible():self.quick.hide();return
        count=len(self.store.state.get('quick_tiles',quick_controls.TILES))
        self.show_flyout(self.quick,368,(490 if quick_controls.backlights() else 430)+max(0,(count+2)//3-2)*84)
        if self.quick.ready:self.quick.send({'type':'show','page':'home'})
        self.refresh_status()

    def quick_change(self,task):
        if self.quick_busy:raise ValueError('Please wait for the current change to finish.')
        self.quick_busy=True;self.status_generation+=1;self.quick.update()
        def run():
            task();value=quick_controls.snapshot();value['unread']=notifications.has_unread();return value
        def done(value):
            self.quick_busy=False;self.accept_status(value);self.refresh_settings();self.refresh_notifications()
        def failed(error):
            self.quick_busy=False;self.quick.update();self.refresh_status()
            self.quick.send({'type':'error','message':error})
        self.background(run,done,failed)

    def quick_action(self,surface,message):
        action=message['action']
        if action=='quick-settings':self.open_settings(message.get('page','home'))
        elif action in ('quick-network','quick-bluetooth','quick-audio','quick-screenshot','quick-display'):
            tool={'quick-network':'network','quick-bluetooth':'bluetooth','quick-audio':'sound',
                  'quick-screenshot':'screenshot','quick-display':'display'}[action]
            surface.hide();settings_backend.launch(tool)
        elif action=='quick-set':
            name,value=message.get('name'),message.get('value')
            if name not in ('volume','muted','wifi','bluetooth','airplane','batterySaver','dnd','output','audioPreset','stickyKeys','slowKeys','bounceKeys','mouseKeys'):
                raise ValueError('Unknown Quick Settings control.')
            self.quick_change(lambda:settings_backend.apply(name,value))
        elif action=='quick-device':
            self.quick_change(lambda:settings_backend.hardware_controls.connect_bluetooth(message.get('id'),message.get('connected')))
        elif action=='quick-brightness':
            self.quick_change(lambda:quick_controls.brightness(message.get('id'),message.get('value')))
        elif action=='quick-tiles':
            self.store.state['quick_tiles']=quick_controls.validate_tiles(message.get('tiles'))
            self.store.save();surface.update()
            if surface.get_visible():
                count=len(self.store.state['quick_tiles'])
                self.show_flyout(surface,368,(490 if quick_controls.backlights() else 430)+max(0,(count+2)//3-2)*84)
        else:raise ValueError('Unknown Quick Settings action.')

    def refresh_notifications(self):
        if not self.notifications.get_visible() or self.notification_pending or self.notification_busy:return True
        self.notification_pending=True;generation=self.notification_generation
        def done(value):
            self.notification_pending=False
            if generation==self.notification_generation:self.accept_notifications(value)
        self.background(notifications.snapshot,done,lambda e:setattr(self,'notification_pending',False))
        return True

    def accept_notifications(self,value):
        for entry in value['entries']:
            ident=entry['appId']
            if ident not in self.apps and ident+'.desktop' in self.apps:ident+='.desktop'
            entry['launchable']=ident in self.apps
            if entry['launchable']:
                entry['appId']=ident;entry['icon']=self.app_info(ident)['icon']
        self.notification_data=value;self.notifications.update()

    def show_notifications(self):
        self.start.hide();self.quick.hide()
        if self.notifications.get_visible():self.notifications.hide();return
        self.show_flyout(self.notifications,400,800,'Notification center')
        if self.notifications.ready:self.notifications.send({'type':'show','page':'home'})
        self.refresh_notifications()

    def notification_action(self,surface,message):
        action=message['action']
        if action=='notification-settings':self.open_settings('notifications');return
        if action=='notification-app':
            app=message.get('id')
            if app not in self.apps and app+'.desktop' in self.apps:app+='.desktop'
            self.launch(app);surface.hide();return
        if action not in ('notification-dismiss','notification-clear','notification-read','notification-dnd'):
            raise ValueError('Unknown notification action.')
        if self.notification_busy:raise ValueError('Please wait for the current change to finish.')
        self.notification_busy=True;self.notification_generation+=1;surface.update()
        def run():
            if action=='notification-dnd':settings_backend.apply('dnd',message.get('value'))
            else:notifications.change(action.removeprefix('notification-'),message.get('ids'))
            return notifications.snapshot()
        def done(value):
            self.notification_busy=False;self.accept_notifications(value);self.refresh_status();self.refresh_settings()
        def failed(error):
            self.notification_busy=False;surface.update();surface.send({'type':'error','message':error})
        self.background(run,done,failed)

    def open_settings(self,page='home'):
        self.start.hide();self.quick.hide();self.notifications.hide()
        surface=self.surfaces.get('settings')
        if surface is None:
            surface=Surface(self,mode='settings')
            self.surfaces['settings']=surface
            surface.set_position(Gtk.WindowPosition.CENTER)
        surface.show_all();surface.present()
        if surface.ready:surface.send({'type':'show','page':page})
        else:surface.pending_page=page
        self.refresh_settings()

    def settings_snapshot(self):
        result=settings_backend.snapshot()
        result.update(facts=settings_backend.facts(),wallpaper=wallpaper.status(),loading=False)
        result.update(startPreferences=self.start_preferences.snapshot(), recentHistoryAllowed=self.recent_history_allowed())
        return result

    def update_settings_surface(self):
        surface=self.surfaces.get('settings')
        if surface:
            display=Gdk.Display.get_default()
            self.settings_data['monitors']=[{'name':display.get_monitor(i).get_model() or 'Display',
                'x':display.get_monitor(i).get_geometry().x,
                'y':display.get_monitor(i).get_geometry().y,
                'width':display.get_monitor(i).get_geometry().width,
                'height':display.get_monitor(i).get_geometry().height,
                'scale':display.get_monitor(i).get_scale_factor(),
                'refresh':round(display.get_monitor(i).get_refresh_rate()/1000,2)} for i in range(display.get_n_monitors())]
            if is_gnome():
                try:
                    import display_details
                    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
                    state=bus.call_sync(display_details.SERVICE,display_details.PATH,display_details.SERVICE,'GetCurrentState',None,None,0,1000,None).unpack()
                    rows=display_details.parse_state(state)
                    for monitor in self.settings_data['monitors']:
                        match=next((r for r in rows if r['connector']==monitor['name']),None)
                        if match and match['resolution']:
                            monitor.update(nativeWidth=match['resolution'][0],nativeHeight=match['resolution'][1],actualScale=match['scale'])
                except GLib.Error:
                    pass
            from effects import wm_name
            self.settings_data['wobble']=('zorin-window-move-effect@zorinos.com' in Gio.Settings.new('org.gnome.shell').get_strv('enabled-extensions')) if is_gnome() else 'compiz' in wm_name()
            surface.update()

    def refresh_settings(self):
        if 'settings' not in self.surfaces or self.settings_busy or self.settings_pending:return True
        self.settings_pending=True;generation=self.settings_generation
        def done(data):
            self.settings_pending=False
            if generation==self.settings_generation:
                self.settings_data=data;self.update_settings_surface()
        def failed(error):
            self.settings_pending=False
            if 'settings' in self.surfaces:self.surfaces['settings'].send({'type':'error','message':error})
        self.background(self.settings_snapshot,done,failed)
        return True

    def settings_change(self,task):
        if self.settings_busy:raise ValueError('Please wait for the current change to finish.')
        self.settings_busy=True;self.settings_generation+=1;self.update_settings_surface()
        def run():
            task()
            return self.settings_snapshot()
        def done(data):
            self.settings_busy=False;self.settings_data=data;self.update_settings_surface();self.refresh_status()
        def failed(error):
            self.settings_busy=False;self.update_settings_surface()
            if 'settings' in self.surfaces:self.surfaces['settings'].send({'type':'error','message':error})
            self.refresh_settings()
        self.background(run,done,failed)

    def wallpaper_tick(self):
        if not self.settings_busy and wallpaper.due():self.settings_change(wallpaper.update)
        return True

    def settings_action(self,surface,message):
        action=message['action']
        if action in ('settings-move','settings-resize','settings-minimize','settings-maximize'):
            self.file_action(surface,{'action':action.replace('settings-','file-')})
        elif action=='settings-set':
            name,value=message.get('name'),message.get('value')
            self.settings_change(lambda:settings_backend.apply(name,value))
        elif action=='settings-start-preference':
            if self.settings_busy: raise ValueError('Please wait for the current change to finish.')
            operation, key, value = message.get('operation'), message.get('key'), message.get('value')
            if operation == 'add':
                if key not in ('roots','exclusions'): raise ValueError('Unknown folder list.')
                chosen = self.pick(surface, folder=True)
                if not chosen: return
                value = chosen[0]
            self.start_preferences.change(operation,key,value)
            if operation == 'style':
                # The window is sized per style when it opens, so close it now.
                self.start.hide()
            if operation in ('style', 'layout', 'columns', 'show-recommended'):
                self.start.update()
            self.settings_generation += 1
            self.search_action(self.start,dict(action='search-cancel'))
            self.refresh_recent_documents(invalidate=True)
            self.settings_data.update(startPreferences=self.start_preferences.snapshot(),recentHistoryAllowed=self.recent_history_allowed())
            self.update_settings_surface()
        elif action=='settings-tool':settings_backend.launch(message.get('tool'))
        elif action=='settings-device':
            self.settings_change(lambda:settings_backend.hardware_controls.connect_bluetooth(message.get('id'),message.get('connected')))
        elif action=='settings-refresh':self.refresh_settings()
        elif action=='settings-effects':
            if is_gnome():subprocess.Popen(['gnome-extensions','prefs','zorin-window-move-effect@zorinos.com'])
            else:subprocess.Popen(['/usr/bin/python3',str(BASE/'effects.py')])
        elif action=='settings-explorer':self.open_explorer('::computer')
        elif action=='settings-launch':self.launch(message.get('id'))
        elif action=='settings-groups':
            self.store.state['groups_visible']=bool(message['value']);self.store.save();self.sync_groups();self.update_settings_surface()
        elif action=='settings-start':self.show_start()
        elif action=='settings-wallpaper-config':
            self.settings_change(lambda:wallpaper.configure(message.get('key'),message.get('value')))
        elif action=='settings-wallpaper-update':self.settings_change(wallpaper.update)
        elif action=='settings-wallpaper-use':
            def use_picture():
                if message.get('id','').startswith('zorin-'):wallpaper.configure('source','current')
                wallpaper.apply(message.get('id',''))
            self.settings_change(use_picture)
        elif action=='settings-wallpaper-restore':self.settings_change(wallpaper.restore)
        elif action=='settings-picture':
            self.modal=True
            dialog=Gtk.FileChooserDialog(title='Choose a background picture',transient_for=surface,action=Gtk.FileChooserAction.OPEN)
            dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Choose picture',Gtk.ResponseType.OK)
            image_filter=Gtk.FileFilter();image_filter.set_name('JPEG and PNG images');image_filter.add_mime_type('image/jpeg');image_filter.add_mime_type('image/png');dialog.add_filter(image_filter)
            path=dialog.get_filename() if dialog.run()==Gtk.ResponseType.OK else None
            dialog.destroy();self.modal=False
            if path:
                def apply_picture():
                    p=Path(path)
                    if p.stat().st_size>30*1024*1024:raise ValueError('Choose an image smaller than 30 MB.')
                    entry=wallpaper.remember(p.read_bytes(),{'source':'local','title':p.name,'credit':''})
                    wallpaper.configure('source','current');wallpaper.apply(entry['id'])
                self.settings_change(apply_picture)
        else:raise ValueError('Unknown Settings action.')

    def open_explorer(self, location='::home'):
        self.notifications.hide()
        self.quick.hide()
        if location.startswith('computer:'):
            location='::computer'
        parsed=urlparse(location)
        if parsed.scheme and (parsed.scheme!='file' or parsed.netloc not in ('','localhost')):
            subprocess.Popen(['nautilus' if is_gnome() else 'thunar',location]);return
        if location.startswith('file://'):
            location = unquote(urlparse(location).path)
        self.start.hide()
        surface = Surface(self, mode='explorer')
        self.surfaces[str(id(surface))] = surface
        surface.set_position(Gtk.WindowPosition.CENTER)
        surface.show_all()
        surface.present()
        self.load_folder(surface, location)

    def load_folder(self, surface, location, hidden=False):
        if location != surface.location:
            surface.preview_current = None
            surface.preview_waiting = None
        surface.request_id += 1
        request = surface.request_id
        surface.send({'type':'file-loading'}) if surface.ready else None
        def loaded(data):
            if request != surface.request_id or str(id(surface)) not in self.surfaces:
                return
            surface.location = data['path']
            surface.file_state = dict(data, hidden=hidden)
            surface.set_title(data['title']+' — File Explorer')
            surface.update()
            file_thumbnails.prefetch(self, surface)
            if surface.file_monitor:
                surface.file_monitor.cancel()
            if not location.startswith('::'):
                surface.file_monitor = Gio.File.new_for_path(data['path']).monitor_directory(Gio.FileMonitorFlags.NONE,None)
                def changed(*args):
                    if getattr(surface,'monitor_refresh',0):
                        GLib.source_remove(surface.monitor_refresh)
                    def refresh():
                        surface.monitor_refresh=0
                        self.load_folder(surface,surface.location,hidden)
                        return False
                    surface.monitor_refresh=GLib.timeout_add(350,refresh)
                surface.file_monitor.connect('changed',changed)
        def failed(error):
            if request==surface.request_id:
                surface.send({'type':'error','message':error})
                surface.send({'type':'file-loaded'})
        self.background(lambda: explorer.listing(location,hidden),loaded,failed)

    def preview_file(self, surface, request):
        surface.preview_current = request
        surface.preview_waiting = request
        if getattr(surface,'preview_busy',False):return
        self.start_preview(surface)

    def start_preview(self, surface):
        request = surface.preview_waiting
        surface.preview_waiting = None
        if not request:return
        surface.preview_busy = True
        def done(result):
            surface.preview_busy = False
            if surface not in self.surfaces.values():return
            if surface.preview_current == request and surface.location == request['location']:
                surface.send({'type':'file-preview','id':request['id'],'result':result})
            if surface.preview_waiting:self.start_preview(surface)
        self.background(lambda:file_preview.read(request['path']),done,
                        lambda _:done(file_preview.unavailable('This file could not be previewed.')))

    def search_action(self,surface,message):
        action=message['action']
        if action in ('search-query','search-cancel'):
            if getattr(surface,'search_cancel',None):surface.search_cancel.set()
            surface.search_results={};surface.preview_current=surface.preview_waiting=None
            surface.search_waiting=None
            if action=='search-cancel':return
            query=message.get('query','')
            if not isinstance(query,str):raise ValueError('Enter a search query.')
            surface.search_waiting=dict(id=message.get('id'),query=query[:160])
            if not getattr(surface,'search_busy',False):self.start_search(surface)
        elif action=='search-preview-cancel':
            surface.preview_current=surface.preview_waiting=None
        else:
            item=getattr(surface,'search_results',{}).get(message.get('key'))
            if not item:raise ValueError('Search again to use this result.')
            if action=='search-app-details' and item['kind']=='app':
                app=self.apps.get(item['id'])
                desktop_file=app.get_filename() if app and hasattr(app,'get_filename') else None
                self.background(lambda:app_details.details(desktop_file),
                                lambda result:surface.send(dict(type='app-details',key=item['key'],details=result)),
                                lambda _:surface.send(dict(type='app-details',key=item['key'],details={})))
            elif action=='search-preview' and item['kind']=='file':
                self.preview_file(surface,dict(path=item['path'],id=message.get('id'),location=surface.location))
            elif action in ('search-open','search-location'):
                if item['kind']=='app':self.launch(item['id'])
                elif item['kind']=='setting':self.open_settings(item['id'])
                else:
                    path=Path(item['path'])
                    if not path.exists() or path.is_symlink():raise ValueError('This search result is no longer available.')
                    if action=='search-location':self.open_explorer(str(path.parent))
                    elif path.is_dir():self.open_explorer(str(path))
                    else:Gio.AppInfo.launch_default_for_uri(path.as_uri(),Gdk.Display.get_default().get_app_launch_context())
                    self.start.hide()
            else:raise ValueError('Unknown search action.')

    def start_search(self,surface):
        request=surface.search_waiting;surface.search_waiting=None
        if not request:return
        surface.search_busy=True;cancel=threading.Event();surface.search_cancel=cancel
        apps=[self.app_info(ident) for ident in self.apps]
        preferences=self.start_preferences.snapshot()
        roots=preferences['roots']
        immediate=unified_search.search(request['query'],apps,[],cancel)
        immediate['scope']=roots
        surface.search_results={item['key']:item for item in immediate['results']}
        surface.send(dict(type='search-results',id=request['id'],searching=True,**immediate))
        def done(result):
            surface.search_busy=False
            if not cancel.is_set():
                surface.search_results={item['key']:item for item in result['results']}
                surface.send(dict(type='search-results',id=request['id'],**result))
            if surface.search_waiting:self.start_search(surface)
        self.background(lambda:unified_search.search(request['query'],apps,roots,cancel,exclusions=preferences['exclusions']),done,
                        lambda error:done(dict(results=[],limited=False,scope=roots,error=error)))

    def start_transfer(self,surface,paths,destination,cut):
        if getattr(surface,'transfer',None) and surface.transfer.active:
            raise ValueError('Finish or cancel the current transfer before pasting again.')
        if sum(bool(getattr(s,'transfer',None) and s.transfer.active) for s in self.surfaces.values())>=2:
            raise ValueError('Two transfers are already active. Finish one before starting another.')
        clipboard_before=self.copied_files
        def update(data):
            def deliver():
                if data['active'] is False and cut and self.copied_files==clipboard_before:
                    remaining=[p for p in paths if os.path.lexists(p)]
                    self.copied_files=(remaining,bool(remaining),'\n'.join(Path(p).as_uri() for p in remaining))
                if surface not in self.surfaces.values() or getattr(surface,'transfer',None) is not job:return False
                surface.send(dict(type='file-transfer',transfer=data))
                if not data['active']:
                    self.load_folder(surface,surface.location,bool((surface.file_state or {}).get('hidden')))
                return False
            GLib.idle_add(deliver)
        job=file_transfer.Transfer(paths,destination,cut,update);surface.transfer=job;job.start()

    def file_action(self, surface, message):
        action = message['action']
        if action.startswith('file-transfer-'):
            job=getattr(surface,'transfer',None)
            if not job or message.get('id')!=job.id:raise ValueError('This transfer is no longer available.')
            operation=action.removeprefix('file-transfer-')
            if operation=='cancel':job.cancel()
            elif operation=='pause':job.pause(message.get('value'))
            elif operation=='answer':job.respond(message.get('question'),message.get('choice'),message.get('all',False))
            elif operation=='dismiss' and not job.active:surface.transfer=None
            else:raise ValueError('Unknown transfer action.')
        elif action == 'file-preview-cancel':
            surface.preview_current = surface.preview_waiting = None
        elif action == 'file-preview':
            path=message.get('path')
            if not any(e['path']==path and not e['folder'] for e in (surface.file_state or {}).get('entries',[])):
                raise ValueError('Select a file in the current folder to preview.')
            self.preview_file(surface,dict(path=path,id=message.get('id'),location=surface.location))
        elif action == 'file-navigate':
            self.load_folder(surface,str(message['path']),bool(message.get('hidden')))
        elif action == 'file-open':
            path=Path(message['path'])
            if path.is_dir():
                self.load_folder(surface,str(path),bool(message.get('hidden')))
            else:
                Gio.AppInfo.launch_default_for_uri(path.as_uri(),Gdk.Display.get_default().get_app_launch_context())
        elif action == 'file-open-with':
            self.modal=True
            dialog=Gtk.AppChooserDialog.new(surface,Gtk.DialogFlags.MODAL,Gio.File.new_for_path(message['path']))
            dialog.get_widget().set_show_all(True)
            if dialog.run()==Gtk.ResponseType.OK:
                app=dialog.get_app_info()
                if app:
                    app.launch([Gio.File.new_for_path(message['path'])],Gdk.Display.get_default().get_app_launch_context())
            dialog.destroy()
            self.modal=False
        elif action in ('file-network','file-trash-view'):
            subprocess.Popen(['nautilus' if is_gnome() else 'thunar','network:///' if action=='file-network' else 'trash:///'])
        elif action == 'file-native':
            subprocess.Popen(['nautilus' if is_gnome() else 'thunar',surface.location if not surface.location.startswith('::') else str(Path.home())])
        elif action in ('file-minimize','file-maximize','file-move','file-resize'):
            if action=='file-minimize':surface.iconify()
            elif action=='file-maximize':
                surface.unmaximize() if surface.is_maximized() else surface.maximize()
            else:
                pointer=Gdk.Display.get_default().get_default_seat().get_pointer()
                _,x,y=pointer.get_position()
                if action=='file-move':surface.begin_move_drag(1,x,y,Gdk.CURRENT_TIME)
                else:surface.begin_resize_drag(Gdk.WindowEdge.SOUTH_EAST,1,x,y,Gdk.CURRENT_TIME)
        elif action=='file-copy-path':
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text('\n'.join(message['paths']),-1)
            surface.send({'type':'notice','message':'Path copied'})
        elif action in ('file-copy','file-cut'):
            paths=[str(Path(p).absolute()) for p in message['paths']]
            text='\n'.join(Path(p).as_uri() for p in paths)
            self.copied_files=(paths,action=='file-cut',text)
            if not Gtk.selection_owner_set(self.clipboard_owner,Gdk.SELECTION_CLIPBOARD,Gdk.CURRENT_TIME):
                raise RuntimeError('Could not copy files to the clipboard.')
            surface.send({'type':'notice','message':f'{len(paths)} item(s) ready to paste'})
        else:
            destination=surface.location
            selected=message.get('paths',[])
            if action == 'file-trash':
                if not selected:return
                dialog=Gtk.MessageDialog(transient_for=surface,modal=True,message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.OK_CANCEL,text=f'Move {len(selected)} item(s) to the Recycle Bin?')
                dialog.format_secondary_text('\n'.join(Path(p).name for p in selected[:8]))
                dialog.set_default_response(Gtk.ResponseType.CANCEL)
                accepted=dialog.run()==Gtk.ResponseType.OK
                dialog.destroy()
                if not accepted:return
                task=lambda: explorer.trash(selected)
            elif action=='file-new-folder':
                task=lambda: explorer.create_folder(destination,message['name'])
            elif action=='file-rename':
                task=lambda: explorer.rename(message['path'],message['name'])
            elif action=='file-rename-drive' and destination=='::computer':
                task=lambda: explorer.rename_drive(message['path'],message['name'])
            elif action=='file-paste':
                clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                paths,cut,text=self.copied_files
                if not text or clipboard.wait_for_text()!=text:
                    paths,cut=explorer.clipboard_read(clipboard)
                if not paths:raise ValueError('Copy files before pasting.')
                self.start_transfer(surface,paths,destination,cut)
                return
            else:
                raise ValueError('Unknown file action')
            surface.send({'type':'notice','message':'Working…'})
            def done(result):
                if str(id(surface)) not in self.surfaces:return
                surface.send({'type':'notice','message':'Done'})
                self.load_folder(surface,surface.location, bool((surface.file_state or {}).get('hidden')))
            self.background(task,done,lambda e:surface.send({'type':'error','message':e}))

    def diagnostics(self, path):
        report = {'apps': len(self.apps), 'pins': len(self.store.state['pins']),
            'groups': len(self.store.state['groups']), 'surfaces': {}, 'timestamp': time.time()}
        pending = list(self.surfaces.items())
        def done(web, result, key):
            try:
                value = web.evaluate_javascript_finish(result)
                report['surfaces'][key] = json.loads(value.to_string())
            except Exception as error:
                report['surfaces'][key] = {'error': str(error)}
            if len(report['surfaces']) == len(pending):
                Path(path).write_text(json.dumps(report, indent=2))
        for key, surface in pending:
            surface.js('JSON.stringify({title:document.title,ready:!!window.desktopState,mode:window.desktopState?.mode,buttons:document.querySelectorAll("button").length,images:document.images.length,brokenImages:[...document.images].filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src),errors:window.desktopErrors||[],text:document.body.innerText.slice(0,1600)})',
                lambda web, result, data, key=key: done(web, result, key))
        return False

    def export_previews(self, directory):
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        def done(web, result, key):
            try:
                web.get_snapshot_finish(result).write_to_png(str(destination/(key+'.png')))
            except Exception as error:
                print('Preview export:', error, file=sys.stderr, flush=True)
        for key, surface in self.surfaces.items():
            if not surface.get_visible():
                continue
            surface.web.get_snapshot(WebKit2.SnapshotRegion.VISIBLE,
                WebKit2.SnapshotOptions.TRANSPARENT_BACKGROUND, None,
                lambda web,result,data,key=key: done(web,result,key), None)
        return False


if __name__ == '__main__':
    if is_gnome() and '--quit' not in sys.argv:
        from gnome_bridge import call
        deadline=time.monotonic()+(20 if '--background' in sys.argv else 3)
        while True:
            try:call('snapshot');break
            except Exception:
                if time.monotonic()>=deadline:
                    raise SystemExit('The Windows 11 GNOME extension is not loaded. Sign out and sign back in, and enable Windows 11 Desktop Companion in Extensions.')
                time.sleep(.2)
    raise SystemExit(Hub().run(sys.argv))
