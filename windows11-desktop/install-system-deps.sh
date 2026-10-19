#!/usr/bin/env bash
set -euo pipefail
desktop_session=${XDG_CURRENT_DESKTOP:-}
if [[ "${desktop_session^^}" == *GNOME* ]]; then
  sudo apt-get update
  sudo apt-get install --no-install-recommends python3-gi python3-gi-cairo python3-dbus python3-pil \
    gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-atspi-2.0 gir1.2-wnck-3.0 \
    git xwayland pulseaudio-utils desktop-file-utils libgtk-3-bin fontconfig \
    libicu74 libssl3t64 libunwind8 libgl1 libegl1 libxkbcommon0 libxcb-xkb1 libxcb-cursor0
  exit 0
fi
sudo apt-get update
sudo apt-get install --no-install-recommends python3-gi python3-dbus \
  gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-atspi-2.0 gir1.2-wnck-3.0 python3-pil libxcomposite1 x11-utils git \
  network-manager-gnome pavucontrol pulseaudio-utils desktop-file-utils xfce4-genmon-plugin \
  libgtk-3-bin fontconfig exo-utils libicu74 libssl3t64 libunwind8 \
  libgl1 libegl1 libxkbcommon0 libxcb-xkb1 libxcb-cursor0 \
  xfce4-docklike-plugin build-essential meson ninja-build gettext pkg-config patch \
  libgtk-3-dev libxfce4panel-2.0-dev libxfce4ui-2-dev libxfce4util-dev \
  libxfce4windowing-0-dev libxi-dev
