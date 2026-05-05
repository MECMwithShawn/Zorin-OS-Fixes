# Zorin OS Display Resolution Fix: NVIDIA Secure Boot / MOK

This fix is for Zorin OS systems where display resolution is stuck at a low fallback mode such as `1024x768` because the NVIDIA kernel module is installed but blocked by Secure Boot.

Typical symptoms:

- Settings only shows fallback resolutions.
- `xrandr --query` shows an output such as `None-1` with only low modes.
- `nvidia-smi` says it cannot communicate with the NVIDIA driver.
- `sudo modprobe nvidia` fails with `Key was rejected by service`.
- `mokutil --sb-state` reports `SecureBoot enabled`.

## What This Fix Changes

The bootloader does not usually need an NVIDIA-specific kernel option. The required NVIDIA DRM modesetting option is applied through modprobe configuration:

```text
/etc/modprobe.d/zorin-nvidia-kms.conf
options nvidia_drm modeset=1
```

The script then rebuilds initramfs and refreshes GRUB:

```bash
sudo update-initramfs -u -k all
sudo update-grub
```

The important Secure Boot step is enrolling the local MOK certificate used to sign the NVIDIA kernel module:

```bash
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der
```

After reboot, the blue MOK manager screen must be completed manually:

```text
Enroll MOK
Continue
Yes
```

Then enter the one-time password created during `mokutil --import`.

## Apply

From the repository root:

```bash
sudo ./boot-mok-display-fix/apply-boot-mok-display-fix.sh
sudo reboot
```

After rebooting and enrolling the key, verify:

```bash
nvidia-smi
xrandr --query
```

If `nvidia-smi` works, the NVIDIA driver is loaded and normal display resolutions should be available in Zorin Settings.

## Notes

- Do not add `nomodeset`; it disables kernel modesetting and can keep the system in fallback graphics.
- Adding `nvidia-drm.modeset=1` to `GRUB_CMDLINE_LINUX_DEFAULT` is usually redundant when `options nvidia_drm modeset=1` exists in `/etc/modprobe.d`.
- If the blue MOK enrollment screen does not appear, run `sudo mokutil --list-new` before rebooting to confirm that a key is pending enrollment.
- If no MOK key exists at `/var/lib/shim-signed/mok/MOK.der`, reinstalling the NVIDIA driver from Zorin/Ubuntu's driver manager usually regenerates the local signing key.
