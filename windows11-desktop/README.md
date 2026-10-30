# Windows 11 desktop for Zorin OS

**GNOME is the primary desktop.** The same installer detects Zorin 18 GNOME or Zorin Lite/Xfce and installs the matching integration. The shared companion provides the Windows 11-style Start menu, File Explorer, Settings, Quick Settings, notification/calendar flyout, Desktop Groups and multitasking UI.


## Save current window layout

Open **Win+Tab → Saved groups → Save current layout…**, enter a name, then choose **Save layout**. Choose **All displays** or a specific display in the save dialog. This captures visible, non-minimized application windows on the current desktop (up to 128 windows). A display-only layout restores only apps on that screen; it does not borrow same-app windows from your laptop and requires its saved display to be connected. Select **Restore layout** on its saved card to restore positions and maximized/fullscreen states. Saved layouts can be renamed and removed. Use the search field or **Ctrl+F** to filter by layout/app name. **Escape** cancels an unfinished name edit, then clears an active search before closing the panel.

Positions scale relative to each monitor’s work area and restored frames are contained within that area, preventing oversized windows from spilling onto an adjacent screen. If a monitor is disconnected, its windows are fitted onto the primary display. Existing windows are reused; missing apps with installed launchers can be opened. Apps without a recognized launcher must already be open. Windows that cannot be resized produce an explicit error rather than being silently omitted. Native Wayland application IDs distinguish apps that share a toolkit window class.

This saves window arrangements, not document contents: browser tabs, files and terminal sessions follow each app’s own restore settings. Multiple windows of the same app retain their slots while the companion remains running; after restarting it, matching uses application identity and window order, not individual document identity. Layout recipes are stored privately in `~/.config/zorin11-hub/snap-groups.json` and are included in desktop backups. To opt in, check **Restore automatically when I sign in** on one saved layout. The companion waits 20 seconds, defers while the desktop is locked or busy (up to two minutes), then restores once per GNOME login and reports the result. Restarting the companion does not repeat it. Uncheck the option to disable it; deleting the chosen layout also disables it. No layout is selected by default.

## Axentra Update (GNOME)

**Axentra Update** adds an update tray icon near the clock, notifications, a package inventory, restart-required status and daily/weekly automatic update schedules. Open it from the tray or Start. Its header uses the installed Zorin OS logo alongside Axentra branding. It starts in the tray without an open window; the settings window requests no main-taskbar or pager entry. This small GTK window uses XWayland on Wayland sessions because GNOME ignores those hiding hints on native Wayland windows. **Check for updates** refreshes repository metadata through Zorin's authenticated APT service; **Review / install updates** opens the native Zorin updater. Background inventory reads the existing APT cache every 30 minutes and displays the last repository refresh separately. Repeated notifications for the same package versions are suppressed, with notification mute and tray-at-sign-in controls.

Install the tray with `python3 update_agent_install.py`. New full GNOME installations include it. **Settings → Software Update → Check for software updates** opens the same Axentra Update window; Software sources and Additional drivers remain native Zorin tools. The existing companion picks up this launch route when its process next starts. Installation preserves the current Zorin policy, including existing automatic security updates. **Save update policy…** authenticates through PolicyKit and supports:

- **System managed:** retain Zorin's existing automatic update configuration. Returning to this mode removes only Axentra's scheduling override.
- **Manual:** notify about updates and disable APT's periodic unattended installation.
- **Automatic / Scheduled:** daily or weekly local-time installs, with either the existing unattended policy (normally security updates) or all configured repository upgrades without removals. Package holds remain respected. Pause for seven days or resume from the same controls.

Scheduled updates use a root-owned helper and systemd timer, wait for AC power and an unmetered connection, retry deferred/missed runs every 30 minutes, and inhibit sleep/shutdown during package work. They do not reboot automatically. Saving a new schedule can trigger a missed run. No schedule is activated until it is explicitly saved and authenticated. Changing a policy or stopping the tray does not cancel a package transaction already in progress. System-managed updates retain their original Zorin behavior.

The existing `/etc/apt/apt.conf.d/99axentra-desktop-guard` hooks remain mandatory for Axentra automatic installs: a verified desktop snapshot must succeed before dpkg changes packages, followed by deferred layout repair. OneDrive/Explorer are not replaced. User tray files and preferences are included in desktop backups; root scheduler files are reference-only and require authenticated reinstallation/configuration. The tray follows `graphical-session.target` and exits at sign-out; schedules run independently. To remove managed scheduling, save **System managed** before uninstalling the theme.

This agent manages APT packages. Flatpak, app stores and firmware continue using their existing updaters. Scheduled-run history is shown in the window; detailed administrator logs are in `/var/log/axentra-update-agent.log` and `journalctl -u axentra-update-agent.service`. Installer/model tests and an isolated GTK test cover the controls; package installation is deliberately not triggered during UI testing.

## Fractional scaling on hybrid graphics

On the tested Intel/NVIDIA laptop, GNOME X11 at laptop 125% / external 100% produces a cropped external display even though the reported native modes and screenshot look correct. Do not use a successful settings readback alone to confirm scaling: check all four edges on the physical screens. This matches the [X11 PRIME transform issue documented by NVIDIA](https://forums.developer.nvidia.com/t/450-75-with-reverse-prime-xrandr-scale-2x2-does-not-work-renders-only-1-4-of-screen-problem-with-nvidia-settings/142424).

Test **Zorin Desktop on Wayland** from the login-screen session selector for independent scaling. Save work before signing out. This is a different session, not a theme reinstall; the package does not switch sessions automatically. The user confirmed improved scaling in Wayland; native window snapping, previews and Snipping Tool capture/recording have also passed local checks. Broader mixed-DPI and suspend/resume coverage remains pending. Both screens at 100% is the fallback if staying on the current X11 session.

## Device Manager (GNOME)

Search **Device Manager** in Start to open a standalone dark hardware tree. Categories expand into PCI controllers, USB devices, cameras/Bluetooth adapters, physical disks and input endpoints, with icons and actual bound driver names. Search by device, driver, category or hardware ID. Select a device and choose **Properties**, double-click it, or use the context menu to view/copy its details. **Refresh** or F5 updates the inventory after connecting or disconnecting hardware; Ctrl+F focuses search and Escape clears it.

The inventory is read-only. It reports driver bindings rather than claiming hardware is healthy, and offers no driver installation, device disable/reset or disk modification. Disk/input drivers can be bound at an ancestor device; Properties identifies that binding location. USB interfaces are combined under their parent, while separate devices with the same name retain distinct identities. Input endpoints can belong to an already-listed controller. Paired Bluetooth accessories remain in Bluetooth settings.

Optional `lspci` provides descriptive PCI names; numeric IDs remain usable without it. Data comes from Linux sysfs ([PCI attributes](https://docs.kernel.org/PCI/sysfs-pci.html), [USB attributes](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-bus-usb), [block attributes](https://www.kernel.org/doc/Documentation/ABI/stable/sysfs-block)). No administrator authentication is required.

Checks: `/usr/bin/python3 -m unittest discover -s companion -p test_hardware_inventory.py` and `/usr/bin/python3 companion/test_device_manager_live.py` (native test requires Xvfb).

## Install on GNOME (default)

Run as your desktop user from a Zorin OS 18 GNOME session:

```bash
git clone https://github.com/MECMwithShawn/Zorin-OS-Fixes.git
cd Zorin-OS-Fixes/windows11-desktop
./install-system-deps.sh
python3 setup.py check
python3 setup.py install
```

**Sign out and sign back in after the first installation or a Shell extension update.** GNOME 46 discovers new extensions at login and caches loaded JavaScript. The installer does not restart your desktop or close applications.

Zorin Taskbar, Zorin Menu and User Themes must be enabled. The installer enables Zorin's bundled Window Move Effect for wobbly windows. The GNOME backend targets Zorin 18's GNOME Shell 46, including Wayland and X11. PowerShell and WezTerm downloads require x86-64; use `--skip-terminal` to skip those downloads. The prebuilt React interface is included, so Node is only needed for development.

Re-run `python3 setup.py install` to upgrade. Your original recovery values, Start pins, Desktop Groups and saved Snap Group recipes are retained. `--desktop gnome` or `--desktop xfce` can make the expected desktop explicit; a mismatched session is rejected.

## GNOME experience


**Lock screen:** open **Settings → Personalization → Lock screen**, or search **Lock screen settings** in Start. The Windows 11 appearance uses GNOME's real clock, account photo, password entry, accessibility, notifications and unlock gestures. The photo stays clear behind the clock and blurs/dims behind native authentication. Installed media controls remain in the native clock. No authentication method or login-screen/GDM file is replaced.

Choose **Windows Spotlight**, **Bing image of the day**, **Zorin wallpapers**, **Use desktop background**, or a personal **Picture**. Online sources refresh daily through `zorin11-lockscreen-wallpaper.timer`; failures retain the last cached photo and retry on the next hourly check. All installed Zorin backgrounds remain available. Lock-screen choices are independent of the desktop except when explicitly following it. A selected personal picture is copied into the private cache so a cloud mount or removable disk is not needed at unlock. The cache keeps up to 30 recent photos plus the selected one.

Preview source, picture, dimming and photo credits, then choose **Apply**. **Revert** discards the draft; getting another online photo only updates the preview. **Native lock timing and privacy** opens GNOME's controls. Automatic locking, password policy and notification privacy settings are preserved.

For an existing installation, run `python3 lockscreen_install.py` from this directory. It adds only the new extension, preferences, launcher and photo timer, and patches the Settings launch route without rebuilding Explorer or touching OneDrive. First activation requires your **next normal sign-in**; preview works immediately and reports pending activation. An already-running companion picks up the route on its next start, while the Start launcher works immediately. The full installer includes this feature. Backups include its code, cached photos and settings; update repair tracks the extension files and enabled state.

Checks: `/usr/bin/python3 -m unittest discover -s tests -p test_lockscreen.py` and `/usr/bin/python3 tests/lockscreen_live.py`. The latter uses a private two-monitor GNOME 46 Wayland session and renders native authentication widgets without submitting credentials or locking the real session. Physical unlock, sign-out and suspend checks must be done separately when the user is ready.


**Adaptive taskbar space:** Start and the app group stay centered on the monitor using Zorin’s native `centerMonitor` placement. Opening an app grows the group by its icon width, split evenly around the center; closing it shrinks the group again. Tray icons grow separately at the right without moving a fitting app group. Native scrolling handles apps that exceed the centered space available beside the tray. No vendor allocation code is replaced. A private two-monitor Wayland test covers one-icon growth, tray growth, shrinkage and non-overlap.

**Taskbar motion:** right-click an empty part of the taskbar and choose **Taskbar motion…**. This opens the combined **Taskbar settings → Motion** page. You can also use **Settings → Personalization → Taskbar → Motion**, or search **Taskbar settings** in Start. Five subtle presets are available: Aurora drift, Breathing glow, Light sweep, Edge ribbon and Active app halo, plus Off. The native dark customization window includes a live preview, accent color, intensity (5–50%) and cycle time (8–40 seconds). **Apply to taskbar** saves the previewed preset, accent, intensity and pause preferences and updates the loaded extension. **Revert changes** discards an unapplied preview; Restore defaults also waits for Apply. Closing the window discards unapplied changes. Quick Settings preset selections remain immediate. After the add-on loads, the native GNOME Quick Settings menu also offers a Taskbar motion tile and preset menu. Aurora drift defaults to 20% intensity and a 20-second cycle.

**Apply at startup** is enabled by default. It restores the saved preset, accent, intensity and timing when you sign in. Turn it off and Apply to keep motion manual on future sign-ins; Apply still starts the chosen preset for the current session, even if the preset is unchanged. The same switch is available in Quick Settings → Taskbar motion. Turning startup off does not erase the preset or stop an already-running effect; choose Off to stop now. The extension waits for late-created Zorin panels and keeps manual activation across extension/lock cycles.

Motion respects GNOME's animation setting and pauses on the lock screen and in Overview. Battery and per-monitor fullscreen pauses are enabled by default and can be changed in the customization window. The preview ignores these two pauses, stops when inactive, and has its own pause button. Active app halo follows the focused app's existing Zorin taskbar icon. Effects are decorative: native icons, previews, clicks, badges and progress remain owned by Zorin. A single 20 fps timer drives all visible panel effects; no animation timer runs while all panels are paused or Off.

For an existing installation, `python3 motion_install.py` adds this extension, its Start launchers and a native Zorin context-menu command, and patches only the companion’s Taskbar launch route, preserving other local code. Existing custom menu entries are retained without duplicate Motion commands; no vendor files are edited. Taskbar settings loads Zorin’s installed Style, Position, Behavior and Action pages unchanged and adds Motion. If the GNOME preferences loader changes in a later release, Motion remains available with a link to native controls. New or updated Shell code loads at your **next normal sign-in**. The right-click menu, updated settings window and preview work immediately; Apply reports when first activation still needs a sign-in. An already-open companion Settings process picks up the new Taskbar route when it next starts; use the Start entry immediately. No logout, restart, Explorer rebuild or OneDrive change is performed. Full installation includes it, backups capture its files and settings, and update repair tracks its enabled state and missing files. This release targets horizontal Zorin taskbars on GNOME 46.

**Snap Layouts:** press Win+Z for the active window. In companion Explorer and Settings, hover over Maximize, right-click it, or focus it and press Down or Shift+F10. Choose a zone to snap; Escape closes the picker. Keys 1–6 focus the first available zone in that layout. Initial focus uses an enabled footer control, and moving keyboard focus off a zone clears its target outline. Caption requests resolve the originating window through GNOME, including duplicate Explorer titles, so an XWayland window ID cannot select an unrelated native window. Ambiguous or closed windows are ignored. Third-party maximize-hover integration remains pending.

Task View and Snap Assist refresh visible window cards in the background, with one capture in flight and no new captures after the panel closes. Minimized windows keep cached previews; filtered, scrolled-out and unmapped cards are skipped. GNOME may pause frame callbacks in fully covered applications, so previews reflect the latest frame the compositor provides. No window-preview images are saved to disk.

In Task View, Ctrl+F focuses search and selects the query. Escape cancels an unfinished desktop rename or clears the search before closing the panel. Enter saves a desktop name. Search and rename tooltips explain these shortcuts, and the search field has an explicit accessibility label.

Alt+Tab also refreshes only visible, nonminimized window and Snap Group previews. Closed windows leave the chooser; minimized windows keep their cached image. Releasing Alt selects the highlighted entry, and Escape cancels. Closing/reopening rejects obsolete capture jobs and results, with at most one Alt+Tab capture queued or running. A capture already running can finish within its three-second timeout; its result is ignored after closing.

| Component | Integration |
|---|---|
| Taskbar | Dark blue appearance, Win11 icons, 48 px bottom taskbar, Start/Search/Task View/apps centered on the monitor, native running-app indicators/previews and notification badges, app-reported progress bars, narrow Show desktop/hover-peek strip |
| Start | Opens on the primary monitor; shared Windows-style pinned apps, ordering, search, All apps, categories, recent documents/apps, desktop-entry actions, local folders and session actions |
| Explorer / This PC | Tabs, sidebar, system drive first as Local Disk (C:), persistent display letters for other mounted drives, capacity, details view, create/rename/copy/cut/paste/trash; advanced locations open the system file manager |
| Settings | Windows-style categories with actual device information and GNOME settings controls; advanced pages open the native tools |
| Quick Settings | Eight editable tiles, Wi-Fi, airplane mode, battery saver, paired Bluetooth devices with connect/disconnect and battery, volume/output, DND, accessibility and supported backlights |
| Notifications | GNOME's current session notifications, read/dismiss/clear and calendar; native notification banners remain managed by GNOME |
| Task Manager | Mission Center provides expandable application/process groups, actual application icons, combined resource usage, and CPU, memory, disk, network and supported GPU graphs |
| Event Viewer | Standalone dark event list, Application/System/Kernel journals, time and severity filters, loaded-event search, details, Copy event and optional auto-refresh |
| Lock screen | Windows 11 presentation around native GNOME unlocking, independent Spotlight/Bing, Zorin collection, personal picture, preview/Apply and daily cache |
| Backgrounds | Windows Spotlight, Bing daily/UHD images, local photos, history, original-background restore **and the installed Zorin wallpaper collection** |
| Desktop menu | Windows-style View, Sort by, Refresh, Paste, New, Display settings, Personalize and Next desktop background; Zorin actions retained under Show more options |
| Desktop Groups (Fences) | Tinted, see-through fences you drag desktop icons into; roll-up, quick-hide, Peek, folder portals. Files stay in place |
| Multitasking | Snap Layouts/Assist, Task View, desktop create/rename/reorder/close, per-desktop backgrounds, saved app/layout recipes and Alt+Tab Snap Groups |
| Terminal | Pinned PowerShell 7.6.7 and WezTerm, PowerShell/Bash profiles, Cascadia Mono, tabs and split panes |

The installer replaces the pinned GNOME Files shortcut with File Explorer and makes it the default for local folders. Network and Trash views remain available through the native file manager.

The narrow strip at the far right of the GNOME taskbar shows the desktop when clicked; click again to restore the windows. Hover to peek temporarily. Notification badges use Zorin's native app notification state. Compatible apps can report progress through `com.canonical.Unity.LauncherEntry`; a blue progress bar then appears on their taskbar icon. Apps that do not report progress have no bar. Bars disappear when the app hides them or its reporting connection closes. The badge switch remains in Taskbar preferences. To hide progress bars, run `gsettings set org.gnome.shell.extensions.zorin-taskbar progress-show-bar false` (use `true` to restore them).

After upgrading GNOME extension code, **sign out and back in when convenient** to load the progress integration. The installer does not restart your session. The desktop-strip setting applies immediately; the new code can be tested separately with the isolated native test below.

Open **Quick Settings** with **Win+A**. Battery saver uses the installed power-profile service and restores the previous mode when switched off; **Settings → System → Power & battery** also lets you choose an available power mode. Airplane mode controls wireless radios through GNOME; a physical radio switch must be released on the device. Wired networking remains available. These controls show as unavailable when their services or hardware are missing. Airplane mode requires GNOME’s radio service; Xfce keeps its Wi-Fi/Bluetooth controls.

Click the arrow beside **Bluetooth** for connected and paired devices, reported battery levels, and **Connect/Disconnect**. Only previously paired devices appear here. **Add device** opens a searchable pairing window: repeated names collapse into one expandable group, individual addresses remain selectable, and discovery stops after 60 seconds or when the window closes. Search by name (for example, AirPods) or address, select the exact device, and confirm pairing or enter its code when requested. Already paired devices are excluded from discovery results. Devices can refuse a connection or omit battery information. The same controls appear under **Settings → Bluetooth & devices**. Use the pencil button to choose tiles; upgrades preserve your existing tile selection, with new controls available in the editor.

The GNOME Bluetooth shortcut opens this paired-device page. Use **Add device** when you want to search nearby. The installer records the previous shortcut for recovery.

In Start, click your profile for Account settings, Lock, Switch user and Sign out. The power button offers Sleep, Shut down and Restart. GNOME confirms Sign out, Shut down and Restart through its native session dialogs and retains application inhibitors.

Organize pinned apps by dragging an app onto the **center** of another app to create a folder, or onto an existing folder to add it. Drop near a tile's edge to reorder pins. Right-click → **Move to Start folder…** provides the same organization with keyboard-accessible controls. Open a folder to rename it or reorder its apps; **Move to Start** and **Move all apps out of folder** retain the app shortcuts. Folder names and ordering survive companion restarts. Escape dismisses the folder or menu before closing Start.

Explorer shows actual **image thumbnails** in **Large icons** and Details views, including downloaded photos inside OneDrive. JPEG, PNG, WebP, GIF, BMP and TIFF are supported; orientation is corrected and animated/multipage images use their first frame. Large icons use an 80 px preview area with a 256 px decoded image for high-DPI displays. Images load near the visible area with four frontend requests and two decoders at a time. A private disk cache survives Explorer restarts; an in-memory cache handles repeat requests. Visible photos have priority, while one worker prepares up to 512 nearby folder images. Changed files invalidate the disk cache using their identity, size and nanosecond timestamps.

Thumbnail decoding accepts regular files up to 32 MiB and 64 megapixels, with a three-second interactive timeout and worker memory/CPU limits (15 seconds for the background library service). Corrupt, unavailable, oversized and unsupported files keep their type icon. Symbolic links, video, SVG, PDF and Office thumbnails are not included. HEIC/HEIF support uses the private decoder described below. Opening an online-only photo can cause OneDrive to retrieve its bytes. Folder prefetch only reads locally available files. Thumbnails stay in `~/.cache/zorin11-hub/thumbnails-v1`, outside OneDrive, with private permissions and an approximately 2 GiB / 32,768-image limit; the oldest entries are evicted. Originals are never rewritten and thumbnails are never uploaded. OneDrive sync settings and integration are preserved.

GNOME installation enables `zorin11-thumbnail-cache.timer`. After sign-in and every 15 minutes after a completed pass, its low-priority user service walks Pictures and the configured OneDrive folder, reuses existing thumbnails, and creates missing ones. It follows no symlinks and skips hidden/dependency folders. It runs one decoder with a 25% CPU quota, idle I/O priority and a 768 MiB service memory limit. No Explorer window needs to be open.

The library service precaches photos on local filesystems. FUSE (including Axentra OneDrive), network and automounted filesystems are excluded before stat, scanning or decoding: a cloud-file open blocked in the kernel can prevent suspend, and a worker timeout cannot reliably cancel it. The legacy `includeOnline` setting and `--include-online` do not override this exclusion. Existing thumbnails remain cached; Explorer still requests cloud previews when browsing. `--root PATH` can be repeated for local folders. Progress counts (without filenames) are saved to `~/.cache/zorin11-hub/thumbnail-status.json`.

Use `systemctl --user start --no-block zorin11-thumbnail-cache.service` to start a pass, or `systemctl --user disable --now zorin11-thumbnail-cache.timer` and `systemctl --user stop zorin11-thumbnail-cache.service` to stop it. GNOME theme restore stops/disables the service and restores its unit files; the disposable thumbnail cache can be removed separately.

Explorer's **Preview** button or **Alt+P** opens a separate read-only preview pane. Supported raster images are decoded to a bounded PNG preview; supported text/code files render as plain text, including HTML. Text files are limited to 1 MB with at most 65,536 characters/1,000 lines shown; images are limited to 10 MB and 25 megapixels, resized to 1,024 px. Animated images show their first frame. Unsupported formats, PDFs and Office documents retain their normal **Open** action. Decoding runs in a timed worker, and changing selection discards stale previews. Preview content is not saved or uploaded.

Start and taskbar Search now combine **Apps, Files, Folders, and Settings**. Apps and settings appear immediately while local filename search runs. Search opens on the **Apps** category; use the category buttons to widen it, arrow keys and Enter, or select a result and choose **Open** / **Open file location**. Click an app in the results list, or its large icon in the details pane, to launch it; hovering an app shows its details, and files/folders/settings still select on click and open on double-click or Enter. For apps, the details pane lists the version, publisher, install source (Debian package, Flatpak, Snap or local), package name, size on disk and categories. Launch commands are never read or shown. Supported files show the same bounded image/text preview as Explorer. Settings results open the actual page (for example, “volume” → Sound).

File search reads names on demand in the folders chosen under **Settings → Personalization → Search & Start**. Desktop, Documents, Downloads, Pictures, Music and Videos are the defaults. Add or remove folders and exclude private subfolders with native folder pickers. Removing every search folder leaves apps/settings searchable. It does not index file contents, save queries or upload results. Hidden items, symbolic links and common dependency/build folders are excluded. File queries need two characters; scans are limited to 25,000 entries, 16 nested levels and about 1.5 seconds of traversal, with up to 80 results per category. A visible notice indicates incomplete results. This is scoped filename search, not a whole-disk content index.

Recent documents appear in Start’s **Recommended** section when desktop file history and **Show recently opened documents** are enabled. Suggestions use existing local desktop history, respect the same search folders/exclusions, and omit private entries, missing files, hidden paths and links. Turn suggestions off in **Search & Start** without deleting your desktop history. Recent-document context menus include **Open file location**.

Right-click an app in Start (or focus it and press **Shift+F10**) for the actions supplied by its installed desktop entry. Search exposes those same actions beside the selected app. File Explorer includes working **New window** and **This PC** actions in Start and its native GNOME taskbar menu. App-specific recent-file jump lists remain future work.

Choose a Start layout under **Settings → Personalization → Search & Start → Start menu style**. **Windows 11** is the default. With it selected, the same Settings page offers three more options:
- **Layout**: More pins (4 rows of pins, 2 recommendations), Default (3 rows, 6) or More recommendations (2 rows, 8).
- **Pinned columns**: 6, 7 or 8.
- **Show Recommended**: when off, the Recommended section is hidden and Pinned gains two rows.

Pinned shows one page at a time. When there are more pins than fit, dots on the right switch pages, and Page Up/Page Down also work while a pin has focus. Use **+** beside Pinned to add up to eight named **tabs**. Right-click any app and choose **Add to <tab>** to put it in a tab. Inside a tab, right-click an app for **Move to first in <tab>** or **Remove from <tab>**. Rename a tab with its **…** button or a double-click, and remove it with **×**; removing a tab never unpins or uninstalls anything. Press Escape while naming a tab to cancel. Pinned itself keeps drag-to-reorder and Start folders. Tabs, layout, columns and the Recommended setting are saved with your other Start preferences.

**Windows 10** opens a square, darker menu. A narrow rail on the left expands with the menu button. It holds your account (Lock, Switch user, Sign out), Documents, Music, Settings and Power (Sleep, Shut down, Restart). Next comes the app list: up to six **Most used** apps from your recent apps, then every app under A–Z headers, with other characters under **#**. Click a letter header for a letter grid that jumps to that section; letters with no apps are greyed out. Pinned apps appear as **tiles** that you can drag to reorder or drop onto each other to make folders, like the Windows 11 pins. Right-click a tile, or press Shift+F10, and choose **Small**, **Medium**, **Wide** or **Large** to resize it. Sizes are saved per app. **Type here to search** at the top uses the shared search. Tiles show app icons only; there is no live tile content.

**Modern** follows Start11's Modern style: the Windows 7 two-column structure in a dark, square Windows 10 look. **Pinned** and **All apps** tabs sit above the left column. Pinned shows your pinned apps and then your recent apps; All apps is a flat alphabetical list. **Search apps, files and settings** is at the bottom. The right column holds a round account picture, your folders, Computer, Settings and a **Shut down** button with the same options arrow as Windows 7.

**Windows 7** opens a narrower two-column menu. On the left are pinned apps, then up to eight recently opened apps that are not pinned, with **All Programs** below them. All Programs lists apps in expandable category folders. Under it, **Search programs and files** uses the same Apps/Files/Folders/Settings search as Windows 11 Start. The details pane is hidden at this width, and a click still launches a result. The right column shows your account picture, your name (your home folder), Documents, Pictures, Music, Videos and Downloads where they exist, Computer (This PC), Settings and Start settings. **Shut down** acts immediately through the same confirmed session action as the Windows 11 power menu, and the arrow next to it offers Switch user, Sign out, Lock, Restart and Sleep. Right-click menus, pinning, Start folders and app actions are the same in both layouts. The choice is saved with your other Start preferences, so older companions ignore it. Changing it closes Start, which reopens at the new size. Three more layouts follow Start11 v2's newer designs:
- **App style with tabs** opens with the A–Z All apps list in a column on the left. Next to it are Pinned and your named tabs, with the same pages, tab actions and columns as Windows 11. Account, Settings and Power sit in the footer.
- **Launcher** takes after phone app launchers. It has a large account picture with Settings and Power at the top, then a rounded search box and chips for Pinned, All apps and each app category. The chips choose what fills a large icon grid. The Pinned chip keeps drag-to-reorder and folders.
- **Full screen** covers the screen's work area (the taskbar stays visible). Search and your account/Settings/Power are along the top. The A–Z list is on the left, and the paged Pinned tabs and Recommended fill the rest.

The selected pin tab is shared by Windows 11, App style with tabs and Full screen.

Three appearance options on the same Settings page apply to every style:
- **Transparency** (Off, 20%, 40% or 60%) lets the desktop show through Start. On X11 you see the blurred backdrop capture; on Wayland, where that capture isn't available, you see the desktop itself.
- **Corners** keeps each style's own corners, or makes them all **Rounded** or **Square**.
- **Start button** changes the taskbar's Start icon on GNOME: Windows 11 (default), Windows 10, Orb, or **Your image…**. Your image accepts any picture under 8 MB and saves a 64 px copy as `~/.config/zorin11-hub/start-button-custom.png`. The GNOME extension draws the button and watches its `start-button` setting. After updating, sign out and back in once to load the new extension code; later changes apply immediately. If the chosen file goes missing, the default icon returns.


Explorer copy/paste now shows progress, transferred bytes, completed/skipped items, **Pause**, **Resume**, and **Cancel transfer**. Collisions offer **Replace the file**, **Keep both**, or **Skip**; matching folders offer **Merge folders** while retaining unrelated destination files. You can apply a choice to remaining file or folder conflicts. File/folder type mismatches and same-file copies cannot replace the original. Failed item operations offer **Retry** or **Skip**; preparation failures show their error.

Each file is staged in the destination filesystem before publication. Cancelling removes its unfinished staging file; completed items remain. Cut/paste removes source files only after their completed copies, and skipped or unfinished sources remain available. Closing the Explorer window cancels its transfer. Transfers support local/mounted filesystems; network and Trash locations still use native tools. Merging keeps existing folder permissions. Keyboard focus returns to Explorer after folder navigation and closing transfer dialogs, so Ctrl+C/Ctrl+X/Ctrl+V continue working.

Task Manager opens [Mission Center](https://missioncenter.io/) in its Apps view with parent/child resource totals merged. The System Monitor launcher and taskbar pin are redirected through recoverable per-user settings, with one visible Task Manager app entry. Extra process-detection metadata lets ChatGPT's known pass-through launcher group under the ChatGPT name and icon. This metadata is excluded from desktop menus and file associations; the actual ChatGPT launcher is preserved. Performance includes GPU graphs supported by the active driver. NVIDIA monitoring requires the NVIDIA driver and NVML; Nouveau does not provide Mission Center's NVIDIA telemetry. Intel GPU metrics vary by driver and permissions. The installer does not change GPU drivers.

Find **Event Viewer** in Start or app search. It opens a standalone GNOME utility with a dark sidebar, event table and selectable details. **Application** reads your user journal; **System** reads system services and **Kernel** reads kernel messages. Applications that do not write to the journal will not appear. Select the current or previous boot, last hour or last 24 hours, then choose a severity filter. The newest 250 matching events are loaded; **Search loaded events** filters only that loaded set.

Select an event for its message, local timestamp, severity, source, service unit, PID and boot ID. **Copy event** copies those details when requested. **Refresh** / **F5** reads again; optional **Auto-refresh** updates every five seconds while the window is open. **Ctrl+F** focuses search; **Escape** clears search or closes the window. Changing filters cancels obsolete queries. Missing permissions, unavailable logs and output limits are shown in the window. Previous-boot events depend on journal retention. Event Viewer reads the Linux journal without elevating permissions, changing services or clearing logs; it does not emulate Windows event IDs or audit channels.

Drive menus include Rename, Copy as path and Properties with filesystem, capacity and free-space details. Drive Rename changes the label shown in Explorer; it does not relabel or remount the filesystem.

Drive letters are Explorer display aliases; file operations retain the actual Linux mount paths. Zorin's system filesystem is C:, even when a separate Windows partition is mounted.

The GTK/WebKit companion runs through XWayland for desktop-surface positioning. The per-user GNOME extension uses Mutter for both native Wayland and X11 application windows, including move/resize, activation, desktop membership and thumbnails. It does not use Shell unsafe-eval mode. Window captures stay in memory.

GNOME notifications are session history, not Xfce's persistent notification log. Notification bodies display as plain text. Clear all opens a keyboard-focused confirmation: Tab stays inside, Escape cancels and restores focus, and a second Escape closes the center. Notification groups expose their expanded state to assistive technology. The companion follows the desktop reduced-motion preference live, including loading indicators. GNOME owns workspace transitions and reduced motion; Zorin's built-in Window Move Effect provides wobbly windows; Compiz workspace-speed controls remain Xfce-only. Taskbar hover previews remain Zorin's native previews; Snap Groups are available through Task View and Alt+Tab. App minimum sizes are enforced by Mutter and may adjust requested snap rectangles. GNOME's idle screen timeout applies to both power sources. GTK4/libadwaita, Qt and Electron applications may keep their own controls and titlebars.

## Desktop fences

Desktop Groups work like Stardock Fences when they are shown (Start → Desktop groups → Show groups):

- **Drag icons in.** Drag icons from the desktop, Files or Explorer into a fence. A desktop file then appears only inside its fence. It stays in `~/Desktop` and stays visible in Files and Explorer, because only the desktop view skips it. Drag it back onto the desktop, or choose **Return to desktop**, to put the icon back.
- **Arrange.** Drag fences by their title bar; they snap to screen edges and to each other. Resize from the bottom-right corner. Drag tiles to reorder them, or drag a tile to another fence to move it. Double-click a tile or press Enter to open it.
- **Roll up.** Double-click a title bar to roll the fence up to just its title. With **Expand on hover when rolled up**, it opens while the pointer is over it.
- **Style.** Right-click a fence (or use **⋯**) for Color (ten tints, including a light Frost), Transparency (glass to opaque), Icon size and Sort by (manual, name, type, date modified).
- **Create and remove.** Right-click the desktop and choose **New fence here**, or use **New fence** in a fence menu. **Delete fence** removes only the fence, and its desktop icons return to the desktop.
- **Hide and Peek.** Double-click empty desktop to hide or show all fences. Win+Shift+F brings fences above your windows.
- **Folder portals.** A folder group mirrors a folder; manage its contents in Explorer.

**Safety.** Fences never move, hide or delete files. The companion publishes the fenced list (`~/.config/zorin11-hub/fenced.json`) with its process ID. If the companion stops or groups are turned off, every icon shows on the desktop again.

Not yet included from Fences: automatic sorting rules, tabbed fences, icon tint/Chameleon, and a blurred-wallpaper (acrylic) background.

## Backgrounds: keep Zorin and add Spotlight/Bing

Installation leaves your selected wallpaper unchanged and never replaces or deletes files in `/usr/share/backgrounds` or `/usr/share/wallpapers`.

Open **Win+I → Personalization → Background**:

- Choose **Windows Spotlight** or **Bing image of the day**, then **Get new wallpaper**.
- Enable **Change the picture daily** for daily refresh while signed in.
- Pick an image from **Zorin wallpapers** to return to the installed collection.
- Use **Browse photos**, **Recent images**, or **Restore original background**.

The desktop's **Change Background** shortcut opens this Background page. **Settings** and **Display settings** also open the corresponding Windows-style pages; advanced controls inside those pages still reach the native tools.

The GNOME desktop menu adapter adds **View → Large/Medium/Small icons**, **Auto arrange icons**, **Show desktop icons**, **Sort by**, **Refresh**, **Paste**, **New → Folder / Document from template**, **Display settings**, **Personalize**, and **Next desktop background**. **Show more options** retains Zorin's native undo/redo, terminal and other desktop actions. Hiding icons only hides their display; it does not move or delete files. File selection menus, dragging and file operations remain owned by Zorin Desktop Icons.

The adapter runs from a per-user extension and references the installed Zorin Desktop Icons files without changing them. On GNOME 46, a newly installed extension activates at the **next sign-in**. Wallpaper controls and shortcut routing work immediately; the installer does not restart the desktop or close applications. The adapter requires Zorin 18's Desktop Icons extension.

If the adapter's links to Zorin Desktop Icons or its compiled schema are missing (for example after **Restore**), the extension keeps Zorin's own desktop running: icons stay visible with Zorin's menu instead of the desktop disappearing. It checks at sign-in and before every desktop relaunch. To bring the Windows-style menu back, run `/usr/bin/python3 windows11-desktop/desktop_menu_install.py` from this repository; the menu returns at the next desktop relaunch or sign-in.

**Next desktop background** fetches another image from the selected Spotlight/Bing feed and opens Background settings for status and credits. With **Picture** selected, it opens the picker instead. Wallpaper changes from the menu and companion serialize through a local lock; failed downloads retain the current picture. Daily refresh runs while the companion is signed in.

Downloaded pictures and credits stay in your local account. Both GNOME light/dark wallpaper values are journaled before changing them. Restore preserves a wallpaper you changed later through another tool. No Windows images, proprietary fonts, personal wallpaper exports or account data are committed.

### Taskbar centering

Taskbar apps sit on the screen's centre line, as in Windows 11, while they fit. At a large display scale (150%) or with a crowded tray, centring on the screen would leave Zorin Taskbar too little room and clip icons. In that case the apps move into the free space beside the tray, and they return to the centre line when there is room again (with a 24 px margin so they don't flip back and forth). The check runs once a second for each monitor. It only changes the taskbar's own centring setting, and only while that is Centered or Monitor Center. Turn it off with:

```bash
gsettings --schemadir ~/.local/share/gnome-shell/extensions/zorin11@zorin-os-fixes/schemas set org.gnome.shell.extensions.zorin11 adaptive-taskbar-center false
```

## Shortcuts

| Shortcut | Action |
|---|---|
| Super / Ctrl+Esc | Start |
| Win+S | Search |
| Win+E | File Explorer |
| Win+I | Settings |
| Win+A | Quick Settings |
| Win+N | Notifications and calendar |
| Win+T / Ctrl+Alt+T | Terminal |
| Win+Z | Snap Layouts |
| Win+Tab | Task View |
| Win+Ctrl+D | New desktop |
| Win+Ctrl+Left / Right | Previous / next desktop |
| Win+Ctrl+F4 | Close desktop, retaining its applications |
| Alt+Tab / Alt+Shift+Tab | Windows and Snap Groups |
| Win+Shift+F | Peek: bring fences above windows / send back (Esc also sends back) |
| Double-click the desktop | Quick-hide or show all fences |

## Restore

From the matching desktop session:

```bash
python3 setup.py restore
# Or without the repository checkout:
python3 "$HOME/.local/share/zorin11-hub/gnome_install.py" restore
```

GNOME recovery records are private files in `~/.config/zorin11-gnome/`. Restore disables the companion extension, stops the companion, restores managed settings/files that still match the installed version, and preserves later manual edits. Downloaded tools/icons and personal pins, groups and wallpaper history remain available. Sign out/in after restoring to finish unloading the extension.

The shared runtime lives in `~/.local/share/zorin11-hub/`; personal state lives in `~/.config/zorin11-hub/`. The GNOME extension is `~/.local/share/gnome-shell/extensions/zorin11@zorin-os-fixes/`.

## Zorin Lite / Xfce

The existing Xfce/X11 backend is retained. See [the complete Xfce guide](XFCE.md) for its native taskbar build, Compiz effects, Windows asset importer, shortcuts and recovery details. It is selected automatically in an Xfce session. GNOME installations do not install or switch to Xfce.

## Development and validation

```bash
python3 -m unittest discover -s tests -v
cd companion
XDG_CURRENT_DESKTOP=XFCE python3 -m unittest -v test_model.py test_explorer.py test_file_preview.py test_file_transfer.py test_unified_search.py test_start_preferences.py test_start_appearance.py test_bluetooth_pairing.py test_hardware_controls.py test_settings.py test_flyouts.py test_desktop_backgrounds.py test_desktop_motion.py test_saved_groups.py test_session_actions.py
# Frontend: use the pinned lockfile, then rebuild committed dist/ assets.
corepack pnpm install --frozen-lockfile
node build.mjs
cd ..
python3 tests/gnome_live.py
# Real WebKit-to-session-service routing on a private Xvfb display and D-Bus;
# the receiving test services cannot lock or end the host session.
python3 companion/test_session_actions_live.py
python3 companion/test_theme_items_live.py
python3 companion/test_search_transfer_live.py
python3 companion/test_start_search_live.py
python3 companion/test_start_classic_live.py
python3 companion/test_start_windows10_live.py
python3 companion/test_start_modern_live.py
python3 companion/test_start_windows11_options_live.py
python3 companion/test_start_more_layouts_live.py
python3 companion/test_start_appearance_live.py
# Headless GNOME Shell with the real extension and Zorin taskbar; never touches the signed-in session.
python3 tests/start_button_live.py
# Power/radio/device services are isolated; this does not change host hardware.
python3 companion/test_quick_hardware_live.py
python3 companion/test_bluetooth_pairing_live.py
# Native taskbar, protocol updates, desktop peek and extension lifecycle on a private display/bus.
node tests/test_progress_state.mjs
python3 tests/taskbar_live.py
# Optional network-dependent verification:
ZORIN11_TEST_FEEDS=1 python3 tests/gnome_live.py
```

The GNOME live test starts a private headless Mutter/Wayland compositor, private D-Bus, settings, runtime and companion state. It exercises the shared UI, native Wayland resizing/desktops/thumbnails, notification read/dismiss, every installed Zorin thumbnail and wallpaper apply/restore. It closes only its disposable processes and windows. The default run does not access image feeds.

GNOME support shares the repository's Linux-based Windows-style experience; it does not provide Windows APIs, Microsoft Windows Terminal, Phone Link, Windows Widgets or commercial Start11/Fences binaries. The broader feature inventory is in [PARITY.md](PARITY.md).

## Playback audio enhancements

Settings → System → Sound and Quick Settings → Sound output include Off, Balanced, Music, Bass boost, Vocal clarity, Movies, Gaming, Custom and Night listening. Six stereo PipeWire peaking filters shape playback at 60, 170, 500, 2k, 6k and 12k Hz. Preset headroom reduces clipping and may lower perceived volume. Night listening is EQ, not a compressor; surround processing is not included.

Choosing a preset enables `zorin11-audio-effects.service` for your user and saves the choice across sign-in. Off stops/disables it and returns streams to their physical output. Hardware volume, default physical output and microphone routing stay unchanged. Output changes rebuild the graph; new default-output playback streams are routed within approximately half a second. Missing PipeWire tools disable the controls.

GNOME Quick Settings includes a **System EQ** tile, and its native Sound output menu includes an **Audio enhancements** submenu. Both list the installed presets and the current selection. **Edit custom preset…** opens six sliders (−12 to +12 dB): changes preview live, **Save as system default** persists the Custom curve, and closing without saving restores the selected default. Abandoned previews expire automatically. Its Sound Settings link opens the companion's Sound page; Advanced still opens GNOME's volume/input controls. The separate `zorin11-audio@zorin-os-fixes` extension loads on the next sign-in after installation. Upgrades refresh an already-running EQ service, and preset changes detect an older loaded engine so newly added presets cannot time out and revert.

HEIC and HEIF photos are supported in Explorer thumbnails, the Preview pane and background precaching. The GNOME installer downloads hash-pinned Pillow 13.0.0 / pillow-heif 1.8.1 binary wheels into a private `heif-runtime` directory for Python 3.12 on Zorin 18 (x86-64 or ARM64). This handles iPhone depth metadata that the older system decoder can reject. Existing verified runtimes are reused; installation failure preserves the previous runtime. Zorin’s `heif-gdk-pixbuf` is the fallback when the private decoder is absent. `install-system-deps.sh` supplies `python3-venv` for the installer; system Python packages are not replaced. Image workers remain bounded by input size, dimensions, memory and execution time; cached PNGs discard source metadata. Existing OneDrive mount and download behavior are retained.

AAE files contain Apple Photos edit instructions. Selecting one in Explorer's Preview pane finds a same-name HEIC/HEIF, JPEG or PNG in that folder and shows it with an explicit **Original photo** notice. Apple adjustments are not applied. Missing originals get an explanation; sidecar contents are never interpreted or used as paths, and sibling lookup is bounded.

## Axentra SnippingTool (Rust)

Open **Axentra SnippingTool** from Start, use **Win+Shift+S** for a screenshot or **Win+Shift+R** for recording (press again to stop). Quick Settings → Screenshot opens the same app. The native Rust/GTK editor follows the [Microsoft Snipping Tool guide](https://support.microsoft.com/en-us/windows/apps/use-snipping-tool-to-capture-screenshots) with Linux-native capture, permission, sharing and printing services.

The compact dark window mirrors the [Windows 11 layout in this reference](https://www.computerhope.com/jargon/s/snipping.htm#win11): New, capture mode and delay sit beneath the title. Capturing/opening an image expands the window and reveals a single icon toolbar. **More tools** groups shapes, emoji, redaction, color picking and rotation; **Ink settings** contains color/thickness. Save, Copy and Share are directly available. Hover an icon for its name; **⋯ → Open image** or Ctrl+O opens an existing picture.

X11 supports rectangle, freeform, window and entire-desktop screenshots across monitors, plus region recording to MP4. Wayland uses the desktop screenshot picker and ScreenCast permission dialog for screen/window recording to WebM. Both recorders offer optional playback audio and microphone switches, initially off. Stop and review before saving; no recording starts merely by opening the app. Capture delays are 0–5 or 10 seconds. Escape cancels selection; arrow keys position a rectangle, Shift+arrows resize it, and Enter captures it.

The editor includes pen, highlighter, shapes, text, emoji, annotation eraser, crop, rotation, zoom, undo/redo, PNG/JPEG save and image clipboard. **Text actions** performs local OCR, copies selected/all text and covers detected email addresses/phone numbers; **Redact** covers manually selected areas. Exported redactions are flattened pixels. Review OCR for missed content. The color tool samples image pixels; **⋯ → Pick screen color** uses the desktop's screen eyedropper. **⋯ → Share / Open with** chooses a local app for editing/sharing; Print opens the native print dialog.

New screenshots are copied and saved to Pictures/Screenshots by default. **⋯ → Settings** changes both behaviors and the destination. Auto-save keeps the original capture; use Save as for edited/redacted copies. Unsaved edits and recordings prompt before replacement/closing. Nothing is uploaded automatically. Copilot's proprietary Perfect screenshot framing and Microsoft's Paint/Clipchamp integration are not included; local editors are available through Open with. See [feature coverage and platform differences](snipping-tool/PARITY.md).

The GNOME installer builds the locked Rust project (Rust 1.75+, Cargo, pkg-config and GTK 3 development files) and installs per-user. `install-system-deps.sh` includes Tesseract, FFmpeg and GStreamer/PipeWire plugins. To update only this app, run `python3 snipping_install.py`. Existing custom shortcuts and subsequent user edits are preserved, and managed shortcuts participate in desktop restoration.

Sound settings and Quick Settings now show sixteen live frequency bars from the selected playback output. Monitoring stops when the controls are hidden; no microphone is opened and no audio is saved. Presets remain fixed choices rather than automatic track classification.

Axentra Mini Media can expose the same persistent system EQ and live bars directly beneath its common player controls. See [the player integration](integrations/minitube/README.md); changes synchronize with Sound settings and affect system playback across player sources.

## Advanced display (GNOME)

Open Start and search **Advanced display** for a standalone dark display-details window. It lists the main screen first, current and preferred resolution, refresh rate, scale, rotation, position, supported modes and reported panel size/current-mode DPI. Choose another monitor with the selector; display changes refresh automatically, with manual Refresh or F5 available. **Open display settings** opens GNOME's arrangement/scaling controls.

Graphics adapters use optional `lspci`; the OpenGL diagnostic renderer uses optional `glxinfo`. Missing tools or panel dimensions show Unavailable. The diagnostic renderer is not necessarily the GPU used by other applications or the compositor. The window only reads display configuration; it never changes modes or drivers. This standalone launcher is installed immediately without rebuilding the shared companion frontend or requiring sign-out.

Validation: `/usr/bin/python3 -m unittest discover -s companion -p test_display_details.py` and `/usr/bin/python3 companion/test_display_details_live.py` (the latter requires python3-dbus and Xvfb).


## Desktop snapshots and update recovery

Create a verified snapshot before a major OS upgrade or after desktop customization:

```bash
/usr/bin/python3 ~/.local/share/zorin11-hub/desktop_backup.py --destination "$HOME/OneDrive/Axentra/Windows 11 Desktop Backups"
# Later snapshots reuse the saved destination:
/usr/bin/python3 ~/.local/share/zorin11-hub/desktop_backup.py
# Check every archived file against the embedded inventory:
/usr/bin/python3 ~/.local/share/zorin11-hub/desktop_backup.py --verify /path/to/snapshot/desktop-snapshot.tar.gz
```

Each dated folder contains the archive, SHA256SUMS, file inventory and restore notes. The tool verifies archive contents before publication and compares the OneDrive copy against the local archive. A remembered mount must be available; it will not silently fall back to an unmounted local directory. Manual snapshots remain available. Optional automatic APT protection is described below.

Snapshots include installed companion code, extensions, icons, SnippingTool, managed launchers/user services, wallpaper history and choices, EQ defaults/custom curve, current GNOME layout settings, original recovery journals and the system account photo. Vendor extension copies and monitor configuration are reference material. OneDrive credentials, browser profiles, personal document trees and thumbnail caches are excluded. The destination stays in private local configuration. Snapshots can contain personal paths and the account photo; do not commit them to this repository. A verified local OneDrive write is not confirmation of cloud upload.

Restore selected components from a staging directory after comparing versions and current files. Do not unpack the whole archive over the home directory: newer Explorer/OneDrive integration or user preferences could be overwritten. The original installation recovery journal undoes the theme; it does not restore the snapshot's current layout. Recheck compatibility after a GNOME/Zorin update before reapplying extensions. Per-user overlays normally survive package updates, but major Shell API changes may still require adaptation.

Account images in Start and Settings now resolve AccountsService's current IconFile, then ~/.face, ~/.face.icon and the legacy imported avatar. The photo is rechecked every five seconds and its modification timestamp invalidates cached previews. Served images are scaled PNGs; no account photo is bundled in the repository.


## Automatic backups before APT updates

After selecting a backup destination with `desktop_backup.py`, enable protection:

```bash
/usr/bin/python3 install_update_guard.py
pkexec /usr/bin/python3 "$PWD/install_update_guard.py" --system --user "$USER"
```

The second command opens administrator authentication. It installs a root-owned APT hook and first verifies a real backup through the same privilege-dropping bridge. It does not install or upgrade any packages. The root hook runs all backup, OneDrive and desktop work as the configured desktop user.

Before APT invokes dpkg, it creates a verified snapshot in the remembered OneDrive folder and keeps a verified local repair copy. Multiple dpkg calls in the same update batch share the first snapshot. If OneDrive is unmounted, unavailable or cannot store a verified copy, the update is postponed with an explanation; sign in, make OneDrive available and retry. This also means unattended/offline APT updates can be postponed while the user's OneDrive mount is unavailable. Local verification does not require waiting for cloud upload. OneDrive continues syncing normally.

A user timer checks for pending repair every minute and at sign-in. It waits at least 60 seconds after package activity, until dpkg locks are released and a GNOME session is available. It supports the tested Zorin 18 / GNOME 46 layout; an unsupported OS/Shell version or changed desktop-adapter API pauses repair for review.

Repair restores missing managed icon, extension and launcher files, and layout settings reset to their schema defaults or recorded original values. Existing edited files and other customization values are preserved. Managed extension membership is merged with unrelated extensions; a global user-extension pause is respected. Wallpaper recovery uses the latest existing selected wallpaper instead of reverting daily Spotlight to an older image. OneDrive/Explorer code, user photos, account/EQ state, credentials, monitor geometry, drivers and vendor files are outside automatic restoration. Restored extension code loads on the next normal sign-in; the guard never restarts Shell or signs you out.

Snapshots accumulate in the selected OneDrive folder; the guard does not delete them. Two local repair archives are retained under `~/.local/state/zorin11-update-guard`. A failed or interrupted update is checked after locks clear as well. This covers APT/dpkg transactions made through APT, including Zorin's APT updater and unattended-upgrades. Direct standalone `dpkg`, Flatpak, Snap, manual file edits and extension downloads outside APT do not run this pre-update hook. Major release upgrades still need compatibility review; this is desktop recovery, not a full-system rollback.

Check protection:

```bash
systemctl --user status zorin11-update-repair.timer
/usr/bin/python3 ~/.local/share/zorin11-hub/update_guard.py status
journalctl --user -u zorin11-update-repair.service
```

Disable it without deleting backups:

```bash
pkexec /usr/bin/python3 ~/.local/share/zorin11-hub/install_update_guard.py --system --remove
/usr/bin/python3 ~/.local/share/zorin11-hub/install_update_guard.py --remove
```

### Wayland validation (2026-10-20)

Select **Zorin Desktop on Wayland** at sign-in; GDM remembers the selection. The companion intentionally runs through XWayland for its positioned panels, while its GNOME Shell bridge enumerates, moves and captures native Wayland windows. Do not replace the Shell bridge with X11 window IDs or root-window screenshots.

Live checks on a Dell above a laptop at 100% / 125% passed all six Snap Layouts on each display, original-position restore, native-window PNG previews, Task View and Start on the primary display. Background helper windows with zero-size frames are omitted from task lists without terminating their processes. Acrylic panels use their normal theme background on Wayland: XWayland root captures cannot supply the composited desktop.

Axentra SnippingTool uses GNOME's permission-mediated Screenshot and ScreenCast pickers on Wayland. Actual screenshots and silent video recordings were confirmed locally; the isolated recording test also covers PipeWire encoding, optional audio, cancellation, descriptor handling and cleanup. Wayland selection remains delegated to GNOME; X11 freeform capture is not claimed as native Wayland parity. OneDrive remained mounted, up to date, with no pending operations or reported issues.

To repeat the live window test (creates and closes only its own test window):

```bash
GDK_BACKEND=x11 /usr/bin/python3 windows11-desktop/companion/test_wayland_live.py
```

The live test requires an unlocked GNOME Wayland session and briefly focuses its own window. Automated coverage is not a claim that every theme interaction or GPU/suspend combination has been tested.

### Suspend/resume diagnostics

`companion/wayland_resume_check.py --watch --output /path/to/private-report` observes logind and captures display geometry, GPU health, panel registration, network state and OneDrive status. It does not initiate sleep or change settings. Start it before requesting suspend. A resume signal also occurs after failed suspend: verify the kernel and systemd-suspend logs before calling a cycle successful.

On the validation machine, the first test failed because a background thumbnail decoder was blocked opening a OneDrive FUSE file. After excluding remote mounts from precaching, two subsequent cycles completed userspace freezing in 0.002 seconds and systemd reported successful sleep return. Both monitors retained their modes and scale in the recorded follow-up.

Wi-Fi recovery separately selected an unusable saved network and waited for credentials. Prefer the intended working profile and disable autoconnect on an unusable profile using NetworkManager's connection editor. This is a per-machine choice: the installer does not change network profiles or embed personal SSIDs/UUIDs. The local preferred priority was set to 100; priority alone was insufficient, so autoconnect on the failing profile was disabled. The latter change still needs a fresh resume validation.

Remaining app lifecycle issues: Mini Media's Soloist child survived sign-out, and OneDrive's tray UI retained invisible windows. The orphaned playback and tray UI were closed locally without stopping the OneDrive sync daemon. Preventing these app-specific lifecycle problems remains separate work; no Mini Media or OneDrive source was replaced.


Event Viewer supports **right-click → Event Properties / Copy event**, double-click or **Alt+Enter** for Properties, and **Ctrl+C** while the event list is focused. Copying selected text in Search or Details retains its normal behavior. Properties and menu actions keep the event that was selected when opened, even if auto-refresh changes the list. These actions work on native Wayland and do not require administrator access.


**Copy a folder path:** click the empty address-bar space or the current (last) breadcrumb to select the full path. **Ctrl+L**, **Alt+D** or **F4** also focuses it, including from folder search. Use **Ctrl+C** to copy, Enter to navigate and Escape to return to breadcrumbs. Ancestor breadcrumbs still navigate normally. Existing customized installations can run `python3 explorer_address_install.py` for a guarded address-only bundle patch, preserving OneDrive and other local frontend integrations. Newly opened Explorer windows use the change.


Advanced display includes **Copy display report**, with all detected displays, current/preferred resolution, scaling, orientation, desktop positions, session type and graphics diagnostics. Copy is unavailable during refresh or after an error, and monitor changes invalidate older in-flight results. It does not alter display configuration.


GNOME background window tracking uses cancellable asynchronous reads, with one request at a time per tracker. Slow Shell replies do not block the GTK loop during these periodic checks. Newer explicit refreshes supersede older pending replies, and closing the tracker cancels outstanding reads. Foreground window commands and explicit refreshes retain their synchronous behavior.

### Desktop shortcut names

Right-click a desktop application shortcut and choose **Rename…**, or select it and press **F2**. Trusted launchers now support changing their displayed name while preserving their command, icon, permissions and filename. The icon menu uses the same Windows-style appearance as the desktop background menu, with icons for Open, Cut, Copy, Rename, Trash and Properties. Regular files continue using Zorin’s native rename operation; special system/drive icons retain their native restrictions.

### Static application windows

If the optional `zorin11-glass@zorin-os-fixes` extension causes changing shades or background bleed-through, run `python3 windows11-desktop/static_window_appearance.py` as your desktop user. It disables that global effect and saves solid active/inactive window settings. Menu styling and application code are preserved. Its settings and recovery records are included in desktop backups.

### Copy paths in GNOME Files

The independent Nautilus extension adds **Copy full path** to a selected file/folder, **Copy full paths** for multiple selections (one per line), and **Copy folder path** to the folder background menu. Local paths are plain text with spaces and Unicode intact; remote locations use their URI. It does not modify the Axentra CloudDrive integration. Restart Files after installing the extension.

### Logout cleanup and recovery validation

The GNOME installer includes the existing session cleanup helper and its graphical-session service. Cleanup matches only exact user-owned Mini Media/Soloist or legacy OneDrive GUI executable paths, using pidfds to avoid reused-PID signalling. The current lowercase `axentra-onedrive` sync daemon is excluded. During an active desktop session, stopping/uninstalling the cleanup service skips app termination; cleanup is permitted only while the graphical-session target is deactivating or inactive.

For read-only recovery diagnostics, use `python3 ~/.local/share/zorin11-hub/wayland_resume_check.py --output ~/.local/state/zorin11-resume-check`. Adding `--watch` records one subsequent sleep/wake cycle without initiating sleep. Logs stay local; no account details or filenames are included in the OneDrive status snapshot.
