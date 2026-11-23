# Pick Windows 11 or Zorin at the login screen

Adds **Windows 11 Desktop** (and **Windows 11 Desktop on Xorg**) to the session list under the gear on the login screen, next to Zorin's own sessions:

| Session you pick | You get |
|---|---|
| Windows 11 Desktop / on Xorg | The Windows 11 layout: zorin11 extensions on, companion (Start, Explorer, Settings, flyouts) starts, Windows 11 icons |
| Zorin Desktop / on Wayland / on Xorg | Zorin's own desktop: zorin11 extensions off, companion doesn't start, Zorin icons. Jelly Mode and Zorin's extensions keep running |
| Anything else | No change |

The login screen remembers your last choice, so you only pick when you want to switch.

## How it works

`zorin11-session-select` runs just before GNOME Shell starts, through a user drop-in for `org.gnome.Shell@.service` (`ExecStartPre`). It reads `DESKTOP_SESSION` (the session file picked at login) and sets things up before Shell loads, so there's no half-switched desktop. The Windows 11 sessions start the same `gnome-session --session=zorin` as Zorin's own; only the name differs.

Each desktop keeps its own:

- **Enabled zorin11 extensions.** Whatever was enabled when you last left Windows 11 is restored (by default `zorin11`, `-desktop`, `-motion`, `-lockscreen`, `-audio`; `-glass` stays off unless you turned it on).
- **Icon theme.** Change icons in either desktop and the other keeps its own. The first time you enter Zorin it uses the Zorin icon theme matching your GTK theme (e.g. `ZorinBlue-Dark`).

The companion follows `X-GNOME-Autostart-enabled` in `~/.config/autostart/zorin11-desktop.desktop`. Other extensions and settings aren't touched. State is in `~/.config/zorin11-hub/session-choice.json`. Errors are logged and never block Shell from starting:

```bash
journalctl --user -b -u 'org.gnome.Shell@*' | grep zorin11-session-select
```

This replaces the [startup-toggle](../startup-toggle/) checkbox as the main way to switch. Both can stay installed: the checkbox follows the same autostart entry.

## Install

Run as your desktop user. It asks for sudo once, for the two session files:

```bash
bash install.sh
```

Then sign out, click the gear on the login screen, and pick a session. **The first login after installing follows whatever is selected there.** If that's still "Zorin Desktop", you get Zorin's own desktop; pick "Windows 11 Desktop" to keep the Windows 11 layout.

## Remove

```bash
bash install.sh remove
```

The desktop stays in whichever mode you last signed into. To go fully back to Zorin, sign into Zorin Desktop before removing, or use [Restore](../README.md#restore).

## Test

Sandboxed (keyfile settings backend and a temporary home, no changes to your real desktop): each run of the selector with `DESKTOP_SESSION=zorin-wayland`, `zorin-windows11`, `zorin-xorg` and `ubuntu` was checked for extensions, icon theme and autostart. Other extensions were untouched, and `ubuntu` changed nothing.
