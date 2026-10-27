// Windows 11 taskbar centering for Zorin Taskbar, as pure decisions.
//
// 'centerMonitor' keeps the apps on the screen's centre line, but Zorin
// Taskbar then limits them to the width minus twice the tray, so a crowded
// tray or a large display scale clips icons. 'centered' uses all the space
// beside the tray but sits off-centre. Use the screen centre while it fits
// and the free space when it does not, as Windows 11 does.

export const CENTER_ELEMENTS = ['leftBox', 'showAppsButton', 'activitiesButton', 'taskbar'];
export const CENTERED_MODES = ['centered', 'centerMonitor'];
// Extra room needed before returning to the screen centre, so a fence-post
// fit does not flip back and forth.
export const MARGIN = 24;

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
