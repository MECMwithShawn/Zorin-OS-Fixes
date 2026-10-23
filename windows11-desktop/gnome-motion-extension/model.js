// Pure geometry shared by the real taskbar and its native preview window.
export const PRESETS = [
    ['aurora', 'Aurora drift', 'Slow pools of accent light'],
    ['breathe', 'Breathing glow', 'A gentle rise and fall in brightness'],
    ['sweep', 'Light sweep', 'A soft highlight gliding across the bar'],
    ['edge', 'Edge ribbon', 'A fine accent line along the top edge'],
    ['halo', 'Active app halo', 'A quiet glow beneath the focused app'],
    ['off', 'Off', 'The original taskbar appearance'],
];
export function normalize(raw = {}) {
    const number = (n, fallback, min, max) => Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
    return {preset: PRESETS.some(p => p[0] === raw.preset) ? raw.preset : 'off',
        intensity: number(raw.intensity, 20, 5, 50), period: number(raw.period, 20, 8, 40),
        accent: /^#[0-9a-f]{6}$/i.test(raw.accent || '') ? raw.accent : '#60cdff',
        pauseBattery: raw.pauseBattery !== false, pauseFullscreen: raw.pauseFullscreen !== false};
}
export function pauseReason(config, state) {
    if (config.preset === 'off') return 'Off';
    if (!state.animations) return 'Paused · Reduced motion';
    if (state.locked) return 'Paused · Screen locked';
    if (state.overview) return 'Paused · Overview';
    if (config.pauseBattery && state.battery) return 'Paused · Battery power';
    if (config.pauseFullscreen && state.fullscreen) return 'Paused · Fullscreen app';
    return '';
}
export function layers(config, width, height, seconds, focus = null) {
    const c = normalize(config);
    if (!(width > 0 && height > 0) || !Number.isFinite(width + height + seconds)) return [];
    const p = ((seconds / c.period) % 1 + 1) % 1, a = c.intensity / 100;
    const wave = Math.sin(p * Math.PI * 2), soft = .65 + .35 * Math.sin(p * Math.PI * 2 - Math.PI / 2);
    const glow = (x, y, rx, ry, alpha, tone = 0) => ({x, y, rx, ry, alpha, tone, edge: false});
    switch (c.preset) {
    case 'aurora': return [glow(width * (.3 + .16 * wave), height * 1.1, width * .34, height * 2, a * .9),
        glow(width * (.72 - .14 * wave), -height * .2, width * .26, height * 1.6, a * .65, 1)];
    case 'breathe': return [glow(width / 2, height, width * .55, height * 2.8, a * soft)];
    case 'sweep': return [glow(width * (-.35 + p * 1.7), height / 2, width * .24, height * 2.3, a)];
    case 'edge': return [{...glow(width * (-.25 + p * 1.5), 1, width * .25, 1.25, Math.min(.8, a * 2.4)), edge: true}];
    case 'halo': return focus && Number.isFinite(focus.x + focus.width) && focus.width > 0
        ? [glow(focus.x + focus.width / 2, height * .85, Math.max(22, focus.width * .85), height * 1.15, a * soft * 1.25)] : [];
    default: return [];
    }
}
