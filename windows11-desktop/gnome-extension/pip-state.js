// Browser picture-in-picture windows, as a pure decision.
//
// On X11 a browser asks the window manager to keep its picture-in-picture
// window on top. Wayland has no way to ask, so under GNOME on Wayland the
// video drops behind the next window you click. Brave, Chrome, Edge and the
// other Chromium browsers title that window "Picture in picture"; Firefox and
// its forks use "Picture-in-Picture". A normal browser window always carries
// the browser's name in its title, so the exact title is enough to tell them
// apart, and the browser check keeps other apps' windows out.

const BROWSER = /brave|chrom|firefox|mozilla|librewolf|waterfox|floorp|zen|edge|vivaldi|opera|yandex/i;

/**
 * @param {object} w title, wmClass (the Wayland app ID or X11 class) and
 *   appId (sandboxed or GTK application ID), any of which may be null.
 * @returns {boolean} whether the window is a browser's picture-in-picture video.
 */
export function isPictureInPicture({title, wmClass, appId}) {
    if (typeof title !== 'string')
        return false;
    const name = title.trim().toLowerCase().replace(/[-\s]+/g, ' ');
    return name === 'picture in picture' && [wmClass, appId].some(id => typeof id === 'string' && BROWSER.test(id));
}
