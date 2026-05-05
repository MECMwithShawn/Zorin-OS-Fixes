#!/usr/bin/env bash
set -euo pipefail

# Reinstall the persistent wake-source disabling service from this folder.
sudo install -m 0755 mini-disable-wakeup.sh /usr/local/sbin/mini-disable-wakeup.sh
sudo install -m 0644 mini-disable-wakeup.service /etc/systemd/system/mini-disable-wakeup.service
sudo systemctl daemon-reload
sudo systemctl enable mini-disable-wakeup.service
sudo systemctl start mini-disable-wakeup.service

# Optional checks.
systemctl status mini-disable-wakeup.service --no-pager
systemctl is-enabled mini-disable-wakeup.service

# Optional one-off cleanup and sleep.
echo 0 | sudo tee /sys/class/rtc/rtc0/wakealarm
loginctl lock-session
systemctl suspend
