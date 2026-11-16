import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import {ExtensionState} from 'resource:///org/gnome/shell/misc/extensionUtils.js';
import {InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const TILING_UUID = 'zorin-tiling-shell@zorinos.com';
const TILING_SCHEMA = 'org.gnome.shell.extensions.zorin-tiling-shell';
const SETTLE_TIME = 500_000; // Wayland clients may confirm their new frame asynchronously.
const FRAME_TOLERANCE = 2;

function rectangle(x, y, width, height) {
    if (![x, y, width, height].every(Number.isFinite) || width < 1 || height < 1)
        return null;
    return {x, y, width, height};
}

function previewFrame(preview) {
    return preview && rectangle(preview.innerX, preview.innerY, preview.innerWidth, preview.innerHeight);
}

function sameFrame(a, b, tolerance = 0) {
    return ['x', 'y', 'width', 'height'].every(key => Math.abs(a[key] - b[key]) <= tolerance);
}

function overlaps(a, b) {
    return a.x < b.x + b.width && b.x < a.x + a.width &&
        a.y < b.y + b.height && b.y < a.y + a.height;
}

function inside(frame, area) {
    return frame.x >= area.x && frame.y >= area.y &&
        frame.x + frame.width <= area.x + area.width &&
        frame.y + frame.height <= area.y + area.height;
}

function layoutIdentity(layout) {
    return [layout.id, ...layout.tiles.map(tile => [tile.x, tile.y, tile.width, tile.height])];
}

function tryCapture(action) {
    try {
        return action();
    } catch (error) {
        console.error('Drag Snap Groups compatibility:', error);
        return null;
    }
}

export class DragSnapGroups {
    constructor(changed = () => {}) {
        this._changed = changed;
        this._injections = new InjectionManager();
        this._groups = new Set();
        this._placements = new Map();
        this._popups = new WeakMap();
        this._pendingEdge = new Map();
        this._moving = new Set();
        this._signals = [];
        this._updateSource = 0;
        this._managerPrototype = null;
        this._popupPrototype = null;
        const schema = Gio.SettingsSchemaSource.get_default()?.lookup(TILING_SCHEMA, true);
        this._edgeSettings = schema?.has_key('edge-tiling-mode')
            ? new Gio.Settings({settings_schema: schema}) : null;

        this._connect(Main.extensionManager, 'extension-state-changed', (_, extension) => {
            if (extension.uuid === TILING_UUID)
                this._sync();
        });
        this._connect(Main.layoutManager, 'startup-complete', () => this._sync(), true);
        this._connect(Main.layoutManager, 'monitors-changed', () => {
            this._reset();
            this._sync();
        }, true);
        this._connect(global.display, 'workareas-changed', () => this._queueUpdate());
        this._connect(global.display, 'grab-op-begin', (_, window, op) => {
            if (window && (op & ~1024) === Meta.GrabOp.MOVING) {
                this._cancelEdgeDrop(window);
                this._moving.add(window);
            }
        });
        this._connect(global.display, 'grab-op-end', (_, window) => {
            if (this._moving.delete(window))
                this._queueUpdate();
        }, true);
        this._sync();
    }

    _connect(object, signal, callback, after = false) {
        const id = after ? object.connect_after(signal, callback) : object.connect(signal, callback);
        this._signals.push([object, id]);
    }

    _sync() {
        const extension = Main.extensionManager.lookup(TILING_UUID);
        const manager = extension?.state === ExtensionState.ACTIVE
            ? extension.stateObj?._tilingManagers?.[0] : null;
        const managerPrototype = manager && Object.getPrototypeOf(manager);
        const popup = manager?._tilingSuggestionsLayout;
        const popupPrototype = popup && Object.getPrototypeOf(popup);
        if (managerPrototype === this._managerPrototype && popupPrototype === this._popupPrototype)
            return;
        this._reset();
        this._injections.clear();
        this._managerPrototype = managerPrototype;
        this._popupPrototype = popupPrototype;
        const registry = this;
        if (typeof managerPrototype?._onWindowGrabEnd === 'function') {
            this._injections.overrideMethod(managerPrototype, '_onWindowGrabEnd', original => function (window) {
                const drop = tryCapture(() => registry._readDrop(this, window));
                const result = original.call(this, window);
                if (drop)
                    tryCapture(() => registry._recordDrop(this, window, drop));
                return result;
            });
        }
        if (typeof popupPrototype?._onSuggestionPress === 'function') {
            this._injections.overrideMethod(popupPrototype, '_onSuggestionPress', original =>
                function (window, card, event, candidates, monitor, preview) {
                    const group = registry._popups.get(this);
                    const rect = group ? previewFrame(preview) : null;
                    const previousTile = window.assignedTile;
                    const result = original.call(this, window, card, event, candidates, monitor, preview);
                    if (rect && this._lastTiledWindow === window)
                        tryCapture(() => registry._recordSuggestion(group, window, previousTile, rect));
                    return result;
                });
        }
    }

    _readDrop(manager, window) {
        const assist = manager._snapAssistingInfo;
        const rect = previewFrame(manager._selectedTilesPreview);
        const workspace = window.get_workspace();
        const monitor = manager._monitor?.index;
        const workArea = manager._workArea;
        if (!rect || !workspace || !Number.isInteger(monitor) || !workArea || !inside(rect, workArea))
            return null;

        // Layout IDs survive edits in Zorin Appearance. Also match the shapes
        // so later drags cannot join a group made with earlier geometry.
        let layoutKey;
        let edgeFrame = null;
        if (assist?.isSnapAssisting) {
            const layouts = manager._snapAssist?._content?._snapAssistLayouts;
            const layout = layouts?.find(item => item.layout?.id === assist.layoutId)?.layout;
            if (Array.isArray(layout?.tiles))
                layoutKey = ['top', ...layoutIdentity(layout)];
        } else if (manager._edgeTilingManager?.isPerformingEdgeTiling()) {
            const outer = manager._selectedTilesPreview?.rect;
            // A full-screen-sized edge drop covers a group without joining it.
            if (!outer || sameFrame(outer, workArea, FRAME_TOLERANCE))
                return null;
            edgeFrame = rectangle(outer.x, outer.y, outer.width, outer.height);
            if (!edgeFrame || !inside(edgeFrame, workArea))
                return null;
            const mode = this._edgeSettings?.get_string('edge-tiling-mode') ?? 'default';
            const layout = manager._edgeTilingManager._currentLayout;
            layoutKey = ['edge', mode];
            if (mode !== 'default' && Array.isArray(layout?.tiles))
                layoutKey.push(...layoutIdentity(layout));
        }
        if (!layoutKey)
            return null;
        return {
            layoutKey: JSON.stringify(layoutKey), workspace, monitor,
            workArea: rectangle(workArea.x, workArea.y, workArea.width, workArea.height),
            rect, edgeFrame, previousTile: window.assignedTile,
            previousPopup: manager._tilingSuggestionsLayout,
        };
    }

    _recordDrop(manager, window, drop) {
        if (!this._eligibleWindow(window, drop.workspace))
            return;
        const popup = manager._tilingSuggestionsLayout;
        drop.popup = popup === drop.previousPopup ? null : popup;
        if (this._hasNewTile(window, drop.previousTile))
            this._commitDrop(window, drop);
        else if (drop.edgeFrame)
            this._confirmEdgeDrop(window, drop);
    }

    _confirmEdgeDrop(window, drop) {
        this._cancelEdgeDrop(window);
        const deadline = GLib.get_monotonic_time() + SETTLE_TIME;
        // Mutter owns the move at the physical edge when it handles the same
        // grab as Tiling Shell. Wait for the exact ungapped frame before
        // recording it or displacing any other member.
        const source = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
            const area = drop.workspace.get_work_area_for_monitor(drop.monitor);
            if (window.get_compositor_private() && !window.minimized &&
                this._eligibleWindow(window, drop.workspace) && sameFrame(area, drop.workArea)) {
                if (window.get_monitor() === drop.monitor &&
                    this._matchesEdgeFrame(window, window.get_frame_rect(), drop.edgeFrame)) {
                    this._pendingEdge.delete(window);
                    tryCapture(() => this._commitDrop(window, drop));
                    return GLib.SOURCE_REMOVE;
                }
                if (GLib.get_monotonic_time() < deadline)
                    return GLib.SOURCE_CONTINUE;
            }
            this._pendingEdge.delete(window);
            return GLib.SOURCE_REMOVE;
        });
        this._pendingEdge.set(window, source);
    }

    _cancelEdgeDrop(window) {
        const source = this._pendingEdge.get(window);
        if (source) {
            GLib.source_remove(source);
            this._pendingEdge.delete(window);
        }
    }

    _commitDrop(window, drop) {
        this._reconcile();
        let group;
        for (const existing of this._groups) {
            if (existing.workspace !== drop.workspace || existing.monitor !== drop.monitor)
                continue;
            if (existing.layoutKey === drop.layoutKey && sameFrame(existing.workArea, drop.workArea))
                group = existing;
        }
        group ??= {workspace: drop.workspace, monitor: drop.monitor, workArea: drop.workArea,
            layoutKey: drop.layoutKey, members: []};
        this._record(group, window, drop.rect, drop.edgeFrame);
        if (drop.popup)
            this._popups.set(drop.popup, group);
    }

    _recordSuggestion(group, window, previousTile, rect) {
        if (this._groups.has(group) && inside(rect, group.workArea) &&
            this._eligibleWindow(window, group.workspace) && this._hasNewTile(window, previousTile))
            this._record(group, window, rect);
    }

    _eligibleWindow(window, workspace) {
        return window.get_workspace() === workspace && !window.skip_taskbar &&
            window.get_window_type() === Meta.WindowType.NORMAL;
    }

    _hasNewTile(window, previousTile) {
        return window.assignedTile && window.assignedTile !== previousTile;
    }

    _matchesEdgeFrame(window, actual, expected) {
        // Mutter can handle a drop at the physical edge itself, without gaps
        // and with a vertical maximize flag for its native half tiles.
        return !window.is_fullscreen() && !(window.get_maximized() & Meta.MaximizeFlags.HORIZONTAL) &&
            sameFrame(actual, expected, FRAME_TOLERANCE);
    }

    _record(group, window, rect, edgeFrame = null) {
        // A newly occupied slot replaces any older placement it covers. This
        // also separates layouts that overlap when switching layouts mid-drag.
        this._forget(window);
        for (const existing of this._groups) {
            if (existing.workspace !== group.workspace || existing.monitor !== group.monitor)
                continue;
            for (const member of [...existing.members]) {
                if (overlaps(rect, member.rect))
                    this._forget(member.window);
            }
        }
        this._groups.add(group);
        const member = {group, window, rect, target: rect, edgeFrame, placed: false,
            deadline: GLib.get_monotonic_time() + SETTLE_TIME, signals: []};
        member.signals.push(window.connect('unmanaged', () => this._forget(window)));
        member.signals.push(window.connect('workspace-changed', () => this._queueUpdate()));
        member.signals.push(window.connect('position-changed', () => this._queueUpdate()));
        member.signals.push(window.connect('size-changed', () => this._queueUpdate()));
        group.members.push(member);
        this._placements.set(window, member);
        this._queueUpdate();
    }

    _forget(window) {
        const member = this._placements.get(window);
        if (!member)
            return;
        this._placements.delete(window);
        for (const id of member.signals)
            window.disconnect(id);
        const {group} = member;
        group.members.splice(group.members.indexOf(member), 1);
        if (group.members.length === 0)
            this._groups.delete(group);
        this._queueUpdate();
    }

    _queueUpdate() {
        if (this._updateSource)
            return;
        this._updateSource = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._reconcile();
            this._updateSource = 0;
            this._changed();
            return GLib.SOURCE_REMOVE;
        });
    }

    _reconcile() {
        for (const group of this._groups) {
            const area = group.workspace.get_work_area_for_monitor(group.monitor);
            for (const member of [...group.members]) {
                const {window, target, edgeFrame} = member;
                if (!area || !sameFrame(area, group.workArea) ||
                    !window.get_compositor_private() || window.get_workspace() !== group.workspace) {
                    this._forget(window);
                    continue;
                }
                if (this._moving.has(window) || window.minimized)
                    continue;
                const actual = window.get_frame_rect();
                const inner = !window.is_fullscreen() && !window.get_maximized() &&
                    sameFrame(actual, target, FRAME_TOLERANCE);
                const outer = edgeFrame && this._matchesEdgeFrame(window, actual, edgeFrame);
                if (window.get_monitor() === group.monitor && (inner || outer)) {
                    const frame = rectangle(actual.x, actual.y, actual.width, actual.height);
                    if (frame)
                        member.rect = frame;
                    member.placed = true;
                } else if (GLib.get_monotonic_time() >= member.deadline || (member.placed && !edgeFrame)) {
                    this._forget(window);
                }
            }
        }
    }

    _restorable(group) {
        return this._groups.has(group) && group.members.length >= 2 && group.members.every(
            member => member.placed && !this._moving.has(member.window));
    }

    forWindow(window) {
        this._reconcile();
        const group = this._placements.get(window)?.group;
        return group && this._restorable(group) ? group : null;
    }

    restore(group, preferredWindow) {
        this._reconcile();
        if (!group || !this._restorable(group))
            return false;
        const focus = group.members.find(member => member.window === preferredWindow) ?? group.members[0];
        const stamp = global.get_current_time();
        if (group.workspace !== global.workspace_manager.get_active_workspace())
            group.workspace.activate(stamp);
        for (const {window, rect} of group.members) {
            if (window.minimized)
                window.unminimize();
            if (!sameFrame(window.get_frame_rect(), rect))
                window.move_resize_frame(true, rect.x, rect.y, rect.width, rect.height);
            window.raise();
        }
        Main.activateWindow(focus.window, stamp);
        this._queueUpdate();
        return true;
    }

    _reset() {
        for (const window of this._pendingEdge.keys())
            this._cancelEdgeDrop(window);
        for (const window of this._placements.keys())
            this._forget(window);
        this._popups = new WeakMap();
        this._moving.clear();
    }

    destroy() {
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        this._injections.clear();
        this._reset();
        if (this._updateSource)
            GLib.source_remove(this._updateSource);
        this._updateSource = 0;
    }
}
