# Windows 11 → Zorin GUI coverage

Target: Windows 11 visual and interaction conventions on Zorin 18, with GNOME as the primary desktop and Lite/Xfce/X11 retained, preserving Linux behavior. This inventory records delivered capabilities and remaining differences; it is not a claim that the desktop is indistinguishable from Windows. Current implementation: 2026-10-19.

GNOME backend (2026-10-19): shared Start, Explorer, Settings, Quick Settings, notification/calendar and Desktop Groups interfaces; Mutter bridge for native Wayland/X11 windows, Task View/desktops, Snap Layouts and saved groups; installed Zorin wallpapers alongside Spotlight/Bing and local photos. Native Zorin taskbar previews remain in use. GNOME notifications last for the login session, workspace animations use Mutter, and application size constraints are enforced by the compositor. The detailed matrix below describes the original Xfce integration where a desktop is named explicitly. See [the GNOME installation guide](README.md) for platform-specific behavior.


| Area | Delivered | Remaining differences / next work |
|---|---|---|
| 1. Desktop | Dark appearance, personal Windows icons, This PC, shortcut groups, optional Spotlight/Bing rotation with history | Desktop context menus and selection visuals remain Xfce; Spotlight refresh is per login session |
| 2. Taskbar | Centered Start/app area, 32 px icons, distinct active/running/closed states through Docklike, live grouped hover thumbnails with close buttons, bounded overflow and minimized/icon fallbacks, live Snap Group cards with whole-layout restoration; Task View button, search, tray overflow, compact Fluent network/audio, clock/date, laptop battery retained | Desktop peek, badges/progress and per-monitor taskbars need further work |
| 3. Start | Anchored rounded panel, pinned grid/reordering, persistent app folders with drag/drop and keyboard controls, All apps/categories, search, recent launches, verified native GNOME account/power actions | Recommended documents, expanded jump lists |
| 4. Search | Unified apps, scoped local filenames/folders and Settings search; category filters, keyboard navigation, safe file previews and Open file location | Whole-disk/content indexing, configurable search scopes and remaining Windows keyboard conventions |
| 5. Window frames | Dark Xfwm/Compiz frames, thin borders, large caption targets, red Close hover, companion captions and edge/corner resizing | Third-party custom title bars and corner/shadow parity vary |
| 6. Snap Layouts | Win+Z six-layout picker, Explorer/Settings maximize hover, target outline, minimum-size checks, Snap Assist, live Snap Groups in Task View, taskbar previews and Alt+Tab; persistent app/layout recipes with on-demand relaunch, rename/remove and screen scaling with combined MRU, live mosaics and release-to-select, restore size, adjustable Focus columns; existing edge/arrow snapping retained | Third-party maximize-hover integration, drag-to-top snap bar, custom free-form zones, document/browser-session restoration |
| 7. File Explorer | This PC drive capacity, personal Windows drive/folder icons, tabs, breadcrumbs/address, sidebar, views, details and bounded image/text preview panes, Windows-style context menus, Rename/Properties, copy/move progress, pause/resume/cancel, conflict choices and per-item retry | Additional preview formats; network/Trash handled by native tools |
| 8. Settings | Windows-style Home/sidebar/cards/search and 12 categories; working controls and real system information | Advanced pages still open Linux tools; individual pages can be progressively integrated |
| 9. Quick Settings | Wi-Fi/Bluetooth toggles and management, volume/mute, output selection with active-stream routing, DND, keyboard accessibility, six editable tiles, hardware backlight and battery readout | Battery-saver/airplane-mode controls, richer connected-device UI, external-monitor DDC/CI brightness; laptop hardware validation |
| 10. Notifications | Unified clock/bell/Win+N flyout, grouped real Xfce history, unread indicator, mark-read/dismiss/clear, DND, keyboard-accessible month calendar, dark rounded bottom-right native toast theme | Calendar-account appointments, richer live notification actions and Windows-specific grouping/animation details |
| 11. Visual design | Dark rounded companion surfaces, accent colors, shadows, captured-background blur for Start/Quick Settings | Uniform Mica/Acrylic across native applications and light-mode counterpart |
| 12. Typography | Segoe UI from personal export, Selawik fallback, tuned companion sizes/spacing, Cascadia terminal | Variable-font coverage and typography consistency in third-party apps |
| 13. Icons | Community Win11 base, Fluent toolbar/tray icons, optional personal Windows system assets at six sizes | Third-party app/tray icon consistency; additional Fluent category artwork |
| 14. Controls | Companion controls plus shared dark GTK3 buttons, entries, toolbars, views, tabs, switches and focus states | GTK4/libadwaita, Qt and custom app controls retain toolkit differences |
| 15. Dialogs | Explorer dialogs with dark action footers and keyboard dismissal; GTK3 dialog palette; native file/authentication dialogs | Windows-style common-dialog layouts, copy/conflict progress experience |
| 16. Lock screen | Spotlight/background shared through Xfce Screensaver; lock preferences accessible | Windows clock/login/avatar layout and transitions; LightDM login screen unchanged |
| 17. Power menu | Existing lock/session/power actions through supported Linux tools | Windows-style confirmation screens; hibernate remains hardware/system dependent |
| 18. Animations | Hover transitions, optional Compiz wobble with recovery preview; native desktop slides, wallpaper crossfades, three speeds, motion-off controls and monitor-aware pacing | Exact Windows easing/background motion; opening/minimizing/snapping/notification parity; Xfwm uses instant workspace switching |
| 19. Virtual desktops | Bottom desktop preview strip; create/name/switch/close; drag to reorder or Move left/right menu; individual pictures with shared Spotlight fallback; Compiz slides/background crossfades; drag windows or Move to menu; cross-desktop search; Win+Ctrl+D/Left/Right/F4; safe app migration; Xfwm and Compiz support | Exact Windows easing/background motion; unavailable thumbnails use cached previews/icons; desktop pictures span all monitors |
| 20. Multimonitor | Settings reports live monitors and opens native arrangement/scaling; wallpaper applies to connected monitors | Per-monitor taskbars, independent wallpaper selection and fractional-scale consistency |
| 21. Widgets | Desktop shortcut groups and folder portals | Calendar/weather/resource widgets; news feed intentionally not added by default |
| 22. System utilities | PowerShell, WezTerm profiles/tabs/splits, screenshot entry; GNOME Task Manager via Mission Center with expandable app groups, icons, supported GPU telemetry and Services view | Device Manager, Disk Management, Event Viewer and clipboard UI; NVIDIA telemetry verification after the pending local reboot |
| 23. Input | Windows-style shortcuts, original Linux drag/drop, keyboard/mouse preferences | Cursor parity, emoji picker, touch keyboard and touch gestures |
| 24. Accessibility | Real Sticky/Slow/Bounce/Mouse Keys, native accessibility preferences, keyboard focus, reduced motion in new Settings | Unified contrast, magnification, scaling and screen-reader validation |
| 25. Theming consistency | GTK3 styling, Xfwm/Compiz, React/WebKit companion, WezTerm, Win11 icon theme | GTK4/libadwaita, Qt, Electron and Flatpak need app-specific validation |

## Next implementation priorities

1. Optional recent documents and configurable search scopes; unified search and Start app folders are complete.
2. Additional Explorer preview formats and GNOME taskbar badge/progress integration; transfer/conflict dialogs are complete.
3. Additional Settings pages and native dialog styling; close remaining icon and spacing differences against the user's Windows reference.
4. Battery-saver and connected-device controls, plus richer notification actions where supported.
5. Validate on the laptop, especially real backlight control, battery, touchpad, scaling, suspend and multiple displays.

All changes should remain reproducible through this package and reversible through its recovery manifest. Personal Windows assets and wallpaper caches stay outside Git. No bootloader, Windows partition, GPU driver or dual-boot configuration changes are part of the visual package.
