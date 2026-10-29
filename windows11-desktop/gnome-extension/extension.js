import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import GdkPixbuf from 'gi://GdkPixbuf';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {TaskbarProgress} from './taskbar-progress.js';
import {TaskbarCentering} from './taskbar-centering.js';
import {TrayDrawer} from './tray-drawer.js';

const XML = `<node><interface name="local.zorin11.Gnome">
<method name="Call"><arg direction="in" type="s"/><arg direction="out" type="s"/></method>
<method name="Capture"><arg direction="in" type="t"/><arg direction="out" type="s"/></method>
</interface></node>`;
const ACTIONS = {'start':'--toggle-start','search':'--search','explorer':'--explorer','settings':'--settings',
'quick':'--quick-settings','notifications':'--notifications','snap':'--snap-layouts','tasks':'--task-view',
'new-desktop':'--desktop new','previous-desktop':'--desktop left','next-desktop':'--desktop right',
'close-desktop':'--desktop close','groups':'--peek','terminal':'--terminal','switch-next':'--switch-next','switch-previous':'--switch-previous'};

export default class Zorin11 extends Extension {
    enable() {
        this._signals=[]; this._buttons=[]; this._hidden=new Map();
        this._settings=this.getSettings();
        this._bindingChanges=[];
        let recovery=[];
        try {const [ok,data]=GLib.file_get_contents(GLib.build_filenamev([GLib.get_home_dir(),'.config/zorin11-gnome/integration-backup.json']));if(ok)recovery=JSON.parse(new TextDecoder().decode(data));}catch(e){}
        for(const [schema,keys] of Object.entries({
            'org.gnome.shell.keybindings':['toggle-application-view','focus-active-notification'],
            'org.gnome.desktop.wm.keybindings':['switch-applications','switch-applications-backward','switch-windows','switch-windows-backward']})) {
            const settings=new Gio.Settings({schema_id:schema});
            for(const key of keys) {
                let before=settings.get_value(key);
                const record=recovery.find(r=>r.schema===schema&&r.key===key);
                if(record&&before.print(true)===record.new)before=GLib.Variant.parse(null,record.old,null,null);
                this._bindingChanges.push({settings,key,before});settings.set_strv(key,[]);
            }
        }
        this._tracker=Shell.WindowTracker.get_default();
        this._notifyIds=new WeakMap();this._nextNotify=1;this._read=new Set();
        this._bridge=Gio.DBusExportedObject.wrapJSObject(XML,this);
        this._bridge.export(Gio.DBus.session,'/local/zorin11/Gnome');
        this._owner=Gio.bus_own_name_on_connection(Gio.DBus.session,'local.zorin11.Gnome',Gio.BusNameOwnerFlags.NONE,null,null);
        for (const key of Object.keys(ACTIONS)) Main.wm.addKeybinding(key,this._settings,Meta.KeyBindingFlags.NONE,Shell.ActionMode.NORMAL,()=>this._launch(key));
        this._injections=new InjectionManager();
        this._menu=null;
        this._connect(Main.extensionManager,'extension-state-changed',(_,extension)=>{
            if(extension.uuid==='zorin-menu@zorinos.com')this._syncMenu();
        });
        this._syncMenu();
        this._connect(global.display,'window-created',(_,win)=>{
            this._connect(win,'shown',()=>this._placeCompanion(win));
        });
        this._connect(this._settings,'changed::start-button',()=>this._panels());
        this._connect(Main.layoutManager,'monitors-changed',()=>this._panels());
        if(global.zorinTaskbar)this._connect(global.zorinTaskbar,'panels-created',()=>this._panels());
        this._panels();
        this._taskbarProgress=new TaskbarProgress();
        this._taskbarCentering=new TaskbarCentering(this._settings);
        this._trayDrawer=new TrayDrawer(this._settings);
    }
    _syncMenu() {
        const menu=Main.extensionManager.lookup('zorin-menu@zorinos.com')?.stateObj;
        if(menu&&menu!==this._menu) {
            this._menu=menu;
            this._injections.overrideMethod(menu,'_toggleMenu',()=>()=>this._launch('start'));
            // Zorin can enable after us and rebuild its buttons with the taskbar.
            this._injections.overrideMethod(menu,'_enableButton',original=>button=>{
                original.call(menu,button);this._hideMenu(button);
            });
        }
        this._panels();
    }
    _connect(object,signal,callback) {const id=object.connect(signal,callback);this._signals.push([object,id]);}
    _launch(action) {
        const runtime=GLib.getenv('ZORIN11_RUNTIME_DIR') || GLib.build_filenamev([GLib.get_home_dir(),'.local/share/zorin11-hub']);
        const path=GLib.build_filenamev([runtime,'app.py']);
        // GTK uses XWayland for desktop/group positioning; native Wayland clients
        // are enumerated and controlled by Mutter through this extension.
        const launcher=new Gio.SubprocessLauncher({flags:Gio.SubprocessFlags.NONE});
        launcher.setenv('GDK_BACKEND','x11',true);
        if(action==='terminal')launcher.spawnv(['/usr/bin/python3',GLib.build_filenamev([runtime,'terminal.py'])]);
        else launcher.spawnv(['/usr/bin/python3',path,...ACTIONS[action].split(' ')]);
    }
    _hideMenu(button) {
        if(this._hidden.has(button))return;
        const visible=button.visible;
        const id=button.connect('notify::visible',()=>{if(button.visible)button.hide();});
        const destroyed=button.connect('destroy',()=>this._hidden.delete(button));
        this._hidden.set(button,{id,destroyed,visible});button.hide();
    }
    _panels() {
        for(const b of this._buttons)b.destroy();this._buttons=[];
        const panels=global.zorinTaskbar?.panels?.map(p=>p.panel) || [Main.panel];
        for(const panel of panels) {
            const old=panel.statusArea['zorin-menu'];
            if(old)this._hideMenu(old);
            for(const [i,action] of ['start','search','tasks'].entries()) {
                const b=new PanelMenu.Button(0.5,action,true);
                const name={start:'start.svg',search:'search.svg',tasks:'taskview.svg'}[action];
                // Start can use the image chosen in Search & Start settings when it still exists.
                const custom=action==='start'?this._settings.get_string('start-button'):'';
                const file=custom&&GLib.file_test(custom,GLib.FileTest.IS_REGULAR)?custom:`${this.path}/${name}`;
                b.add_child(new St.Icon({gicon:Gio.icon_new_for_string(file),icon_size:24}));
                b.connect('button-press-event',()=>{this._launch(action);return Clutter.EVENT_STOP;});
                panel.addToStatusArea(`zorin11-${action}`,b,i,'left');this._buttons.push(b);
            }
            for(const [i,action] of ['quick','notifications'].entries()) {
                const b=new PanelMenu.Button(0.5,action,true);
                b.add_child(new St.Icon({icon_name:action==='quick'?'preferences-system-symbolic':'preferences-system-notifications-symbolic',icon_size:18}));
                b.connect('button-press-event',()=>{this._launch(action);return Clutter.EVENT_STOP;});
                panel.addToStatusArea(`zorin11-${action}`,b,i,'right');this._buttons.push(b);
            }
        }
    }
    _placeCompanion(win) {
        const title=win.get_title() || '';
        if(!['Zorin 11 Start','Quick settings','Notifications and calendar'].includes(title))return;
        const app=this._tracker.get_window_app(win);
        if(!(win.get_wm_class() || '').toLowerCase().startsWith('zorin11'))return;
        const area=global.workspace_manager.get_active_workspace().get_work_area_for_monitor(title==='Zorin 11 Start'?Main.layoutManager.primaryIndex:global.display.get_current_monitor());
        const r=win.get_frame_rect();
        const x=title==='Zorin 11 Start'?area.x+(area.width-r.width)/2:area.x+area.width-r.width-12;
        win.move_frame(true,Math.round(x),Math.max(area.y+12,area.y+area.height-r.height-12));
        win.make_above();win.activate(global.get_current_time());
    }
    _windows(){return global.get_window_actors().map(a=>a.meta_window).filter(w=>w&&!w.is_override_redirect());}
    _window(id){const w=this._windows().find(w=>w.get_stable_sequence()===id);if(!w)throw Error('That window has closed.');return w;}
    _rows() {
        const focus=global.display.focus_window;
        return this._windows().map(w=>{
            const r=w.get_frame_rect(),app=this._tracker.get_window_app(w);
            return {id:w.get_stable_sequence(),title:w.get_title()||'',app:app?.get_id()||'',
                cls:w.get_wm_class()||app?.get_id()||'',pid:w.get_pid(),
                rect:[r.x,r.y,r.width,r.height],workspace:w.get_workspace()?.index()??0,
                minimized:w.minimized,maximized:w.get_maximized()!==0,fullscreen:w.is_fullscreen(),
                skip:w.skip_taskbar,type:w.get_window_type(),sticky:w.is_on_all_workspaces(),
                resizable:w.allows_resize(),focused:w===focus};
        });
    }
    _notifications() {
        const rows=[];
        for(const source of Main.messageTray.getSources())for(const n of source.notifications) {
            if(!this._notifyIds.has(n))this._notifyIds.set(n,String(this._nextNotify++));
            const id=this._notifyIds.get(n);
            rows.push({n,id,time:(n.datetime?.to_unix()||Date.now()/1000)*1000,app:source.title||'Notification',
                appId:source.app?.get_id()||'',title:n.title||'',body:n.body||'',read:n.acknowledged||this._read.has(id)});
        }
        return rows;
    }
    async CaptureAsync([id],invocation) {
        try {
            const w=this._window(id),actor=w.get_compositor_private();
            if(w.minimized||!actor||actor.width*actor.height>18000000){invocation.return_value(new GLib.Variant('(s)',['']));return;}
            const texture=actor.paint_to_content(null).get_texture();
            const stream=Gio.MemoryOutputStream.new_resizable();
            const pix=await Shell.Screenshot.composite_to_stream(texture,0,0,texture.get_width(),texture.get_height(),1,null,0,0,1,stream);
            stream.close(null);
            const ratio=Math.min(480/pix.width,280/pix.height,1);
            const scaled=pix.scale_simple(Math.max(1,Math.round(pix.width*ratio)),Math.max(1,Math.round(pix.height*ratio)),GdkPixbuf.InterpType.BILINEAR);
            const [ok,bytes]=scaled.save_to_bufferv('png',[],[]);
            invocation.return_value(new GLib.Variant('(s)',[ok?GLib.base64_encode(bytes):'']));
        }catch(e){invocation.return_value(new GLib.Variant('(s)',['']));}
    }
    Call(text) {
        if(text.length>65536)throw Error('Request too large');
        const p=JSON.parse(text), wm=global.workspace_manager;
        let result=true;
        switch(p.op) {
        case 'taskbar-status': result=this._taskbarProgress?.snapshot() || [];break;
        case 'panels': result=(global.zorinTaskbar?.panels?.map(panel=>panel.panel)||[Main.panel]).map(panel=>({
            zorinStartVisible:panel.statusArea['zorin-menu']?.visible||false,
            windowsStartVisible:panel.statusArea['zorin11-start']?.visible||false}));break;
        case 'snapshot': result={windows:this._rows(),current:wm.get_active_workspace_index(),count:wm.n_workspaces,
            names:new Gio.Settings({schema_id:'org.gnome.desktop.wm.preferences'}).get_strv('workspace-names'),
            width:global.stage.width,height:global.stage.height};break;
        case 'window': {
            const w=this._window(p.id),stamp=global.get_current_time();
            switch(p.action){
            case 'activate': w.get_workspace().activate(stamp);w.unminimize();w.activate(stamp);break;
            case 'close':w.delete(stamp);break;
            case 'minimize':w.minimize();break;
            case 'unminimize':w.unminimize();break;
            case 'maximize':w.maximize(Meta.MaximizeFlags.BOTH);break;
            case 'unmaximize':w.unmaximize(Meta.MaximizeFlags.BOTH);break;
            case 'fullscreen':p.value?w.make_fullscreen():w.unmake_fullscreen();break;
            case 'move': {
                if(!Array.isArray(p.rect)||p.rect.length!==4||!p.rect.every(Number.isFinite)||p.rect[2]<1||p.rect[3]<1||p.rect.some(v=>Math.abs(v)>100000))throw Error('Invalid rectangle');
                if(!w.allows_resize())throw Error('Window cannot be resized');
                w.unmaximize(Meta.MaximizeFlags.BOTH);w.unmake_fullscreen();w.move_resize_frame(true,...p.rect.map(Math.round));break;
            }
            case 'workspace':if(!Number.isInteger(p.index)||p.index<0||p.index>=wm.n_workspaces)throw Error('Unknown desktop');w.change_workspace_by_index(p.index,false);break;
            default:throw Error('Unknown window action');
            }break;
        }
        case 'workspace': {
            if(!Number.isInteger(p.index)||p.index<0||p.index>=wm.n_workspaces)throw Error('Unknown desktop');
            wm.get_workspace_by_index(p.index).activate(global.get_current_time());break;
        }
        case 'count': {
            if(!Number.isInteger(p.count)||p.count<1||p.count>32)throw Error('Choose 1–32 desktops');
            while(wm.n_workspaces<p.count)wm.append_new_workspace(false,global.get_current_time());
            while(wm.n_workspaces>p.count)wm.remove_workspace(wm.get_workspace_by_index(wm.n_workspaces-1),global.get_current_time());
            new Gio.Settings({schema_id:'org.gnome.desktop.wm.preferences'}).set_int('num-workspaces',p.count);break;
        }
        case 'rename': {
            if(!Number.isInteger(p.index)||p.index<0||p.index>=wm.n_workspaces||typeof p.name!=='string')throw Error('Unknown desktop');
            const s=new Gio.Settings({schema_id:'org.gnome.desktop.wm.preferences'}),names=s.get_strv('workspace-names');
            while(names.length<wm.n_workspaces)names.push(`Desktop ${names.length+1}`);
            names[p.index]=p.name.slice(0,40);s.set_strv('workspace-names',names);break;
        }
        case 'notifications': result=this._notifications().slice(-200).reverse().map(({n,...row})=>row);break;
        case 'notification': {
            if(!['clear','dismiss','read'].includes(p.action))throw Error('Unknown notification action');
            for(const row of this._notifications())if(p.action==='clear'||p.ids?.includes(row.id)) {
                if(p.action==='read'){this._read.add(row.id);row.n.acknowledged=true;}
                else row.n.destroy();
            }break;
        }
        case 'modifiers':result=global.get_pointer()[2];break;
        case 'overview':Main.overview.toggle();break;
        default:throw Error('Unknown operation');
        }
        return JSON.stringify(result);
    }
    disable() {
        this._taskbarProgress?.destroy();this._taskbarProgress=null;
        this._taskbarCentering?.destroy();this._taskbarCentering=null;
        this._trayDrawer?.destroy();this._trayDrawer=null;
        this._injections?.clear();
        for(const {settings,key,before} of this._bindingChanges || [])if(settings.get_strv(key).length===0)settings.set_value(key,before);
        this._bindingChanges=[];
        for(const key of Object.keys(ACTIONS))Main.wm.removeKeybinding(key);
        for(const [obj,id] of this._signals){try{obj.disconnect(id);}catch(e){}}
        for(const b of this._buttons)b.destroy();
        for(const [actor,{id,destroyed,visible}] of this._hidden){try{actor.disconnect(id);actor.disconnect(destroyed);if(visible)actor.show();}catch(e){}}
        this._bridge?.unexport();if(this._owner)Gio.bus_unown_name(this._owner);
        this._signals=[];this._buttons=[];this._hidden=new Map();
    }
}
