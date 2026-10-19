// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <gtk/gtk.h>
#include <libxfce4windowing/libxfce4windowing.h>

namespace LivePreview {
void update(GtkImage* image, XfwWindow* window, int width = 256, int height = 144);
}
