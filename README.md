# Zorin OS Fixes

A consolidated repository for Zorin OS fixes, including wake-source suspend fixes, display resolution notes, and other desktop repair work.

## Included Fixes

- `Zorin OS Stay Asleep` wake-source service and script for persistent suspend reliability.
- Keyboard double-typing (key chatter) fix using Bounce Keys, for mechanical/gaming keyboards.
- Slow qBittorrent downloads fix: open the listening port through UFW and the router, with a checker script.
- Link to the dedicated NVIDIA display-resolution fix for Secure Boot systems where the driver is installed but blocked until the local MOK key is enrolled.
- Reference links to existing repositories:
  - https://github.com/shawnmbrooks85/Zorin-OS-Stay-Asleep
  - https://github.com/shawnmbrooks85/Zorin-OS-NVIDIA-Display-Fix
  - https://github.com/shawnmbrooks85/zorin-imsm-raid0-busybox-fix

## Contents

- `mini-disable-wakeup.service` — systemd service unit for applying wake-source settings.
- `mini-disable-wakeup.sh` — shell script disabling known wake sources and clearing RTC wake alarms.
- `keyboard-bounce-keys.sh` — enables Bounce Keys to stop a keyboard from double-typing characters.
- `qbittorrent-port-check.sh` — checks whether qBittorrent's listening port is open from the internet and says what to fix.
- `commands.sh` — convenience command record for install/test operations.
- `README.md` — documentation for this consolidated fix repository.

## Purpose

This repository is intended to gather all Zorin OS desktop fixes in one place so they can be shared, documented, and versioned together.

## Suspend Wake-Source Fix

Install the persistent wake-source disabling service:

```bash
sudo install -m 0755 mini-disable-wakeup.sh /usr/local/sbin/mini-disable-wakeup.sh
sudo install -m 0644 mini-disable-wakeup.service /etc/systemd/system/mini-disable-wakeup.service
sudo systemctl daemon-reload
sudo systemctl enable mini-disable-wakeup.service
sudo systemctl start mini-disable-wakeup.service
```

## Display Resolution / MOK Boot Fix

The NVIDIA display-resolution repair now lives in its own repository:

https://github.com/shawnmbrooks85/Zorin-OS-NVIDIA-Display-Fix

Use that fix when Zorin OS is stuck at a fallback resolution such as `1024x768` on an NVIDIA system with Secure Boot enabled.

Observed failure pattern:

```text
nvidia-smi has failed because it couldn't communicate with the NVIDIA driver
modprobe: ERROR: could not insert 'nvidia': Key was rejected by service
SecureBoot enabled
```

The NVIDIA bootloader configuration should stay simple. Do not add `nomodeset`. A separate GRUB NVIDIA argument is usually not required because the dedicated fix enables NVIDIA DRM KMS through modprobe configuration:

```text
/etc/modprobe.d/zorin-nvidia-kms.conf
options nvidia_drm modeset=1
```

Apply it from the dedicated repository:

```bash
git clone https://github.com/shawnmbrooks85/Zorin-OS-NVIDIA-Display-Fix.git
cd Zorin-OS-NVIDIA-Display-Fix
sudo ./apply-boot-mok-display-fix.sh
sudo reboot
```

At the blue MOK screen after reboot:

```text
Enroll MOK
Continue
Yes
```

Enter the one-time password created by the script. After the next boot, verify:

```bash
nvidia-smi
xrandr --query
```

If `nvidia-smi` works, the NVIDIA module is loaded and normal monitor resolutions should return in Zorin Settings.

See the dedicated repository for the full script and troubleshooting notes.

## Keyboard Double-Typing (Key Chatter) Fix

Fixes a mechanical or gaming keyboard that sometimes types a character twice from one key press. Tested on a Corsair K70 CORE RGB on Zorin OS 18.1 (XFCE, X11).

This is key chatter: the switch registers two presses a few milliseconds apart. It is not key repeat (the default repeat delay is 500 ms), so changing repeat settings won't help.

The fix is **Bounce Keys**, which ignores a second press of the same key within a short window. A 40 ms window filters chatter while still allowing fast intentional double letters ("hello", "coffee"). Different keys pressed together are not affected, so gaming is fine.

Apply it as your normal user (no sudo):

```bash
./keyboard-bounce-keys.sh        # 40 ms (default)
./keyboard-bounce-keys.sh 60     # if doubles still get through
./keyboard-bounce-keys.sh 25     # if real double letters get dropped
./keyboard-bounce-keys.sh off    # undo
```

The script detects the desktop:

| Zorin edition | Desktop | Setting changed |
|---|---|---|
| Lite | XFCE | `xfconf-query -c accessibility -p /BounceKeys` and `/BounceKeys/Delay` |
| Core | GNOME | `org.gnome.desktop.a11y.keyboard bouncekeys-enable` and `bouncekeys-delay` |

On XFCE, the `gsettings` GNOME keys exist but do nothing, so set it through `xfconf-query` (or Settings > Accessibility > Keyboard > Bounce Keys). The setting persists across reboots.

Check the current setting (XFCE):

```bash
xfconf-query -c accessibility -lv | grep -i bounce
```

If the same one or two keys keep chattering even at 60 ms, the switch is likely worn or dirty. Try compressed air under the keycap; hot-swappable boards (like the K70 CORE) can have a single switch replaced.

## qBittorrent Slow Downloads (Closed Port) Fix

Fixes slow qBittorrent downloads on Zorin OS 18.1 (qBittorrent 5.2.4 Flatpak) behind a home router.

**Cause:** qBittorrent's settings were fine (defaults), but its listening port was closed from the internet. Zorin OS has UFW enabled, which drops incoming connections by default, and the router had no port forward. Peers could not connect in, so qBittorrent could only make outgoing connections, reaching far fewer peers.

Things that were ruled out: qBittorrent's settings (defaults are tuned for speed), a DNS ad blocker (Pi-hole had not blocked any tracker lookups) and Wi-Fi (6 GHz, decent signal).

### Find the port

qBittorrent: **Tools → Options → Connection → Port used for incoming connections**. Or from the config file:

| Install | Config file |
|---|---|
| Flatpak | `~/.var/app/org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf` |
| Native (apt) | `~/.config/qBittorrent/qBittorrent.conf` |

```bash
grep 'Session\\Port=' ~/.var/app/org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf
```

If both files exist, the Flatpak one is the one the Flatpak app uses. The examples below use port `4522`; substitute yours.

### Fix

1. **Open the port in UFW:**

   ```bash
   sudo ufw allow 4522 comment 'qBittorrent'
   ```

2. **Forward the port on the router** to this machine's LAN IP (give the machine a DHCP reservation so the IP doesn't change). On ASUS routers: **WAN → Virtual Server / Port Forwarding**:
   - Turn **Enable Port Forwarding** **ON** (master switch at the top; rules do nothing while it's off).
   - Add a rule: Service Name `qBittorrent`, Protocol **BOTH** (TCP and UDP; DHT and uTP use UDP), External Port `4522`, Internal Port `4522`, Internal IP = this machine's LAN IP, Source IP empty.
   - Click **OK**, then **Apply**.

3. **ISP gateway:** if the ISP gateway is in bridge or IP Passthrough mode to your router (AT&T gateways in this setup), nothing is needed there. If both devices do NAT (double NAT), forward the port on the ISP gateway to the router as well.

### Verify

```bash
./qbittorrent-port-check.sh          # reads the port from qBittorrent's config
./qbittorrent-port-check.sh 4522     # or check a specific port
```

It checks that qBittorrent is listening, counts UFW drops on that port, and asks canyouseeme.org whether the port is reachable from the internet (this sends your public IP and the port number to that site). Exit code is 0 when open. Example output after the fix:

```text
port:      4522
listening: yes (TCP)
firewall:  0 UFW drop(s) on port 4522 from the network in the last hour
internet:  Success: I can see your service on <public-ip> on port ( 4522 )
OK: peers can connect to you.
```

In qBittorrent, the connection icon in the status bar turns into a green globe within a few minutes, and downloads speed up as peers connect in.

Gotchas found while fixing this:
- **Testing from a Docker container is misleading.** Containers on this host couldn't reach the host's LAN IP at all (even a known-open web port timed out), so a container-based "port closed" result says nothing about the firewall. Test from the internet instead.
- **Check that the forward rule was actually saved.** Rules added in the ASUS dialog aren't active until you click OK, then Apply.
- The checker only tests TCP. With the router rule set to BOTH and the UFW rule covering both protocols, UDP is open too.

## Next Steps

1. Add the `zorin-imsm-raid0-busybox-fix` files if available.
2. Add machine-specific notes for other Zorin OS hardware repairs.

## Quick Install: Wake Fix Only

```bash
sudo install -m 0755 mini-disable-wakeup.sh /usr/local/sbin/mini-disable-wakeup.sh
sudo install -m 0644 mini-disable-wakeup.service /etc/systemd/system/mini-disable-wakeup.service
sudo systemctl daemon-reload
sudo systemctl enable mini-disable-wakeup.service
sudo systemctl start mini-disable-wakeup.service
```

## Notes

- The current contents are copied from the existing `Zorin OS Stay Asleep` fix.
- The NVIDIA display fix is maintained separately at https://github.com/shawnmbrooks85/Zorin-OS-NVIDIA-Display-Fix.
- This repo is a starting point for a broader Zorin OS fix collection.
