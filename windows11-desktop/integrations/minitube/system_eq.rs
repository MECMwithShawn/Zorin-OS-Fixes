//! Shared system EQ controls; the desktop helper owns presets, persistence and DSP.
use gtk::prelude::*;
use serde::Deserialize;
use std::{
    cell::Cell,
    io::Read,
    os::fd::AsRawFd,
    path::PathBuf,
    process::{Command, Stdio},
    rc::Rc,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    time::Duration,
};

#[derive(Deserialize)]
struct Preset {
    id: String,
    name: String,
}
#[derive(Deserialize, Default, Clone)]
struct Meter {
    levels: Vec<f64>,
    available: bool,
}

fn runtime() -> PathBuf {
    std::env::var_os("ZORIN11_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| glib::home_dir().join(".local/share/zorin11-hub"))
}
fn selection() -> String {
    let path = glib::user_config_dir().join("zorin11-hub/audio-effects.json");
    std::fs::read(path)
        .ok()
        .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())
        .and_then(|v| v["preset"].as_str().map(str::to_owned))
        .unwrap_or_else(|| "off".into())
}
fn stop_reader(mut child: std::process::Child) {
    // Let Python release its playback-monitor child before forceful fallback.
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
    for _ in 0..50 {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    let _ = child.wait();
}
fn reader(meter: Arc<Mutex<Meter>>, visible: Arc<AtomicBool>, stop: Arc<AtomicBool>) {
    let mut child: Option<std::process::Child> = None;
    let mut bytes = Vec::new();
    while !stop.load(Ordering::Relaxed) {
        if !visible.load(Ordering::Relaxed) {
            if let Some(c) = child.take() {
                stop_reader(c);
            }
            if let Ok(mut m) = meter.lock() {
                *m = Meter::default();
            }
            bytes.clear();
        } else if child.is_none() {
            child = Command::new("/usr/bin/python3")
                .arg(runtime().join("audio_spectrum.py"))
                .arg("--stream")
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .spawn()
                .ok();
            let nonblocking =
                child
                    .as_ref()
                    .and_then(|c| c.stdout.as_ref())
                    .is_some_and(|out| unsafe {
                        let fd = out.as_raw_fd();
                        let flags = libc::fcntl(fd, libc::F_GETFL);
                        flags >= 0 && libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) == 0
                    });
            if !nonblocking {
                if let Some(c) = child.take() {
                    stop_reader(c);
                }
            }
        }
        if let Some(c) = child.as_mut() {
            let mut buffer = [0u8; 8192];
            if let Some(out) = c.stdout.as_mut() {
                if let Ok(n) = out.read(&mut buffer) {
                    bytes.extend_from_slice(&buffer[..n]);
                }
            }
            while let Some(end) = bytes.iter().position(|b| *b == b'\n') {
                let line: Vec<_> = bytes.drain(..=end).collect();
                if let Ok(value) = serde_json::from_slice::<Meter>(&line) {
                    if let Ok(mut m) = meter.lock() {
                        *m = value;
                    }
                }
            }
            if bytes.len() > 32768 {
                bytes.clear();
            }
            if c.try_wait().ok().flatten().is_some() {
                child = None;
                bytes.clear();
                if let Ok(mut m) = meter.lock() {
                    *m = Meter::default();
                }
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    if let Some(c) = child {
        stop_reader(c);
    }
}

pub fn widget() -> gtk::Box {
    let panel = gtk::Box::new(gtk::Orientation::Vertical, 6);
    panel.set_widget_name("system-eq-panel");
    panel.set_margin_start(18);
    panel.set_margin_end(18);
    panel.set_margin_top(8);
    panel.set_margin_bottom(8);
    let row = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let label = gtk::Label::new(Some("System EQ"));
    label.set_xalign(0.);
    row.pack_start(&label, false, false, 0);
    let choice = gtk::ComboBoxText::new();
    choice.set_widget_name("system-eq-preset");
    if let Some(accessible) = choice.accessible() {
        accessible.set_name("System EQ preset");
    }
    choice.set_tooltip_text(Some(
        "Changes the shared playback EQ in system Sound settings",
    ));
    let presets: Vec<Preset> = std::fs::read(runtime().join("audio-presets.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default();
    for preset in &presets {
        choice.append(Some(&preset.id), &preset.name);
    }
    let installed = runtime().join("audio_effects.py").is_file() && !presets.is_empty();
    choice.set_sensitive(installed);
    choice.set_active_id(Some(&selection()));
    row.pack_start(&choice, true, true, 0);
    let settings = gtk::Button::with_label("⋯");
    settings.set_tooltip_text(Some("Open system Sound settings"));
    settings.connect_clicked(|_| {
        let _ = Command::new("/usr/bin/python3")
            .arg(runtime().join("app.py"))
            .args(["--settings", "sound"])
            .spawn();
    });
    row.pack_end(&settings, false, false, 0);
    panel.pack_start(&row, false, false, 0);
    let canvas = gtk::DrawingArea::new();
    canvas.set_size_request(240, 62);
    canvas.set_widget_name("system-eq-spectrum");
    panel.pack_start(&canvas, false, false, 0);
    let caption = gtk::Label::new(Some(if installed {
        "Waiting for playback"
    } else {
        "Install the desktop audio enhancements to use System EQ"
    }));
    caption.set_line_wrap(true);
    caption.set_xalign(0.);
    panel.pack_start(&caption, false, false, 0);
    let busy = Rc::new(Cell::new(false));
    let syncing = Rc::new(Cell::new(false));
    let (tx, rx) = mpsc::channel::<Result<(), String>>();
    let b = busy.clone();
    let s = syncing.clone();
    let text = caption.clone();
    choice.connect_changed(move |c| {
        if s.get() || b.get() {
            return;
        }
        let Some(id) = c.active_id() else { return };
        b.set(true);
        c.set_sensitive(false);
        text.set_text("Applying system EQ…");
        let tx = tx.clone();
        let id = id.to_string();
        std::thread::spawn(move || {
            let result = Command::new("/usr/bin/python3")
                .arg(runtime().join("audio_effects.py"))
                .args(["--set", &id])
                .output()
                .map_err(|e| e.to_string())
                .and_then(|o| {
                    if o.status.success() {
                        Ok(())
                    } else {
                        Err(String::from_utf8_lossy(&o.stderr).trim().to_owned())
                    }
                });
            let _ = tx.send(result);
        });
    });
    let meter = Arc::new(Mutex::new(Meter::default()));
    let visible = Arc::new(AtomicBool::new(false));
    let stop = Arc::new(AtomicBool::new(false));
    if installed {
        let m = meter.clone();
        let v = visible.clone();
        let q = stop.clone();
        std::thread::spawn(move || reader(m, v, q));
    }
    let m = meter.clone();
    canvas.connect_draw(move |area, c| {
        let state = m.lock().map(|s| s.clone()).unwrap_or_default();
        let width = area.allocated_width() as f64 / 16.;
        let height = area.allocated_height() as f64;
        for i in 0..16 {
            let value = state
                .levels
                .get(i)
                .copied()
                .filter(|v| v.is_finite())
                .unwrap_or(0.)
                .clamp(0., 1.);
            c.set_source_rgba(0.3, 0.5, 0.6, 0.15);
            c.rectangle(i as f64 * width, 0., width - 3., height);
            let _ = c.fill();
            c.set_source_rgb(0.38, 0.80, 1.);
            let h = (value * height).max(1.);
            c.rectangle(i as f64 * width, height - h, width - 3., h);
            let _ = c.fill();
        }
        glib::Propagation::Proceed
    });
    let weak = panel.downgrade();
    let stopped = stop.clone();
    panel.connect_destroy(move |_| stopped.store(true, Ordering::Relaxed));
    let last_error = Rc::new(std::cell::RefCell::new(None::<String>));
    glib::timeout_add_local(Duration::from_millis(100), move || {
        let Some(panel) = weak.upgrade() else {
            stop.store(true, Ordering::Relaxed);
            return glib::ControlFlow::Break;
        };
        let shown = panel.is_mapped()
            && panel
                .window()
                .is_some_and(|w| !w.state().contains(gtk::gdk::WindowState::ICONIFIED));
        visible.store(shown, Ordering::Relaxed);
        if let Ok(result) = rx.try_recv() {
            busy.set(false);
            *last_error.borrow_mut() = result.err();
        }
        if !busy.get() {
            syncing.set(true);
            choice.set_active_id(Some(&selection()));
            syncing.set(false);
            choice.set_sensitive(installed);
            let connected = meter.lock().map(|m| m.available).unwrap_or(false);
            let text = last_error.borrow();
            caption.set_text(text.as_deref().unwrap_or(if !installed {
                "System EQ is not installed"
            } else if connected {
                "Bass                         Live playback                         Treble"
            } else {
                "Waiting for output"
            }));
        }
        if shown {
            canvas.queue_draw();
        }
        glib::ControlFlow::Continue
    });
    panel
}
