#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

echo "== Zorin OS NVIDIA Secure Boot / MOK display fix =="

if ! command -v mokutil >/dev/null 2>&1; then
  echo "mokutil is required. Install it with: sudo apt install mokutil" >&2
  exit 1
fi

if ! command -v update-initramfs >/dev/null 2>&1; then
  echo "update-initramfs is required; this script expects an Ubuntu/Zorin system." >&2
  exit 1
fi

echo
echo "Current kernel command line:"
cat /proc/cmdline

if grep -qw "nomodeset" /proc/cmdline; then
  echo
  echo "WARNING: nomodeset is present. Remove it from /etc/default/grub before relying on NVIDIA modesetting." >&2
fi

echo
echo "Secure Boot state:"
mokutil --sb-state || true

echo
echo "NVIDIA hardware:"
lspci | grep -Ei "vga|3d|display|nvidia" || true

echo
echo "NVIDIA driver package state:"
dpkg -l | grep -E "nvidia-driver|nvidia-dkms|linux-modules-nvidia|xserver-xorg-video-nvidia" || true

echo
echo "Ensuring NVIDIA DRM kernel modesetting is enabled."
install -d -m 0755 /etc/modprobe.d
cat >/etc/modprobe.d/zorin-nvidia-kms.conf <<'EOF'
# Zorin OS display-resolution fix for NVIDIA + Secure Boot systems.
# Keep DRM KMS enabled so GNOME/Wayland can expose real monitor modes.
options nvidia_drm modeset=1
EOF

echo
echo "Refreshing initramfs so module options and NVIDIA modules are available during boot."
update-initramfs -u -k all

if command -v update-grub >/dev/null 2>&1; then
  echo
  echo "Refreshing GRUB. No NVIDIA GRUB parameter is normally required when nvidia_drm modeset=1 is set in modprobe.d."
  update-grub
fi

echo
if [ -r /var/lib/shim-signed/mok/MOK.der ]; then
  if mokutil --test-key /var/lib/shim-signed/mok/MOK.der >/dev/null 2>&1; then
    echo "The local NVIDIA module signing key is already enrolled."
  else
    echo "The local NVIDIA module signing key is not enrolled."
    echo "Staging MOK enrollment for: /var/lib/shim-signed/mok/MOK.der"
    echo "You will be prompted for a one-time password. Use that same password at the blue MOK screen after reboot."
    mokutil --import /var/lib/shim-signed/mok/MOK.der
  fi
else
  echo "No /var/lib/shim-signed/mok/MOK.der file was found."
  echo "If NVIDIA still fails with 'Key was rejected by service', reinstall the driver or create/enroll a MOK key."
fi

echo
echo "Done."
echo "Next step: reboot. At the blue MOK screen choose Enroll MOK -> Continue -> Yes, then enter the one-time password."
echo "After boot, verify with: nvidia-smi && xrandr --query"
