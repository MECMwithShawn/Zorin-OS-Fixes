# Windows 11 Desktop Parity — TODO

Target: Zorin OS 18.1 GNOME 46 (default), with Lite/Xfce 4.20 retained. Extend the existing Python/GTK3/WebKit/React companion. Existing Xfce-only validations below do not imply GNOME parity.

Source of truth: [PARITY.md](PARITY.md). Refer to [VALIDATION.md](VALIDATION.md) before modifying tested behavior.

## P0 — Highest-impact desktop improvements
- [x] Taskbar: live grouped hover thumbnails, per-window Close, minimized/icon fallbacks and scrollable overflow. Includes launcher-less app grouping; verified on Xfwm, Compiz and the installed desktop on 2026-10-18.
- [ ] Taskbar: per-app badges and progress indicators when real application state is available.
- [x] Taskbar: Snap Group cards with live layout previews; restore grouped positions and minimized members together; remove stale/closed members.
- [x] Window switching: native GTK Alt+Tab chooser with individual windows and Snap Groups, live mosaics, combined MRU, forward/reverse cycling, release-to-select and Escape. Xfce shortcuts work on Xfwm and Compiz; verified 2026-10-18.
- [x] Start: app folders with drag/drop creation, persistent ordering, rename, keyboard-accessible move controls and ungrouping. Shared GNOME/Xfce interface; verified 2026-10-19.
- [x] Start: optional recommended/recent documents from existing local desktop history, respecting search scopes, private entries and exclusions. Verified 2026-10-19.
- [x] Search: unified apps, scoped local filenames/folders and settings search with previews, filters and keyboard navigation. Verified 2026-10-19.
- [x] Search: configurable folders and exclusions through Search & Start settings. Verified 2026-10-19.
- [ ] Search: optional content indexing beyond bounded filename search.
- [ ] Perform Windows 11 screenshot-based visual comparisons at matched scale for taskbar, Start, flyouts and window chrome.

## P1 — Window management and Explorer
- [ ] Expand maximize-hover Snap Layouts to compatible third-party windows; keep Win+Z fallback.
- [x] Persist Snap Group app/layout recipes across restarts; on-demand relaunch, rename/remove and monitor scaling.
- [ ] Investigate top-edge snap bar and custom free-form zones without breaking native tiling.
- [x] Task View: workspace thumbnails plus create, rename and remove desktop actions. Verified 2026-10-18.
- [x] Task View: reorder desktops and choose separate desktop wallpapers. Drag or Move left/right; local JPEG/PNG per desktop; shared Spotlight fallback. Verified 2026-10-18 on Xfwm and Compiz.
- [x] Desktop switching: native Compiz slides, individual-picture crossfades, three speeds and reduced-motion controls. Standard Xfwm retains instant switching. Verified 2026-10-18.
- [x] Task View: display Snap Groups and per-workspace previews. Includes drag/Move to, cross-desktop search and Win+Ctrl desktop shortcuts; verified on Xfwm and Compiz.
- [x] Explorer: read-only image/text preview pane with allowlisted content, file/pixel limits, timed decoding and stale-selection rejection. Verified 2026-10-19.
- [x] Explorer: Windows-style context menus, Rename, Properties, Copy as path and drive details.
- [x] Explorer: copy/move progress, pause/resume/cancel, Replace/Skip/Keep both, folder merge, apply-to-remaining choices and per-item error/retry dialogs. Verified 2026-10-19.
- [x] Start/search: real installed desktop-entry actions; Explorer New window/This PC also appear in the native GNOME taskbar menu.
- [ ] Expand app-specific recent-file jump lists where supported.

## P2 — System appearance and utilities
- [ ] Match corner radii, caption spacing, shadows, controls and hover states across supported window managers.
- [ ] Acrylic/Mica-inspired translucent surfaces with solid/reduced-effects fallback and reasonable GPU use.
- [ ] Validate GTK3, GTK4/libadwaita, Qt, Electron and Flatpak differences; avoid fragile global overrides.
- [ ] Improve notification actions/grouping and animations while respecting DND and logging preferences.
- [x] Quick Settings: supported battery saver with previous-mode restoration, GNOME airplane mode, connected/paired Bluetooth controls and reported device battery. Shared Settings controls and unavailable/hardware-lock states; verified 2026-10-19. AirPods stayed connected during live discovery/cleanup. Searchable pairing groups duplicate names, preserves address selection, handles confirmation/PINs and stops scanning after one minute; new physical pairing through this picker remains pending.
- [ ] Build a Windows-inspired clock/avatar lock screen while preserving native GNOME/GDM and Xfce authentication.
- [x] GNOME Task Manager: Mission Center, expandable application groups, program icons, merged usage and supported GPU graphs. Intel and NVIDIA RTX 4090 laptop telemetry verified in Mission Center after the local NVIDIA driver reboot.
- [ ] Windows-inspired Device Manager, Disk Management and Event Viewer equivalents; Task Manager includes Mission Center's Services view.
- [ ] Polish cursor, emoji input, scaling, accessibility, keyboard navigation and reduced-motion behavior.
- [ ] Evaluate per-monitor taskbars, wallpapers, snapping and mixed-DPI layouts.
- [ ] Retain and validate existing 4K Spotlight/Bing rotation rather than duplicate it.

## Premium Visual Fidelity — rendering and polish
- [x] Extend the dark palette to native GTK3 controls/dialogs; match Explorer dialog footers, active/inactive borders and all-edge/corner resizing in Explorer/Settings. Other toolkits still need app-specific work.
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
