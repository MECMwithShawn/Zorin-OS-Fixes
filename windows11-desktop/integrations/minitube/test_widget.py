"""Real GTK player EQ actions with private state and controlled helper processes."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
if '--private' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='player-eq-test-') as directory:
        root=Path(directory);(root/'runtime').mkdir(mode=0o700)
        hub=root/'hub';hub.mkdir()
        source=Path(__file__).resolve().parents[2]/'companion'
        sys.path.insert(0,str(source));import audio_effects
        (hub/'audio-presets.json').write_text(json.dumps(audio_effects.PRESETS))
        (hub/'audio_effects.py').write_text('''import json,os,sys
from pathlib import Path
p=Path(os.environ['XDG_CONFIG_HOME'])/'zorin11-hub/audio-effects.json'
p.parent.mkdir(parents=True,exist_ok=True)
if sys.argv[2]=='gaming':raise SystemExit('Test device unavailable')
p.write_text(json.dumps({'preset':sys.argv[2]}))
''')
        (hub/'audio_spectrum.py').write_text('''import json,time
while True:
 print(json.dumps({'available':True,'levels':[.2,.4,.6,.8]*4}),flush=True);time.sleep(.1)
''')
        (hub/'app.py').write_text("from pathlib import Path\nPath(__file__).with_name('settings-opened').touch()\n")
        env=dict(os.environ,XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),
                 XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),
                 GIO_USE_VFS='local',GDK_BACKEND='x11',GTK_USE_PORTAL='0',ZORIN11_RUNTIME_DIR=str(hub))
        env.pop('AT_SPI_BUS_ADDRESS',None)
        raise SystemExit(subprocess.run(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--private',sys.argv[1]],env=env,timeout=45).returncode)
import gi
gi.require_version('Atspi','2.0');gi.require_version('Gtk','3.0')
from gi.repository import Atspi,Gtk,Gdk
def walk(n):
    yield n
    for i in range(n.get_child_count()):yield from walk(n.get_child_at_index(i))
def find(name):
    return next((n for n in walk(Atspi.get_desktop(0)) if n.get_name()==name and n.get_state_set().contains(Atspi.StateType.SHOWING)),None)
def wait(fn):
    end=time.monotonic()+7
    while time.monotonic()<end:
        value=fn()
        if value:return value
        time.sleep(.1)
    raise AssertionError('Player EQ fixture timed out')
state=Path(os.environ['XDG_CONFIG_HOME'])/'zorin11-hub/audio-effects.json'
def chosen():return json.loads(state.read_text())['preset'] if state.exists() else 'off'
def key(*keys):subprocess.run(['xdotool','key','--clearmodifiers',*keys],check=True)
proc=subprocess.Popen([sys.argv[-1]])
try:
    combo=wait(lambda:find('System EQ preset'))
    rect=combo.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    def pick(index):
        subprocess.run(['xdotool','mousemove',str(rect.x+rect.width//2),str(rect.y+rect.height//2),'click','1'],check=True)
        key('Home',*(['Down']*index),'Return')
    pick(2);wait(lambda:chosen()=='music')
    pick(4);wait(lambda:chosen()=='voice')
    # Changes from Settings are reflected without re-applying the previous value.
    state.write_text(json.dumps({'preset':'bass'}))
    wait(lambda:combo.get_selection_iface().get_selected_child(0).get_name()=='Bass boost')
    pick(6);wait(lambda:find('Test device unavailable'))
    assert chosen()=='bass'
    pick(2);wait(lambda:chosen()=='music')
    wait(lambda:find('Bass                         Live playback                         Treble'))
    more=wait(lambda:find('⋯'));more.get_action_iface().do_action(0)
    wait(lambda:(Path(os.environ['ZORIN11_RUNTIME_DIR'])/'settings-opened').exists())
    if os.environ.get('ZORIN11_TEST_OUTPUT'):
        time.sleep(.4);Gtk.init([])
        root=Gdk.get_default_root_window();_,_,w,h=root.get_geometry()
        Gdk.pixbuf_get_from_window(root,0,0,w,h).savev(os.environ['ZORIN11_TEST_OUTPUT'],'png',[],[])
    print('PASS native player EQ changes, external setting synchronization, failure recovery, live bars and Sound settings action')
finally:
    proc.terminate();proc.wait(timeout=5)
