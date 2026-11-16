// Pure rules for the glass look, kept free of Shell imports so tests can load them.
export const DEFAULTS = {enabled: true, active: 90, inactive: 85, blur: 30};

// Percentages are clamped so a bad config can never make a window vanish.
export function normalize(raw) {
    const cfg = raw && typeof raw === 'object' ? raw : {};
    const pct = (value, fallback) => {
        const n = Number(value);
        return Number.isFinite(n) ? Math.round(Math.max(60, Math.min(100, n))) : fallback;
    };
    const blur = Number(cfg.blur);
    return {
        enabled: cfg.enabled === undefined ? DEFAULTS.enabled : !!cfg.enabled,
        active: pct(cfg.active, DEFAULTS.active),
        inactive: pct(cfg.inactive, DEFAULTS.inactive),
        blur: Number.isFinite(blur) ? Math.round(Math.max(0, Math.min(80, blur))) : DEFAULTS.blur,
    };
}

// Window types follow Meta.WindowType: NORMAL 0, DIALOG 3, MODAL_DIALOG 4.
const GLASS_TYPES = new Set([0, 3, 4]);
// Axentra Terminal draws its own acrylic; doubling it would over-blur.
const OWN_EFFECT = new Set(['axentra-terminal', 'Axentra-terminal', 'AxentraTerminal']);

export function wantsGlass(info) {
    return GLASS_TYPES.has(info.type) && !info.skipTaskbar && !OWN_EFFECT.has(info.wmClass ?? '');
}

// Returns the 0-255 opacity for a window's contents; 255 means leave it solid.
export function opacityFor(cfg, info) {
    if (!cfg.enabled || info.fullscreen)
        return 255;
    return Math.round((info.focused ? cfg.active : cfg.inactive) * 255 / 100);
}
