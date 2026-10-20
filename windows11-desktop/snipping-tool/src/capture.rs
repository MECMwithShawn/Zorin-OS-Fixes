use gdk::prelude::*;
use gdk_pixbuf::Pixbuf;
use glib::variant::ToVariant;
use std::collections::HashMap;
use x11rb::{
    connection::Connection,
    protocol::xproto::{AtomEnum, ConnectionExt, MapState},
};

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Mode {
    Rectangle,
    Freeform,
    Window,
    Fullscreen,
}
#[derive(Clone, Copy, Debug)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}
impl Rect {
    pub fn contains(&self, x: f64, y: f64) -> bool {
        x >= self.x as f64
            && y >= self.y as f64
            && x < (self.x + self.w) as f64
            && y < (self.y + self.h) as f64
    }
}
pub fn desktop() -> Result<Pixbuf, String> {
    let root = gdk::Window::default_root_window();
    let (_, _, w, h) = root.geometry();
    if w as i64 * h as i64 > 40_000_000 {
        return Err("Desktop exceeds the 40 megapixel capture limit.".into());
    }
    root.pixbuf(0, 0, w, h)
        .ok_or("The desktop could not be captured.".into())
}
pub fn windows() -> Vec<Rect> {
    windows_inner().unwrap_or_default()
}
fn windows_inner() -> Result<Vec<Rect>, Box<dyn std::error::Error>> {
    let (c, screen) = x11rb::connect(None)?;
    let root = c.setup().roots[screen].root;
    let atom = |name: &[u8]| -> Result<u32, Box<dyn std::error::Error>> {
        Ok(c.intern_atom(false, name)?.reply()?.atom)
    };
    let stack = atom(b"_NET_CLIENT_LIST_STACKING")?;
    let ext = atom(b"_NET_FRAME_EXTENTS")?;
    let kind = atom(b"_NET_WM_WINDOW_TYPE")?;
    let desktop = atom(b"_NET_WM_WINDOW_TYPE_DESKTOP")?;
    let dock = atom(b"_NET_WM_WINDOW_TYPE_DOCK")?;
    let ids = c
        .get_property(false, root, stack, AtomEnum::WINDOW, 0, 4096)?
        .reply()?;
    let ids = ids
        .value32()
        .map(|v| v.collect::<Vec<_>>())
        .unwrap_or_default();
    let ids = if ids.is_empty() {
        c.query_tree(root)?.reply()?.children
    } else {
        ids
    };
    let mut result = vec![];
    for id in ids.into_iter().rev() {
        let Ok(attrs) = c.get_window_attributes(id)?.reply() else {
            continue;
        };
        if attrs.map_state != MapState::VIEWABLE {
            continue;
        }
        let Ok(geom) = c.get_geometry(id)?.reply() else {
            continue;
        };
        let Ok(pos) = c.translate_coordinates(id, root, 0, 0)?.reply() else {
            continue;
        };
        let types = c
            .get_property(false, id, kind, AtomEnum::ATOM, 0, 16)?
            .reply()?;
        if types
            .value32()
            .is_some_and(|mut v| v.any(|t| t == desktop || t == dock))
        {
            continue;
        }
        let e = c
            .get_property(false, id, ext, AtomEnum::CARDINAL, 0, 4)?
            .reply()?;
        let e = e
            .value32()
            .map(|v| v.collect::<Vec<_>>())
            .unwrap_or_default();
        let e = if e.len() == 4 { e } else { vec![0; 4] };
        result.push(Rect {
            x: pos.dst_x as i32 - e[0] as i32,
            y: pos.dst_y as i32 - e[2] as i32,
            w: geom.width as i32 + (e[0] + e[1]) as i32,
            h: geom.height as i32 + (e[2] + e[3]) as i32,
        });
    }
    Ok(result)
}
// Wayland capture is mediated by the desktop portal, including user consent.
pub fn portal(done: impl FnOnce(Result<Pixbuf, String>) + 'static) -> Result<(), String> {
    let bus = gio::bus_get_sync(gio::BusType::Session, gio::Cancellable::NONE)
        .map_err(|e| e.to_string())?;
    let token = format!("snip{}_{}", std::process::id(), glib::monotonic_time());
    let sender = bus
        .unique_name()
        .ok_or("No session bus identity")?
        .trim_start_matches(':')
        .replace('.', "_");
    let request = format!("/org/freedesktop/portal/desktop/request/{sender}/{token}");
    let cb = std::rc::Rc::new(std::cell::RefCell::new(Some(done)));
    let cb2 = cb.clone();
    let watch = std::rc::Rc::new(std::cell::RefCell::new(None));
    let watch2 = watch.clone();
    let id = bus.signal_subscribe(
        Some("org.freedesktop.portal.Desktop"),
        Some("org.freedesktop.portal.Request"),
        Some("Response"),
        Some(&request),
        None,
        gio::DBusSignalFlags::NONE,
        move |b, _, _, _, _, p| {
            if let Some(id) = watch2.borrow_mut().take() {
                b.signal_unsubscribe(id)
            }
            if let Some(cb) = cb2.borrow_mut().take() {
                cb((|| {
                    let (code, results) = p
                        .get::<(u32, HashMap<String, glib::Variant>)>()
                        .ok_or("Invalid screenshot response")?;
                    if code != 0 {
                        return Err("Capture cancelled.".into());
                    }
                    let uri = results
                        .get("uri")
                        .and_then(|v| v.get::<String>())
                        .ok_or("No screenshot returned")?;
                    let (file, _) = glib::filename_from_uri(&uri).map_err(|e| e.to_string())?;
                    crate::load_image(&file)
                })());
            }
        },
    );
    *watch.borrow_mut() = Some(id);
    let opts = HashMap::from([
        ("handle_token", token.to_variant()),
        ("interactive", true.to_variant()),
    ]);
    let result = bus.call_sync(
        Some("org.freedesktop.portal.Desktop"),
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot",
        "Screenshot",
        Some(&("", opts).to_variant()),
        None,
        gio::DBusCallFlags::NONE,
        5000,
        gio::Cancellable::NONE,
    );
    if let Err(e) = result {
        if let Some(id) = watch.borrow_mut().take() {
            bus.signal_unsubscribe(id)
        }
        return Err(e.to_string());
    }
    // A vanished portal must not leave the editor hidden indefinitely.
    glib::timeout_add_local_once(std::time::Duration::from_secs(120), move || {
        if let Some(id) = watch.borrow_mut().take() {
            bus.signal_unsubscribe(id);
            let _ = bus.call_sync(
                Some("org.freedesktop.portal.Desktop"),
                &request,
                "org.freedesktop.portal.Request",
                "Close",
                None,
                None,
                gio::DBusCallFlags::NONE,
                2000,
                gio::Cancellable::NONE,
            );
        }
        if let Some(cb) = cb.borrow_mut().take() {
            cb(Err("Screen capture timed out.".into()))
        }
    });
    Ok(())
}
