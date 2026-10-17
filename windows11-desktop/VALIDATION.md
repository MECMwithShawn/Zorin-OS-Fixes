# Validation — 2026-10-17

Validated on Zorin OS 18.1 Lite, Xfce 4.20, X11, Ubuntu noble, x86-64.

- Six persistence/model tests, five file-operation tests, and six portability tests passed.
- The complete companion was installed in a separate X11 display and D-Bus session with a disposable home directory, panel **4**, and deliberately nonstandard plugin IDs. It correctly found and styled the panel, installed the full-size status tray and terminal integration, upgraded without duplicating plugins, and restored **every managed file and Xfconf value** exactly. The original backup survived the upgrade.
- The laptop battery preservation branch is covered by the panel-layout tests. Physical laptop hardware has not yet been tested.
- A clean per-user installation of the downloaded tools and Cascadia fonts passed in a disposable home directory. PowerShell 7.6.7 executed on Linux; WezTerm reported its pinned version, parsed the configuration, and loaded Cascadia Mono. The real Xfce preferred-terminal helper launched a disposable command and preserved arguments containing spaces and a semicolon.
- The Compiz wobbly plugin loaded in a separate Xephyr display. Its independent watchdog restored Xfwm after the unconfirmed preview while retaining the application window. The user subsequently enabled the effect on the main desktop. Zorin's inherited `GTK_CSD=1` initially broke the decorator's backing pixmaps; setting `GTK_CSD=0` only for Compiz and its decorator fixed this. Regular applications retain their original client-side decoration setting.
- The live tray rendered the Microsoft Fluent network/speaker pair at 48×20 px. Clicking it opened the working Quick Settings surface. GTK CSS parsed successfully.
- The existing Start/Explorer/Quick Settings interface reported no broken images or JavaScript errors. Earlier live WebKit checks covered file creation, rename, clipboard copy/paste, Start alignment, and Explorer maximize/restore.

## Caption and Fluent polish pass

- The original Metacity caption theme loaded through the installed `libmetacity` parser. Its native Compiz frame renders with extents `1,1,32,1`; the Xfwm counterpart and GTK3 caption CSS were also visually checked. The nested Xephyr software renderer emitted texture warnings, so the main NVIDIA desktop was used to verify the final Compiz appearance.
- Explorer/Quick Settings browser interaction checks passed with the new Fluent glyphs. The live WebKit Explorer loaded all drive icons at 48 px, kept capacity bars clear of their icons, and maximized/restored correctly under Compiz.
- Start was centered exactly over its button (0 px center difference), with a 12 px taskbar gap. Quick Settings retained 12 px right and taskbar margins.
- A second isolated install/upgrade/restore run included the new caption assets and settings. Every managed file and Xfconf value returned to its original state; the first recovery record survived the upgrade. Network-applet process restart was stubbed in this session test to avoid touching the real desktop's agent.
- The live recovery record matched all 208 managed files and 53 Xfconf settings. The confirmed wobble setting remained enabled. Six portability tests and five file-operation tests also passed.

The session test uses the installed operating system and packages with a clean test home; it is not a test of a freshly installed Zorin ISO. A real laptop check is still needed for its GPU, display scaling, battery, and suspend/resume behavior. Compiz stays optional because graphics-driver behavior can differ between machines.
