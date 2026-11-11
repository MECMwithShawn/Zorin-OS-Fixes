#!/usr/bin/python3
"""GNOME's own "Unlock Keyring" prompt answered by a YubiKey touch, in a private headless GNOME
Shell with a private gnome-keyring-daemon and a stand-in for the key. Never touches the signed-in
session, its keyrings or a real YubiKey."""
import json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from gnome_live import until,systemd_fixture
ROOT=Path(__file__).resolve().parents[1]
UUID='zorin11@zorin-os-fixes'
# Stands in for keyring_unlock.py: the real `password` command with the key's touch faked.
HELPER=r'''
import json,os,sys,time
sys.path.insert(0,os.environ['YUBIKEY_DIR'])
import keyring_unlock as ku
mode=open(os.environ['FAKE_MODE']).read().strip()
key=bytes.fromhex(os.environ['FAKE_KEY'])
ku.fido.devices=lambda:[] if mode=='nokey' else ['/dev/fake']
def touch(path,text,action,stop=None):
    time.sleep(.3)
    return key
ku.with_touch=touch
with open(os.environ['FAKE_LOG'],'a') as log:log.write(json.dumps({'argv':sys.argv[1:],'mode':mode})+'\n')
rc=ku.main(sys.argv[1:])
with open(os.environ['FAKE_LOG'],'a') as log:log.write(json.dumps({'rc':rc})+'\n')
sys.exit(rc)
'''

def session(temp,output):
    from gi.repository import Gio,GLib
    sys.path.insert(0,str(ROOT/'yubikey'))
    import keyring_unlock as ku
    extensions=temp/'data/gnome-shell/extensions'
    shutil.copytree(ROOT/'gnome-extension',extensions/UUID)
    subprocess.run(['glib-compile-schemas',str(extensions/UUID/'schemas')],check=True)
    shellsettings=Gio.Settings.new('org.gnome.shell')
    shellsettings.set_strv('enabled-extensions',[UUID])
    shellsettings.set_strv('disabled-extensions',[p.name for p in Path('/usr/share/gnome-shell/extensions').iterdir() if p.is_dir()])
    shellsettings.set_string('welcome-dialog-last-shown-version','46.0')
    Gio.Settings.sync()
    key=os.urandom(32)
    mode,log_path=temp/'mode',temp/'helper.log'
    (temp/'helper.py').write_text(HELPER);mode.write_text('touch');log_path.write_text('')
    env=dict(os.environ,ZORIN11_YUBIKEY_HELPER=str(temp/'helper.py'),YUBIKEY_DIR=str(ROOT/'yubikey'),
             FAKE_MODE=str(mode),FAKE_KEY=key.hex(),FAKE_LOG=str(log_path))
    children=[]
    log=(output/'shell.log').open('w')
    def start(args,**kw):
        p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,**kw);children.append(p);return p
    def helper_runs():
        return [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    start(['/usr/bin/python3',__file__,'--systemd-fixture']);time.sleep(.3)
    start(['gnome-shell','--headless','--wayland','--no-x11','--virtual-monitor','1280x800','--wayland-display','yubikey-prompt-test'],env=env)
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    def owned(name):
        return bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',
                             GLib.Variant('(s)',(name,)),GLib.VariantType('(b)'),0,1000,None).unpack()[0]
    try:
        until(lambda:owned('org.gnome.keyring.SystemPrompter') and owned('local.zorin11.Gnome'),30)
        until(lambda:'Registering session with GDM' in (output/'shell.log').read_text())
        start(['gnome-keyring-daemon','--start','--foreground','--components=secrets'],env=dict(os.environ,HOME=str(temp)))
        until(lambda:owned(ku.SECRETS))
        k=ku.Keyring(bus)
        def create(label,password):
            props={'org.freedesktop.Secret.Collection.Label':GLib.Variant('s',label)}
            return k._call(ku.ROOT,ku.INTERNAL,'CreateWithMasterPassword',GLib.Variant('(a{sv}(oayays))',(props,k._secret(password))),'(o)').unpack()[0]
        def lock(*paths):
            k._call(ku.ROOT,ku.SERVICE,'Lock',GLib.Variant('(ao)',(list(paths),)),'(aoo)')
            time.sleep(1)  # gnome-keyring asserts if Unlock follows Lock too closely
        one,two,other=create('One',b'pw-one'),create('Two',b'pw-two'),create('Other',b'pw-other')
        def configure(sealed):
            ku.save_config({'version':1,'rp':ku.RP,'credential':ku.b64(b'id'),'salt':ku.b64(b's'*32),
                            'keyrings':{p:{'label':l,**ku.seal(key,p,pw)} for p,(l,pw) in sealed.items()}})
        configure({one:('One',b'pw-one'),two:('Two',b'pw-two')})
        # An app asks first: GNOME's prompt, our touch, both set-up keyrings open.
        lock(one,two,other)
        assert k.prompt_unlock([one],timeout=20),'the prompt completed'
        assert not k.locked(one) and not k.locked(two),'One by the prompt, Two by the helper'
        runs=helper_runs();assert len(runs)==2 and '“One”' in runs[0]['argv'][-1] and runs[1]['rc']==0,runs
        print('An app asking first: GNOME prompt filled after a touch; both keyrings open',flush=True)
        # A keyring that isn't set up keeps the normal prompt.
        log_path.write_text('');lock(one,two,other)
        started=time.monotonic()
        assert not k.prompt_unlock([other],timeout=4) and k.locked(other)
        runs=helper_runs();assert runs[-1]['rc']==3 and time.monotonic()-started>=3.5,runs
        print('Another keyring: left to typing',flush=True)
        # A stale saved password is tried once, then left to typing (no loop).
        configure({one:('One',b'not-it'),two:('Two',b'pw-two')})
        log_path.write_text('')
        assert not k.prompt_unlock([one],timeout=5) and k.locked(one)
        assert sum('argv' in r for r in helper_runs())==1,helper_runs()
        print('Stale password: tried once, then typing',flush=True)
        # Closing the prompt while it waits for the key stops the helper.
        configure({one:('One',b'pw-one'),two:('Two',b'pw-two')})
        log_path.write_text('');mode.write_text('nokey')
        assert not k.prompt_unlock([one],timeout=2)
        until(lambda:helper_runs() and 'rc' in helper_runs()[-1],5)
        assert helper_runs()[-1]['rc']==1,helper_runs()
        print('Closed while waiting for the key: helper stopped',flush=True)
        # Sign-in: `keyring_unlock.py unlock` goes through the same prompt.
        mode.write_text('touch');log_path.write_text('');lock(one,two,other)
        r=subprocess.run(['/usr/bin/python3',str(ROOT/'yubikey/keyring_unlock.py'),'unlock'],capture_output=True,text=True,timeout=60)
        assert r.returncode==0,r.stderr
        assert not k.locked(one) and not k.locked(two) and k.locked(other)
        assert (Path(os.environ['XDG_RUNTIME_DIR'])/'zorin11-yubikey-unlock.done').exists()
        print('Sign-in unlock: one GNOME prompt, one touch, both keyrings open',flush=True)
        k.close()
        text=(output/'shell.log').read_text()
        assert 'JS ERROR' not in text and 'keyringPrompt: Failed' not in text,text[-6000:]
        print('PASS',flush=True)
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        log.close()

if __name__=='__main__':
    if '--systemd-fixture' in sys.argv:systemd_fixture()
    elif '--session' in sys.argv:session(Path(sys.argv[-2]),Path(sys.argv[-1]))
    else:
        output=Path(os.environ.get('ZORIN11_TEST_OUTPUT','/tmp/zorin11-yubikey-prompt-test'));output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='zorin11-yubikey-prompt-') as directory:
            temp=Path(directory)
            for name in ('data','config','cache','runtime'):(temp/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config'),XDG_CACHE_HOME=str(temp/'cache'),XDG_RUNTIME_DIR=str(temp/'runtime'),GSETTINGS_BACKEND='keyfile',XDG_CURRENT_DESKTOP='GNOME',XDG_SESSION_TYPE='wayland',GTK_USE_PORTAL='0',WAYLAND_DISPLAY='yubikey-prompt-test',DISPLAY='',XAUTHORITY='')
            result=subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--session',str(temp),str(output)],env=env,capture_output=True,text=True,timeout=180)
            print(result.stdout)
            if result.returncode:print(result.stderr[-5000:]);print((output/'shell.log').read_text()[-5000:])
            raise SystemExit(result.returncode)
