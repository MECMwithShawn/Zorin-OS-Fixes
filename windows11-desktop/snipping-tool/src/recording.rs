use crate::{capture::Rect, extras::PrivateDir};
use std::{
    os::unix::{fs::PermissionsExt, process::CommandExt},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

pub struct Clip {
    pub path: PathBuf,
    pub _dir: PrivateDir,
    pub saved: bool,
}
pub struct Recording {
    child: Option<Child>,
    dir: Option<PrivateDir>,
    path: PathBuf,
    pub started: Instant,
}
impl Recording {
    pub fn x11(rect: Rect, output: bool, mic: bool) -> Result<Self, String> {
        let dir = PrivateDir::new()?;
        let path = dir.0.join("Recording.mp4");
        let mut c = Command::new("ffmpeg");
        c.args([
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "x11grab",
            "-framerate",
            "30",
            "-draw_mouse",
            "1",
            "-video_size",
        ])
        .arg(format!("{}x{}", rect.w, rect.h))
        .arg("-i")
        .arg(format!(
            "{}+{},{}",
            std::env::var("DISPLAY").unwrap_or_else(|_| ":0".into()),
            rect.x,
            rect.y
        ));
        let mut audio = 0;
        if output {
            let o = Command::new("pactl")
                .arg("get-default-sink")
                .output()
                .map_err(|e| e.to_string())?;
            if !o.status.success() {
                return Err("Could not find the playback output.".into());
            }
            let sink = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if sink.is_empty() {
                return Err("No playback output is available.".into());
            }
            c.args(["-thread_queue_size", "512", "-f", "pulse", "-i"])
                .arg(format!("{sink}.monitor"));
            audio += 1;
        }
        if mic {
            c.args(["-thread_queue_size", "512", "-f", "pulse", "-i", "default"]);
            audio += 1;
        }
        c.args([
            "-map",
            "0:v",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
        ]);
        if audio == 2 {
            c.args([
                "-filter_complex",
                "[1:a][2:a]amix=inputs=2:normalize=1[a]",
                "-map",
                "[a]",
            ]);
        } else if audio == 1 {
            c.args(["-map", "1:a"]);
        } else {
            c.arg("-an");
        }
        if audio > 0 {
            c.args(["-c:a", "aac", "-b:a", "192k"]);
        }
        c.args(["-movflags", "+faststart", "-t", "7200"]).arg(&path);
        Self::spawn(c, dir, path)
    }
    pub fn spawn(mut c: Command, dir: PrivateDir, path: PathBuf) -> Result<Self, String> {
        let log = std::fs::File::create(dir.0.join("recorder.log")).map_err(|e| e.to_string())?;
        // Stop capture if the parent exits unexpectedly; do not leave a recorder behind.
        unsafe {
            c.pre_exec(|| {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGINT) < 0 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let child = c
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(log)
            .spawn()
            .map_err(|e| format!("Could not start recording: {e}"))?;
        Ok(Self {
            child: Some(child),
            dir: Some(dir),
            path,
            started: Instant::now(),
        })
    }
    pub fn exited(&mut self) -> bool {
        self.child
            .as_mut()
            .and_then(|c| c.try_wait().ok().flatten())
            .is_some()
    }
    pub fn stop(mut self) -> Result<Clip, String> {
        let mut c = self.child.take().ok_or("No recorder")?;
        if c.try_wait().map_err(|e| e.to_string())?.is_none() {
            unsafe {
                libc::kill(c.id() as i32, libc::SIGINT);
            }
        }
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            if let Some(s) = c.try_wait().map_err(|e| e.to_string())? {
                if !s.success() && s.code() != Some(255) {
                    return Err("Recording failed. Check that the selected display and audio devices are available.".into());
                }
                break;
            }
            if Instant::now() > deadline {
                let _ = c.kill();
                let _ = c.wait();
                return Err("Recording could not finish within 15 seconds.".into());
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        if std::fs::metadata(&self.path).map(|m| m.len()).unwrap_or(0) < 100 {
            return Err("No video frames were recorded.".into());
        }
        std::fs::set_permissions(&self.path, std::fs::Permissions::from_mode(0o600))
            .map_err(|e| e.to_string())?;
        Ok(Clip {
            path: self.path.clone(),
            _dir: self.dir.take().unwrap(),
            saved: false,
        })
    }
}
impl Drop for Recording {
    fn drop(&mut self) {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
}
pub fn save_clip(from: &Path, to: &Path) -> Result<(), String> {
    let temp = to.with_file_name(format!(".axentra-{}.tmp", glib::uuid_string_random()));
    let result = (|| {
        let mut source = std::fs::File::open(from)?;
        let mut out = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        out.set_permissions(std::fs::Permissions::from_mode(0o600))?;
        std::io::copy(&mut source, &mut out)?;
        out.sync_all()?;
        std::fs::rename(&temp, to)
    })()
    .map_err(|e: std::io::Error| e.to_string());
    if result.is_err() {
        let _ = std::fs::remove_file(temp);
    }
    result
}
