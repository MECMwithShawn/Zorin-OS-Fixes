use gdk_pixbuf::Pixbuf;
use gio::prelude::*;
use std::{
    io::Write,
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub struct PrivateDir(pub PathBuf);
impl PrivateDir {
    pub fn new() -> Result<Self, String> {
        let p = glib::user_cache_dir()
            .join("axentra-snipping")
            .join(glib::uuid_string_random().as_str());
        std::fs::create_dir_all(&p).map_err(|e| e.to_string())?;
        std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o700))
            .map_err(|e| e.to_string())?;
        Ok(Self(p))
    }
}
impl Drop for PrivateDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
#[derive(Clone)]
pub struct Preferences {
    pub autosave: bool,
    pub autocopy: bool,
    pub folder: PathBuf,
}
impl Preferences {
    fn path() -> PathBuf {
        glib::user_config_dir().join("axentra-snipping/settings.ini")
    }
    pub fn load() -> Self {
        let k = glib::KeyFile::new();
        let _ = k.load_from_file(Self::path(), glib::KeyFileFlags::NONE);
        Self {
            autosave: k.boolean("Capture", "autosave").unwrap_or(true),
            autocopy: k.boolean("Capture", "autocopy").unwrap_or(true),
            folder: k
                .string("Capture", "folder")
                .ok()
                .map(|p| PathBuf::from(p.as_str()))
                .filter(|p| p.is_absolute())
                .unwrap_or_else(|| {
                    glib::user_special_dir(glib::UserDirectory::Pictures)
                        .unwrap_or_else(glib::home_dir)
                        .join("Screenshots")
                }),
        }
    }
    pub fn save(&self) -> Result<(), String> {
        let p = Self::path();
        std::fs::create_dir_all(p.parent().unwrap()).map_err(|e| e.to_string())?;
        let k = glib::KeyFile::new();
        k.set_boolean("Capture", "autosave", self.autosave);
        k.set_boolean("Capture", "autocopy", self.autocopy);
        k.set_string("Capture", "folder", &self.folder.to_string_lossy());
        gio::File::for_path(p)
            .replace_contents(
                k.to_data().as_bytes(),
                None,
                false,
                gio::FileCreateFlags::PRIVATE | gio::FileCreateFlags::REPLACE_DESTINATION,
                gio::Cancellable::NONE,
            )
            .map(|_| ())
            .map_err(|e| e.to_string())
    }
    pub fn save_capture(&self, p: &Pixbuf) -> Result<PathBuf, String> {
        std::fs::create_dir_all(&self.folder).map_err(|e| e.to_string())?;
        let name = format!(
            "Screenshot {} {}.png",
            glib::DateTime::now_local()
                .and_then(|d| d.format("%Y-%m-%d %H-%M-%S"))
                .map(|s| s.to_string())
                .unwrap_or_default(),
            &glib::uuid_string_random()[..8]
        );
        let path = self.folder.join(name);
        let bytes = p.save_to_bufferv("png", &[]).map_err(|e| e.to_string())?;
        let f = gio::File::for_path(&path)
            .create(gio::FileCreateFlags::PRIVATE, gio::Cancellable::NONE)
            .map_err(|e| e.to_string())?;
        f.write_all(&bytes, gio::Cancellable::NONE)
            .map_err(|e| e.to_string())?;
        f.close(gio::Cancellable::NONE).map_err(|e| e.to_string())?;
        Ok(path)
    }
}
#[derive(Clone, Debug)]
pub struct Word {
    pub text: String,
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
    pub line: String,
}
#[derive(Clone, Default)]
pub struct Ocr {
    pub words: Vec<Word>,
    pub text: String,
}
impl Ocr {
    pub fn parse(tsv: &str) -> Self {
        let mut result = Self::default();
        let mut last = String::new();
        for row in tsv.lines().skip(1) {
            let v: Vec<_> = row.splitn(12, '\t').collect();
            if v.len() != 12 || v[0] != "5" || v[11].trim().is_empty() {
                continue;
            }
            let n = |i: usize| v[i].parse::<i32>().unwrap_or(0);
            if n(8) <= 0 || n(9) <= 0 {
                continue;
            }
            let line = v[1..5].join(":");
            if !result.text.is_empty() {
                result.text.push(if line == last { ' ' } else { '\n' });
            }
            result.text.push_str(v[11]);
            last = line.clone();
            result.words.push(Word {
                text: v[11].into(),
                x: n(6),
                y: n(7),
                w: n(8),
                h: n(9),
                line,
            });
        }
        result
    }
    pub fn private_boxes(&self) -> Vec<(i32, i32, i32, i32)> {
        let email = regex::Regex::new(r"(?i)[^\s@]+@[^\s@]+\.[a-z]{2,}").unwrap();
        let phone = regex::Regex::new(r"(?:\+?[0-9][0-9 ().-]{5,}[0-9])").unwrap();
        let mut result = vec![];
        let mut start = 0;
        while start < self.words.len() {
            let mut end = start + 1;
            while end < self.words.len() && self.words[end].line == self.words[start].line {
                end += 1;
            }
            let words = &self.words[start..end];
            let line = words
                .iter()
                .map(|w| w.text.as_str())
                .collect::<Vec<_>>()
                .join(" ");
            let mut ranges: Vec<_> = email
                .find_iter(&line)
                .map(|m| (m.start(), m.end()))
                .collect();
            ranges.extend(
                phone
                    .find_iter(&line)
                    .filter(|m| {
                        let count = m.as_str().chars().filter(|c| c.is_ascii_digit()).count();
                        (7..=15).contains(&count)
                    })
                    .map(|m| (m.start(), m.end())),
            );
            let mut offset = 0;
            for w in words {
                if ranges
                    .iter()
                    .any(|&(a, b)| a < offset + w.text.len() && b > offset)
                {
                    result.push((w.x - 2, w.y - 2, w.w + 4, w.h + 4));
                }
                offset += w.text.len() + 1;
            }
            start = end;
        }
        result
    }
}
pub fn recognize(png: Vec<u8>) -> Result<Ocr, String> {
    let dir = PrivateDir::new()?;
    let input = dir.0.join("input.png");
    std::fs::write(&input, png).map_err(|e| e.to_string())?;
    let output = std::fs::File::create(dir.0.join("text.tsv")).map_err(|e| e.to_string())?;
    let mut child = Command::new("tesseract")
        .arg(input)
        .args(["stdout", "--psm", "11", "tsv"])
        .stdin(Stdio::null())
        .stdout(output)
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| {
            "Install tesseract-ocr and its language data to use Text actions.".to_owned()
        })?;
    let deadline = Instant::now() + Duration::from_secs(45);
    loop {
        if let Some(s) = child.try_wait().map_err(|e| e.to_string())? {
            if !s.success() {
                return Err("Text recognition failed.".into());
            }
            break;
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Text recognition timed out.".into());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    let bytes = std::fs::read(dir.0.join("text.tsv")).map_err(|e| e.to_string())?;
    if bytes.len() > 8_000_000 {
        return Err("Too much recognized text.".into());
    }
    Ok(Ocr::parse(&String::from_utf8_lossy(&bytes)))
}
pub fn export_temp(p: &Pixbuf, dir: &PrivateDir) -> Result<PathBuf, String> {
    let path = dir.0.join("Snip.png");
    let mut f = std::fs::File::create(&path).map_err(|e| e.to_string())?;
    f.write_all(&p.save_to_bufferv("png", &[]).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    Ok(path)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ocr_boxes_and_privacy() {
        let t="level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t20\t100\t20\t95\tuser@example.com\n5\t1\t1\t1\t2\t1\t10\t50\t90\t20\t95\t303-555-0142\n5\t1\t1\t1\t3\t1\t10\t80\t50\t20\t95\tHello";
        let r = Ocr::parse(t);
        assert_eq!(r.words.len(), 3);
        assert_eq!(r.private_boxes().len(), 2);
        assert_eq!(r.text, "user@example.com\n303-555-0142\nHello");
    }
}
