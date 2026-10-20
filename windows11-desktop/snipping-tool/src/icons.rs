//! Original, consistently sized line icons; independent of the desktop icon theme.
use gtk::prelude::*;

pub fn image(name: &str) -> gtk::Image {
    let paths = match name {
        "pen" => r##"<path d="m5 16-1 4 4-1L19 8l-3-3Z M14 7l3 3 M4 20h7"/>"##,
        "highlight" => r##"<path d="m8 16-3-3L15 3l6 6-10 10-3-3Z M5 14l-3 5h6 M3 22h16"/>"##,
        "erase" => {
            r##"<path d="m4 12 8-8a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3l-8 8H8l-4-4a3 3 0 0 1 0-4Z M8 8l8 8 M12 20h9"/>"##
        }
        "shapes" => {
            r##"<rect x="3" y="3" width="11" height="11" rx="1"/><circle cx="15.5" cy="15.5" r="5.5"/>"##
        }
        "rect" => r##"<rect x="3" y="5" width="18" height="14" rx="2"/>"##,
        "window" => r##"<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8h18"/>"##,
        "full" => {
            r##"<path d="M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5"/><rect x="6" y="7" width="12" height="10" rx="1"/>"##
        }
        "free" => r##"<path d="M10 4C2 3 1 15 6 18c4 3 8-1 10 1s5-4 3-7-5-9-9-8Z"/>"##,
        "ellipse" => r##"<ellipse cx="12" cy="12" rx="9" ry="7"/>"##,
        "arrow" => r##"<path d="M4 20 20 4 M8 4h12v12"/>"##,
        "text" => r##"<path d="M4 6V4h16v2 M12 4v16 M8 20h8"/>"##,
        "crop" => r##"<path d="M7 2v15h15 M2 7h15v15 M21 3 3 21"/>"##,
        "ocr" => {
            r##"<path d="M7 3H3v4 M17 3h4v4 M3 17v4h4 M21 17v4h-4 M7 8h10 M12 8v9 M9 17h6"/>"##
        }
        "emoji" => {
            r##"<circle cx="12" cy="12" r="9"/><path d="M8 14c1 4 7 4 8 0 M8 8v1 M16 8v1"/>"##
        }
        "redact" => {
            r##"<path d="M4 5h16 M4 19h16"/><rect x="3" y="9" width="18" height="6" fill="#ececec"/>"##
        }
        "picker" => r##"<path d="m14 4 6 6 M17 2l5 5-5 5-5-5Z M13 8 4 17l-1 4 4-1 9-9"/>"##,
        "rotate" => r##"<path d="M19 7a8 8 0 1 0 1 9 M19 2v6h-6"/>"##,
        "color" => {
            r##"<circle cx="12" cy="12" r="9"/><circle cx="8" cy="8" r="1"/><circle cx="16" cy="8" r="1"/><circle cx="7" cy="14" r="1"/><circle cx="14" cy="16" r="2" fill="#ff6666" stroke="#ff6666"/>"##
        }
        "undo" => r##"<path d="M8 4 3 9l5 5 M3 9h11a6 6 0 0 1 0 12"/>"##,
        "redo" => r##"<path d="m16 4 5 5-5 5 M21 9H10a6 6 0 0 0 0 12"/>"##,
        "save" => r##"<path d="M4 3h13l4 4v14H3V3Z M7 3v6h10V3 M7 21v-8h10v8"/>"##,
        "copy" => {
            r##"<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 5V3H3v13h2"/>"##
        }
        "share" => r##"<path d="M15 3h6v6 M21 3 11 13 M10 5H4v16h16v-7"/>"##,
        "video" => {
            r##"<rect x="2" y="6" width="13" height="12" rx="2"/><path d="m15 10 6-4v12l-6-4"/>"##
        }
        "clock" => r##"<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>"##,
        _ => {
            r##"<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>"##
        }
    };
    let svg = format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><g fill="none" stroke="#ececec" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{paths}</g></svg>"##
    );
    let loader = gdk_pixbuf::PixbufLoader::with_type("svg").expect("GTK SVG loader");
    loader.write(svg.as_bytes()).expect("built-in icon");
    loader.close().expect("built-in icon");
    gtk::Image::from_pixbuf(loader.pixbuf().as_ref())
}

pub fn decorate(b: &impl IsA<gtk::Button>, name: &str, label: &str, tip: &str) {
    let b = b.as_ref();
    b.set_label("");
    b.set_image(Some(&image(name)));
    b.set_always_show_image(true);
    b.set_tooltip_text(Some(tip));
    b.style_context().add_class("icon-button");
    if let Some(a) = b.accessible() {
        a.set_name(label);
    }
}
