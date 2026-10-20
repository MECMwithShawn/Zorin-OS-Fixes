// Session-only LauncherEntry progress. No file paths, commands or saved history.
export class ProgressState {
    constructor() { this.entries = new Map(); this.serial = 0; }
    update(sender, uri, values) {
        if (typeof sender !== 'string' || !sender.startsWith(':') ||
            typeof uri !== 'string' || !/^application:\/\/[^/\s]{1,240}\.desktop$/.test(uri)) return false;
        const app = uri.slice('application://'.length), key = `${sender}/${app}`;
        if (!this.entries.has(key) && this.entries.size >= 256) return false;
        const next = {...(this.entries.get(key) || {sender, app, value: 0, visible: false})};
        let changed = false;
        if (typeof values?.progress === 'number' && Number.isFinite(values.progress)) {
            next.value = Math.max(0, Math.min(1, values.progress)); changed = true;
        }
        if (typeof values?.['progress-visible'] === 'boolean') {
            next.visible = values['progress-visible']; changed = true;
        }
        if (!changed) return false;
        next.serial = ++this.serial; this.entries.set(key, next); return true;
    }
    removeSender(sender) {
        let changed = false;
        for (const [key, row] of this.entries) if (row.sender === sender) {
            this.entries.delete(key); changed = true;
        }
        return changed;
    }
    get(app) {
        // Independent producers may report the same app; hiding one leaves the others intact.
        return [...this.entries.values()].filter(r => r.app === app && r.visible)
            .sort((a, b) => b.serial - a.serial)[0] || null;
    }
}
