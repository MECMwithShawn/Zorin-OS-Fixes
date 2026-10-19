// SPDX-License-Identifier: GPL-3.0-or-later
// Group membership belongs to the companion's current session. The panel only
// reads typed records and sends opaque tokens; it never invents placements.
#include "SnapGroups.hpp"
#include "GroupMenu.hpp"
#include "Group.hpp"
#include "Xfw.hpp"
#include "LivePreview.hpp"
#include <libxfce4windowing/xfw-x11.h>
#include <algorithm>
#include <set>
#include <cmath>

namespace {
constexpr auto bus = "local.zorin11.SnapGroups";
constexpr auto path = "/local/zorin11/SnapGroups";
struct Request {
    GWeakRef widget;
    unsigned revision;
    explicit Request(GtkWidget* box, unsigned serial = 0): revision(serial) { g_weak_ref_init(&widget, box); }
    ~Request() { g_weak_ref_clear(&widget); }
};
// Look up synchronously; never keep a client pointer across asynchronous work.
XfwWindow* window(guint64 xid) {
    for (auto* node = xfw_screen_get_windows(Xfw::mXfwScreen); node; node = node->next) {
        auto* w = XFW_WINDOW(node->data);
        if (xfw_window_x11_get_xid(w) == xid) return w;
    }
    return nullptr;
}
struct Member { guint64 xid; int x, y, width, height; };
struct Record { std::string token; std::vector<Member> members; guint64 preferred = 0; };
}

SnapGroups::SnapGroups(GroupMenu* parent): menu(parent)
{
    box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
    gtk_box_pack_end(GTK_BOX(menu->mBox), box, false, false, 0);
    g_object_set_data(G_OBJECT(box), "z11-snap-owner", this);
    g_dbus_proxy_new_for_bus(G_BUS_TYPE_SESSION,
        static_cast<GDBusProxyFlags>(G_DBUS_PROXY_FLAGS_DO_NOT_AUTO_START | G_DBUS_PROXY_FLAGS_DO_NOT_LOAD_PROPERTIES),
        nullptr, bus, path, bus, nullptr,
        +[](GObject*, GAsyncResult* result, gpointer data) {
            auto* request = static_cast<Request*>(data);
            GError* error = nullptr;
            auto* ready = g_dbus_proxy_new_for_bus_finish(result, &error);
            auto* widget = static_cast<GObject*>(g_weak_ref_get(&request->widget));
            auto* self = widget ? static_cast<SnapGroups*>(g_object_get_data(widget, "z11-snap-owner")) : nullptr;
            if (self && ready) {
                self->proxy = ready;
                g_signal_connect(ready, "g-signal", G_CALLBACK(+[](GDBusProxy*, gchar*, gchar*, GVariant*, gpointer owner) {
                    static_cast<SnapGroups*>(owner)->refresh();
                }), self);
                g_signal_connect(ready, "notify::g-name-owner", G_CALLBACK(+[](GObject*, GParamSpec*, gpointer owner) {
                    static_cast<SnapGroups*>(owner)->refresh();
                }), self);
                self->refresh();
            } else if (ready) g_object_unref(ready);
            if (widget) g_object_unref(widget);
            g_clear_error(&error);
            delete request;
        }, new Request(box));
}

SnapGroups::~SnapGroups()
{
    hide();
    g_object_set_data(G_OBJECT(box), "z11-snap-owner", nullptr);
    if (proxy) { g_signal_handlers_disconnect_by_data(proxy, this); g_object_unref(proxy); }
    gtk_widget_destroy(box);
}

void SnapGroups::show()
{
    if (!Settings::showPreviews) { hide(); gtk_widget_hide(box); return; }
    gtk_box_reorder_child(GTK_BOX(menu->mBox), box, -1);
    if (visible) return;
    visible = true;
    // Hidden flyouts must not briefly display records from a former session.
    gtk_widget_hide(box);
    refresh();
    timer = g_timeout_add(270 + g_random_int_range(0, 60), +[](gpointer data) -> gboolean {
        auto* self = static_cast<SnapGroups*>(data);
        self->update();
        // Also catch desktop moves without polling while flyouts are hidden.
        self->refresh();
        return G_SOURCE_CONTINUE;
    }, this);
}

void SnapGroups::hide()
{
    visible = false; ++revision; pending = false;
    if (timer) { g_source_remove(timer); timer = 0; }
}

void SnapGroups::refresh()
{
    if (!visible || !proxy || pending) return;
    pending = true;
    g_dbus_proxy_call(proxy, "List", nullptr, G_DBUS_CALL_FLAGS_NO_AUTO_START, 1000, nullptr,
        +[](GObject* object, GAsyncResult* result, gpointer data) {
            auto* request = static_cast<Request*>(data);
            GError* error = nullptr;
            auto* value = g_dbus_proxy_call_finish(G_DBUS_PROXY(object), result, &error);
            auto* widget = static_cast<GObject*>(g_weak_ref_get(&request->widget));
            auto* self = widget ? static_cast<SnapGroups*>(g_object_get_data(widget, "z11-snap-owner")) : nullptr;
            if (self && request->revision == self->revision) {
                self->pending = false;
                if (self->visible) self->render(value);
            }
            if (widget) g_object_unref(widget);
            if (value) g_variant_unref(value);
            g_clear_error(&error); delete request;
        }, new Request(box, revision));
}

void SnapGroups::render(GVariant* value)
{
    std::set<guint64> app;
    menu->mGroup->mWindows.forEach([&](GroupWindow* w) { app.insert(xfw_window_x11_get_xid(w->mXfwWindow)); });
    std::vector<Record> records;
    std::string next;
    if (value && g_variant_is_of_type(value, G_VARIANT_TYPE("(a(sa(tiiii)))"))) {
        auto* array = g_variant_get_child_value(value, 0);
        for (gsize i = 0; i < std::min(g_variant_n_children(array), gsize(8)); ++i) {
            auto* row = g_variant_get_child_value(array, i);
            const gchar* token; GVariant* members;
            g_variant_get(row, "(&s@a(tiiii))", &token, &members);
            Record record; record.token = token;
            GVariantIter iter; g_variant_iter_init(&iter, members); Member member;
            while (g_variant_iter_next(&iter, "(tiiii)", &member.xid, &member.x, &member.y, &member.width, &member.height)) {
                if (member.width > 0 && member.height > 0 && member.width <= 32768 && member.height <= 32768 &&
                    std::abs(double(member.x)) < 100000 && std::abs(double(member.y)) < 100000 && window(member.xid)) {
                    record.members.push_back(member);
                    if (!record.preferred && app.count(member.xid)) record.preferred = member.xid;
                }
            }
            if (record.preferred && record.members.size() >= 2 && record.members.size() <= 6) {
                next += record.token;
                for (auto& m: record.members) {
                    next += ":"+std::to_string(m.xid)+","+std::to_string(m.x)+","+std::to_string(m.y)+","+std::to_string(m.width)+","+std::to_string(m.height);
                    next += xfw_window_get_name(window(m.xid));
                }
                records.push_back(record);
            }
            g_variant_unref(members); g_variant_unref(row);
        }
        g_variant_unref(array);
    }
    bool wasVisible = gtk_widget_get_visible(box);
    if (next == signature) {
        gtk_widget_set_visible(box, !records.empty());
        if (wasVisible != !records.empty()) menu->mPopupIdle.start();
        return;
    }
    signature = next; tiles.clear();
    auto* children = gtk_container_get_children(GTK_CONTAINER(box));
    for (auto* node = children; node; node = node->next) gtk_widget_destroy(GTK_WIDGET(node->data));
    g_list_free(children);
    for (const auto& record: records) {
        auto* card = gtk_button_new();
        gtk_style_context_add_class(gtk_widget_get_style_context(card), "z11-snap-group");
        auto* content = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
        gtk_container_add(GTK_CONTAINER(card), content);
        auto title = "Snap group · "+std::to_string(record.members.size())+" windows";
        auto* label = gtk_label_new(title.c_str());
        gtk_label_set_xalign(GTK_LABEL(label), 0);
        gtk_widget_set_size_request(label, -1, 30);
        gtk_box_pack_start(GTK_BOX(content), label, false, false, 0);
        auto* mosaic = gtk_fixed_new(); gtk_widget_set_size_request(mosaic, 256, 144);
        gtk_style_context_add_class(gtk_widget_get_style_context(mosaic), "z11-snap-mosaic");
        gtk_box_pack_start(GTK_BOX(content), mosaic, false, false, 0);
        int left=100000, top=100000, right=-100000, bottom=-100000;
        for (auto& m: record.members) { left=std::min(left,m.x);top=std::min(top,m.y);right=std::max(right,m.x+m.width);bottom=std::max(bottom,m.y+m.height); }
        double scale = std::min(252.0/(right-left), 140.0/(bottom-top));
        int ox=(256-std::lround((right-left)*scale))/2, oy=(144-std::lround((bottom-top)*scale))/2;
        std::string description = title+". Restore together: ";
        for (auto& m: record.members) {
            int width=std::max(1,int(m.width*scale)-2), height=std::max(1,int(m.height*scale)-2);
            auto* image = gtk_image_new(); gtk_widget_set_size_request(image,width,height);
            gtk_style_context_add_class(gtk_widget_get_style_context(image), "z11-snap-tile");
            gtk_fixed_put(GTK_FIXED(mosaic),image,ox+std::lround((m.x-left)*scale),oy+std::lround((m.y-top)*scale));
            tiles.push_back({m.xid,GTK_IMAGE(image),width,height});
            description += std::string(xfw_window_get_name(window(m.xid)))+"; ";
        }
        atk_object_set_name(gtk_widget_get_accessible(card),description.c_str());
        gtk_widget_set_tooltip_text(card,description.c_str());
        g_object_set_data_full(G_OBJECT(card),"z11-snap-record",new Record(record),+[](gpointer p){delete static_cast<Record*>(p);});
        g_signal_connect(card,"clicked",G_CALLBACK(+[](GtkButton* button,gpointer data){
            auto* self=static_cast<SnapGroups*>(data);
            auto* selected=static_cast<Record*>(g_object_get_data(G_OBJECT(button),"z11-snap-record"));
            if (self->proxy) g_dbus_proxy_call(self->proxy,"Activate",g_variant_new("(st)",selected->token.c_str(),selected->preferred),
                G_DBUS_CALL_FLAGS_NO_AUTO_START,1500,nullptr,nullptr,nullptr);
            self->menu->hide();
        }),this);
        gtk_box_pack_end(GTK_BOX(box),card,false,false,0);
    }
    gtk_widget_show_all(box);gtk_widget_set_visible(box,!records.empty());
    menu->mPopupIdle.start();
    update();
}

void SnapGroups::update()
{
    if (!visible || tiles.empty()) return;
    // Rotate which member gets the first free capture slot.
    std::rotate(tiles.begin(),tiles.begin()+1,tiles.end());
    for (auto& tile: tiles) {
        auto* w=window(tile.xid);
        if (w) LivePreview::update(tile.image,w,tile.width,tile.height);
    }
}
