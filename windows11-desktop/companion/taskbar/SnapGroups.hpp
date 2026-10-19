// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <gtk/gtk.h>
#include <string>
#include <vector>
class GroupMenu;

class SnapGroups {
public:
    explicit SnapGroups(GroupMenu* menu);
    ~SnapGroups();
    void show();
    void hide();
private:
    struct Tile { guint64 xid; GtkImage* image; int width, height; };
    GroupMenu* menu;
    GtkWidget* box;
    GDBusProxy* proxy = nullptr;
    guint timer = 0;
    unsigned revision = 0;
    bool visible = false, pending = false;
    std::string signature;
    std::vector<Tile> tiles;
    void refresh();
    void render(GVariant* value);
    void update();
};
