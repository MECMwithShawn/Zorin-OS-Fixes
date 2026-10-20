// Copy into the player's examples/system_eq_test.rs to run the isolated GTK fixture.
#[path="../src/system_eq.rs"]
mod system_eq;
use gtk::prelude::*;
fn main() {
    let app=gtk::Application::new(Some("local.zorin11.SystemEqTest"),gio::ApplicationFlags::empty());
    app.connect_activate(|app|{
        let window=gtk::ApplicationWindow::new(app);
        window.set_title("System EQ integration test");
        window.set_default_size(420,220);
        window.add(&system_eq::widget());
        window.show_all();
    });
    app.run();
}
