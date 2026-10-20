# Windows 11 desktop for Zorin OS

**GNOME is the primary desktop.** The same installer detects Zorin 18 GNOME or Zorin Lite/Xfce and installs the matching integration. The shared companion provides the Windows 11-style Start menu, File Explorer, Settings, Quick Settings, notification/calendar flyout, Desktop Groups and multitasking UI.

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

| Component | Integration |
|---|---|
| Taskbar | Dark blue appearance, Win11 icons, 48 px bottom taskbar, centered Start/Search/Task View/app area, native running-app indicators and previews |
| Start | Opens on the primary monitor; shared Windows-style pinned apps, ordering, search, All apps, categories, recent documents/apps, desktop-entry actions, local folders and session actions |
| Explorer / This PC | Tabs, sidebar, system drive first as Local Disk (C:), persistent display letters for other mounted drives, capacity, details view, create/rename/copy/cut/paste/trash; advanced locations open the system file manager |
| Settings | Windows-style categories with actual device information and GNOME settings controls; advanced pages open the native tools |
| Quick Settings | Eight editable tiles, Wi-Fi, airplane mode, battery saver, paired Bluetooth devices with connect/disconnect and battery, volume/output, DND, accessibility and supported backlights |
| Notifications | GNOME's current session notifications, read/dismiss/clear and calendar; native notification banners remain managed by GNOME |
| Task Manager | Mission Center provides expandable application/process groups, actual application icons, combined resource usage, and CPU, memory, disk, network and supported GPU graphs |
| Backgrounds | Windows Spotlight, Bing daily/UHD images, local photos, history, original-background restore **and the installed Zorin wallpaper collection** |
| Desktop Groups | Shared movable shortcut groups and folder portals; original files stay in place |
| Multitasking | Snap Layouts/Assist, Task View, desktop create/rename/reorder/close, per-desktop backgrounds, saved app/layout recipes and Alt+Tab Snap Groups |
| Terminal | Pinned PowerShell 7.6.7 and WezTerm, PowerShell/Bash profiles, Cascadia Mono, tabs and split panes |

The installer replaces the pinned GNOME Files shortcut with File Explorer and makes it the default for local folders. Network and Trash views remain available through the native file manager.

Open **Quick Settings** with **Win+A**. Battery saver uses the installed power-profile service and restores the previous mode when switched off; **Settings → System → Power & battery** also lets you choose an available power mode. Airplane mode controls wireless radios through GNOME; a physical radio switch must be released on the device. Wired networking remains available. These controls show as unavailable when their services or hardware are missing. Airplane mode requires GNOME’s radio service; Xfce keeps its Wi-Fi/Bluetooth controls.

Click the arrow beside **Bluetooth** for connected and paired devices, reported battery levels, and **Connect/Disconnect**. Only previously paired devices appear here. **Add device** opens a searchable pairing window: repeated names collapse into one expandable group, individual addresses remain selectable, and discovery stops after 60 seconds or when the window closes. Search by name (for example, AirPods) or address, select the exact device, and confirm pairing or enter its code when requested. Already paired devices are excluded from discovery results. Devices can refuse a connection or omit battery information. The same controls appear under **Settings → Bluetooth & devices**. Use the pencil button to choose tiles; upgrades preserve your existing tile selection, with new controls available in the editor.

The GNOME Bluetooth shortcut opens this paired-device page. Use **Add device** when you want to search nearby. The installer records the previous shortcut for recovery.

In Start, click your profile for Account settings, Lock, Switch user and Sign out. The power button offers Sleep, Shut down and Restart. GNOME confirms Sign out, Shut down and Restart through its native session dialogs and retains application inhibitors.

Organize pinned apps by dragging an app onto the **center** of another app to create a folder, or onto an existing folder to add it. Drop near a tile's edge to reorder pins. Right-click → **Move to Start folder…** provides the same organization with keyboard-accessible controls. Open a folder to rename it or reorder its apps; **Move to Start** and **Move all apps out of folder** retain the app shortcuts. Folder names and ordering survive companion restarts. Escape dismisses the folder or menu before closing Start.

Explorer shows actual **image thumbnails** in **Large icons** and Details views, including downloaded photos inside OneDrive. JPEG, PNG, WebP, GIF, BMP and TIFF are supported; orientation is corrected and animated/multipage images use their first frame. Large icons use an 80 px preview area with a 256 px decoded image for high-DPI displays. Images load near the visible area with four frontend requests and two decoders at a time. A private disk cache survives Explorer restarts; an in-memory cache handles repeat requests. Visible photos have priority, while one worker prepares up to 512 nearby folder images. Changed files invalidate the disk cache using their identity, size and nanosecond timestamps.

Thumbnail decoding accepts regular files up to 32 MiB and 64 megapixels, with a three-second interactive timeout and worker memory/CPU limits (15 seconds for the background library service). Corrupt, unavailable, oversized and unsupported files keep their type icon. Symbolic links, video, SVG, HEIC, PDF and Office thumbnails are not included. Opening an online-only photo can cause OneDrive to retrieve its bytes. Folder prefetch only reads locally available files. Thumbnails stay in `~/.cache/zorin11-hub/thumbnails-v1`, outside OneDrive, with private permissions and an approximately 2 GiB / 32,768-image limit; the oldest entries are evicted. Originals are never rewritten and thumbnails are never uploaded. OneDrive sync settings and integration are preserved.

GNOME installation enables `zorin11-thumbnail-cache.timer`. After sign-in and every 15 minutes after a completed pass, its low-priority user service walks Pictures and the configured OneDrive folder, reuses existing thumbnails, and creates missing ones. It follows no symlinks and skips hidden/dependency folders. It runs one decoder with a 25% CPU quota, idle I/O priority and a 768 MiB service memory limit. No Explorer window needs to be open.

The library service defaults to locally available photos. To include online-only OneDrive photos, set `{"includeOnline": true}` in `~/.config/zorin11-hub/thumbnail-cache.json`, or run `thumbnail_cache.py --include-online` manually. This reads photo contents through the existing OneDrive mount and may download them. `--root PATH` can be repeated for a manual pass over other folders. Progress counts (without filenames) are saved to `~/.cache/zorin11-hub/thumbnail-status.json`.

Use `systemctl --user start --no-block zorin11-thumbnail-cache.service` to start a pass, or `systemctl --user disable --now zorin11-thumbnail-cache.timer` and `systemctl --user stop zorin11-thumbnail-cache.service` to stop it. GNOME theme restore stops/disables the service and restores its unit files; the disposable thumbnail cache can be removed separately.

Explorer's **Preview** button or **Alt+P** opens a separate read-only preview pane. Supported raster images are decoded to a bounded PNG preview; supported text/code files render as plain text, including HTML. Text files are limited to 1 MB with at most 65,536 characters/1,000 lines shown; images are limited to 10 MB and 25 megapixels, resized to 1,024 px. Animated images show their first frame. Unsupported formats, PDFs and Office documents retain their normal **Open** action. Decoding runs in a timed worker, and changing selection discards stale previews. Preview content is not saved or uploaded.

Start and taskbar Search now combine **Apps, Files, Folders, and Settings**. Apps and settings appear immediately while local filename search runs. Use the category buttons, arrow keys and Enter, or select a result and choose **Open** / **Open file location**. Supported files show the same bounded image/text preview as Explorer. Settings results open the actual page (for example, “volume” → Sound).

File search reads names on demand in the folders chosen under **Settings → Personalization → Search & Start**. Desktop, Documents, Downloads, Pictures, Music and Videos are the defaults. Add or remove folders and exclude private subfolders with native folder pickers. Removing every search folder leaves apps/settings searchable. It does not index file contents, save queries or upload results. Hidden items, symbolic links and common dependency/build folders are excluded. File queries need two characters; scans are limited to 25,000 entries, 16 nested levels and about 1.5 seconds of traversal, with up to 80 results per category. A visible notice indicates incomplete results. This is scoped filename search, not a whole-disk content index.

Recent documents appear in Start’s **Recommended** section when desktop file history and **Show recently opened documents** are enabled. Suggestions use existing local desktop history, respect the same search folders/exclusions, and omit private entries, missing files, hidden paths and links. Turn suggestions off in **Search & Start** without deleting your desktop history. Recent-document context menus include **Open file location**.

Right-click an app in Start (or focus it and press **Shift+F10**) for the actions supplied by its installed desktop entry. Search exposes those same actions beside the selected app. File Explorer includes working **New window** and **This PC** actions in Start and its native GNOME taskbar menu. App-specific recent-file jump lists remain future work.


Explorer copy/paste now shows progress, transferred bytes, completed/skipped items, **Pause**, **Resume**, and **Cancel transfer**. Collisions offer **Replace the file**, **Keep both**, or **Skip**; matching folders offer **Merge folders** while retaining unrelated destination files. You can apply a choice to remaining file or folder conflicts. File/folder type mismatches and same-file copies cannot replace the original. Failed item operations offer **Retry** or **Skip**; preparation failures show their error.

Each file is staged in the destination filesystem before publication. Cancelling removes its unfinished staging file; completed items remain. Cut/paste removes source files only after their completed copies, and skipped or unfinished sources remain available. Closing the Explorer window cancels its transfer. Transfers support local/mounted filesystems; network and Trash locations still use native tools. Merging keeps existing folder permissions. Keyboard focus returns to Explorer after folder navigation and closing transfer dialogs, so Ctrl+C/Ctrl+X/Ctrl+V continue working.

Task Manager opens [Mission Center](https://missioncenter.io/) in its Apps view with parent/child resource totals merged. The System Monitor launcher and taskbar pin are redirected through recoverable per-user settings, with one visible Task Manager app entry. Extra process-detection metadata lets ChatGPT's known pass-through launcher group under the ChatGPT name and icon. This metadata is excluded from desktop menus and file associations; the actual ChatGPT launcher is preserved. Performance includes GPU graphs supported by the active driver. NVIDIA monitoring requires the NVIDIA driver and NVML; Nouveau does not provide Mission Center's NVIDIA telemetry. Intel GPU metrics vary by driver and permissions. The installer does not change GPU drivers.

Drive menus include Rename, Copy as path and Properties with filesystem, capacity and free-space details. Drive Rename changes the label shown in Explorer; it does not relabel or remount the filesystem.

Drive letters are Explorer display aliases; file operations retain the actual Linux mount paths. Zorin's system filesystem is C:, even when a separate Windows partition is mounted.

The GTK/WebKit companion runs through XWayland for desktop-surface positioning. The per-user GNOME extension uses Mutter for both native Wayland and X11 application windows, including move/resize, activation, desktop membership and thumbnails. It does not use Shell unsafe-eval mode. Window captures stay in memory.

GNOME notifications are session history, not Xfce's persistent notification log. GNOME owns workspace transitions and reduced motion; Zorin's built-in Window Move Effect provides wobbly windows; Compiz workspace-speed controls remain Xfce-only. Taskbar hover previews remain Zorin's native previews; Snap Groups are available through Task View and Alt+Tab. App minimum sizes are enforced by Mutter and may adjust requested snap rectangles. GNOME's idle screen timeout applies to both power sources. GTK4/libadwaita, Qt and Electron applications may keep their own controls and titlebars.

## Backgrounds: keep Zorin and add Spotlight/Bing

Installation leaves your selected wallpaper unchanged and never replaces or deletes files in `/usr/share/backgrounds` or `/usr/share/wallpapers`.

Open **Win+I → Personalization → Background**:

- Choose **Windows Spotlight** or **Bing image of the day**, then **Get new wallpaper**.
- Enable **Change the picture daily** for daily refresh while signed in.
- Pick an image from **Zorin wallpapers** to return to the installed collection.
- Use **Browse photos**, **Recent images**, or **Restore original background**.

Downloaded pictures and credits stay in your local account. Both GNOME light/dark wallpaper values are journaled before changing them. Restore preserves a wallpaper you changed later through another tool. No Windows images, proprietary fonts, personal wallpaper exports or account data are committed.

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
| Win+Shift+F | Bring Desktop Groups forward / send back |

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
XDG_CURRENT_DESKTOP=XFCE python3 -m unittest -v test_model.py test_explorer.py test_file_preview.py test_file_transfer.py test_unified_search.py test_start_preferences.py test_bluetooth_pairing.py test_hardware_controls.py test_settings.py test_flyouts.py test_desktop_backgrounds.py test_desktop_motion.py test_saved_groups.py test_session_actions.py
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
# Power/radio/device services are isolated; this does not change host hardware.
python3 companion/test_quick_hardware_live.py
python3 companion/test_bluetooth_pairing_live.py
# Optional network-dependent verification:
ZORIN11_TEST_FEEDS=1 python3 tests/gnome_live.py
```

The GNOME live test starts a private headless Mutter/Wayland compositor, private D-Bus, settings, runtime and companion state. It exercises the shared UI, native Wayland resizing/desktops/thumbnails, notification read/dismiss, every installed Zorin thumbnail and wallpaper apply/restore. It closes only its disposable processes and windows. The default run does not access image feeds.

GNOME support shares the repository's Linux-based Windows-style experience; it does not provide Windows APIs, Microsoft Windows Terminal, Phone Link, Windows Widgets or commercial Start11/Fences binaries. The broader feature inventory is in [PARITY.md](PARITY.md).

## Playback audio enhancements

Settings → System → Sound and Quick Settings → Sound output include Off, Balanced, Music, Bass boost, Vocal clarity, Movies, Gaming and Night listening. Six stereo PipeWire peaking filters shape playback at 60, 170, 500, 2k, 6k and 12k Hz. Preset headroom reduces clipping and may lower perceived volume. Night listening is EQ, not a compressor; surround processing is not included.

Choosing a preset enables `zorin11-audio-effects.service` for your user and saves the choice across sign-in. Off stops/disables it and returns streams to their physical output. Hardware volume, default physical output and microphone routing stay unchanged. Output changes rebuild the graph; new default-output playback streams are routed within approximately half a second. Missing PipeWire tools disable the controls.
