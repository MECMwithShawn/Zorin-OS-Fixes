mod actions;
mod capture;
mod document;
mod extras;
mod icons;
mod portal_record;
mod recording;
use capture::Mode;
use document::{Document, Mark, Point, Tool};
use gdk_pixbuf::Pixbuf;
use gtk::prelude::*;
use std::{
    cell::{Cell, RefCell},
    path::{Path, PathBuf},
    rc::Rc,
    time::Duration,
};

struct Ui {
    window: gtk::ApplicationWindow,
    canvas: gtk::DrawingArea,
    status: gtk::Label,
    mode: gtk::ComboBoxText,
    delay: gtk::ComboBoxText,
    color: gtk::ColorButton,
    width: gtk::SpinButton,
    doc: RefCell<Option<Document>>,
    pending: RefCell<Option<Mark>>,
    tool: Cell<Tool>,
    generation: Cell<u64>,
    capturing: Cell<bool>,
    editing: gtk::Box,
    toolbar: gtk::Box,
    expanded: Cell<bool>,
    save: gtk::Button,
    copy: gtk::Button,
    cancel: gtk::Button,
    prefs: RefCell<extras::Preferences>,
    portal_session: RefCell<Option<portal_record::Session>>,
    pending_portal: RefCell<Option<(gio::DBusConnection, String)>>,
    record_mode: gtk::ToggleButton,
    recording: RefCell<Option<recording::Recording>>,
    clip: RefCell<Option<recording::Clip>>,
    stop: gtk::Button,
    play: gtk::Button,
    shares: RefCell<Vec<extras::PrivateDir>>,
    zoom: gtk::ComboBoxText,
}
fn button(label: &str, tip: &str) -> gtk::Button {
    let b = gtk::Button::with_label(label);
    b.set_tooltip_text(Some(tip));
    b
}
fn load_image(path: &Path) -> Result<Pixbuf, String> {
    let (_, w, h) = Pixbuf::file_info(path).ok_or("This file is not a supported image.")?;
    if w as i64 * h as i64 > 40_000_000 {
        return Err("Image exceeds the 40 megapixel limit.".into());
    }
    Pixbuf::from_file(path).map_err(|e| e.to_string())
}
impl Ui {
    fn new(app: &gtk::Application) -> Rc<Self> {
        let window = gtk::ApplicationWindow::new(app);
        window.set_title("Axentra SnippingTool");
        window.set_default_size(620, 220);
        window.set_position(gtk::WindowPosition::Center);
        window.set_icon_name(Some("zorin11-snipping-tool"));
        let root = gtk::Box::new(gtk::Orientation::Vertical, 0);
        window.add(&root);
        let header = gtk::HeaderBar::new();
        header.set_title(Some("Axentra SnippingTool"));
        header.set_show_close_button(true);
        header.set_decoration_layout(Some(":minimize,maximize,close"));
        // A quiet, left-aligned title strip, separate from the capture commands.
        header.set_custom_title(Some(&gtk::Label::new(None)));
        let title = gtk::Box::new(gtk::Orientation::Horizontal, 9);
        let logo = gdk_pixbuf::PixbufLoader::with_type("svg").expect("GTK SVG loader");
        logo.set_size(20, 20);
        let _ = logo.write(include_bytes!("../icon.svg"));
        let _ = logo.close();
        title.pack_start(
            &gtk::Image::from_pixbuf(logo.pixbuf().as_ref()),
            false,
            false,
            0,
        );
        title.pack_start(
            &gtk::Label::new(Some("Axentra SnippingTool")),
            false,
            false,
            0,
        );
        header.pack_start(&title);
        window.set_titlebar(Some(&header));
        let commands = gtk::Box::new(gtk::Orientation::Horizontal, 6);
        commands.style_context().add_class("capture-bar");
        root.pack_start(&commands, false, false, 0);
        let new = button("＋ New", "New snip (Ctrl+N)");
        new.style_context().add_class("new-snip");
        commands.pack_start(&new, false, false, 0);
        let mode = gtk::ComboBoxText::new();
        for (id, name) in [
            ("rect", "Rectangle mode"),
            ("window", "Window mode"),
            ("full", "Full-screen mode"),
            ("free", "Free-form mode"),
        ] {
            mode.append(Some(id), name)
        }
        mode.set_active_id(Some("rect"));
        mode.set_tooltip_text(Some("Capture mode (Alt+M)"));
        if is_wayland() {
            mode.remove_all();
            mode.append(Some("portal"), "GNOME picker");
            mode.set_active_id(Some("portal"));
            mode.set_sensitive(false);
            mode.set_tooltip_text(Some(
                "Wayland uses the desktop permission-controlled capture picker",
            ));
        }
        let mode_group = gtk::Box::new(gtk::Orientation::Horizontal, 0);
        let mode_icon = icons::image("rect");
        mode_group.pack_start(&mode_icon, false, false, 3);
        mode_group.pack_start(&mode, false, false, 0);
        commands.pack_start(&mode_group, false, false, 0);
        mode.connect_changed(move |m| {
            let i = icons::image(m.active_id().as_deref().unwrap_or("rect"));
            mode_icon.set_from_pixbuf(i.pixbuf().as_ref());
        });
        let delay = gtk::ComboBoxText::new();
        for sec in [0, 1, 2, 3, 4, 5, 10] {
            delay.append(
                Some(&sec.to_string()),
                &if sec == 0 {
                    "No delay".into()
                } else {
                    format!("{sec} seconds")
                },
            );
        }
        delay.set_active_id(Some("0"));
        delay.set_tooltip_text(Some("Capture delay (Alt+D)"));
        commands.pack_start(&icons::image("clock"), false, false, 0);
        commands.pack_start(&delay, false, false, 0);
        let record_mode = gtk::ToggleButton::new();
        icons::decorate(&record_mode, "video", "Record", "Video mode (Win+Shift+R)");
        commands.pack_start(&record_mode, false, false, 0);
        let more = gtk::MenuButton::new();
        icons::decorate(&more, "more", "⋯", "More options");
        commands.pack_end(&more, false, false, 0);
        let menu = gtk::Menu::new();
        let open = gtk::MenuItem::with_label("Open image");
        let share = gtk::MenuItem::with_label("Share / Open with");
        let print = gtk::MenuItem::with_label("Print");
        let prefs = gtk::MenuItem::with_label("Settings");
        let screen_color = gtk::MenuItem::with_label("Pick screen color");
        menu.append(&open);
        menu.append(&screen_color);
        menu.append(&share);
        menu.append(&print);
        menu.append(&gtk::SeparatorMenuItem::new());
        menu.append(&prefs);
        menu.show_all();
        more.set_popup(Some(&menu));

        // One contextual icon toolbar replaces the old two rows of text buttons.
        let toolbar = gtk::Box::new(gtk::Orientation::Horizontal, 4);
        toolbar.style_context().add_class("tools");
        root.pack_start(&toolbar, false, false, 0);
        let editing = gtk::Box::new(gtk::Orientation::Horizontal, 4);
        toolbar.pack_start(&editing, false, false, 0);
        let mut toolbuttons = vec![];
        let first = gtk::RadioButton::new();
        first.set_mode(false);
        icons::decorate(&first, "pen", "Pen", "Ballpoint pen");
        editing.pack_start(&first, false, false, 0);
        toolbuttons.push((Tool::Pen, first.clone()));
        for (t, icon, label) in [
            (Tool::Highlight, "highlight", "Highlight"),
            (Tool::Eraser, "erase", "Eraser"),
        ] {
            let b = gtk::RadioButton::from_widget(&first);
            b.set_mode(false);
            icons::decorate(&b, icon, label, label);
            editing.pack_start(&b, false, false, 0);
            toolbuttons.push((t, b));
        }
        let shapes = gtk::MenuButton::new();
        icons::decorate(&shapes, "shapes", "More tools", "Shapes and more tools");
        let tools_popup = gtk::Popover::new(Some(&shapes));
        let tools_grid = gtk::Grid::new();
        tools_grid.set_row_spacing(4);
        tools_grid.set_column_spacing(4);
        tools_grid.set_margin_start(8);
        tools_grid.set_margin_end(8);
        tools_grid.set_margin_top(8);
        tools_grid.set_margin_bottom(8);
        for (i, (t, icon, label)) in [
            (Tool::Rectangle, "rect", "Rectangle"),
            (Tool::Ellipse, "ellipse", "Ellipse"),
            (Tool::Arrow, "arrow", "Arrow"),
            (Tool::Emoji, "emoji", "Emoji"),
            (Tool::Redact, "redact", "Redact"),
            (Tool::Picker, "picker", "Color picker"),
        ]
        .into_iter()
        .enumerate()
        {
            let b = gtk::RadioButton::with_label_from_widget(&first, label);
            b.set_mode(false);
            b.set_image(Some(&icons::image(icon)));
            b.set_always_show_image(true);
            b.set_tooltip_text(Some(label));
            b.set_halign(gtk::Align::Fill);
            tools_grid.attach(&b, (i % 2) as i32, (i / 2) as i32, 1, 1);
            let popup = tools_popup.clone();
            b.connect_clicked(move |_| popup.popdown());
            toolbuttons.push((t, b));
        }
        let rotate = button("Rotate", "Rotate clockwise");
        rotate.set_image(Some(&icons::image("rotate")));
        rotate.set_always_show_image(true);
        tools_grid.attach(&rotate, 0, 3, 2, 1);
        let popup = tools_popup.clone();
        rotate.connect_clicked(move |_| popup.popdown());
        tools_popup.add(&tools_grid);
        tools_grid.show_all();
        shapes.set_popover(Some(&tools_popup));
        editing.pack_start(&shapes, false, false, 0);
        for (t, icon, label) in [(Tool::Text, "text", "Text"), (Tool::Crop, "crop", "Crop")] {
            let b = gtk::RadioButton::from_widget(&first);
            b.set_mode(false);
            icons::decorate(&b, icon, label, label);
            editing.pack_start(&b, false, false, 0);
            toolbuttons.push((t, b));
        }
        let text_actions = button("", "Extract and redact text locally");
        icons::decorate(
            &text_actions,
            "ocr",
            "Text actions",
            "Text actions — copy or redact text",
        );
        editing.pack_start(&text_actions, false, false, 0);
        editing.pack_start(
            &gtk::Separator::new(gtk::Orientation::Vertical),
            false,
            false,
            5,
        );
        let ink = gtk::MenuButton::new();
        icons::decorate(&ink, "color", "Ink settings", "Ink color and stroke width");
        let ink_popup = gtk::Popover::new(Some(&ink));
        let ink_box = gtk::Box::new(gtk::Orientation::Horizontal, 10);
        ink_box.set_margin_start(12);
        ink_box.set_margin_end(12);
        ink_box.set_margin_top(12);
        ink_box.set_margin_bottom(12);
        let color = gtk::ColorButton::with_rgba(&gdk::RGBA::new(1., 0.25, 0.25, 1.));
        color.set_title("Ink color");
        color.set_tooltip_text(Some("Ink color"));
        ink_box.pack_start(&color, false, false, 0);
        ink_box.pack_start(&gtk::Label::new(Some("Thickness")), false, false, 0);
        let width = gtk::SpinButton::with_range(1., 24., 1.);
        width.set_value(4.);
        width.set_tooltip_text(Some("Stroke width"));
        ink_box.pack_start(&width, false, false, 0);
        ink_popup.add(&ink_box);
        ink_box.show_all();
        ink.set_popover(Some(&ink_popup));
        editing.pack_start(&ink, false, false, 0);
        let undo = button("", "Undo (Ctrl+Z)");
        icons::decorate(&undo, "undo", "Undo", "Undo (Ctrl+Z)");
        let redo = button("", "Redo (Ctrl+Shift+Z)");
        icons::decorate(&redo, "redo", "Redo", "Redo (Ctrl+Shift+Z)");
        editing.pack_start(&undo, false, false, 0);
        editing.pack_start(&redo, false, false, 0);
        let save = button("", "Save as (Ctrl+S)");
        icons::decorate(&save, "save", "Save as", "Save as (Ctrl+S)");
        let copy = button("", "Copy (Ctrl+C)");
        icons::decorate(&copy, "copy", "Copy", "Copy (Ctrl+C)");
        let share_button = button("", "Share / Open with");
        icons::decorate(&share_button, "share", "Share", "Share / Open with");
        toolbar.pack_end(&share_button, false, false, 0);
        toolbar.pack_end(&copy, false, false, 0);
        toolbar.pack_end(&save, false, false, 0);
        let zoom = gtk::ComboBoxText::new();
        for (id, label) in [("fit", "Fit"), ("1", "100%"), ("2", "200%"), ("4", "400%")] {
            zoom.append(Some(id), label);
        }
        zoom.set_active_id(Some("fit"));
        zoom.set_tooltip_text(Some("Image zoom"));
        let canvas = gtk::DrawingArea::new();
        canvas.set_hexpand(true);
        canvas.set_vexpand(true);
        canvas.add_events(
            gdk::EventMask::BUTTON_PRESS_MASK
                | gdk::EventMask::BUTTON_RELEASE_MASK
                | gdk::EventMask::POINTER_MOTION_MASK,
        );
        let scroll = gtk::ScrolledWindow::new(gtk::Adjustment::NONE, gtk::Adjustment::NONE);
        scroll.add(&canvas);
        root.pack_start(&scroll, true, true, 0);
        let footer = gtk::Box::new(gtk::Orientation::Horizontal, 10);
        footer.style_context().add_class("footer");
        let status = gtk::Label::new(None);
        status.set_xalign(0.);
        status.set_line_wrap(true);
        status.set_max_width_chars(70);
        footer.pack_end(&zoom, false, false, 0);
        let footer_visibility = footer.clone();
        status.connect_label_notify(move |s| footer_visibility.set_visible(!s.text().is_empty()));
        footer.pack_start(&status, true, true, 0);
        let cancel = button("Cancel capture", "Cancel the capture delay");
        footer.pack_end(&cancel, false, false, 0);
        let stop = button("■ Stop recording", "Stop and review the recording");
        footer.pack_end(&stop, false, false, 0);
        let play = button("▶ Play recording", "Open recording in your video player");
        footer.pack_end(&play, false, false, 0);
        root.pack_end(&footer, false, false, 0);
        let ui = Rc::new(Self {
            window,
            canvas,
            status,
            mode,
            delay,
            color,
            width,
            doc: RefCell::new(None),
            pending: RefCell::new(None),
            tool: Cell::new(Tool::Pen),
            generation: Cell::new(0),
            capturing: Cell::new(false),
            editing,
            toolbar,
            expanded: Cell::new(false),
            save,
            copy,
            cancel,
            prefs: RefCell::new(extras::Preferences::load()),
            record_mode,
            portal_session: RefCell::new(None),
            pending_portal: RefCell::new(None),
            recording: RefCell::new(None),
            clip: RefCell::new(None),
            stop,
            play,
            shares: RefCell::new(vec![]),
            zoom,
        });
        let u = ui.clone();
        prefs.connect_activate(move |_| u.preferences());
        let u = ui.clone();
        screen_color.connect_activate(move |_| {
            if u.capturing.get() || u.recording.borrow().is_some() {
                return;
            }
            u.capturing.set(true);
            u.window.hide();
            let current = u.clone();
            if let Err(e) = capture::pick_color(move |r| {
                current.capturing.set(false);
                current.window.present();
                match r {
                    Ok((r, g, b)) => {
                        let hex = format!(
                            "#{:02X}{:02X}{:02X}",
                            (r * 255.).round() as u8,
                            (g * 255.).round() as u8,
                            (b * 255.).round() as u8
                        );
                        gtk::Clipboard::get(&gdk::SELECTION_CLIPBOARD).set_text(&hex);
                        current.color.set_rgba(&gdk::RGBA::new(r, g, b, 1.));
                        current
                            .status
                            .set_text(&format!("{hex} copied to clipboard"));
                    }
                    Err(e) => current.status.set_text(&e),
                }
            }) {
                u.capturing.set(false);
                u.window.present();
                u.status.set_text(&e);
            }
        });
        let u = ui.clone();
        text_actions.connect_clicked(move |_| u.text_actions());
        let u = ui.clone();
        share.connect_activate(move |_| u.share());
        let u = ui.clone();
        share_button.connect_clicked(move |_| u.share());
        let u = ui.clone();
        print.connect_activate(move |_| u.print_image());
        let u = ui.clone();
        rotate.connect_clicked(move |_| {
            let result = u.doc.borrow_mut().as_mut().map(|d| d.rotate());
            u.refresh();
            if let Some(Err(e)) = result {
                u.status.set_text(&e);
            }
        });
        let u = ui.clone();
        ui.zoom.connect_changed(move |_| u.refresh());
        let u = ui.clone();
        ui.stop.connect_clicked(move |_| u.stop_recording());
        let u = ui.clone();
        ui.play.connect_clicked(move |_| {
            if let Some(c) = u.clip.borrow().as_ref() {
                let _ = gio::AppInfo::launch_default_for_uri(
                    gio::File::for_path(&c.path).uri().as_str(),
                    gio::AppLaunchContext::NONE,
                );
            }
        });
        let u = ui.clone();
        ui.record_mode.connect_toggled(move |b| {
            u.mode.set_sensitive(!b.is_active() && !is_wayland());
            if b.is_active() {
                u.mode.set_active_id(Some("rect"));
            }
            u.canvas.queue_draw();
        });
        for (t, b) in toolbuttons {
            let u = ui.clone();
            let shapes = shapes.clone();
            b.connect_toggled(move |b| {
                if b.is_active() {
                    u.tool.set(t);
                    if matches!(t, Tool::Rectangle | Tool::Ellipse | Tool::Arrow | Tool::Emoji | Tool::Redact | Tool::Picker) {
                        shapes.style_context().add_class("active-tool");
                    } else {
                        shapes.style_context().remove_class("active-tool");
                    }
                    u.status.set_text(match t {
                        Tool::Crop => {
                            "Drag across the image to crop. Undo restores the previous image."
                        }
                        Tool::Text => "Click the image to add text.",
                        Tool::Emoji => "Click the image to place an emoji.",
                        Tool::Eraser => "Click an annotation to remove it. Screenshot pixels are retained.",
                        Tool::Picker => "Click an image pixel to copy its exact HEX color. Capture the screen first to sample it.",
                        Tool::Redact => "Drag over private content to cover it. Save as exports flattened pixels.",
                        _ => "Drag across the image to annotate.",
                    });
                    if t == Tool::Highlight {
                        u.color.set_rgba(&gdk::RGBA::new(1., 0.86, 0.15, 1.));
                    }
                }
            });
        }
        let u = ui.clone();
        new.connect_clicked(move |_| u.start_capture());
        let u = ui.clone();
        open.connect_activate(move |_| u.open());
        let u = ui.clone();
        ui.save.connect_clicked(move |_| {
            u.save();
        });
        let u = ui.clone();
        ui.copy.connect_clicked(move |_| u.copy());
        let u = ui.clone();
        undo.connect_clicked(move |_| u.history(false));
        let u = ui.clone();
        redo.connect_clicked(move |_| u.history(true));
        let u = ui.clone();
        ui.cancel.connect_clicked(move |_| {
            u.generation.set(u.generation.get() + 1);
            if let Some((bus, path)) = u.pending_portal.borrow_mut().take() {
                let _ = bus.call_sync(
                    Some("org.freedesktop.portal.Desktop"),
                    &path,
                    "org.freedesktop.portal.Request",
                    "Close",
                    None,
                    None,
                    gio::DBusCallFlags::NONE,
                    2000,
                    gio::Cancellable::NONE,
                );
            }
            u.portal_session.borrow_mut().take();
            u.cancel.hide();
            u.capturing.set(false);
            u.status.set_text("Capture cancelled.");
        });
        let u = ui.clone();
        ui.canvas.connect_draw(move |area, c| {
            let bg = if u.doc.borrow().is_some() {
                0.105
            } else {
                0.125
            };
            c.set_source_rgb(bg, bg, bg);
            let _ = c.paint();
            if let Some(d) = u.doc.borrow().as_ref() {
                let (s, x, y) = u.transform();
                let _ = c.save();
                c.translate(x, y);
                c.scale(s, s);
                d.draw(c);
                if let Some(m) = u.pending.borrow().as_ref() {
                    document::draw_mark(c, m)
                }
                let _ = c.restore();
            } else {
                c.set_source_rgb(0.78, 0.78, 0.78);
                c.select_font_face("Sans", cairo::FontSlant::Normal, cairo::FontWeight::Normal);
                c.set_font_size(14.);
                let text = if u.clip.borrow().is_some() {
                    "Recording ready — Play or Save as"
                } else if u.record_mode.is_active() {
                    "Select New or press Win + Shift + R to record."
                } else {
                    "Press Win + Shift + S to start a snip."
                };
                if let Ok(ext) = c.text_extents(text) {
                    c.move_to(
                        (area.allocated_width() as f64 - ext.width()) / 2. - ext.x_bearing(),
                        (area.allocated_height() as f64 - ext.height()) / 2. - ext.y_bearing(),
                    );
                    let _ = c.show_text(text);
                }
            }
            glib::Propagation::Proceed
        });
        let u = ui.clone();
        ui.canvas.connect_button_press_event(move |_, e| {
            if e.button() != 1 {
                return glib::Propagation::Proceed;
            }
            let Some(p) = u.point(e.position()) else {
                return glib::Propagation::Proceed;
            };
            if u.tool.get() == Tool::Eraser {
                if let Some(d) = u.doc.borrow_mut().as_mut() {
                    d.erase(p);
                }
                u.refresh();
                return glib::Propagation::Stop;
            }
            if u.tool.get() == Tool::Picker {
                if let Some(d) = u.doc.borrow().as_ref() {
                    if let Ok(hex) = d.pixel(p) {
                        gtk::Clipboard::get(&gdk::SELECTION_CLIPBOARD).set_text(&hex);
                        u.status.set_text(&format!("{hex} copied to clipboard"));
                    }
                }
                return glib::Propagation::Stop;
            }
            let color = u.color.rgba();
            let mut mark = Mark {
                tool: u.tool.get(),
                points: vec![p],
                color: (color.red(), color.green(), color.blue()),
                width: u.width.value()
                    * (if u.tool.get() == Tool::Highlight {
                        4.
                    } else {
                        1.
                    }),
                text: String::new(),
            };
            if matches!(mark.tool, Tool::Text | Tool::Emoji) {
                let dialog = gtk::Dialog::with_buttons(
                    Some(if mark.tool == Tool::Emoji {
                        "Add emoji"
                    } else {
                        "Add text"
                    }),
                    Some(&u.window),
                    gtk::DialogFlags::MODAL,
                    &[
                        ("Cancel", gtk::ResponseType::Cancel),
                        ("Add", gtk::ResponseType::Accept),
                    ],
                );
                let entry = gtk::Entry::new();
                entry.set_max_length(500);
                if mark.tool == Tool::Emoji {
                    entry.set_text("👍");
                    let emojis = gtk::Box::new(gtk::Orientation::Horizontal, 4);
                    for text in ["👍", "✅", "❌", "⭐", "❤️", "⚠️", "😊"] {
                        let b = gtk::Button::with_label(text);
                        let e = entry.clone();
                        b.connect_clicked(move |_| e.set_text(text));
                        emojis.pack_start(&b, false, false, 0);
                    }
                    dialog.content_area().pack_start(&emojis, false, false, 4);
                }
                entry.set_activates_default(true);
                dialog.set_default_response(gtk::ResponseType::Accept);
                dialog.content_area().pack_start(&entry, true, true, 12);
                dialog.show_all();
                if dialog.run() == gtk::ResponseType::Accept && !entry.text().is_empty() {
                    mark.text = entry.text().to_string();
                    if let Some(d) = u.doc.borrow_mut().as_mut() {
                        d.mark(mark)
                    }
                    u.refresh();
                }
                dialog.close();
            } else {
                *u.pending.borrow_mut() = Some(mark);
            }
            glib::Propagation::Stop
        });
        let u = ui.clone();
        ui.canvas.connect_motion_notify_event(move |_, e| {
            if let Some(p) = u.point(e.position()) {
                if let Some(m) = u.pending.borrow_mut().as_mut() {
                    if !matches!(m.tool, Tool::Pen | Tool::Highlight) {
                        m.points.truncate(1)
                    }
                    m.points.push(p);
                    u.canvas.queue_draw();
                }
            }
            glib::Propagation::Proceed
        });
        let u = ui.clone();
        ui.canvas.connect_button_release_event(move |_, e| {
            if e.button() == 1 {
                let mark = u.pending.borrow_mut().take();
                if let Some(m) = mark {
                    let result = {
                        let mut doc = u.doc.borrow_mut();
                        if let Some(d) = doc.as_mut() {
                            if m.tool == Tool::Crop {
                                d.crop(m.points[0], *m.points.last().unwrap())
                            } else if m.tool == Tool::Redact {
                                let (w, h) = d.size();
                                let (x, y, rw, rh) =
                                    document::bounds(m.points[0], *m.points.last().unwrap(), w, h);
                                d.redact(&[(x, y, rw, rh)])
                            } else {
                                d.mark(m);
                                Ok(())
                            }
                        } else {
                            Ok(())
                        }
                    };
                    u.refresh();
                    if let Err(e) = result {
                        u.status.set_text(&e);
                    }
                }
            }
            glib::Propagation::Proceed
        });
        let u = ui.clone();
        ui.window.connect_key_press_event(move |_, e| {
            if e.state().contains(gdk::ModifierType::MOD1_MASK) {
                match e.keyval() {
                    gdk::keys::constants::n | gdk::keys::constants::N => u.start_capture(),
                    gdk::keys::constants::m | gdk::keys::constants::M => u.mode.popup(),
                    gdk::keys::constants::d | gdk::keys::constants::D => u.delay.popup(),
                    _ => return glib::Propagation::Proceed,
                }
                return glib::Propagation::Stop;
            }
            if e.state().contains(gdk::ModifierType::CONTROL_MASK) {
                match e.keyval() {
                    gdk::keys::constants::n | gdk::keys::constants::N => u.start_capture(),
                    gdk::keys::constants::s | gdk::keys::constants::S => {
                        u.save();
                    }
                    gdk::keys::constants::c | gdk::keys::constants::C => u.copy(),
                    gdk::keys::constants::o | gdk::keys::constants::O => u.open(),
                    gdk::keys::constants::z | gdk::keys::constants::Z => {
                        u.history(e.state().contains(gdk::ModifierType::SHIFT_MASK))
                    }
                    gdk::keys::constants::y | gdk::keys::constants::Y => u.history(true),
                    gdk::keys::constants::r | gdk::keys::constants::R
                        if e.state().contains(gdk::ModifierType::SHIFT_MASK) =>
                    {
                        u.stop_recording()
                    }
                    gdk::keys::constants::p | gdk::keys::constants::P => u.print_image(),
                    _ => return glib::Propagation::Proceed,
                }
                return glib::Propagation::Stop;
            }
            glib::Propagation::Proceed
        });
        let u = ui.clone();
        ui.window.connect_delete_event(move |_, _| {
            if u.replace_ok() {
                u.generation.set(u.generation.get() + 1);
                gtk::Clipboard::get(&gdk::SELECTION_CLIPBOARD).store();
                glib::Propagation::Proceed
            } else {
                glib::Propagation::Stop
            }
        });
        ui.toolbar.show_all();
        ui.toolbar.set_no_show_all(true);
        ui.toolbar.hide();
        footer.show_all();
        footer.set_no_show_all(true);
        footer.hide();
        ui.window.show_all();
        ui.cancel.hide();
        ui.stop.hide();
        ui.play.hide();
        ui.refresh();
        footer.set_visible(false);
        ui
    }
    fn transform(&self) -> (f64, f64, f64) {
        let Some(d) = self.doc.borrow().as_ref().map(|d| d.size()) else {
            return (1., 0., 0.);
        };
        let (w, h) = (
            self.canvas.allocated_width() as f64,
            self.canvas.allocated_height() as f64,
        );
        let s = self
            .zoom
            .active_id()
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or_else(|| {
                ((w - 40.) / d.0 as f64)
                    .min((h - 40.) / d.1 as f64)
                    .min(1.)
                    .max(0.01)
            });
        (s, (w - d.0 as f64 * s) / 2., (h - d.1 as f64 * s) / 2.)
    }
    fn point(&self, p: Point) -> Option<Point> {
        let size = self.doc.borrow().as_ref().map(|d| d.size())?;
        let (s, x, y) = self.transform();
        let p = ((p.0 - x) / s, (p.1 - y) / s);
        if p.0 >= 0. && p.1 >= 0. && p.0 < size.0 as f64 && p.1 < size.1 as f64 {
            Some(p)
        } else {
            None
        }
    }
    fn refresh(&self) {
        let doc = self.doc.borrow();
        let has = doc.is_some();
        if let Some(d) = doc.as_ref() {
            if let Some(z) = self.zoom.active_id().and_then(|s| s.parse::<f64>().ok()) {
                let (w, h) = d.size();
                self.canvas
                    .set_size_request((w as f64 * z) as i32 + 40, (h as f64 * z) as i32 + 40);
            } else {
                self.canvas.set_size_request(-1, -1);
            }
        }
        let ready = has || self.clip.borrow().is_some();
        self.toolbar.set_visible(ready);
        self.editing.set_visible(has);
        self.zoom.set_visible(has);
        self.copy.set_visible(has);
        if ready && !self.expanded.replace(true) {
            self.window.resize(1060, 760);
        }
        self.save.set_sensitive(ready);
        self.copy.set_sensitive(has);
        if let Some(d) = doc.as_ref() {
            let (w, h) = d.size();
            self.status.set_text(&format!(
                "{w} × {h} pixels  •  {}",
                if d.dirty {
                    "Unsaved changes"
                } else {
                    "Saved image"
                }
            ));
            self.window.set_title(if d.dirty {
                "Axentra SnippingTool • Unsaved"
            } else {
                "Axentra SnippingTool"
            });
        }
        self.canvas.queue_draw();
    }
    fn set_image(&self, p: Pixbuf, dirty: bool) {
        self.capturing.set(false);
        self.clip.borrow_mut().take();
        self.play.hide();
        self.zoom.set_active_id(Some("fit"));
        match Document::new(p, dirty) {
            Ok(d) => {
                *self.doc.borrow_mut() = Some(d);
                self.pending.borrow_mut().take();
                self.refresh();
            }
            Err(e) => self.status.set_text(&e),
        }
        self.window.show();
        self.window.present();
    }
    fn history(&self, redo: bool) {
        if let Some(d) = self.doc.borrow_mut().as_mut() {
            if redo {
                d.redo()
            } else {
                d.undo()
            }
        }
        self.refresh();
    }
    fn replace_ok(&self) -> bool {
        if self.recording.borrow().is_some() || self.capturing.get() {
            self.status
                .set_text("Finish or cancel the current capture first.");
            return false;
        }
        if self.clip.borrow().as_ref().is_some_and(|c| !c.saved) {
            let d = gtk::MessageDialog::new(
                Some(&self.window),
                gtk::DialogFlags::MODAL,
                gtk::MessageType::Question,
                gtk::ButtonsType::None,
                "Save your recording before continuing?",
            );
            d.add_buttons(&[
                ("Cancel", gtk::ResponseType::Cancel),
                ("Discard", gtk::ResponseType::Reject),
                ("Save", gtk::ResponseType::Accept),
            ]);
            let result = d.run();
            d.close();
            return match result {
                gtk::ResponseType::Reject => true,
                gtk::ResponseType::Accept => self.save(),
                _ => false,
            };
        }
        if !self.doc.borrow().as_ref().is_some_and(|d| d.dirty) {
            return true;
        }
        let d = gtk::MessageDialog::new(
            Some(&self.window),
            gtk::DialogFlags::MODAL,
            gtk::MessageType::Question,
            gtk::ButtonsType::None,
            "Save your snip before continuing?",
        );
        d.add_buttons(&[
            ("Cancel", gtk::ResponseType::Cancel),
            ("Discard", gtk::ResponseType::Reject),
            ("Save", gtk::ResponseType::Accept),
        ]);
        d.set_default_response(gtk::ResponseType::Cancel);
        let r = d.run();
        d.close();
        match r {
            gtk::ResponseType::Reject => true,
            gtk::ResponseType::Accept => self.save(),
            _ => false,
        }
    }
    fn open(&self) {
        if self.capturing.get() {
            return;
        }
        if !self.replace_ok() {
            return;
        }
        let d = gtk::FileChooserDialog::new(
            Some("Open image"),
            Some(&self.window),
            gtk::FileChooserAction::Open,
        );
        d.add_buttons(&[
            ("Cancel", gtk::ResponseType::Cancel),
            ("Open", gtk::ResponseType::Accept),
        ]);
        let f = gtk::FileFilter::new();
        f.set_name(Some("Images"));
        f.add_pixbuf_formats();
        d.add_filter(f);
        if d.run() == gtk::ResponseType::Accept {
            if let Some(p) = d.filename() {
                match load_image(&p) {
                    Ok(p) => self.set_image(p, false),
                    Err(e) => self.status.set_text(&e),
                }
            }
        }
        d.close();
    }
    fn save(&self) -> bool {
        if self.clip.borrow().is_some() {
            let result = self.save_recording();
            if result {
                if let Some(c) = self.clip.borrow_mut().as_mut() {
                    c.saved = true;
                }
            }
            return result;
        }
        let image = match self.doc.borrow().as_ref().map(|d| d.render()) {
            Some(Ok(p)) => p,
            Some(Err(e)) => {
                self.status.set_text(&e);
                return false;
            }
            None => return false,
        };
        let d = gtk::FileChooserDialog::new(
            Some("Save snip"),
            Some(&self.window),
            gtk::FileChooserAction::Save,
        );
        d.add_buttons(&[
            ("Cancel", gtk::ResponseType::Cancel),
            ("Save", gtk::ResponseType::Accept),
        ]);
        d.set_do_overwrite_confirmation(true);
        let folder = self.prefs.borrow().folder.clone();
        let _ = std::fs::create_dir_all(&folder);
        d.set_current_folder(&folder);
        d.set_current_name(&format!(
            "Screenshot {}.png",
            glib::DateTime::now_local()
                .and_then(|d| d.format("%Y-%m-%d %H-%M-%S"))
                .map(|s| s.to_string())
                .unwrap_or_else(|_| "capture".into())
        ));
        for (name, patterns) in [
            ("PNG image", vec!["*.png"]),
            ("JPEG image", vec!["*.jpg", "*.jpeg"]),
        ] {
            let f = gtk::FileFilter::new();
            f.set_name(Some(name));
            for p in patterns {
                f.add_pattern(p)
            }
            d.add_filter(f)
        }
        let mut saved = false;
        if d.run() == gtk::ResponseType::Accept {
            if let Some(mut p) = d.filename() {
                if p.extension().is_none() {
                    p.set_extension("png");
                    // The native chooser confirmed the typed name, not the appended one.
                    if p.exists() {
                        let confirm = gtk::MessageDialog::new(
                            Some(&self.window),
                            gtk::DialogFlags::MODAL,
                            gtk::MessageType::Question,
                            gtk::ButtonsType::None,
                            &format!("Replace {}?", p.display()),
                        );
                        confirm.add_buttons(&[
                            ("Cancel", gtk::ResponseType::Cancel),
                            ("Replace", gtk::ResponseType::Accept),
                        ]);
                        let replace = confirm.run() == gtk::ResponseType::Accept;
                        confirm.close();
                        if !replace {
                            d.close();
                            return false;
                        }
                    }
                }
                let ext = p
                    .extension()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_lowercase();
                let format = match ext.as_str() {
                    "png" => Some("png"),
                    "jpg" | "jpeg" => Some("jpeg"),
                    _ => None,
                };
                let result = if let Some(format) = format {
                    image
                        .save_to_bufferv(
                            format,
                            if format == "jpeg" {
                                &[("quality", "95")]
                            } else {
                                &[]
                            },
                        )
                        .map_err(|e| e.to_string())
                        .and_then(|bytes| {
                            gio::File::for_path(&p)
                                .replace_contents(
                                    &bytes,
                                    None,
                                    false,
                                    gio::FileCreateFlags::REPLACE_DESTINATION,
                                    gio::Cancellable::NONE,
                                )
                                .map(|_| ())
                                .map_err(|e| e.to_string())
                        })
                } else {
                    Err("Use a .png, .jpg or .jpeg filename.".into())
                };
                match result {
                    Ok(()) => {
                        if let Some(doc) = self.doc.borrow_mut().as_mut() {
                            doc.dirty = false
                        }
                        self.refresh();
                        self.status.set_text(&format!("Saved to {}", p.display()));
                        saved = true
                    }
                    Err(e) => self.status.set_text(&format!("Could not save: {e}")),
                }
            }
        }
        d.close();
        saved
    }
    fn copy(&self) {
        if let Some(d) = self.doc.borrow().as_ref() {
            match d.render() {
                Ok(p) => {
                    let c = gtk::Clipboard::get(&gdk::SELECTION_CLIPBOARD);
                    c.set_image(&p);
                    self.status
                        .set_text("Image copied. Paste it into another app.");
                }
                Err(e) => self.status.set_text(&e),
            }
        }
    }
    fn start_capture(self: &Rc<Self>) {
        if self.recording.borrow().is_some() {
            self.stop_recording();
            return;
        }
        if self.capturing.get() {
            return;
        }
        if !self.replace_ok() {
            return;
        }
        self.capturing.set(true);
        self.generation.set(self.generation.get() + 1);
        let generation = self.generation.get();
        let seconds = self
            .delay
            .active_id()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(0);
        self.status
            .set_text(&format!("Capturing in {seconds} seconds…"));
        self.cancel.show();
        let u = self.clone();
        glib::timeout_add_local_once(Duration::from_secs(seconds), move || {
            if u.generation.get() != generation {
                return;
            }
            u.cancel.hide();
            u.window.hide();
            let u = u.clone();
            glib::timeout_add_local_once(Duration::from_millis(250), move || {
                if u.generation.get() != generation {
                    return;
                }
                u.capture();
            });
        });
    }
    fn capture(self: &Rc<Self>) {
        if is_wayland() {
            if self.record_mode.is_active() {
                self.capturing.set(false);
                self.window.present();
                self.status
                    .set_text("Wayland recording is being initialized through the desktop portal.");
                self.record_wayland();
                return;
            }
            let u = self.clone();
            if let Err(e) = capture::portal(move |r| match r {
                Ok(p) => u.capture_ready(p),
                Err(e) => {
                    u.capturing.set(false);
                    u.window.show();
                    u.window.present();
                    u.status.set_text(&e)
                }
            }) {
                self.capturing.set(false);
                self.window.show();
                self.status.set_text(&e)
            }
            return;
        }
        let image = match capture::desktop() {
            Ok(p) => p,
            Err(e) => {
                self.capturing.set(false);
                self.window.show();
                self.status.set_text(&e);
                return;
            }
        };
        let mode = if self.record_mode.is_active() {
            Mode::Rectangle
        } else {
            match self.mode.active_id().as_deref() {
                Some("free") => Mode::Freeform,
                Some("window") => Mode::Window,
                Some("full") => Mode::Fullscreen,
                _ => Mode::Rectangle,
            }
        };
        if mode == Mode::Fullscreen {
            self.capture_ready(image)
        } else {
            self.overlay(image, mode)
        }
    }
    fn overlay(self: &Rc<Self>, image: Pixbuf, mode: Mode) {
        let windows = capture::windows();
        let overlay = gtk::Window::new(gtk::WindowType::Toplevel);
        overlay.set_title("Snipping selection");
        overlay.set_decorated(false);
        overlay.set_keep_above(true);
        overlay.set_skip_taskbar_hint(true);
        overlay.set_skip_pager_hint(true);
        overlay.set_type_hint(gdk::WindowTypeHint::Notification);
        overlay.set_app_paintable(true);
        let scale = gdk::Window::default_root_window().scale_factor().max(1) as f64;
        let (w, h) = (image.width(), image.height());
        overlay.set_default_size((w as f64 / scale) as i32, (h as f64 / scale) as i32);
        overlay.move_(0, 0);
        overlay.resize((w as f64 / scale) as i32, (h as f64 / scale) as i32);
        let area = gtk::DrawingArea::new();
        area.add_events(
            gdk::EventMask::BUTTON_PRESS_MASK
                | gdk::EventMask::BUTTON_RELEASE_MASK
                | gdk::EventMask::POINTER_MOTION_MASK,
        );
        overlay.add(&area);
        let points = Rc::new(RefCell::new(Vec::<Point>::new()));
        let hover = Rc::new(Cell::new(None::<capture::Rect>));
        let p = points.clone();
        let image2 = image.clone();
        let selected = hover.clone();
        area.connect_draw(move |_, c| {
            let _ = c.save();
            c.scale(1. / scale, 1. / scale);
            c.set_source_pixbuf(&image2, 0., 0.);
            let _ = c.paint();
            c.set_source_rgba(0., 0., 0., 0.40);
            let _ = c.paint();
            let points = p.borrow();
            let rect = if mode == Mode::Window {
                selected.get().map(|r| {
                    (
                        r.x as f64 * scale,
                        r.y as f64 * scale,
                        r.w as f64 * scale,
                        r.h as f64 * scale,
                    )
                })
            } else {
                points.first().zip(points.last()).map(|(a, b)| {
                    let (x, y, w, h) = document::bounds(*a, *b, w, h);
                    (x as f64, y as f64, w as f64, h as f64)
                })
            };
            if let Some((x, y, rw, rh)) = rect {
                let _ = c.save();
                if mode == Mode::Freeform {
                    if let Some(a) = points.first() {
                        c.move_to(a.0, a.1);
                        for p in &points[1..] {
                            c.line_to(p.0, p.1)
                        }
                        c.close_path();
                    }
                } else {
                    c.rectangle(x, y, rw, rh)
                }
                c.clip();
                c.set_source_pixbuf(&image2, 0., 0.);
                let _ = c.paint();
                let _ = c.restore();
                c.set_source_rgb(0.38, 0.78, 1.);
                c.set_line_width(2. * scale);
                if mode == Mode::Freeform {
                    if let Some(a) = points.first() {
                        c.move_to(a.0, a.1);
                        for p in &points[1..] {
                            c.line_to(p.0, p.1)
                        }
                        c.close_path();
                    }
                } else {
                    c.rectangle(x, y, rw, rh)
                }
                let _ = c.stroke();
            }
            let _ = c.restore();
            c.set_source_rgba(0.12, 0.12, 0.12, 0.96);
            c.rectangle(18., 18., 460., 52.);
            let _ = c.fill();
            c.set_source_rgb(1., 1., 1.);
            c.set_font_size(16.);
            c.move_to(32., 49.);
            let _ = c.show_text(if mode == Mode::Window {
                "Click a window to capture  •  Esc to cancel"
            } else {
                "Drag to select your snip  •  Esc to cancel"
            });
            glib::Propagation::Proceed
        });
        let p = points.clone();
        area.connect_button_press_event(move |_, e| {
            if e.button() == 1 {
                let (x, y) = e.position();
                *p.borrow_mut() = vec![(x * scale, y * scale)];
            }
            glib::Propagation::Stop
        });
        let p = points.clone();
        let selected = hover.clone();
        let windows2 = windows.clone();
        area.connect_motion_notify_event(move |a, e| {
            let (x, y) = e.position();
            if mode == Mode::Window {
                selected.set(windows2.iter().find(|r| r.contains(x, y)).copied());
            } else {
                let mut p = p.borrow_mut();
                if !p.is_empty() {
                    if mode == Mode::Rectangle {
                        p.truncate(1)
                    }
                    p.push((x * scale, y * scale));
                }
            }
            a.queue_draw();
            glib::Propagation::Stop
        });
        let p = points.clone();
        let o = overlay.clone();
        let u = self.clone();
        let selection_image = image.clone();
        area.connect_button_release_event(move |_, e| {
            let image = &selection_image;
            if e.button() != 1 {
                return glib::Propagation::Proceed;
            }
            let (x, y) = e.position();
            let mut pts = p.borrow().clone();
            if mode == Mode::Window {
                if let Some(r) = windows.iter().find(|r| r.contains(x, y)) {
                    pts = vec![
                        (r.x as f64 * scale, r.y as f64 * scale),
                        ((r.x + r.w) as f64 * scale, (r.y + r.h) as f64 * scale),
                    ];
                } else {
                    return glib::Propagation::Stop;
                }
            } else {
                pts.push((x * scale, y * scale));
            }
            if let (Some(a), Some(b)) = (pts.first(), pts.last()) {
                let (a, b) = if mode == Mode::Freeform {
                    (
                        pts.iter().fold((f64::INFINITY, f64::INFINITY), |a, p| {
                            (a.0.min(p.0), a.1.min(p.1))
                        }),
                        pts.iter()
                            .fold((0_f64, 0_f64), |a, p| (a.0.max(p.0), a.1.max(p.1))),
                    )
                } else {
                    (*a, *b)
                };
                let (x, y, cw, ch) = document::bounds(a, b, w, h);
                if cw >= 2 && ch >= 2 {
                    if u.record_mode.is_active() {
                        o.close();
                        u.record_area(capture::Rect { x, y, w: cw, h: ch });
                        return glib::Propagation::Stop;
                    }
                    let result = if mode == Mode::Freeform {
                        (|| -> Result<Pixbuf, String> {
                            let s = cairo::ImageSurface::create(cairo::Format::ARgb32, cw, ch)
                                .map_err(|e| e.to_string())?;
                            let c = cairo::Context::new(&s).map_err(|e| e.to_string())?;
                            c.translate(-(x as f64), -(y as f64));
                            c.move_to(pts[0].0, pts[0].1);
                            for p in &pts[1..] {
                                c.line_to(p.0, p.1)
                            }
                            c.close_path();
                            c.clip();
                            c.set_source_pixbuf(&image, 0., 0.);
                            let _ = c.paint();
                            gdk::pixbuf_get_from_surface(&s, 0, 0, cw, ch)
                                .ok_or("Could not capture selection".into())
                        })()
                    } else {
                        image
                            .new_subpixbuf(x, y, cw, ch)
                            .copy()
                            .ok_or("Could not capture selection".into())
                    };
                    o.close();
                    match result {
                        Ok(p) => u.capture_ready(p),
                        Err(e) => {
                            u.window.show();
                            u.status.set_text(&e)
                        }
                    }
                }
            }
            glib::Propagation::Stop
        });
        let o = overlay.clone();
        let u = self.clone();
        let keyboard_points = points.clone();
        let keyboard_area = area.clone();
        let keyboard_image = image.clone();
        overlay.connect_key_press_event(move |_, e| {
            let direction = match e.keyval() {
                gdk::keys::constants::Left => Some((-1., 0.)),
                gdk::keys::constants::Right => Some((1., 0.)),
                gdk::keys::constants::Up => Some((0., -1.)),
                gdk::keys::constants::Down => Some((0., 1.)),
                _ => None,
            };
            if let Some((dx, dy)) = direction {
                let mut pts = keyboard_points.borrow_mut();
                if pts.len() < 2 {
                    *pts = vec![
                        (w as f64 / 2. - 50., h as f64 / 2. - 50.),
                        (w as f64 / 2. + 50., h as f64 / 2. + 50.),
                    ];
                }
                if e.state().contains(gdk::ModifierType::SHIFT_MASK) {
                    let last = pts.last_mut().unwrap();
                    last.0 = (last.0 + dx * 10.).clamp(0., w as f64);
                    last.1 = (last.1 + dy * 10.).clamp(0., h as f64);
                } else {
                    for p in pts.iter_mut() {
                        p.0 = (p.0 + dx).clamp(0., w as f64);
                        p.1 = (p.1 + dy).clamp(0., h as f64);
                    }
                }
                keyboard_area.queue_draw();
                return glib::Propagation::Stop;
            }
            if e.keyval() == gdk::keys::constants::Return && mode == Mode::Rectangle {
                let pts = keyboard_points.borrow();
                if let Some((a, b)) = pts.first().zip(pts.last()) {
                    let (x, y, cw, ch) = document::bounds(*a, *b, w, h);
                    if cw >= 2 && ch >= 2 {
                        o.close();
                        if u.record_mode.is_active() {
                            u.record_area(capture::Rect { x, y, w: cw, h: ch });
                        } else if let Some(p) = keyboard_image.new_subpixbuf(x, y, cw, ch).copy() {
                            u.capture_ready(p);
                        }
                    }
                }
                return glib::Propagation::Stop;
            }
            if e.keyval() == gdk::keys::constants::Escape {
                o.close();
                u.window.show();
                u.window.present();
                u.status.set_text("Capture cancelled.");
                glib::Propagation::Stop
            } else {
                glib::Propagation::Proceed
            }
        });
        let u = self.clone();
        overlay.connect_delete_event(move |_, _| {
            u.capturing.set(false);
            u.window.show();
            u.window.present();
            u.status.set_text("Capture cancelled.");
            glib::Propagation::Proceed
        });
        // This X11-only selection surface must span the root, including panels.
        // Mutter constrains managed windows to a work area on mixed monitors.
        overlay.realize();
        if let Some(w) = overlay.window() {
            w.set_override_redirect(true);
        }
        overlay.show_all();
        overlay.present();
        if let Some(w) = overlay.window() {
            let cursor = gdk::Cursor::from_name(&w.display(), "crosshair");
            w.set_cursor(cursor.as_ref());
            w.raise();
            w.focus(0); // X11 CurrentTime
            if let Some(seat) = w.display().default_seat() {
                if seat.grab(
                    &w,
                    gdk::SeatCapabilities::ALL,
                    true,
                    cursor.as_ref(),
                    None,
                    None,
                ) != gdk::GrabStatus::Success
                {
                    overlay.close();
                    self.capturing.set(false);
                    self.window.present();
                    self.status
                        .set_text("Another screen picker is active. Try again after closing it.");
                } else {
                    overlay.connect_destroy(move |_| seat.ungrab());
                }
            }
        }
    }
}
fn is_wayland() -> bool {
    std::env::var("XDG_SESSION_TYPE").unwrap_or_default() == "wayland"
        || gdk::Display::default().is_some_and(|d| d.type_().name().contains("Wayland"))
}

fn main() {
    if std::env::args().any(|a| a == "--help") {
        println!("Axentra SnippingTool\n  --record                Record a region; invoke again to stop\n  --stop                  Stop recording\n  --capture               Start a snip immediately\n  --mode rect|free|window|full\n  --delay 0|1|2|3|4|5|10\n  --open FILE             Open an image for editing\nKeyboard: Ctrl+N new, Ctrl+O open, Ctrl+S save, Ctrl+C copy, Ctrl+Z undo, Ctrl+Shift+Z redo, Esc cancel selection");
        return;
    }
    let app = gtk::Application::new(
        Some("io.github.mecmwithshawn.SnippingTool"),
        gio::ApplicationFlags::HANDLES_COMMAND_LINE,
    );
    let ui = Rc::new(RefCell::new(None::<Rc<Ui>>));
    let holder = ui.clone();
    app.connect_command_line(move |app, line| {
        if holder.borrow().is_none() {
            let css = gtk::CssProvider::new();
            let _ = css.load_from_data(include_bytes!("style.css"));
            if let Some(screen) = gdk::Screen::default() {
                gtk::StyleContext::add_provider_for_screen(
                    &screen,
                    &css,
                    gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
                );
            }
            if let Some(s) = gtk::Settings::default() {
                s.set_gtk_application_prefer_dark_theme(true);
            }
            *holder.borrow_mut() = Some(Ui::new(app));
        }
        let u = holder.borrow().as_ref().unwrap().clone();
        u.window.present();
        let args = line.arguments();
        let mut capture = false;
        let mut iter = args.iter().skip(1);
        while let Some(arg) = iter.next() {
            match arg.to_string_lossy().as_ref() {
                "--capture" => {
                    u.record_mode.set_active(false);
                    capture = true;
                }
                "--record" => {
                    if u.recording.borrow().is_some() {
                        u.stop_recording();
                        return 0;
                    }
                    u.record_mode.set_active(true);
                    capture = true;
                }
                "--stop" => {
                    u.stop_recording();
                    return 0;
                }
                "--mode" => {
                    if let Some(v) = iter.next() {
                        if !u.mode.set_active_id(Some(&v.to_string_lossy())) {
                            eprint!("Invalid capture mode\n");
                            return 1;
                        }
                    }
                }
                "--delay" => {
                    if let Some(v) = iter.next() {
                        if !u.delay.set_active_id(Some(&v.to_string_lossy())) {
                            eprint!("Delay must be 0–5 or 10\n");
                            return 1;
                        }
                    }
                }
                "--open" => {
                    if let Some(p) = iter.next() {
                        if u.replace_ok() {
                            match load_image(&PathBuf::from(p)) {
                                Ok(p) => u.set_image(p, false),
                                Err(e) => u.status.set_text(&e),
                            }
                        }
                    }
                }
                _ => {
                    eprint!("Unknown option; use --help\n");
                    return 1;
                }
            }
        }
        if capture {
            u.start_capture()
        }
        0
    });
    let shutdown_ui = ui.clone();
    app.connect_shutdown(move |_| {
        if let Some(u) = shutdown_ui.borrow().as_ref() {
            u.recording.borrow_mut().take();
            u.portal_session.borrow_mut().take();
            u.clip.borrow_mut().take();
            u.shares.borrow_mut().clear();
        }
    });
    app.run();
}
