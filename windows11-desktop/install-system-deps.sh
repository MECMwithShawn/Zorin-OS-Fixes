#!/usr/bin/env bash
set -euo pipefail
desktop_session=${XDG_CURRENT_DESKTOP:-}
if [[ "${desktop_session^^}" == *GNOME* ]]; then
  sudo apt-get update
  sudo apt-get install --no-install-recommends python3-gi python3-gi-cairo python3-dbus python3-pil python3-venv heif-gdk-pixbuf \
    gjs gir1.2-gtk-4.0 gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-atspi-2.0 gir1.2-wnck-3.0 gir1.2-gdm-1.0 \
    git flatpak xwayland pulseaudio-utils desktop-file-utils libgtk-3-bin fontconfig \
    cargo rustc build-essential pkg-config libgtk-3-dev tesseract-ocr tesseract-ocr-eng ffmpeg \
    gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-plugins-good gstreamer1.0-plugins-bad fonts-noto-color-emoji \
    libicu74 libssl3t64 libunwind8 libgl1 libegl1 libxkbcommon0 libxcb-xkb1 libxcb-cursor0
  flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
  flatpak install --noninteractive -y flathub io.missioncenter.MissionCenter
  exit 0
fi
sudo apt-get update
sudo apt-get install --no-install-recommends python3-gi python3-dbus \
  gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-atspi-2.0 gir1.2-wnck-3.0 python3-pil heif-gdk-pixbuf libxcomposite1 x11-utils git \
  network-manager-gnome pavucontrol pulseaudio-utils desktop-file-utils xfce4-genmon-plugin \
  libgtk-3-bin fontconfig exo-utils libicu74 libssl3t64 libunwind8 \
  libgl1 libegl1 libxkbcommon0 libxcb-xkb1 libxcb-cursor0 \
  xfce4-docklike-plugin build-essential meson ninja-build gettext pkg-config patch \
  libgtk-3-dev libxfce4panel-2.0-dev libxfce4ui-2-dev libxfce4util-dev \
  libxfce4windowing-0-dev libxi-dev
