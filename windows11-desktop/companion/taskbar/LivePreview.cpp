// SPDX-License-Identifier: GPL-3.0-or-later
// Zorin11: isolated XComposite capture; never retain a foreign window pointer.
#include "LivePreview.hpp"
#include <libxfce4windowing/xfw-x11.h>
#include <string>
#include <algorithm>

namespace {
unsigned active = 0;
struct Request {
    GWeakRef image;
    GSubprocess* child;
    guint timeout;
    int width, height;
    gulong destroy;
    bool destroyed = false;
};

void completed(GObject* object, GAsyncResult* result, gpointer data)
{
    auto* request = static_cast<Request*>(data);
    GBytes* bytes = nullptr;
    GError* error = nullptr;
    bool ok = g_subprocess_communicate_finish(G_SUBPROCESS(object), result, &bytes, nullptr, &error);
    if (request->timeout) g_source_remove(request->timeout);
    auto* image = static_cast<GtkImage*>(g_weak_ref_get(&request->image));
    if (image && !request->destroyed) {
        g_signal_handler_disconnect(image, request->destroy);
        g_object_set_data(G_OBJECT(image), "z11-pending", nullptr);
        if (ok && g_subprocess_get_successful(request->child) && bytes &&
            g_bytes_get_size(bytes) > 0 && g_bytes_get_size(bytes) <= 1024*1024) {
            GInputStream* stream = g_memory_input_stream_new_from_bytes(bytes);
            int scale = gtk_widget_get_scale_factor(GTK_WIDGET(image));
            GdkPixbuf* pix = gdk_pixbuf_new_from_stream_at_scale(stream, request->width*scale, request->height*scale, true, nullptr, nullptr);
            if (pix) {
                auto* surface = gdk_cairo_surface_create_from_pixbuf(pix, scale, nullptr);
                gtk_image_set_from_surface(image, surface);
                g_object_set_data(G_OBJECT(image), "z11-cached", GINT_TO_POINTER(1));
                gtk_widget_set_tooltip_text(GTK_WIDGET(image), nullptr);
                cairo_surface_destroy(surface);
                g_object_unref(pix);
            }
            g_object_unref(stream);
        }
    }
    if (image) g_object_unref(image);
    if (bytes) g_bytes_unref(bytes);
    g_clear_error(&error);
    g_weak_ref_clear(&request->image);
    g_object_unref(request->child);
    --active;
    delete request;
}
}

void LivePreview::update(GtkImage* image, XfwWindow* window, int width, int height)
{
    auto* widget = GTK_WIDGET(image);
    if (!g_object_get_data(G_OBJECT(image), "z11-cached")) {
        auto* icon = xfw_window_get_icon(window, std::min({64, width, height}), gtk_widget_get_scale_factor(widget));
        if (icon) {
            auto* surface = gdk_cairo_surface_create_from_pixbuf(icon, gtk_widget_get_scale_factor(widget), nullptr);
            gtk_image_set_from_surface(image, surface);
            cairo_surface_destroy(surface);
        }
        else gtk_image_set_from_icon_name(image, "application-x-executable", GTK_ICON_SIZE_DIALOG);
        gtk_widget_set_tooltip_text(widget, "Preview unavailable — click to open this window");
    }
    if (xfw_window_is_minimized(window)) {
        gtk_widget_set_tooltip_text(widget, "Minimized — last available preview; click to restore");
        return;
    }
    // Only the visible flyout is sampled. Two helpers maximum across all apps,
    // with one in-flight request per card and a hard timeout for each helper.
    if (!gtk_widget_get_mapped(widget) || active >= 2 || g_object_get_data(G_OBJECT(image), "z11-pending")) return;
    gchar* helper = g_build_filename(g_get_user_data_dir(), "zorin11-hub", "window_preview.py", nullptr);
    std::string xid = std::to_string(xfw_window_x11_get_xid(window));
    GSubprocess* child = g_subprocess_new(static_cast<GSubprocessFlags>(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE),
                                         nullptr, "/usr/bin/python3", helper, xid.c_str(), nullptr);
    g_free(helper);
    if (!child) return;
    auto* request = new Request;
    request->child = child;
    request->width = width; request->height = height;
    g_weak_ref_init(&request->image, image);
    g_object_set_data(G_OBJECT(image), "z11-pending", GINT_TO_POINTER(1));
    request->destroy = g_signal_connect(widget, "destroy", G_CALLBACK(+[](GtkWidget*, gpointer data) {
        auto* r = static_cast<Request*>(data);
        r->destroyed = true;
        g_subprocess_force_exit(r->child);
    }), request);
    request->timeout = g_timeout_add(2000, +[](gpointer data) -> gboolean {
        auto* r = static_cast<Request*>(data);
        r->timeout = 0;
        g_subprocess_force_exit(r->child);
        return G_SOURCE_REMOVE;
    }, request);
    ++active;
    g_subprocess_communicate_async(child, nullptr, nullptr, completed, request);
}
