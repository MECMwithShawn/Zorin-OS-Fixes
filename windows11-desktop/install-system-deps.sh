#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install --no-install-recommends python3-gi python3-dbus \
  gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-atspi-2.0 gir1.2-wnck-3.0 python3-pil libxcomposite1 x11-utils git \
  network-manager-gnome pavucontrol pulseaudio-utils desktop-file-utils xfce4-genmon-plugin \
  libgtk-3-bin fontconfig exo-utils libicu74 libssl3t64 libunwind8 \
  libgl1 libegl1 libxkbcommon0 libxcb-xkb1 libxcb-cursor0
