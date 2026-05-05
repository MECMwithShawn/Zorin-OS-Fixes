# Zorin OS Fixes

A consolidated repository for Zorin OS fixes, including wake-source suspend fixes, display resolution notes, and other desktop repair work.

## Included Fixes

- `Zorin OS Stay Asleep` wake-source service and script for persistent suspend reliability.
- Link to the dedicated NVIDIA display-resolution fix for Secure Boot systems where the driver is installed but blocked until the local MOK key is enrolled.
- Reference links to existing repositories:
  - https://github.com/shawnmbrooks85/Zorin-OS-Stay-Asleep
  - https://github.com/shawnmbrooks85/Zorin-OS-NVIDIA-Display-Fix
  - https://github.com/shawnmbrooks85/zorin-imsm-raid0-busybox-fix

## Contents

- `mini-disable-wakeup.service` — systemd service unit for applying wake-source settings.
- `mini-disable-wakeup.sh` — shell script disabling known wake sources and clearing RTC wake alarms.
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
