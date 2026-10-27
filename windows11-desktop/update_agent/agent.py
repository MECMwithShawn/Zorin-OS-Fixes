#!/usr/bin/python3
"""Axentra Update: Zorin's APT updater behind Quick Settings, with an optional tray icon."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import model
import system as scheduler

ROOT = Path(__file__).resolve().parent
PREFS = Path.home()/'.config/zorin11-hub/update-agent.json'
# Read by the desktop companion for the Quick Settings tile and Settings page.
STATUS = Path.home()/'.config/zorin11-hub/update-status.json'

if '--scan' in sys.argv:
    print(json.dumps(model.scan())); raise SystemExit

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, Gio, GLib, GdkPixbuf, AyatanaAppIndicator3 as Indicator
GLib.set_prgname('zorin11-update-agent')
GLib.set_application_name('Axentra Update')


def read_json(path, default):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return default


def date(value):
    return time.strftime('%b %d, %Y · %H:%M', time.localtime(value)) if value else 'Not recorded'


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.axentra.Update', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.busy = False
        self.report = None
        self.prefs = read_json(PREFS, {})
        self.timer = None
        self.saving = False

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        action = Gio.SimpleAction.new('open', None)
        action.connect('activate', lambda *_: self.open())
        self.add_action(action)
        self.indicator = Indicator.Indicator.new('axentra-update', str(ROOT/'update.svg'), Indicator.IndicatorCategory.SYSTEM_SERVICES)
        self.indicator.set_title('Axentra Update')
        self.show_tray_icon()
        self.menu = Gtk.Menu()
        self.summary = self.item('Checking update inventory…', None)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.item('Open Axentra Update', self.open)
        self.item('Check for updates…', self.refresh)
        self.item('Review / install updates…', self.install_updates)
        self.item('Update schedule…', self.open)
        self.item('Mute notifications for 24 hours', self.snooze)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.item('Quit tray agent', self.quit)
        self.menu.show_all(); self.indicator.set_menu(self.menu)
        GLib.timeout_add_seconds(3, lambda: (self.poll(), False)[1])
        self.timer = GLib.timeout_add_seconds(1800, self.poll)
        self.last_history = None
        GLib.timeout_add_seconds(30, self.watch_history)

    def watch_history(self):
        history=read_json(scheduler.STATE/'history.json', [])
        last=history[-1] if history else None
        if last != self.last_history:
            self.last_history=last
            if not self.busy: self.poll()
        return True

    def do_command_line(self, command):
        if '--tray' not in command.get_arguments(): self.open()
        return 0

    def item(self, label, callback):
        item = Gtk.MenuItem(label=label)
        if callback: item.connect('activate', lambda *_: callback())
        else: item.set_sensitive(False)
        self.menu.append(item); return item

    def show_tray_icon(self):
        # Quick Settings and Settings are the default entry points; the tray icon is opt-in.
        self.indicator.set_status(Indicator.IndicatorStatus.ACTIVE if self.prefs.get('tray_icon', False) else Indicator.IndicatorStatus.PASSIVE)

    def write_status(self, report):
        status = dict(count=len(report['packages']), security=sum(p['security'] for p in report['packages']),
                      reboot=report['reboot'], checked=report['checked'])
        scheduler.atomic(STATUS, (json.dumps(status)+'\n').encode(), 0o600)

    def save_prefs(self):
        scheduler.atomic(PREFS, (json.dumps(self.prefs, indent=2)+'\n').encode(), 0o600)

    def snooze(self):
        self.prefs['snooze_until'] = int(time.time())+86400
        self.save_prefs(); self.message('Notifications muted for 24 hours. Update schedules are unchanged.')

    def background(self, job, done):
        def work():
            try: result, error = job(), None
            except Exception as exc: result, error = None, str(exc)
            GLib.idle_add(done, result, error)
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        if self.busy: return True
        self.busy = True
        def finished(report, error):
            self.busy = False
            if error:
                self.summary.set_label('Update inventory unavailable')
                self.message('Could not read updates: '+error)
                return False
            self.report = report
            try: self.write_status(report)
            except OSError: pass
            count = len(report['packages'])
            text = 'Restart required' if report['reboot'] else f'{count} package updates available' if count else 'No pending APT updates'
            self.summary.set_label(text)
            self.indicator.set_icon_full('software-update-urgent' if report['reboot'] else 'software-update-available' if count else str(ROOT/'update.svg'), text)
            if model.clear_notification(report, self.prefs):
                self.save_prefs()
                self.withdraw_notification('updates')
            note = model.notification(report, self.prefs)
            if note:
                key, title, body = note
                n = Gio.Notification.new(title); n.set_body(body); n.set_default_action('app.open')
                self.send_notification('updates', n)
                self.prefs['notified'] = key; self.save_prefs()
            self.render()
            history = read_json(scheduler.STATE/'history.json', [])
            if history and history[-1]['state'] == 'failed' and self.prefs.get('failure') != history[-1]['time']:
                if self.prefs.get('notifications', True) and self.prefs.get('snooze_until', 0) <= time.time():
                    n = Gio.Notification.new('Scheduled Zorin update needs attention'); n.set_body(history[-1]['message']); n.set_default_action('app.open'); self.send_notification('update-failure', n)
                    self.prefs['failure'] = history[-1]['time']; self.save_prefs()
            return False
        self.background(lambda: json.loads(subprocess.check_output(['/usr/bin/python3', str(ROOT/'agent.py'), '--scan'], text=True, timeout=90)), finished)
        return True

    def message(self, text):
        if self.window: self.feedback.set_text(text)

    def refresh(self):
        self.open()
        if self.busy: self.message('An update check is already in progress.'); return
        self.busy = True; self.message('Refreshing package lists with Zorin’s package service…')
        try:
            from aptkit.simpleclient import SimpleAPTClient
            self.client = SimpleAPTClient(self.window)
            def done(*_):
                self.busy = False; self.message('Repository refresh completed.'); self.poll()
            def failed(error, *args):
                self.busy = False; self.message('Refresh failed or was cancelled: '+str(error))
            self.client.set_finished_callback(done)
            self.client.set_error_callback(failed)
            self.client.set_cancelled_callback(lambda *_: failed('Cancelled'))
            self.client.update_cache()
        except Exception as error:
            self.busy = False; self.message('Could not refresh: '+str(error))

    def install_updates(self):
        try: subprocess.Popen(['/usr/bin/update-manager'], start_new_session=True)
        except OSError as error: self.open(); self.message(str(error))

    def label(self, text='', css=None):
        label = Gtk.Label(label=text, xalign=0)
        label.set_line_wrap(True); label.set_max_width_chars(85)
        if css: label.get_style_context().add_class(css)
        return label

    def button(self, text, action):
        b = Gtk.Button(label=text); b.connect('clicked', lambda *_: action()); return b

    def open(self):
        if self.window: self.window.present(); return
        win = Gtk.ApplicationWindow(application=self, title='Axentra Update')
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        self.window = win
        win.set_default_size(820, 760)
        win.set_icon_from_file(str(ROOT/'update.svg'))
        win.connect('delete-event', self.close)
        css = Gtk.CssProvider()
        css.load_from_data(b'window { background: #202124; color: #f4f5f7; } .update-title { font-size: 28px; font-weight: bold; } .update-muted { color: #b8c4ce; } .update-card { background: #2b2d31; border-radius: 12px; padding: 18px; } button { padding: 8px 14px; }')
        Gtk.StyleContext.add_provider_for_screen(win.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        scroll = Gtk.ScrolledWindow(); win.add(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=24); scroll.add(box)
        header=Gtk.Box(spacing=16)
        logo=Path('/usr/share/pixmaps/zorin-logo.svg')
        self.os_logo=Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(logo),58,58,True)) if logo.is_file() else Gtk.Image.new_from_icon_name('distributor-logo',Gtk.IconSize.DIALOG)
        self.os_logo.get_accessible().set_name('Zorin OS logo')
        header.pack_start(self.os_logo,False,False,0)
        branding=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        branding.pack_start(self.label('Zorin OS Update', 'update-title'),False,False,0)
        branding.pack_start(self.label('AXENTRA  ·  Keep your desktop current, on your schedule', 'update-muted'),False,False,0)
        header.pack_start(branding,True,True,0);box.pack_start(header,False,False,0)
        self.headline = self.label('Reading update inventory…')
        self.headline.get_style_context().add_class('update-card'); box.pack_start(self.headline, False, False, 0)
        actions = Gtk.Box(spacing=8)
        actions.pack_start(self.button('Check for updates', self.refresh), False, False, 0)
        actions.pack_start(self.button('Review / install updates', self.install_updates), False, False, 0)
        box.pack_start(actions, False, False, 0)
        self.details = self.label('', 'update-muted'); box.pack_start(self.details, False, False, 0)
        self.packages = self.label()
        expander = Gtk.Expander(label='Available package updates'); expander.add(self.packages); box.pack_start(expander, False, False, 0)
        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); settings.get_style_context().add_class('update-card'); box.pack_start(settings, False, False, 0)
        settings.pack_start(self.label('Update preferences'), False, False, 0)
        self.mode = Gtk.ComboBoxText()
        for key, label in [('system','System managed — keep Zorin’s current policy'),('manual','Manual — notify, do not install automatically'),('daily','Automatic — every day'),('weekly','Scheduled — once a week')]: self.mode.append(key,label)
        settings.pack_start(self.mode, False, False, 0)
        self.scope = Gtk.ComboBoxText()
        self.scope.append('security','Existing unattended policy (normally security updates)')
        self.scope.append('all','All configured repository updates — no package removals')
        settings.pack_start(self.scope, False, False, 0)
        row = Gtk.Box(spacing=10)
        self.day = Gtk.ComboBoxText()
        for day in scheduler.DAYS: self.day.append(day, day)
        self.hour = Gtk.SpinButton.new_with_range(0,23,1); self.minute = Gtk.SpinButton.new_with_range(0,59,1)
        for widget in (self.day, self.label('Time'), self.hour, self.label(':'), self.minute): row.pack_start(widget, False, False, 0)
        settings.pack_start(row, False, False, 0)
        settings.pack_start(self.label('Local time · AC power and unmetered network required. Missed runs catch up when available. Never reboots automatically. Saving a schedule may start a missed run.', 'update-muted'), False, False, 0)
        self.policy_text = self.label('', 'update-muted'); settings.pack_start(self.policy_text, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.apply = self.button('Save update policy…', self.configure)
        self.apply.set_sensitive(not self.saving)
        row.pack_start(self.apply,False,False,0)
        self.pause = self.button('Pause 7 days…', lambda: self.configure(7))
        self.resume = self.button('Resume…', lambda: self.configure(0))
        row.pack_start(self.pause,False,False,0); row.pack_start(self.resume,False,False,0)
        settings.pack_start(row,False,False,0)
        self.notify_check = Gtk.CheckButton(label='Notify me near the clock when updates or a restart are needed')
        self.notify_check.set_active(self.prefs.get('notifications',True))
        self.notify_check.connect('toggled',self.notifications_changed)
        settings.pack_start(self.notify_check,False,False,0)
        tray=Gtk.CheckButton(label='Show a separate update icon in the tray')
        tray.set_active(self.prefs.get('tray_icon',False))
        tray.connect('toggled',self.tray_icon_changed)
        settings.pack_start(tray,False,False,0)
        startup=Gtk.CheckButton(label='Check for updates in the background when I sign in')
        startup.set_active(subprocess.run(['systemctl','--user','is-enabled','zorin11-update-agent.service'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
        startup.connect('toggled',self.startup_changed)
        settings.pack_start(startup,False,False,0)
        settings.pack_start(self.button('Software sources and native update policy', lambda: subprocess.Popen(['/usr/bin/software-properties-gtk'])),False,False,0)
        self.history = self.label('', 'update-muted')
        expander = Gtk.Expander(label='Scheduled update history'); expander.add(self.history); box.pack_start(expander, False, False, 0)
        box.pack_start(self.label('Desktop layout backups and post-update repair remain active. This agent manages APT system packages; app stores, Flatpak and firmware keep their own updaters.', 'update-muted'),False,False,0)
        self.feedback = self.label('', 'update-muted'); box.pack_start(self.feedback,False,False,0)
        self.load_policy(); self.mode.connect('changed',lambda *_: self.sensitivity())
        self.render(); win.show_all(); self.sensitivity(); win.present()

    def close(self,*_):
        self.window.destroy(); self.window=None; return True

    def notifications_changed(self,widget):
        self.prefs['notifications']=widget.get_active()
        if widget.get_active(): self.prefs['snooze_until']=0
        self.save_prefs()

    def tray_icon_changed(self,widget):
        self.prefs['tray_icon']=widget.get_active(); self.save_prefs(); self.show_tray_icon()

    def startup_changed(self,widget):
        result=subprocess.run(['systemctl','--user','enable' if widget.get_active() else 'disable','zorin11-update-agent.service'],capture_output=True,text=True)
        self.message('Background update checks saved.' if result.returncode==0 else 'Could not save background checks: '+result.stderr)

    def load_policy(self):
        config = read_json(scheduler.CONFIG, scheduler.DEFAULT)
        self.mode.set_active_id(config['mode']); self.scope.set_active_id(config['scope']); self.day.set_active_id(config['day'])
        self.hour.set_value(config['hour']); self.minute.set_value(config['minute'])
        self.policy_text.set_text('Paused until '+date(config['paused_until']) if config['paused_until']>time.time() else 'Administrator authentication is required to change system update policy.')

    def sensitivity(self):
        mode=self.mode.get_active_id(); scheduled=mode in ('daily','weekly')
        for w in (self.hour,self.minute,self.scope,self.pause,self.resume): w.set_sensitive(scheduled)
        self.day.set_sensitive(mode=='weekly')

    def configure(self, pause_days=None):
        if self.saving: return
        old=read_json(scheduler.CONFIG,scheduler.DEFAULT)
        config=dict(mode=self.mode.get_active_id(),scope=self.scope.get_active_id(),day=self.day.get_active_id(),hour=self.hour.get_value_as_int(),minute=self.minute.get_value_as_int(),paused_until=old['paused_until'] if pause_days is None else int(time.time())+pause_days*86400 if pause_days else 0)
        try: scheduler.validate(config)
        except ValueError as e: self.message(str(e)); return
        self.saving=True; self.apply.set_sensitive(False); self.message('Authenticate to save the system update policy…')
        def save():
            if not scheduler.HELPER.exists() or scheduler.HELPER.read_bytes() != (ROOT/'system.py').read_bytes():
                subprocess.run(['/usr/bin/pkexec','/usr/bin/python3','-I',str(ROOT/'system.py'),'install'],check=True)
            subprocess.run(['/usr/bin/pkexec',str(scheduler.HELPER),'configure','--config',json.dumps(config)],check=True)
        def done(result,error):
            self.saving=False
            if self.window:
                self.apply.set_sensitive(True); self.load_policy(); self.sensitivity()
                self.message('Policy was not saved: '+error if error else 'Update policy saved. No automatic restart will be performed.')
            self.poll(); return False
        self.background(save,done)

    def render(self):
        if not self.window: return
        if self.report:
            report=self.report; packages=report['packages']
            security=sum(p['security'] for p in packages)
            self.headline.set_text('Restart required — restart when you are ready' if report['reboot'] else f'{len(packages)} package updates available' if packages else 'No pending APT updates')
            self.details.set_text(f"Inventory checked: {date(report['checked'])}\nLast successful repository refresh: {date(report['refreshed'])}\n{security} security updates · {sum(p['held'] for p in packages)} held packages\n{model.policy_summary(read_json(scheduler.CONFIG, scheduler.DEFAULT), report['system_auto'])}")
            self.packages.set_text('\n'.join(p['name']+' → '+p['version']+(' · security' if p['security'] else '')+(' · held' if p['held'] else '') for p in packages[:100])+ ('\n…See the native updater for all packages.' if len(packages)>100 else '') or 'No package upgrades in the current APT cache.')
        history=read_json(scheduler.STATE/'history.json',[])
        self.history.set_text('\n'.join(date(row['time'])+' · '+row['message'] for row in reversed(history[-12:])) or 'No Axentra scheduled runs yet. Existing Zorin updates are recorded by the native updater.')


if __name__ == '__main__': App().run(sys.argv)
