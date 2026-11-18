# One switch for Windows 11 or Zorin's own desktop

Makes the **Windows 11 Desktop** checkbox in Startup Applications control the whole layout:

- **Unticked:** the Windows 11 extensions (`zorin11`, `zorin11-desktop`, `zorin11-motion`,
  `zorin11-lockscreen`, `zorin11-audio`) are disabled. Zorin's own extensions, including
  Jelly Mode (`zorin-window-move-effect`), keep running.
- **Ticked:** those extensions are enabled again, and the Windows 11 app starts at the next sign-in.

Either way, GNOME's global "disable all extensions" switch is cleared, because Jelly Mode is an extension too.
The change applies as soon as you click the box. Sign out and back in for a clean switch.

A systemd user path unit watches `~/.config/autostart/zorin11-desktop.desktop` and runs the script whenever it changes.
If the entry is removed, nothing is changed.

## Install

```bash
install -m 0755 zorin11-startup-sync ~/.local/bin/
install -m 0644 zorin11-startup-sync.path zorin11-startup-sync.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now zorin11-startup-sync.path
```

## Remove

```bash
systemctl --user disable --now zorin11-startup-sync.path
rm ~/.local/bin/zorin11-startup-sync ~/.config/systemd/user/zorin11-startup-sync.{path,service}
```
