#!/usr/bin/env bash
set -euo pipefail
# Disable common immediate-wake sources on this machine: onboard/ASMedia USB controllers and enabled PCI root ports.
for dev in XHC RP09 RP02 RP05 PXSX RP07 RP17 RP21 PEG0; do
  if grep -q "^${dev}[[:space:]]" /proc/acpi/wakeup 2>/dev/null && grep "^${dev}[[:space:]]" /proc/acpi/wakeup | grep -q '\*enabled'; then
    echo "$dev" > /proc/acpi/wakeup || true
  fi
done
for path in \
  /sys/bus/pci/devices/0000:00:14.0/power/wakeup \
  /sys/bus/pci/devices/0000:06:00.0/power/wakeup \
  /sys/bus/pci/devices/0000:07:00.0/power/wakeup \
  /sys/bus/pci/devices/0000:00:1d.0/power/wakeup \
  /sys/bus/pci/devices/0000:00:1c.1/power/wakeup \
  /sys/bus/pci/devices/0000:00:1c.4/power/wakeup \
  /sys/bus/pci/devices/0000:00:1c.6/power/wakeup \
  /sys/bus/pci/devices/0000:00:1b.0/power/wakeup \
  /sys/bus/pci/devices/0000:00:1b.4/power/wakeup; do
  if [ -w "$path" ]; then
    echo disabled > "$path" || true
  fi
done
# Clear RTC wake alarm if any userspace timer set one.
echo 0 > /sys/class/rtc/rtc0/wakealarm 2>/dev/null || true
