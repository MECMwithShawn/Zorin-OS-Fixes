//! Permission-mediated Wayland recording. No compositor bypass or persistent grant.
use crate::{extras::PrivateDir, recording::Recording, Ui};
use gio::prelude::*;
use glib::variant::{ObjectPath, ToVariant};
use gtk::prelude::*;
use std::{
    cell::RefCell,
    collections::HashMap,
    os::{fd::AsRawFd, unix::process::CommandExt},
    process::Command,
    rc::Rc,
    time::Duration,
};
const DEST: &str = "org.freedesktop.portal.Desktop";
const ROOT: &str = "/org/freedesktop/portal/desktop";
const IFACE: &str = "org.freedesktop.portal.ScreenCast";
type Values = HashMap<String, glib::Variant>;
pub struct Session {
    bus: gio::DBusConnection,
    path: String,
    watch: Option<gio::SignalSubscriptionId>,
}
impl Drop for Session {
    fn drop(&mut self) {
        if let Some(watch) = self.watch.take() {
            self.bus.signal_unsubscribe(watch);
        }
        self.bus.call(
            Some(DEST),
            &self.path,
            "org.freedesktop.portal.Session",
            "Close",
            None,
            None,
            gio::DBusCallFlags::NONE,
            2000,
            gio::Cancellable::NONE,
            |_| {},
        );
    }
}
fn request(
    ui: Rc<Ui>,
    bus: &gio::DBusConnection,
    method: &str,
    params: impl FnOnce(String) -> glib::Variant,
    done: impl FnOnce(Result<Values, String>) + 'static,
) {
    let token = format!("snip_{}", glib::uuid_string_random().replace('-', "_"));
    let sender = bus
        .unique_name()
        .unwrap()
        .trim_start_matches(':')
        .replace('.', "_");
    let path = format!("{ROOT}/request/{sender}/{token}");
    *ui.pending_portal.borrow_mut() = Some((bus.clone(), path.clone()));
    let cb = Rc::new(RefCell::new(Some(done)));
    let c = cb.clone();
    let watch = Rc::new(RefCell::new(None));
    let w = watch.clone();
    let u = ui.clone();
    let active_path = path.clone();
    *watch.borrow_mut() = Some(bus.signal_subscribe(
        Some(DEST),
        Some("org.freedesktop.portal.Request"),
        Some("Response"),
        Some(&path),
        None,
        gio::DBusSignalFlags::NONE,
        move |bus, _, _, _, _, p| {
            if let Some(id) = w.borrow_mut().take() {
                bus.signal_unsubscribe(id);
            }
            if u.pending_portal
                .borrow()
                .as_ref()
                .is_some_and(|(_, p)| p == &active_path)
            {
                u.pending_portal.borrow_mut().take();
            }
            if let Some(f) = c.borrow_mut().take() {
                f(p.get::<(u32, Values)>()
                    .ok_or("Invalid screen-sharing response".into())
                    .and_then(|(code, v)| {
                        if code == 0 {
                            Ok(v)
                        } else {
                            Err("Recording cancelled.".into())
                        }
                    }));
            }
        },
    ));
    let p = params(token);
    let fail_watch = watch.clone();
    let fail_cb = cb.clone();
    let fail_bus = bus.clone();
    let fail_ui = ui.clone();
    let failure_path = path.clone();
    bus.call(
        Some(DEST),
        ROOT,
        IFACE,
        method,
        Some(&p),
        None,
        gio::DBusCallFlags::NONE,
        5000,
        gio::Cancellable::NONE,
        move |result| {
            if let Err(e) = result {
                if let Some(id) = fail_watch.borrow_mut().take() {
                    fail_bus.signal_unsubscribe(id);
                }
                if fail_ui
                    .pending_portal
                    .borrow()
                    .as_ref()
                    .is_some_and(|(_, p)| p == &failure_path)
                {
                    fail_ui.pending_portal.borrow_mut().take();
                }
                if let Some(f) = fail_cb.borrow_mut().take() {
                    f(Err(e.to_string()));
                }
            }
        },
    );
    let bus = bus.clone();
    glib::timeout_add_local_once(Duration::from_secs(120), move || {
        if let Some(id) = watch.borrow_mut().take() {
            bus.signal_unsubscribe(id);
            let _ = bus.call_sync(
                Some(DEST),
                &path,
                "org.freedesktop.portal.Request",
                "Close",
                None,
                None,
                gio::DBusCallFlags::NONE,
                2000,
                gio::Cancellable::NONE,
            );
            if ui
                .pending_portal
                .borrow()
                .as_ref()
                .is_some_and(|(_, p)| p == &path)
            {
                ui.pending_portal.borrow_mut().take();
            }
        }
        if let Some(f) = cb.borrow_mut().take() {
            f(Err("Screen sharing timed out.".into()));
        }
    });
}
fn fail(u: &Ui, e: &str) {
    u.capturing.set(false);
    u.cancel.hide();
    u.portal_session.borrow_mut().take();
    u.window.present();
    u.status.set_text(e);
}
pub fn start(u: Rc<Ui>) {
    let bus = match gio::bus_get_sync(gio::BusType::Session, gio::Cancellable::NONE) {
        Ok(b) => b,
        Err(e) => {
            fail(&u, &e.to_string());
            return;
        }
    };
    let d = gtk::Dialog::with_buttons(
        Some("Record a screen or window"),
        Some(&u.window),
        gtk::DialogFlags::MODAL,
        &[
            ("Cancel", gtk::ResponseType::Cancel),
            ("Choose screen", gtk::ResponseType::Accept),
        ],
    );
    let note=gtk::Label::new(Some("Choose the source in the desktop permission dialog.\nRecording starts after approval. Use Win+Shift+R to stop."));
    d.content_area().pack_start(&note, false, false, 12);
    let audio = gtk::CheckButton::with_label("Include playback audio");
    let mic = gtk::CheckButton::with_label("Include microphone");
    d.content_area().pack_start(&audio, false, false, 8);
    d.content_area().pack_start(&mic, false, false, 8);
    d.show_all();
    let accept = d.run() == gtk::ResponseType::Accept;
    let audio = audio.is_active();
    let mic = mic.is_active();
    d.close();
    if !accept {
        fail(&u, "Recording cancelled.");
        return;
    }
    u.capturing.set(true);
    u.cancel.show();
    let gen = u.generation.get();
    let u2 = u.clone();
    let b = bus.clone();
    request(
        u.clone(),
        &bus,
        "CreateSession",
        move |token| {
            let opts = Values::from([
                ("handle_token".into(), token.to_variant()),
                (
                    "session_handle_token".into(),
                    format!("session_{}", glib::uuid_string_random().replace('-', "_"))
                        .to_variant(),
                ),
            ]);
            (opts,).to_variant()
        },
        move |result| {
            let value = match result {
                Ok(v) => v,
                Err(e) => {
                    if u2.generation.get() == gen {
                        fail(&u2, &e);
                    }
                    return;
                }
            };
            let Some(path) = value.get("session_handle").and_then(|v| v.get::<String>()) else {
                fail(&u2, "No recording session returned.");
                return;
            };
            let weak = Rc::downgrade(&u2);
            let watch = b.signal_subscribe(
                Some(DEST),
                Some("org.freedesktop.portal.Session"),
                Some("Closed"),
                Some(&path),
                None,
                gio::DBusSignalFlags::NONE,
                move |_, _, _, _, _, _| {
                    if let Some(u) = weak.upgrade() {
                        if u.recording.borrow().is_some() {
                            u.stop_recording();
                        } else if u.capturing.get() {
                            u.generation.set(u.generation.get() + 1);
                            fail(&u, "Screen sharing ended.");
                        }
                    }
                },
            );
            let session = Session {
                bus: b.clone(),
                path: path.clone(),
                watch: Some(watch),
            };
            if u2.generation.get() != gen {
                return;
            }
            *u2.portal_session.borrow_mut() = Some(session);
            let object = ObjectPath::try_from(path.clone()).unwrap();
            let u3 = u2.clone();
            let b2 = b.clone();
            request(
                u2,
                &b,
                "SelectSources",
                move |token| {
                    (
                        object,
                        Values::from([
                            ("handle_token".into(), token.to_variant()),
                            ("types".into(), 3u32.to_variant()),
                            ("multiple".into(), false.to_variant()),
                            ("cursor_mode".into(), 2u32.to_variant()),
                        ]),
                    )
                        .to_variant()
                },
                move |r| {
                    if u3.generation.get() != gen {
                        return;
                    }
                    if let Err(e) = r {
                        fail(&u3, &e);
                        return;
                    }
                    if u3.generation.get() != gen {
                        return;
                    }
                    let object = ObjectPath::try_from(path.clone()).unwrap();
                    let u4 = u3.clone();
                    let b3 = b2.clone();
                    request(
                        u3,
                        &b2,
                        "Start",
                        move |token| {
                            (
                                object,
                                "",
                                Values::from([("handle_token".into(), token.to_variant())]),
                            )
                                .to_variant()
                        },
                        move |r| {
                            if u4.generation.get() != gen {
                                return;
                            }
                            let node = match r.and_then(|v| {
                                v.get("streams")
                                    .and_then(|s| s.get::<Vec<(u32, Values)>>())
                                    .and_then(|streams| streams.first().map(|s| s.0))
                                    .ok_or("No screen selected".into())
                            }) {
                                Ok(n) => n,
                                Err(e) => {
                                    fail(&u4, &e);
                                    return;
                                }
                            };
                            b3.call_with_unix_fd_list(
                                Some(DEST),
                                ROOT,
                                IFACE,
                                "OpenPipeWireRemote",
                                Some(
                                    &(ObjectPath::try_from(path).unwrap(), Values::new())
                                        .to_variant(),
                                ),
                                None,
                                gio::DBusCallFlags::NONE,
                                5000,
                                None::<&gio::UnixFDList>,
                                gio::Cancellable::NONE,
                                move |result| {
                                    if u4.generation.get() != gen {
                                        return;
                                    }
                                    let result = result.map_err(|e| e.to_string()).and_then(
                                        |(reply, fds)| launch(reply, fds, node, audio, mic),
                                    );

                                    u4.capturing.set(false);
                                    u4.cancel.hide();
                                    match result {
                                        Ok(rec) => u4.record_started(rec),
                                        Err(e) => fail(&u4, &e),
                                    }
                                },
                            );
                        },
                    );
                },
            );
        },
    );
}

fn launch(
    reply: glib::Variant,
    fds: gio::UnixFDList,
    node: u32,
    audio: bool,
    mic: bool,
) -> Result<Recording, String> {
    let handle = reply
        .child_value(0)
        .get::<glib::variant::Handle>()
        .ok_or("No screen file descriptor")?;
    let fd = fds.get(handle.0).map_err(|e| e.to_string())?;
    let dir = PrivateDir::new()?;
    let path = dir.0.join("Recording.webm");
    let mut command = Command::new("gst-launch-1.0");
    command
        .args(["-e", "-q", "pipewiresrc"])
        .arg(format!("fd={}", fd.as_raw_fd()))
        .arg(format!("path={node}"))
        .args([
            "do-timestamp=true",
            "!",
            "queue",
            "!",
            "videoconvert",
            "!",
            "videorate",
            "!",
            "video/x-raw,framerate=30/1",
            "!",
            "vp8enc",
            "deadline=1",
            "cpu-used=8",
            "!",
            "queue",
            "!",
            "mux.",
            "webmmux",
            "name=mux",
            "!",
            "filesink",
        ])
        .arg(format!("location={}", path.display()));
    let mut sources = vec![];
    if audio {
        let o = Command::new("pactl")
            .arg("get-default-sink")
            .output()
            .map_err(|e| e.to_string())?;
        let sink = String::from_utf8_lossy(&o.stdout).trim().to_string();
        if !o.status.success() || sink.is_empty() {
            return Err("No playback output available".into());
        }
        sources.push(format!("{sink}.monitor"));
    }
    if mic {
        sources.push("@DEFAULT_SOURCE@".into());
    }
    if !sources.is_empty() {
        command.args([
            "audiomixer",
            "name=mix",
            "!",
            "audioconvert",
            "!",
            "opusenc",
            "!",
            "queue",
            "!",
            "mux.",
        ]);
        for s in sources {
            command.args(["pulsesrc"]).arg(format!("device={s}")).args([
                "!",
                "queue",
                "!",
                "audioconvert",
                "!",
                "audioresample",
                "!",
                "mix.",
            ]);
        }
    }
    let raw = fd.as_raw_fd();
    unsafe {
        command.pre_exec(move || {
            if libc::fcntl(raw, libc::F_SETFD, 0) < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    Recording::spawn(command, dir, path)
}
