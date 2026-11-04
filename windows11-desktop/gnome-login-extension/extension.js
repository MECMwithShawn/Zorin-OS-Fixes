import Clutter from 'gi://Clutter';
import GDesktopEnums from 'gi://GDesktopEnums';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GnomeDesktop from 'gi://GnomeDesktop';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import {LoginDialog} from 'resource:///org/gnome/shell/gdm/loginDialog.js';
import * as AuthPrompt from 'resource:///org/gnome/shell/gdm/authPrompt.js';
import {formatDateWithCFormatString} from 'resource:///org/gnome/shell/misc/dateUtils.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Layout from 'resource:///org/gnome/shell/ui/layout.js';

// The login screen can't read a home folder; lockscreen.py publishes its photo here.
const PICTURE = '/var/lib/zorin11-login/background.jpg';

// Presentation only: no verifier, password entry or session start is replaced.
// Without the picture it keeps GNOME's own background, so login never depends on it.
export default class LoginScreen extends Extension {
    enable() {
        this._group = null; this._clock = null; this._dialog = null;
        this._backgrounds = []; this._chosen = false; this._idle = 0;
        this._monitors = Main.layoutManager.connect('monitors-changed', () => this._renderBackground());
        const owner = this;
        this._injections = new InjectionManager();
        this._injections.overrideMethod(LoginDialog.prototype, '_init', original => function (...args) {
            original.call(this, ...args);
            try { owner._attach(this); } catch (e) { console.error(`Axentra login screen: ${e.message}`); }
        });
        for (const method of ['_showUserList', '_loadUserList']) {
            this._injections.overrideMethod(LoginDialog.prototype, method, original => function (...args) {
                const result = original.call(this, ...args);
                owner._chooseOnlyUser(this);
                return result;
            });
        }
        const current = Main.screenShield?._dialog;
        if (current instanceof LoginDialog) {
            this._attach(current);
            this._chooseOnlyUser(current);
        }
    }
    _attach(dialog) {
        this._dialog = dialog;
        dialog.add_style_class_name('zorin11-login');
        this._logoId = dialog._logoBin.connect('notify::visible', () => {
            if (dialog._logoBin.visible) dialog._logoBin.hide();
        });
        dialog._logoBin.hide();
        // The clock replaces the taskbar date while the sign-in page is showing.
        Main.panel.statusArea.dateMenu?.container.hide();
        this._group = new St.Widget({layout_manager: new Clutter.FixedLayout(), reactive: false,
            x_expand: true, y_expand: true});
        dialog.get_parent().insert_child_at_index(this._group, 0);
        this._renderBackground();
        this._addClock();
    }
    _picture() {
        const file = Gio.File.new_for_path(PICTURE);
        return file.query_exists(null) ? file : null;
    }
    _renderBackground() {
        for (const widget of this._backgrounds) widget.destroy();
        this._backgrounds = [];
        const file = this._group ? this._picture() : null;
        if (!file) return;
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        for (const monitor of Main.layoutManager.monitors) {
            const widget = new St.Widget({x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height,
                reactive: false, effect: new Shell.BlurEffect({brightness: .72, radius: 30 * scale})});
            const background = new Meta.Background({meta_display: global.display});
            background.set_file(file, GDesktopEnums.BackgroundStyle.ZOOM);
            const actor = new Meta.BackgroundActor({meta_display: global.display, monitor: monitor.index,
                request_mode: Clutter.RequestMode.CONTENT_SIZE});
            actor.content.background = background;
            widget.add_child(actor);
            this._group.add_child(widget);
            this._backgrounds.push(widget);
        }
    }
    _addClock() {
        this._clock = new St.Widget({layout_manager: new Clutter.BinLayout(), reactive: false});
        this._clock.add_constraint(new Layout.MonitorConstraint({primary: true}));
        const box = new St.BoxLayout({vertical: true, style_class: 'zorin11-login-clock',
            x_expand: true, y_expand: true, x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.START});
        this._time = new St.Label({style_class: 'zorin11-login-time', x_align: Clutter.ActorAlign.CENTER});
        this._date = new St.Label({style_class: 'zorin11-login-date', x_align: Clutter.ActorAlign.CENTER});
        box.add_child(this._time); box.add_child(this._date);
        this._clock.add_child(box);
        this._group.add_child(this._clock);
        this._wallClock = new GnomeDesktop.WallClock({time_only: true});
        this._wallClockId = this._wallClock.connect('notify::clock', () => this._updateClock());
        this._updateClock();
    }
    _updateClock() {
        this._time.text = this._wallClock.clock;
        this._date.text = formatDateWithCFormatString(new Date(), '%A, %B %-d');
    }
    // Windows goes straight to the password box for a lone account. This is a
    // single click on that account; Cancel still returns to the full list.
    _chooseOnlyUser(dialog) {
        if (this._chosen || this._idle) return;
        this._idle = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._idle = 0;
            const list = dialog._userList;
            if (this._chosen || dialog._disableUserList || !dialog._userListLoaded || list.numItems() !== 1 ||
                dialog._user || dialog._authPrompt.verificationStatus !== AuthPrompt.AuthPromptStatus.NOT_VERIFYING)
                return GLib.SOURCE_REMOVE;
            this._chosen = true;
            list._onItemActivated(Object.values(list._items)[0]);
            return GLib.SOURCE_REMOVE;
        });
    }
    disable() {
        this._injections.clear();
        Main.layoutManager.disconnect(this._monitors);
        if (this._idle) GLib.source_remove(this._idle);
        this._idle = 0;
        if (this._wallClockId) this._wallClock.disconnect(this._wallClockId);
        this._wallClockId = 0; this._wallClock = null;
        this._group?.destroy();
        this._group = this._clock = null; this._backgrounds = [];
        if (this._dialog) {
            this._dialog.remove_style_class_name('zorin11-login');
            this._dialog._logoBin.disconnect(this._logoId);
            this._dialog._updateLogo();
            Main.panel.statusArea.dateMenu?.container.show();
            this._dialog = null;
        }
    }
}
