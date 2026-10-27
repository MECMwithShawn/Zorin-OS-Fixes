#!/usr/bin/gjs -m
import Gtk from 'gi://Gtk?version=4.0';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import {buildMotionControls} from './controls.js';

const App = GObject.registerClass(class extends Gtk.Application {
    _init() { super._init({application_id: 'local.zorin11.TaskbarMotion', flags: Gio.ApplicationFlags.DEFAULT_FLAGS}); }
    vfunc_activate() {
        if (this.window) { this.window.present(); return; }
        Gtk.Settings.get_default().gtk_application_prefer_dark_theme = true;
        const win = new Gtk.ApplicationWindow({application: this, title: 'Taskbar motion', default_width: 760, default_height: 800});
        this.window = win; win.add_css_class('motion-window');
        const scroll = new Gtk.ScrolledWindow({hscrollbar_policy: Gtk.PolicyType.NEVER});
        scroll.set_child(buildMotionControls(win)); win.set_child(scroll);
        win.connect('close-request', () => { this.window = null; return false; });
        win.present();
    }
});
new App().run([]);
