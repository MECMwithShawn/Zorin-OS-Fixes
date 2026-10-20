import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

function read(path, fallback) {
    try {const [ok, bytes] = GLib.file_get_contents(path); return ok ? JSON.parse(new TextDecoder().decode(bytes)) : fallback;}
    catch (_) {return fallback;}
}
export default class AudioPresets extends Extension {
    enable() {
        this._runtime = GLib.getenv('ZORIN11_RUNTIME_DIR') || GLib.build_filenamev([GLib.get_home_dir(), '.local/share/zorin11-hub']);
        this._config = GLib.build_filenamev([GLib.get_user_config_dir(), 'zorin11-hub/audio-effects.json']);
        this._status = GLib.build_filenamev([GLib.get_user_runtime_dir(), 'zorin11-audio/status.json']);
        this._presets = read(GLib.build_filenamev([this._runtime, 'audio-presets.json']), []);
        this._menus = new Map(); this._hidden = new Map(); this._busy = false; this._alive = true;
        this._sync();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {this._sync(); return GLib.SOURCE_CONTINUE;});
    }
    _sync() {
        const panels = new Set([Main.panel, ...(global.zorinTaskbar?.panels?.map(p => p.panel) || [])]);
        const active = new Set();
        for (const panel of panels) {
            const output = panel.statusArea.quickSettings?._volumeOutput?._output;
            if (!output) continue;
            active.add(output);
            if (!this._menus.has(output)) {
                const menu = new PopupMenu.PopupSubMenuMenuItem('Audio enhancements', true);
                menu.icon.icon_name = 'multimedia-volume-control-symbolic';
                const rows = new Map();
                for (const preset of this._presets) {
                    const row = new PopupMenu.PopupMenuItem(preset.name);
                    row.connect('activate', () => this._apply(preset.id));
                    menu.menu.addMenuItem(row); rows.set(preset.id, row);
                }
                menu.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
                menu.menu.addAction('More sound settings', () => {
                    Main.panel.closeQuickSettings();
                    new Gio.Subprocess({argv: ['/usr/bin/python3', `${this._runtime}/app.py`, '--settings', 'sound'], flags: Gio.SubprocessFlags.NONE}).init(null);
                });
                output.menu.addMenuItem(menu, 1);
                this._menus.set(output, {menu, rows});
            }
            // The DSP sink is an implementation detail, not another physical output.
            for (const [id, row] of output._deviceItems || []) {
                const device = output._control.lookup_output_id(id);
                const stream = device ? output._control.lookup_stream_id(device.get_stream_id()) : null;
                if (stream?.get_name() === 'zorin11.eq.input') {
                    row.hide();
                    if (!this._hidden.has(row)) this._hidden.set(row, row.connect('destroy', () => this._hidden.delete(row)));
                }
            }
        }
        for (const [output, entry] of this._menus) {
            if (!active.has(output)) {entry.menu.destroy(); this._menus.delete(output);}
        }
        const selected = read(this._config, {}).preset || 'off';
        const preset = this._presets.find(p => p.id === selected);
        const status = read(this._status, {});
        for (const {menu, rows} of this._menus.values()) {
            menu.label.text = `Audio enhancements · ${this._busy ? 'Applying…' : preset?.name || 'Off'}`;
            for (const [id, row] of rows) {row.setOrnament(id === selected ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE); row.setSensitive(!this._busy);}
            menu.accessible_name = `Audio enhancements: ${preset?.name || 'Off'}${status.error ? ', unavailable' : ''}`;
        }
    }
    _apply(id) {
        if (this._busy || !this._presets.some(p => p.id === id)) return;
        this._busy = true; this._sync();
        try {
            const process = Gio.Subprocess.new(['/usr/bin/python3', `${this._runtime}/audio_effects.py`, '--set', id], Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            process.communicate_utf8_async(null, null, (child, result) => {
                try {
                    const [ok, , error] = child.communicate_utf8_finish(result);
                    if (this._alive && (!ok || !child.get_successful())) Main.notifyError('Audio enhancements', error.trim() || 'Could not apply this preset.');
                } catch (error) {if (this._alive) Main.notifyError('Audio enhancements', error.message);}
                if (this._alive) {this._busy = false; this._sync();}
            });
        } catch (error) {this._busy = false; this._sync(); Main.notifyError('Audio enhancements', error.message);}
    }
    disable() {
        this._alive = false;
        if (this._timer) GLib.source_remove(this._timer); this._timer = 0;
        for (const {menu} of this._menus.values()) menu.destroy(); this._menus.clear();
        for (const [row, id] of this._hidden) {row.disconnect(id); row.show();} this._hidden.clear();
    }
}
