// The installed Zorin desktop still owns icons, drag/drop and file operations.
import GLib from 'gi://GLib';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export default class DesktopMenu extends Extension {
    enable() {
        this._injections = new InjectionManager();
        this._ding = null;
        this._signal = Main.extensionManager.connect('extension-state-changed', (_, extension) => {
            if (extension.uuid === 'zorin-desktop-icons@zorinos.com') this._sync();
        });
        if (Main.layoutManager._startingUp) {
            this._startup = Main.layoutManager.connect('startup-complete', () => {
                this._idle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    this._idle = 0;
                    this._sync();
                    return GLib.SOURCE_REMOVE;
                });
            });
        }
        this._sync();
    }
    _sync() {
        const ding = Main.extensionManager.lookup('zorin-desktop-icons@zorinos.com')?.stateObj;
        if (!ding?.data?.isEnabled || ding === this._ding) return;
        if (typeof ding.launchDesktop !== 'function' || typeof ding.doRelaunch !== 'function')
            throw new Error('This version of Zorin Desktop Icons is not supported.');
        if (!this._overlayReady()) {
            // Never stop a working desktop for an adapter that cannot launch.
            console.warn(`${this.uuid}: desktop menu adapter is incomplete; keeping Zorin's desktop.`);
            return;
        }
        this._ding = ding;
        const overlay = this.path;
        const ready = () => this._overlayReady();
        this._injections.overrideMethod(ding, 'launchDesktop', original => function (...args) {
            // A restore or partial copy can remove the vendor links after login;
            // relaunch Zorin's own desktop instead of respawning a missing file.
            if (!ready()) return original.apply(this, args);
            // Only the synchronous launch sees the overlay. Zorin's process
            // supervisor, monitor geometry and Wayland client ownership remain intact.
            const descriptor = Object.getOwnPropertyDescriptor(this, 'path');
            Object.defineProperty(this, 'path', {value: overlay, configurable: true});
            try { return original.apply(this, args); }
            finally {
                if (descriptor) Object.defineProperty(this, 'path', descriptor);
                else delete this.path;
            }
        });
        ding.killCurrentProcess();
        ding.doRelaunch(100);
    }
    _overlayReady() {
        // file_test follows the installer's links, so removed or dangling ones fail.
        return ['app/ding.js', 'app/desktopManager.js', 'app/zorinOriginal/desktopManager.js',
            'schemas/gschemas.compiled'].every(file => GLib.file_test(
            GLib.build_filenamev([this.path, file]), GLib.FileTest.IS_REGULAR));
    }
    disable() {
        if (this._signal) Main.extensionManager.disconnect(this._signal);
        this._signal = 0;
        if (this._startup) Main.layoutManager.disconnect(this._startup);
        if (this._idle) GLib.source_remove(this._idle);
        this._startup = this._idle = 0;
        this._injections?.clear();
        if (this._ding?.data?.isEnabled) {
            this._ding.killCurrentProcess();
            this._ding.doRelaunch(100);
        }
        this._ding = null;
    }
}
