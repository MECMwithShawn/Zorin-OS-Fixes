# Windows 11 desktop for Zorin Lite

Reusable setup for **Zorin OS 18 Lite, Xfce, X11, Intel/AMD x86-64**. This is the configuration developed on the desktop PC, packaged for the same Zorin edition on a dual-boot laptop. The installer discovers panel/plugin IDs and uses the current account's home directory. It does not copy disk names, display resolution, network settings, or the desktop PC's personal data.

## Install on the laptop

Run inside a terminal in the laptop's Zorin desktop, as your normal user:

```bash
git clone https://github.com/MECMwithShawn/Zorin-OS-Fixes.git
cd Zorin-OS-Fixes/windows11-desktop
./install-system-deps.sh
python3 setup.py check
python3 setup.py install
```

The dependency command requests sudo for Ubuntu packages. Desktop customization, PowerShell, WezTerm, and fonts install into your account. A prebuilt React frontend is included; Node is not needed for installation. Downloads are pinned in `dependencies.json`; PowerShell, WezTerm, Cascadia, and the PowerShell icon are checked against recorded SHA-256 hashes. The icon theme uses a pinned Git revision. Allow about 1 GB for downloads and extracted tools.

Run `python3 setup.py install` again after pulling updates. It retains the original recovery record and your saved Start pins/groups while reapplying the managed appearance. `--skip-terminal` skips tool downloads; already installed local PowerShell/WezTerm are still integrated.

## Included

| Component | Behavior |
|---|---|
| Desktop | Dark Zorin theme, 48 px bottom taskbar, centered Start/app area, Windows-style spacing and controls |
| Window captions | Original flat dark Xfwm/Compiz frames, thin borders, 46 px caption controls, red Close hover, and matching GTK3 title buttons |
| Start | Pinned apps, drag ordering, search, All apps, categories, recent launches, power/session actions |
| File Explorer / This PC | Tabs, sidebar, address navigation, details view, mounted drives and capacity bars, create/rename/copy/cut/paste/trash |
| Desktop Groups | Movable, resizable shortcut groups and live folder portals; original files stay in place |
| Status tray | Microsoft Fluent Wi-Fi/Ethernet/offline and speaker/mute icons, crisp at their native size; chevron reveals hidden tray apps |
| Quick Settings | Wi-Fi/Bluetooth toggles, volume/mute and output selection, keyboard accessibility, editable tiles, laptop brightness and battery status when available |
| Notifications & calendar | Clock/bell/Win+N flyout, grouped local history, read/dismiss/clear, Do Not Disturb, keyboard-navigable calendar and dark bottom-right toast banners |
| Settings | Windows 11 style sidebar, searchable categories, real system information and working controls; advanced pages open the corresponding Linux tools |
| Backgrounds | Optional Windows Spotlight or Bing daily images, UHD preference, local photo selection, 60-image history and original-background restore |
| Battery | The laptop's existing power/battery panel plugin stays visible when a battery is detected |
| PowerShell | Microsoft PowerShell 7.6.7, installed per user with a Start entry |
| Terminal | WezTerm with PowerShell and Bash profiles, tabs, split panes, Cascadia Mono, dark Campbell colors, Windows-style title buttons |
| Window Effects | Optional Compiz wobbly windows, with a timed preview and an off switch |

The duplicate Wi-Fi icon is removed by using `nm-applet --no-indicator` with `show-applet=false`. NetworkManager and its password/VPN agent keep running. The tray chevron can still reveal other applications. Right-click the tray and open its properties to choose which applications stay visible; newly discovered tray applications may initially appear until you hide them there.

## Match the Windows shell icons and fonts

The default installer uses the community [Win11 icon theme](https://github.com/yeyushengfan258/Win11-icon-theme) plus the bundled [Microsoft Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) for the status tray, Explorer toolbar, and Quick Settings. For the closest match in This PC, drive icons, and folders, export shell icons from **your own Windows installation**:

1. Boot Windows and copy `export-windows-assets.ps1` there.
2. Run it in **Windows PowerShell 5.1**, without administrator privileges:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\export-windows-assets.ps1
   ```

   Optionally add `-IncludeFonts` to include the locally installed Segoe UI fonts. The ZIP is created on the Windows desktop. Keep this personal export local; Microsoft Windows assets and fonts are not included in this repository.

3. Copy the ZIP to Zorin's Downloads folder, then run:

   ```bash
   python3 setup.py install --windows-assets "$HOME/Downloads/Zorin11-Windows-assets.zip"
   ```

This imports six sizes (16–256 px), including the computer, drive, USB drive, folder, user folders, Recycle Bin, and Explorer icons. Segoe UI is used when imported; Selawik is the default fallback. Drive labels and capacity are read from the laptop itself.

## Use it

| Shortcut | Action |
|---|---|
| Windows key / Ctrl+Esc | Start |
| Win+S | Search |
| Win+E | File Explorer |
| Win+A | Quick Settings |
| Win+N / taskbar clock or bell | Notifications and calendar |
| Win+I | Windows-style Settings |
| Win+T / Ctrl+Alt+T | Terminal |
| Win+Shift+F | Bring Desktop Groups forward / send them back |
| Ctrl+Shift+T in Terminal | New tab |
| Ctrl+Shift+Space in Terminal | Select PowerShell or Bash profile |
| Alt+Shift+D in Terminal | Split horizontally |
| Alt+Shift+- in Terminal | Split vertically |

Search Start for **Window Effects** to preview wobble. Its **Install wobble support** button installs the optional Compiz packages through the Linux authentication dialog. A preview returns to Xfwm automatically unless you choose **Keep** within 15 seconds; an independent watchdog also recovers if the preview UI fails. Kept effects return on login. **Turn off** restores Xfwm. Compiz uses a private profile and preserves Start, Explorer, and terminal shortcuts. Window decoration and snapping behavior can differ while it is active.

Emergency recovery, from a terminal or TTY in your session:

```bash
python3 "$HOME/.local/share/zorin11-hub/effects.py" --disable
```

For a TTY, set `DISPLAY` to your actual X11 display before that command (commonly `:0`).

## Notifications and Quick Settings

Click the taskbar **clock** or **bell**, or press **Win+N**, for the notification center and calendar. The bell shows an unread indicator and Do Not Disturb state. The calendar supports previous/next month, date selection with arrow keys, Home for today, Page Up/Down for months, and collapse/expand. This is a date browser; calendar-account appointments are not connected.

Notifications come from Xfce Notifyd's existing local log, grouped by application. You can mark them read, dismiss one or a group, or clear all after confirming. The latest 200 are displayed; older retained entries remain accessible in native notification preferences. The installer enables local history and uses Xfce's existing retention limit, defaulting to 1,000 when none is set. Excluded applications and transient notifications retain their native logging behavior. **Settings → System → Notifications → Notification history** turns storage on/off. Restore returns the original logging, banner theme/location, clock command and panel plugin settings, while retaining the user's notification history.

**Win+A** opens Quick Settings. Use the button beside volume to choose a sound output; current streams using the previous default output move with it, while explicitly separate app routes remain unchanged. The Accessibility tile exposes Sticky/Slow/Bounce/Mouse Keys. The pencil button chooses which of six tiles appear, and saves the selection. Bluetooth's main button toggles power; its arrow opens device management. Wi-Fi uses the same split control.

Brightness appears only for real kernel backlight devices (usually a laptop's built-in screen), controlled through the active user's logind session. External-monitor DDC/CI brightness is not implemented. Battery details appear only when a battery is detected. Native hardware controls report errors instead of claiming a failed change succeeded.

## Settings and Windows Spotlight

Open **Win+I → Personalization → Background**. Choose **Windows Spotlight** or **Bing image of the day**, then **Get new wallpaper**. Turn on **Change the picture daily** to refresh once per local calendar day while signed in. On login, the companion checks for an update; an offline failure leaves the existing picture in place and retries no more than hourly. Rotation does not require Settings to stay open. New installations keep the current background until you choose a source.

Bing requests UHD with a 1080p fallback. Spotlight uses the original landscape image returned by Microsoft's Windows 11 feed (up to 4K); images can differ between devices and days. These are unofficial feed integrations and service availability can change. No Microsoft account is used. The downloader requests metadata and image assets only, never the feed's analytics or action links. Images, credits, and history stay in your local account; they are not bundled or uploaded to this repository.

**Browse photos** accepts JPEG/PNG images. Recent images can be selected again. **Restore original background** disables rotation and restores the backed-up Xfce background properties, preserving properties you changed manually after the companion applied its picture. Xfce Screensaver reads the desktop background; the separate LightDM login screen is not changed. The full package restore also restores managed wallpaper settings and stops rotation, while retaining the image cache.

Settings includes working volume/output/mute, Wi-Fi and Bluetooth power, Do Not Disturb, screen blanking timeouts, keyboard accessibility, and desktop-group controls. Display arrangement, network configuration, software updates, drivers, themes, and other advanced configuration open the installed Linux settings tools. Hardware, storage, account and OS information come from this device. Settings does not label Zorin as Windows or invent security/update status.

The broader Windows 11 replication inventory and remaining work are tracked in [PARITY.md](PARITY.md).

## Restore the previous desktop

```bash
python3 setup.py restore
```

Or, without the repository checkout:

```bash
python3 "$HOME/.local/share/zorin11-hub/install.py" --uninstall
```

The installer saves the original file contents and typed Xfconf/GSettings values **before** modifying them in `~/.config/zorin11-hub/integration-backup.json`. Restore changes only entries that still match the installed values. Later manual edits are preserved and reported. Saved pins, groups, imported reference assets, source files, downloaded tools, icon themes, fonts, and installed system packages remain available. Restore does not remove packages or personal files.

## Files and limits

Caption changes appear immediately for native window frames. Reopen an existing GTK3 application if it has cached the previous styling. Applications that draw their own controls, including GTK4/libadwaita and some cross-platform apps, may retain their own title bars. Compiz theme updates refresh the decorator without replacing the window manager or changing the saved wobble preference.

- Application: `~/.local/share/zorin11-hub/`
- Pins/groups: `~/.config/zorin11-hub/layout.json`
- Background state/history: `~/.config/zorin11-hub/wallpapers.json` and `wallpapers/`
- Runtime log: `~/.config/zorin11-hub/desktop.log`
- Optional effects log: `~/.config/zorin11-hub/effects.log`
- Terminal preferences: `~/.config/wezterm/wezterm.lua`
- Download cache: `~/.cache/zorin11-setup/`

This is a Linux desktop styled after Windows 11, with working Linux applications. It does not provide Windows APIs, Microsoft Windows Terminal, commercial Start11/Fences binaries, or Windows-only commands such as `winver`. WezTerm supplies the terminal experience. Thunar remains available for advanced file operations, network browsing, and Trash. Phone Link, Windows widgets, and every Windows shell feature are outside this package. Zorin Core/GNOME, Wayland, ARM, and older Zorin releases are not supported by this installer.

The package leaves dual-boot configuration, Windows partitions, bootloader settings, GPU drivers, display modes, and suspend fixes to their existing tools.

## Development and validation

The companion uses Python/GTK3/WebKit2GTK 4.1 and a local React interface. All UI assets are local; no web server is exposed.

```bash
python3 -m unittest discover -s tests -v
cd companion
python3 -m unittest -v test_model.py test_explorer.py test_settings.py test_flyouts.py
# For frontend changes, use the committed pnpm lockfile:
corepack pnpm install --frozen-lockfile
node build.mjs
```

Live tests require an X11 session and briefly open disposable windows. `test_live.py` uses a separate application ID and temporary files. `test_native.py` should be run with a temporary `ZORIN11_CONFIG_DIR`. `test_flyouts_live.py` uses Xephyr and a private D-Bus session, config and cache to verify notification ingestion/read/delete without modifying the live user history. Browser UI tests additionally need Playwright and a Chromium executable; see their environment variables.

Original artwork/code and the Fluent icon license are included with their notices. Windows reference exports, SSH credentials, account photos, screenshots of personal applications, and machine recovery manifests must never be committed.

Spotlight feed protocol reference: [ORelio/Spotlight-Downloader](https://github.com/ORelio/Spotlight-Downloader/blob/master/SpotlightAPI.md). The Python integration here is original code using the documented v4 image feed.

Notification integration uses the [Xfce Notifyd log interface](https://github.com/xfce-mirror/xfce4-notifyd/blob/xfce4-notifyd-0.9.7/common/xfce-notify-log-util.c) and [Xfce clock command](https://github.com/xfce-mirror/xfce4-panel/blob/xfce4-panel-4.20.3/plugins/clock/clock.c). Backlight control uses [logind SetBrightness](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html).
