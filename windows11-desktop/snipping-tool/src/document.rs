use cairo::{Context, Format, ImageSurface};
use gdk::prelude::*;
use gdk_pixbuf::Pixbuf;

pub type Point = (f64, f64);
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Tool {
    Pen,
    Highlight,
    Rectangle,
    Ellipse,
    Arrow,
    Text,
    Crop,
}
#[derive(Clone)]
pub struct Mark {
    pub tool: Tool,
    pub points: Vec<Point>,
    pub color: (f64, f64, f64),
    pub width: f64,
    pub text: String,
}
#[derive(Clone)]
struct Frame {
    base: Pixbuf,
    marks: Vec<Mark>,
}
pub struct Document {
    frame: Frame,
    undo: Vec<Frame>,
    redo: Vec<Frame>,
    pub dirty: bool,
}
pub fn bounds(a: Point, b: Point, w: i32, h: i32) -> (i32, i32, i32, i32) {
    let x = a.0.min(b.0).floor().clamp(0., w as f64) as i32;
    let y = a.1.min(b.1).floor().clamp(0., h as f64) as i32;
    let right = a.0.max(b.0).ceil().clamp(0., w as f64) as i32;
    let bottom = a.1.max(b.1).ceil().clamp(0., h as f64) as i32;
    (x, y, right - x, bottom - y)
}
impl Document {
    pub fn new(base: Pixbuf, dirty: bool) -> Result<Self, String> {
        if base.width() as i64 * base.height() as i64 > 40_000_000 {
            return Err("Image exceeds the 40 megapixel limit.".into());
        }
        Ok(Self {
            frame: Frame {
                base,
                marks: vec![],
            },
            undo: vec![],
            redo: vec![],
            dirty,
        })
    }
    pub fn size(&self) -> (i32, i32) {
        (self.frame.base.width(), self.frame.base.height())
    }
    fn remember(&mut self) {
        self.undo.push(self.frame.clone());
        if self.undo.len() > 20 {
            self.undo.remove(0);
        }
        self.redo.clear();
        self.dirty = true;
    }
    pub fn mark(&mut self, mark: Mark) {
        if mark.points.is_empty() {
            return;
        }
        self.remember();
        self.frame.marks.push(mark);
    }
    pub fn undo(&mut self) {
        if let Some(f) = self.undo.pop() {
            self.redo.push(self.frame.clone());
            self.frame = f;
            self.dirty = true;
        }
    }
    pub fn redo(&mut self) {
        if let Some(f) = self.redo.pop() {
            self.undo.push(self.frame.clone());
            self.frame = f;
            self.dirty = true;
        }
    }
    pub fn draw(&self, c: &Context) {
        c.set_source_pixbuf(&self.frame.base, 0., 0.);
        let _ = c.paint();
        for m in &self.frame.marks {
            draw_mark(c, m)
        }
    }
    pub fn render(&self) -> Result<Pixbuf, String> {
        let (w, h) = self.size();
        let s = ImageSurface::create(Format::ARgb32, w, h).map_err(|e| e.to_string())?;
        let c = Context::new(&s).map_err(|e| e.to_string())?;
        self.draw(&c);
        gdk::pixbuf_get_from_surface(&s, 0, 0, w, h).ok_or("Could not render the image.".into())
    }
    pub fn crop(&mut self, a: Point, b: Point) -> Result<(), String> {
        let (w, h) = self.size();
        let (x, y, cw, ch) = bounds(a, b, w, h);
        if cw < 2 || ch < 2 {
            return Err("Drag a larger crop area.".into());
        }
        let p = self
            .render()?
            .new_subpixbuf(x, y, cw, ch)
            .copy()
            .ok_or("Could not crop image")?;
        self.remember();
        self.frame = Frame {
            base: p,
            marks: vec![],
        };
        Ok(())
    }
}
pub fn draw_mark(c: &Context, m: &Mark) {
    let Some(&a) = m.points.first() else { return };
    let b = *m.points.last().unwrap();
    let _ = c.save();
    c.set_source_rgba(
        m.color.0,
        m.color.1,
        m.color.2,
        if m.tool == Tool::Highlight { 0.32 } else { 1. },
    );
    c.set_line_width(m.width);
    c.set_line_cap(cairo::LineCap::Round);
    c.set_line_join(cairo::LineJoin::Round);
    match m.tool {
        Tool::Pen | Tool::Highlight => {
            c.move_to(a.0, a.1);
            if m.points.len() == 1 {
                c.line_to(a.0 + 0.01, a.1);
            }
            for p in &m.points[1..] {
                c.line_to(p.0, p.1);
            }
            let _ = c.stroke();
        }
        Tool::Rectangle => {
            c.rectangle(
                a.0.min(b.0),
                a.1.min(b.1),
                (a.0 - b.0).abs(),
                (a.1 - b.1).abs(),
            );
            let _ = c.stroke();
        }
        Tool::Ellipse => {
            let rx = (a.0 - b.0).abs() / 2.;
            let ry = (a.1 - b.1).abs() / 2.;
            if rx > 0. && ry > 0. {
                c.translate((a.0 + b.0) / 2., (a.1 + b.1) / 2.);
                c.scale(rx, ry);
                c.arc(0., 0., 1., 0., std::f64::consts::TAU);
                c.set_line_width(m.width / rx.min(ry));
                let _ = c.stroke();
            }
        }
        Tool::Arrow => {
            let angle = (b.1 - a.1).atan2(b.0 - a.0);
            let len = 12. + m.width * 2.;
            c.move_to(a.0, a.1);
            c.line_to(b.0, b.1);
            for delta in [-0.5, 0.5] {
                c.move_to(b.0, b.1);
                c.line_to(
                    b.0 - len * (angle + delta).cos(),
                    b.1 - len * (angle + delta).sin(),
                );
            }
            let _ = c.stroke();
        }
        Tool::Text => {
            c.select_font_face("Sans", cairo::FontSlant::Normal, cairo::FontWeight::Normal);
            c.set_font_size(16. + m.width * 2.);
            c.move_to(a.0, a.1);
            let _ = c.show_text(&m.text);
        }
        Tool::Crop => {
            c.set_source_rgb(0.38, 0.78, 1.);
            c.set_line_width(1.);
            c.set_dash(&[5., 3.], 0.);
            c.rectangle(
                a.0.min(b.0),
                a.1.min(b.1),
                (a.0 - b.0).abs(),
                (a.1 - b.1).abs(),
            );
            let _ = c.stroke();
        }
    }
    let _ = c.restore();
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn clipped_reverse_selection() {
        assert_eq!(bounds((130., 90.), (-10., 20.), 100, 80), (0, 20, 100, 60));
        assert_eq!(bounds((10., 10.), (10., 10.), 100, 100), (10, 10, 0, 0));
    }
    #[test]
    fn pixels_crop_and_history() {
        gtk::init().expect("Run under xvfb-run for rendering tests");
        let p = Pixbuf::new(gdk_pixbuf::Colorspace::Rgb, true, 8, 100, 80).unwrap();
        p.fill(0xffffffff);
        let mut d = Document::new(p, false).unwrap();
        d.mark(Mark {
            tool: Tool::Pen,
            points: vec![(10., 10.), (90., 10.)],
            color: (1., 0., 0.),
            width: 6.,
            text: String::new(),
        });
        let p = d.render().unwrap();
        let bytes = p.read_pixel_bytes();
        let offset = (10 * p.rowstride() + 50 * p.n_channels()) as usize;
        assert!(bytes[offset] > 240 && bytes[offset + 1] < 10);
        d.crop((30., 0.), (70., 30.)).unwrap();
        assert_eq!(d.size(), (40, 30));
        d.undo();
        assert_eq!(d.size(), (100, 80));
        d.undo();
        let p = d.render().unwrap();
        assert!(p.read_pixel_bytes()[offset + 1] > 240);
        d.redo();
        assert!(d.render().unwrap().read_pixel_bytes()[offset + 1] < 10);
    }
}
