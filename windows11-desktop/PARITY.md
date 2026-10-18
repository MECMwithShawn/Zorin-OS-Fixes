# Windows 11 → Zorin Lite GUI coverage

Target: Windows 11 visual and interaction conventions on Zorin 18 Lite/Xfce/X11, preserving Linux behavior. This inventory records delivered capabilities and remaining differences; it is not a claim that the desktop is indistinguishable from Windows. Current implementation: 2026-10-17.

| Area | Delivered | Remaining differences / next work |
|---|---|---|
| 1. Desktop | Dark appearance, personal Windows icons, This PC, shortcut groups, optional Spotlight/Bing rotation with history | Desktop context menus and selection visuals remain Xfce; Spotlight refresh is per login session |
| 2. Taskbar | Centered Start/app area, pins/running indicators through Docklike, search, tray overflow, compact Fluent network/audio, clock/date, laptop battery retained | Windows thumbnail styling, badges/progress, Task View and per-monitor taskbars need further work |
| 3. Start | Anchored rounded panel, pinned grid/reordering, All apps/categories, search, recent launches, account and power actions | Recommended documents, app folders, expanded jump lists |
| 4. Search | Local application search, category navigation, Settings search | Unified file/settings search, previews and full keyboard navigation parity |
| 5. Window frames | Dark Xfwm/Compiz frames, thin borders, large caption targets, red Close hover, companion captions | Third-party custom title bars and corner/shadow parity vary |
| 6. Snap Layouts | Existing Xfwm/Compiz edge and keyboard snapping | Maximize-hover layout chooser, Snap Groups and custom zones |
| 7. File Explorer | This PC drive capacity, personal Windows drive/folder icons, tabs, breadcrumbs/address, sidebar, views, details pane, common file operations | Content preview pane, richer context menus, network/Trash handled by native tools |
| 8. Settings | Windows-style Home/sidebar/cards/search and 12 categories; working controls and real system information | Advanced pages still open Linux tools; individual pages can be progressively integrated |
| 9. Quick Settings | Wi-Fi/Bluetooth toggles and management, volume/mute, output selection with active-stream routing, DND, keyboard accessibility, six editable tiles, hardware backlight and battery readout | Battery-saver/airplane-mode controls, richer connected-device UI, external-monitor DDC/CI brightness; laptop hardware validation |
| 10. Notifications | Unified clock/bell/Win+N flyout, grouped real Xfce history, unread indicator, mark-read/dismiss/clear, DND, keyboard-accessible month calendar, dark rounded bottom-right native toast theme | Calendar-account appointments, richer live notification actions and Windows-specific grouping/animation details |
| 11. Visual design | Dark rounded companion surfaces, accent colors, shadows, captured-background blur for Start/Quick Settings | Uniform Mica/Acrylic across native applications and light-mode counterpart |
| 12. Typography | Segoe UI from personal export, Selawik fallback, tuned companion sizes/spacing, Cascadia terminal | Variable-font coverage and typography consistency in third-party apps |
| 13. Icons | Community Win11 base, Fluent toolbar/tray icons, optional personal Windows system assets at six sizes | Third-party app/tray icon consistency; additional Fluent category artwork |
| 14. Controls | Companion buttons, switches, sliders, selects, progress and focus states | Native GTK/Qt controls retain toolkit differences |
| 15. Dialogs | Functional file-operation dialogs and native file/authentication dialogs | Windows-style common-dialog layouts, copy/conflict progress experience |
| 16. Lock screen | Spotlight/background shared through Xfce Screensaver; lock preferences accessible | Windows clock/login/avatar layout and transitions; LightDM login screen unchanged |
| 17. Power menu | Existing lock/session/power actions through supported Linux tools | Windows-style confirmation screens; hibernate remains hardware/system dependent |
| 18. Animations | Hover transitions, optional Compiz wobble with recovery preview | Opening/minimizing/snapping/workspace/notification motion parity |
| 19. Virtual desktops | Native Xfce/Compiz workspaces retained | Windows Task View thumbnails, names and transitions |
| 20. Multimonitor | Settings reports live monitors and opens native arrangement/scaling; wallpaper applies to connected monitors | Per-monitor taskbars, independent wallpaper selection and fractional-scale consistency |
| 21. Widgets | Desktop shortcut groups and folder portals | Calendar/weather/resource widgets; news feed intentionally not added by default |
| 22. System utilities | PowerShell, WezTerm profiles/tabs/splits, screenshot entry, native administration tools | Windows-style Task Manager, Device Manager, Disk Management, Services, Event Viewer and clipboard UI |
| 23. Input | Windows-style shortcuts, original Linux drag/drop, keyboard/mouse preferences | Cursor parity, emoji picker, touch keyboard and touch gestures |
| 24. Accessibility | Real Sticky/Slow/Bounce/Mouse Keys, native accessibility preferences, keyboard focus, reduced motion in new Settings | Unified contrast, magnification, scaling and screen-reader validation |
| 25. Theming consistency | GTK3 styling, Xfwm/Compiz, React/WebKit companion, WezTerm, Win11 icon theme | GTK4/libadwaita, Qt, Electron and Flatpak need app-specific validation |

## Next implementation priorities

1. Snap layout chooser and improved task switching, preserving reliable window-manager behavior.
2. Additional Settings pages and native dialog styling; close remaining icon and spacing differences against the user's Windows reference.
3. Battery-saver and connected-device controls, plus richer notification actions where supported.
4. Validate on the laptop, especially real backlight control, battery, touchpad, scaling, suspend and multiple displays.

All changes should remain reproducible through this package and reversible through its recovery manifest. Personal Windows assets and wallpaper caches stay outside Git. No bootloader, Windows partition, GPU driver or dual-boot configuration changes are part of the visual package.
