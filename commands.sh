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

# Optional display-resolution repair for NVIDIA systems with Secure Boot enabled:
# https://github.com/shawnmbrooks85/Zorin-OS-NVIDIA-Display-Fix

# Keyboard double-typing (key chatter) fix: enable Bounce Keys at 40 ms (no sudo).
./keyboard-bounce-keys.sh 40

# qBittorrent slow downloads: open the listening port (4522 here) and verify from the internet.
sudo ufw allow 4522 comment 'qBittorrent'
./qbittorrent-port-check.sh
