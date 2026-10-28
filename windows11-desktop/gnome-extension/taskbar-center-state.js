// Windows 11 taskbar centering for Zorin Taskbar, as pure decisions.
//
// 'centerMonitor' keeps the apps on the screen's centre line, but Zorin
// Taskbar then limits them to the width minus twice the tray, so a crowded
// tray or a large display scale clips icons. 'centered' uses all the space
// beside the tray but sits off-centre. Use the screen centre while it fits
// and the free space when it does not, as Windows 11 does. In the free space
// the group is then nudged towards the screen centre as far as the tray allows.

export const CENTER_ELEMENTS = ['leftBox', 'showAppsButton', 'activitiesButton', 'taskbar'];
export const CENTERED_MODES = ['centered', 'centerMonitor'];
// Extra room needed before returning to the screen centre, so a fence-post
// fit does not flip back and forth.
export const MARGIN = 24;
// Space kept between the nudged apps group and its neighbours.
export const GAP = 8;

/**
 * @param {object} s mode, overflow (apps are clipped/scrollable), width of
 *   the panel, pad (panel end padding), groupStart/groupEnd (allocated apps
 *   group), prevEnd/nextStart (neighbouring groups, or null).
 * @returns {'centered'|'centerMonitor'|null} the mode to switch to, if any.
 */
export function decide(s) {
    if (s.mode === 'centerMonitor')
        return s.overflow ? 'centered' : null;
    if (s.mode !== 'centered' || s.overflow)
        return null;
    const size = s.groupEnd - s.groupStart, center = s.width / 2;
    const left = s.prevEnd ?? s.pad, right = s.nextStart ?? s.width - s.pad;
    return center - size / 2 - MARGIN >= left && center + size / 2 + MARGIN <= right ? 'centerMonitor' : null;
}

/**
 * Pixels to move a 'centered' group so it sits as close to the screen centre
 * as its neighbours allow; 0 in any other mode or when the apps are clipped.
 * Takes the same state as decide().
 */
export function shift(s) {
    if (s.mode !== 'centered' || s.overflow)
        return 0;
    const left = (s.prevEnd ?? s.pad) + (s.prevEnd === null ? 0 : GAP) - s.groupStart;
    const right = (s.nextStart ?? s.width - s.pad) - (s.nextStart === null ? 0 : GAP) - s.groupEnd;
    const wanted = s.width / 2 - (s.groupStart + s.groupEnd) / 2;
    return Math.round(Math.min(Math.max(wanted, Math.min(left, 0)), Math.max(right, 0)));
}

/** Positions with the centred elements moved to mode; null when nothing applies. */
export function withMode(positions, mode) {
    if (!Array.isArray(positions))
        return null;
    const taskbar = positions.find(p => p?.element === 'taskbar');
    if (!taskbar || !CENTERED_MODES.includes(taskbar.position) || taskbar.position === mode)
        return null;
    return positions.map(p => CENTER_ELEMENTS.includes(p.element) && CENTERED_MODES.includes(p.position)
        ? {...p, position: mode} : p);
}
