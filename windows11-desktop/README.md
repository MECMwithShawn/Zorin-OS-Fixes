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
| Start | Opens on the primary monitor; shared Windows-style pinned apps, ordering, search, All apps, categories, recent launches, local folders and session actions |
| Explorer / This PC | Tabs, sidebar, system drive first as Local Disk (C:), persistent display letters for other mounted drives, capacity, details view, create/rename/copy/cut/paste/trash; advanced locations open the system file manager |
| Settings | Windows-style categories with actual device information and GNOME settings controls; advanced pages open the native tools |
| Quick Settings | Network, Bluetooth, volume/output, Do Not Disturb, accessibility, supported backlights and battery information |
| Notifications | GNOME's current session notifications, read/dismiss/clear and calendar; native notification banners remain managed by GNOME |
| Task Manager | Mission Center provides expandable application/process groups, actual application icons, combined resource usage, and CPU, memory, disk, network and supported GPU graphs |
| Backgrounds | Windows Spotlight, Bing daily/UHD images, local photos, history, original-background restore **and the installed Zorin wallpaper collection** |
| Desktop Groups | Shared movable shortcut groups and folder portals; original files stay in place |
| Multitasking | Snap Layouts/Assist, Task View, desktop create/rename/reorder/close, per-desktop backgrounds, saved app/layout recipes and Alt+Tab Snap Groups |
| Terminal | Pinned PowerShell 7.6.7 and WezTerm, PowerShell/Bash profiles, Cascadia Mono, tabs and split panes |

The installer replaces the pinned GNOME Files shortcut with File Explorer and makes it the default for local folders. Network and Trash views remain available through the native file manager.

In Start, click your profile for Account settings, Lock, Switch user and Sign out. The power button offers Sleep, Shut down and Restart. GNOME confirms Sign out, Shut down and Restart through its native session dialogs and retains application inhibitors.

Organize pinned apps by dragging an app onto the **center** of another app to create a folder, or onto an existing folder to add it. Drop near a tile's edge to reorder pins. Right-click → **Move to Start folder…** provides the same organization with keyboard-accessible controls. Open a folder to rename it or reorder its apps; **Move to Start** and **Move all apps out of folder** retain the app shortcuts. Folder names and ordering survive companion restarts. Escape dismisses the folder or menu before closing Start.

Explorer's **Preview** button or **Alt+P** opens a read-only preview pane. Supported raster images are decoded to a bounded PNG preview; supported text/code files render as plain text, including HTML. Text files are limited to 1 MB with at most 65,536 characters/1,000 lines shown; images are limited to 10 MB and 25 megapixels, resized to 1,024 px. Animated images show their first frame. Unsupported formats, PDFs and Office documents retain their normal **Open** action. Decoding runs in a timed worker, and changing selection discards stale previews. Preview content is not saved or uploaded.

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
XDG_CURRENT_DESKTOP=XFCE python3 -m unittest -v test_model.py test_explorer.py test_file_preview.py test_settings.py test_flyouts.py test_desktop_backgrounds.py test_desktop_motion.py test_saved_groups.py test_session_actions.py
# Frontend: use the pinned lockfile, then rebuild committed dist/ assets.
corepack pnpm install --frozen-lockfile
node build.mjs
cd ..
python3 tests/gnome_live.py
# Real WebKit-to-session-service routing on a private Xvfb display and D-Bus;
# the receiving test services cannot lock or end the host session.
python3 companion/test_session_actions_live.py
python3 companion/test_theme_items_live.py
# Optional network-dependent verification:
ZORIN11_TEST_FEEDS=1 python3 tests/gnome_live.py
```

The GNOME live test starts a private headless Mutter/Wayland compositor, private D-Bus, settings, runtime and companion state. It exercises the shared UI, native Wayland resizing/desktops/thumbnails, notification read/dismiss, every installed Zorin thumbnail and wallpaper apply/restore. It closes only its disposable processes and windows. The default run does not access image feeds.

GNOME support shares the repository's Linux-based Windows-style experience; it does not provide Windows APIs, Microsoft Windows Terminal, Phone Link, Windows Widgets or commercial Start11/Fences binaries. The broader feature inventory is in [PARITY.md](PARITY.md).
