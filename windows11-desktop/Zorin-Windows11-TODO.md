# Windows 11 Desktop Parity — TODO

Target: Zorin OS 18.1 Lite, Xfce 4.20, X11. Extend the existing Python/GTK3/WebKit/React companion rather than replacing the desktop stack.

Source of truth: [PARITY.md](PARITY.md). Refer to [VALIDATION.md](VALIDATION.md) before modifying tested behavior.

## P0 — Highest-impact desktop improvements
- [ ] Taskbar: live thumbnail hover previews, close controls and fallbacks for windows without previews.
- [ ] Taskbar: per-app badges and progress indicators when real application state is available.
- [ ] Taskbar: expose Snap Groups in previews and switching, handling closed/minimized windows correctly.
- [ ] Start: app folders with drag/drop creation and persistent ordering.
- [ ] Start: optional recommended/recent documents, with local-only indexing and privacy exclusions.
- [ ] Search: unified apps, local files and settings search with previews and keyboard navigation.
- [ ] Perform Windows 11 screenshot-based visual comparisons at matched scale for taskbar, Start, flyouts and window chrome.

## P1 — Window management and Explorer
- [ ] Expand maximize-hover Snap Layouts to compatible third-party windows; keep Win+Z fallback.
- [ ] Investigate top-edge snap bar and persistent layout presets without breaking native tiling.
- [x] Task View: workspace thumbnails plus create, rename and remove desktop actions. Verified 2026-10-18.
- [ ] Task View: reorder desktops and choose separate desktop wallpapers.
- [x] Task View: display Snap Groups and per-workspace previews. Includes drag/Move to, cross-desktop search and Win+Ctrl desktop shortcuts; verified on Xfwm and Compiz.
- [ ] Explorer: safe preview pane with allowlisted content types and file-size limits.
- [ ] Explorer: richer context menus, file properties, transfer/conflict dialogs and reliable operation errors.
- [ ] Add Start/taskbar jump lists and recent-item actions where supported.

## P2 — System appearance and utilities
- [ ] Match corner radii, caption spacing, shadows, controls and hover states across supported window managers.
- [ ] Acrylic/Mica-inspired translucent surfaces with solid/reduced-effects fallback and reasonable GPU use.
- [ ] Validate GTK3, GTK4/libadwaita, Qt, Electron and Flatpak differences; avoid fragile global overrides.
- [ ] Improve notification actions/grouping and animations while respecting DND and logging preferences.
- [ ] Add supported battery-saver, airplane-mode and connected-device controls to Quick Settings.
- [ ] Build a Windows-inspired clock/avatar lock screen without weakening LightDM/Xfce authentication.
- [ ] Windows-inspired Task Manager, Device Manager, Disk Management, Services and Event Viewer equivalents using real Linux information and permission boundaries.
- [ ] Polish cursor, emoji input, scaling, accessibility, keyboard navigation and reduced-motion behavior.
- [ ] Evaluate per-monitor taskbars, wallpapers, snapping and mixed-DPI layouts.
- [ ] Retain and validate existing 4K Spotlight/Bing rotation rather than duplicate it.

## Premium Visual Fidelity — rendering and polish
- [ ] Detect native monitor resolution, refresh rate, DPI, GPU renderer and active scale without changing display modes automatically.
- [ ] Verify native-resolution rendering at 1080p, 1440p and 4K, including 100%, 125%, 150% and 200% scaling where supported; document Xfce/X11 fractional-scaling limits.
- [ ] Eliminate blurry text and bitmap upscaling in the companion; ensure appropriate WebKit device scale and consistent font hinting/antialiasing.
- [ ] Standardize Segoe UI Variable where locally available and license-permitted, with Selawik fallback; tune weights, line heights and baseline alignment.
- [ ] Render Fluent vector icons or multi-resolution assets at intended pixel sizes and test HiDPI tray, taskbar and Explorer icons.
- [ ] Establish design tokens for radii, spacing, shadows, colors, translucency and accent states across Start, Settings, Explorer and flyouts.
- [ ] Offer GPU-friendly Acrylic/Mica-inspired effects with graceful fallback, reduced-motion support and no sensitive-content capture.
- [ ] Refine window transitions, hover and focus animations for consistent pacing without introducing input lag or tearing.
- [ ] Ensure Spotlight/Bing wallpaper downloads match the target monitor aspect ratio and available native resolution while preserving cached originals.
- [ ] Produce matched Windows 11/Zorin screenshot comparisons at identical resolution and UI scale; record visual defects as reproducible issues.
- [ ] Profile CPU/GPU use, memory, idle activity, frame pacing and launch latency on real hardware before enabling effects by default.
- [ ] Maintain exact restore/rollback coverage for every new rendering or appearance setting.

## Validation and release requirements
- [ ] Define screenshots, geometry, interaction states and keyboard accessibility acceptance criteria before implementation.
- [ ] Verify fresh install, upgrade, rollback and user-setting preservation on isolated X11/Xephyr sessions.
- [ ] Verify Xfwm and optional Compiz separately with fail-safe window-manager recovery.
- [ ] Test actual laptop battery, backlight, touchpad, scaling, suspend and external displays.
- [ ] Preserve private Windows assets/fonts locally; never commit proprietary exports, credentials or recovery manifests.
- [ ] Make no changes to bootloader, partitions, GPU drivers, disk layout or unrelated fixes.
- [ ] Update PARITY.md, VALIDATION.md and README.md after each verified milestone.

**Definition of done:** a stable, reversible, reproducible Windows 11-like Linux desktop. Exact third-party app parity and Windows API compatibility are out of scope.
