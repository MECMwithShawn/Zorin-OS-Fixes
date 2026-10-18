"""Exercise the real WebKit bridge on disposable files and a private app ID."""
import json,os,tempfile,time,re,subprocess
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='zorin11-live-') as directory:
    root=Path(directory)
    os.environ['ZORIN11_CONFIG_DIR']=str(root/'config')
    os.environ['ZORIN11_APP_ID']='local.zorin11.DesktopHub.LiveTest'
    from app import Hub,GLib,Gtk,Gdk
    from platform_ui import panel_button
    hub=Hub();hub.register(None)
    prior_clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
    hub.store.state['groups_visible']=False;hub.sync_groups()
    (root/'source.txt').write_text('original data')
    (root/'target').mkdir()
    hub.open_explorer(str(root))
    surface=next(s for s in hub.surfaces.values() if s.mode=='explorer')
    loop=GLib.MainLoop();deadline=time.monotonic()+18;stage=0;failure=[]
    def send(action,**payload):
        surface.js('window.webkit.messageHandlers.desktop.postMessage('+json.dumps(json.dumps(dict(action=action,**payload)))+')')
    def tick():
        global stage, mapped_at
        try:
            if time.monotonic()>deadline:raise AssertionError('Live test timed out at stage '+str(stage))
            if not surface.ready or not surface.file_state:return True
            if stage==0:
                send('file-new-folder',name='Created in WebKit');stage=1
            elif stage==1 and (root/'Created in WebKit').is_dir():
                send('file-rename',path=str(root/'Created in WebKit'),name='Renamed');stage=2
            elif stage==2 and (root/'Renamed').is_dir():
                send('file-copy',paths=[str(root/'source.txt')]);stage=3
            elif stage==3 and hub.copied_files[0]:
                from explorer import clipboard_read
                paths,cut=clipboard_read(Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD))
                assert paths==[str(root/'source.txt')] and not cut
                send('file-navigate',path=str(root/'target'));stage=4
            elif stage==4 and surface.location==str(root/'target'):
                send('file-paste');stage=5
            elif stage==5 and (root/'target/source.txt').exists():
                assert (root/'target/source.txt').read_text()=='original data'
                assert (root/'source.txt').read_text()=='original data'
                hub.show_quick();stage=6
            elif stage==6:
                assert hub.quick.get_size().width==368 and hub.quick.get_size().height in (430,490),hub.quick.get_size()
                hub.quick.hide();hub.show_start();mapped_at=time.monotonic();stage=7
            elif stage==7:
                if time.monotonic()-mapped_at<.8:return True
                outputs=subprocess.check_output(['xrandr','--current'],text=True)
                if not re.search(r'^\S+ connected',outputs,re.M):
                    print('Live WebKit passed: create, rename, native clipboard, navigate, copy/paste; Quick Settings size.')
                    print('SKIP on-screen Start placement: no connected XRandR output.')
                    loop.quit();return False
                x,y,w,h=panel_button('Start');sw,sh=hub.start.get_size()
                import gi
                gi.require_version('GdkX11','3.0')
                from gi.repository import GdkX11
                xid=hub.start.get_window().get_xid()
                info=subprocess.check_output(['xwininfo','-id',str(xid)],text=True)
                sx=int(re.search(r'Absolute upper-left X:\s+(-?\d+)',info)[1]);sy=int(re.search(r'Absolute upper-left Y:\s+(-?\d+)',info)[1])
                assert abs((sx+sw/2)-(x+w/2))<=1,((sx,sw),(x,w))
                assert sy+sh<=y-8
                print('Live WebKit passed: create, rename, native file clipboard, navigate, copy/paste; Quick Settings geometry; Start anchoring.')
                loop.quit();return False
        except Exception as error:
            failure.append(str(error));loop.quit();return False
        return True
    GLib.timeout_add(100,tick);loop.run()
    if prior_clipboard is not None:Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(prior_clipboard,-1)
    for s in list(hub.surfaces.values()):s.destroy()
    hub.workers.shutdown(wait=True,cancel_futures=True)
    if failure:raise AssertionError(failure[0])
