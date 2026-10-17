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
| Start | Pinned apps, drag ordering, search, All apps, categories, recent launches, power/session actions |
| File Explorer / This PC | Tabs, sidebar, address navigation, details view, mounted drives and capacity bars, create/rename/copy/cut/paste/trash |
| Desktop Groups | Movable, resizable shortcut groups and live folder portals; original files stay in place |
| Status tray | Microsoft Fluent Wi-Fi/Ethernet/offline and speaker/mute icons, crisp at their native size; chevron reveals hidden tray apps |
| Quick Settings | Network status, Wi-Fi control, volume/mute, sound settings, Bluetooth settings, Do Not Disturb |
| Battery | The laptop's existing power/battery panel plugin stays visible when a battery is detected |
| PowerShell | Microsoft PowerShell 7.6.7, installed per user with a Start entry |
| Terminal | WezTerm with PowerShell and Bash profiles, tabs, split panes, Cascadia Mono, dark Campbell colors, Windows-style title buttons |
| Window Effects | Optional Compiz wobbly windows, with a timed preview and an off switch |

The duplicate Wi-Fi icon is removed by using `nm-applet --no-indicator` with `show-applet=false`. NetworkManager and its password/VPN agent keep running. The tray chevron can still reveal other applications. Right-click the tray and open its properties to choose which applications stay visible; newly discovered tray applications may initially appear until you hide them there.

## Match the Windows shell icons and fonts

The default installer uses the community [Win11 icon theme](https://github.com/yeyushengfan258/Win11-icon-theme) plus the bundled [Microsoft Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) for the status tray. For the closest match in This PC, drive icons, and folders, export shell icons from **your own Windows installation**:

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
| Win+I | Xfce Settings |
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

- Application: `~/.local/share/zorin11-hub/`
- Pins/groups: `~/.config/zorin11-hub/layout.json`
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
python3 -m unittest -v test_model.py test_explorer.py
# For frontend changes, use the committed pnpm lockfile:
corepack pnpm install --frozen-lockfile
node build.mjs
```

Live tests require an X11 session and briefly open disposable windows. `test_live.py` uses a separate application ID and temporary files. `test_native.py` should be run with a temporary `ZORIN11_CONFIG_DIR`. Browser UI tests additionally need Playwright and a Chromium executable; see their environment variables.

Original artwork/code and the Fluent icon license are included with their notices. Windows reference exports, SSH credentials, account photos, screenshots of personal applications, and machine recovery manifests must never be committed.
