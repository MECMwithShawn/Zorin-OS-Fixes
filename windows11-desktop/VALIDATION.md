# Validation — 2026-10-17

Validated on Zorin OS 18.1 Lite, Xfce 4.20, X11, Ubuntu noble, x86-64.

- Six persistence/model tests, five file-operation tests, and six portability tests passed.
- The complete companion was installed in a separate X11 display and D-Bus session with a disposable home directory, panel **4**, and deliberately nonstandard plugin IDs. It correctly found and styled the panel, installed the full-size status tray and terminal integration, upgraded without duplicating plugins, and restored **every managed file and Xfconf value** exactly. The original backup survived the upgrade.
- The laptop battery preservation branch is covered by the panel-layout tests. Physical laptop hardware has not yet been tested.
- A clean per-user installation of the downloaded tools and Cascadia fonts passed in a disposable home directory. PowerShell 7.6.7 executed on Linux; WezTerm reported its pinned version, parsed the configuration, and loaded Cascadia Mono. The real Xfce preferred-terminal helper launched a disposable command and preserved arguments containing spaces and a semicolon.
- The Compiz wobbly plugin loaded in a separate Xephyr display. Its independent watchdog restored Xfwm after the unconfirmed preview while retaining the application window. The user subsequently enabled the effect on the main desktop. Zorin's inherited `GTK_CSD=1` initially broke the decorator's backing pixmaps; setting `GTK_CSD=0` only for Compiz and its decorator fixed this. A native X11 probe then displayed its title bar and controls, with frame extents `6,6,29,6`, and the decorator errors stopped. Regular applications retain their original client-side decoration setting.
- The live tray rendered the Microsoft Fluent network/speaker pair at 48×20 px. Clicking it opened the working Quick Settings surface. GTK CSS parsed successfully.
- The existing Start/Explorer/Quick Settings interface reported no broken images or JavaScript errors. Earlier live WebKit checks covered file creation, rename, clipboard copy/paste, Start alignment, and Explorer maximize/restore.

The session test uses the installed operating system and packages with a clean test home; it is not a test of a freshly installed Zorin ISO. A real laptop check is still needed for its GPU, display scaling, battery, and suspend/resume behavior. Compiz stays optional because graphics-driver behavior can differ between machines.
