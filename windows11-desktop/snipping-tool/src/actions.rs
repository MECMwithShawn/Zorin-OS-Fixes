use crate::{
    extras::{Preferences, PrivateDir},
    recording, Ui,
};
use gtk::prelude::*;
use std::{cell::Cell, rc::Rc, time::Duration};
impl Ui {
    pub fn preferences(&self) {
        let d = gtk::Dialog::with_buttons(
            Some("SnippingTool settings"),
            Some(&self.window),
            gtk::DialogFlags::MODAL,
            &[
                ("Cancel", gtk::ResponseType::Cancel),
                ("Save settings", gtk::ResponseType::Accept),
            ],
        );
        let p = self.prefs.borrow().clone();
        let save = gtk::CheckButton::with_label("Automatically save new screenshots");
        save.set_active(p.autosave);
        let copy = gtk::CheckButton::with_label("Automatically copy new screenshots");
        copy.set_active(p.autocopy);
        let folder =
            gtk::FileChooserButton::new("Screenshots folder", gtk::FileChooserAction::SelectFolder);
        folder.set_filename(&p.folder);
        let note=gtk::Label::new(Some("Auto-save retains the original capture. Edits and redactions require Save as.\nRecordings are saved only when you choose Save as."));
        note.set_line_wrap(true);
        let area = d.content_area();
        area.set_margin_start(18);
        area.set_margin_end(18);
        area.set_spacing(14);
        area.pack_start(&save, false, false, 0);
        area.pack_start(&copy, false, false, 0);
        area.pack_start(&folder, false, false, 0);
        area.pack_start(&note, false, false, 10);
        d.show_all();
        if d.run() == gtk::ResponseType::Accept {
            let next = Preferences {
                autosave: save.is_active(),
                autocopy: copy.is_active(),
                folder: folder.filename().unwrap_or(p.folder),
            };
            match next.save() {
                Ok(()) => {
                    *self.prefs.borrow_mut() = next;
                    self.status.set_text("Capture settings saved.");
                }
                Err(e) => self.status.set_text(&e),
            }
        }
        d.close();
    }
    pub fn capture_ready(&self, p: gdk_pixbuf::Pixbuf) {
        self.clip.borrow_mut().take();
        self.record_mode.set_active(false);
        self.set_image(p.clone(), true);
        let prefs = self.prefs.borrow().clone();
        if prefs.autocopy {
            self.copy();
        }
        if prefs.autosave {
            match prefs.save_capture(&p) {
                Ok(path) => {
                    if let Some(d) = self.doc.borrow_mut().as_mut() {
                        d.dirty = false;
                    }
                    self.refresh();
                    self.status
                        .set_text(&format!("Saved original to {}", path.display()));
                }
                Err(e) => self
                    .status
                    .set_text(&format!("Auto-save failed: {e}. Use Save as.")),
            }
        }
    }
    pub fn text_actions(self: &Rc<Self>) {
        let png = match self
            .doc
            .borrow()
            .as_ref()
            .and_then(|d| d.render().ok())
            .and_then(|p| p.save_to_bufferv("png", &[]).ok())
        {
            Some(p) => p,
            None => return,
        };
        let progress = gtk::Dialog::with_buttons(
            Some("Recognizing text locally…"),
            Some(&self.window),
            gtk::DialogFlags::MODAL,
            &[("Cancel", gtk::ResponseType::Cancel)],
        );
        let label = gtk::Label::new(Some("Reading text on this device. No image is uploaded."));
        progress.content_area().pack_start(&label, true, true, 20);
        progress.show_all();
        let cancelled = Rc::new(Cell::new(false));
        let c = cancelled.clone();
        progress.connect_response(move |d, _| {
            c.set(true);
            // Destroy synchronously so a modal progress window cannot reappear.
            unsafe {
                d.destroy();
            }
        });
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let _ = tx.send(crate::extras::recognize(png));
        });
        let u = self.clone();
        glib::timeout_add_local(Duration::from_millis(100), move || {
            if cancelled.get() {
                return glib::ControlFlow::Break;
            }
            match rx.try_recv() {
                Ok(result) => {
                    unsafe {
                        progress.destroy();
                    }
                    match result {
                        Ok(text) => u.show_text(text),
                        Err(e) => u.status.set_text(&e),
                    }
                    glib::ControlFlow::Break
                }
                Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                    unsafe {
                        progress.destroy();
                    }
                    u.status.set_text("Text recognition stopped unexpectedly.");
                    glib::ControlFlow::Break
                }
                _ => glib::ControlFlow::Continue,
            }
        });
    }
    fn show_text(&self, ocr: crate::extras::Ocr) {
        let d = gtk::Dialog::with_buttons(
            Some("Text actions"),
            Some(&self.window),
            gtk::DialogFlags::MODAL,
            &[
                ("Close", gtk::ResponseType::Close),
                ("Copy selected", gtk::ResponseType::Other(1)),
                ("Copy all text", gtk::ResponseType::Other(2)),
                ("Quick redact", gtk::ResponseType::Other(3)),
            ],
        );
        d.set_default_size(700, 430);
        let view = gtk::TextView::new();
        view.set_editable(false);
        view.set_wrap_mode(gtk::WrapMode::Word);
        let buffer = view.buffer().unwrap();
        buffer.set_text(&ocr.text);
        let scroll = gtk::ScrolledWindow::new(gtk::Adjustment::NONE, gtk::Adjustment::NONE);
        scroll.add(&view);
        d.content_area().pack_start(&scroll, true, true, 8);
        let note=gtk::Label::new(Some("Quick redact covers detected email addresses and phone numbers. Review for missed text.\nThe original auto-saved capture is retained; Save as exports your redacted image."));
        note.set_line_wrap(true);
        d.content_area().pack_start(&note, false, false, 8);
        d.show_all();
        loop {
            match d.run() {
                gtk::ResponseType::Other(1) => {
                    if let Some((a, b)) = buffer.selection_bounds() {
                        if let Some(t) = buffer.text(&a, &b, false) {
                            gtk::Clipboard::get(&gdk::SELECTION_CLIPBOARD).set_text(&t);
                        }
                    }
                }
                gtk::ResponseType::Other(2) => {
                    gtk::Clipboard::get(&gdk::SELECTION_CLIPBOARD).set_text(&ocr.text)
                }
                gtk::ResponseType::Other(3) => {
                    let boxes = ocr.private_boxes();
                    if boxes.is_empty() {
                        note.set_text("No email addresses or phone numbers detected. Use Redact to cover text manually.");
                        continue;
                    }
                    let result = self.doc.borrow_mut().as_mut().map(|doc| doc.redact(&boxes));
                    self.refresh();
                    if let Some(Err(e)) = result {
                        self.status.set_text(&e);
                    } else {
                        self.copy();
                        self.status.set_text(
                            "Detected private text covered. Review the result, then Save as.",
                        );
                    }
                    break;
                }
                _ => break,
            }
        }
        d.close();
    }
    pub fn print_image(&self) {
        let Some(Ok(p)) = self.doc.borrow().as_ref().map(|d| d.render()) else {
            return;
        };
        let op = gtk::PrintOperation::new();
        op.set_n_pages(1);
        op.set_job_name("Axentra SnippingTool image");
        op.connect_draw_page(move |_, context, _| {
            let Some(c) = context.cairo_context() else {
                return;
            };
            let scale =
                (context.width() / p.width() as f64).min(context.height() / p.height() as f64);
            c.scale(scale, scale);
            c.set_source_pixbuf(&p, 0., 0.);
            let _ = c.paint();
        });
        if let Err(e) = op.run(gtk::PrintOperationAction::PrintDialog, Some(&self.window)) {
            self.status.set_text(&e.to_string());
        }
    }
    pub fn share(&self) {
        let path = if let Some(c) = self.clip.borrow().as_ref() {
            c.path.clone()
        } else {
            let Some(Ok(p)) = self.doc.borrow().as_ref().map(|d| d.render()) else {
                return;
            };
            let dir = match PrivateDir::new() {
                Ok(d) => d,
                Err(e) => {
                    self.status.set_text(&e);
                    return;
                }
            };
            let path = match crate::extras::export_temp(&p, &dir) {
                Ok(p) => p,
                Err(e) => {
                    self.status.set_text(&e);
                    return;
                }
            };
            self.shares.borrow_mut().push(dir);
            path
        };
        let file = gio::File::for_path(&path);
        let chooser =
            gtk::AppChooserDialog::new(Some(&self.window), gtk::DialogFlags::MODAL, &file);
        chooser.set_heading("Open this snip in an app to share or edit");
        if chooser.run() == gtk::ResponseType::Ok {
            if let Some(app) = chooser.app_info() {
                if let Err(e) = app.launch(&[file], gio::AppLaunchContext::NONE) {
                    self.status.set_text(&e.to_string());
                }
            }
        }
        chooser.close();
    }
    pub fn record_area(self: &Rc<Self>, rect: crate::capture::Rect) {
        self.capturing.set(false);
        let d = gtk::Dialog::with_buttons(
            Some("Record selected area"),
            Some(&self.window),
            gtk::DialogFlags::MODAL,
            &[
                ("Cancel", gtk::ResponseType::Cancel),
                ("Start recording", gtk::ResponseType::Accept),
            ],
        );
        let area = d.content_area();
        let text = gtk::Label::new(Some(&format!(
            "{} × {} pixels · 30 fps\nRecording begins after a 3-second countdown.",
            rect.w, rect.h
        )));
        area.pack_start(&text, false, false, 12);
        let sound = gtk::CheckButton::with_label("Include playback audio");
        let mic = gtk::CheckButton::with_label("Include microphone");
        area.pack_start(&sound, false, false, 8);
        area.pack_start(&mic, false, false, 8);
        d.show_all();
        let accept = d.run() == gtk::ResponseType::Accept;
        let audio = sound.is_active();
        let microphone = mic.is_active();
        d.close();
        if !accept {
            self.window.present();
            return;
        }
        self.capturing.set(true);
        self.generation.set(self.generation.get() + 1);
        let gen = self.generation.get();
        self.window.present();
        self.cancel.show();
        self.status.set_text("Recording starts in 3 seconds…");
        let u = self.clone();
        glib::timeout_add_local_once(Duration::from_secs(3), move || {
            if u.generation.get() != gen {
                return;
            }
            u.cancel.hide();
            u.window.iconify();
            // Give the compositor time to remove the editor before the first frame.
            glib::timeout_add_local_once(Duration::from_millis(250), move || {
                if u.generation.get() != gen {
                    return;
                }
                u.capturing.set(false);
                match recording::Recording::x11(rect, audio, microphone) {
                    Ok(rec) => u.record_started(rec),
                    Err(e) => {
                        u.window.present();
                        u.status.set_text(&e);
                    }
                }
            });
        });
    }
    pub fn record_started(self: &Rc<Self>, rec: recording::Recording) {
        self.clip.borrow_mut().take();
        *self.recording.borrow_mut() = Some(rec);
        self.window.iconify();
        self.stop.show();
        let u = self.clone();
        glib::timeout_add_local(Duration::from_millis(250), move || {
            let mut recording = u.recording.borrow_mut();
            let Some(r) = recording.as_mut() else {
                return glib::ControlFlow::Break;
            };
            let elapsed = r.started.elapsed().as_secs();
            let ended = r.exited();
            u.status.set_text(&format!(
                "● Recording {:02}:{:02} · Ctrl+Shift+R to stop",
                elapsed / 60,
                elapsed % 60
            ));
            u.window.set_title(&format!(
                "● Recording {:02}:{:02} — Axentra SnippingTool",
                elapsed / 60,
                elapsed % 60
            ));
            drop(recording);
            if ended {
                u.stop_recording();
                return glib::ControlFlow::Break;
            }
            glib::ControlFlow::Continue
        });
    }
    pub fn stop_recording(self: &Rc<Self>) {
        let Some(rec) = self.recording.borrow_mut().take() else {
            return;
        };
        self.stop.hide();
        self.capturing.set(true);
        self.window.present();
        self.status.set_text("Finishing recording…");
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let _ = tx.send(rec.stop());
        });
        let u = self.clone();
        glib::timeout_add_local(Duration::from_millis(100), move || match rx.try_recv() {
            Ok(result) => {
                u.portal_session.borrow_mut().take();
                u.capturing.set(false);
                match result {
                    Ok(clip) => {
                        *u.clip.borrow_mut() = Some(clip);
                        u.doc.borrow_mut().take();
                        u.refresh();
                        u.save.set_sensitive(true);
                        u.play.show();
                        u.status.set_text("Recording ready. Play it, Save as, or open it in another app to edit/share.");
                    }
                    Err(e) => u.status.set_text(&e),
                }
                u.window.set_title("Axentra SnippingTool");
                glib::ControlFlow::Break
            }
            Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                u.capturing.set(false);
                u.status.set_text("Recorder stopped unexpectedly.");
                glib::ControlFlow::Break
            }
            _ => glib::ControlFlow::Continue,
        });
    }
    pub fn save_recording(&self) -> bool {
        let clip = self.clip.borrow();
        let Some(clip) = clip.as_ref() else {
            return false;
        };
        let ext = clip.path.extension().unwrap_or_default().to_string_lossy();
        let chooser = gtk::FileChooserDialog::new(
            Some("Save recording"),
            Some(&self.window),
            gtk::FileChooserAction::Save,
        );
        chooser.add_buttons(&[
            ("Cancel", gtk::ResponseType::Cancel),
            ("Save", gtk::ResponseType::Accept),
        ]);
        chooser.set_do_overwrite_confirmation(true);
        chooser.set_current_name(&format!(
            "Recording {}.{ext}",
            glib::DateTime::now_local()
                .and_then(|d| d.format("%Y-%m-%d %H-%M-%S"))
                .unwrap_or_default()
        ));
        let mut saved = false;
        if chooser.run() == gtk::ResponseType::Accept {
            if let Some(mut path) = chooser.filename() {
                if path.extension().is_none() {
                    path.set_extension(ext.as_ref());
                    if path.exists() {
                        let d = gtk::MessageDialog::new(
                            Some(&self.window),
                            gtk::DialogFlags::MODAL,
                            gtk::MessageType::Question,
                            gtk::ButtonsType::None,
                            &format!("Replace {}?", path.display()),
                        );
                        d.add_buttons(&[
                            ("Cancel", gtk::ResponseType::Cancel),
                            ("Replace", gtk::ResponseType::Accept),
                        ]);
                        let accept = d.run() == gtk::ResponseType::Accept;
                        d.close();
                        if !accept {
                            chooser.close();
                            return false;
                        }
                    }
                }
                if path
                    .extension()
                    .map(|e| e.to_string_lossy().eq_ignore_ascii_case(ext.as_ref()))
                    .unwrap_or(false)
                {
                    match recording::save_clip(&clip.path, &path) {
                        Ok(()) => {
                            saved = true;
                            self.status
                                .set_text(&format!("Saved to {}", path.display()));
                        }
                        Err(e) => self.status.set_text(&e),
                    }
                } else {
                    self.status
                        .set_text(&format!("Use a .{ext} filename for this recording."));
                }
            }
        }
        chooser.close();
        saved
    }
}
impl Ui {
    pub fn record_wayland(self: &Rc<Self>) {
        self.status
            .set_text("Select a screen or window in the desktop sharing dialog.");
        crate::portal_record::start(self.clone());
    }
}
