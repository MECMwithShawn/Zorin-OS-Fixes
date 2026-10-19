"""Build the pinned Docklike extension in the user's cache, without root."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

BASE = Path(__file__).resolve().parent/'taskbar'
REVISION = '9dc36e03d1b4d685b8eb76c02e701ccfbcc55bc8'
URL = 'https://codeload.github.com/xfce-mirror/xfce4-docklike-plugin/tar.gz/'+REVISION
SHA256 = '8d09122addd48e656ea888297a77f6cfa2ba8a9d5bc321f99ebbaa2bacb84728'


def fingerprint():
    digest = hashlib.sha256((REVISION+platform.machine()).encode())
    # A system upgrade may change the panel ABI; rebuild against its headers.
    versions = subprocess.check_output(['dpkg-query', '-W', '-f=${Package} ${Version}\n',
        'libxfce4panel-2.0-4', 'libxfce4windowing-0-0', 'libgtk-3-0t64'], text=True)
    digest.update(versions.encode())
    for name in ('docklike.patch', 'LivePreview.cpp', 'LivePreview.hpp', 'SnapGroups.cpp', 'SnapGroups.hpp'):
        digest.update((BASE/name).read_bytes())
    return digest.hexdigest()[:24]


def build():
    cache = Path.home()/'.cache/zorin11-taskbar'
    target = cache/fingerprint()
    artifact = target/'libdocklike.so'
    stamp = target/'build.json'
    if artifact.exists() and stamp.exists():
        info = json.loads(stamp.read_text())
        if hashlib.sha256(artifact.read_bytes()).hexdigest() == info.get('sha256'):
            return artifact
    missing = [n for n in ('meson', 'ninja', 'c++', 'pkg-config', 'patch', 'msgfmt') if not shutil.which(n)]
    if missing:
        raise RuntimeError('Taskbar build tools missing: '+', '.join(missing)+'. Run windows11-desktop/install-system-deps.sh first.')
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache/(REVISION+'.tar.gz')
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(8*1024*1024)
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError('Docklike source checksum mismatch')
        archive.write_bytes(data)
    print('Building Windows-style taskbar previews…', flush=True)
    with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as temp:
        temp = Path(temp)
        with tarfile.open(archive) as tar:
            tar.extractall(temp, filter='data')
        source = temp/('xfce4-docklike-plugin-'+REVISION)
        subprocess.run(['patch', '-p1', '-i', str(BASE/'docklike.patch')], cwd=source, check=True)
        for name in ('LivePreview.cpp', 'LivePreview.hpp', 'SnapGroups.cpp', 'SnapGroups.hpp'):
            shutil.copy2(BASE/name, source/'src'/name)
        subprocess.run(['meson', 'setup', 'build', '--prefix=/usr', '--libdir=lib',
            '--buildtype=release', '-Dx11=enabled', '-Dwayland=disabled'], cwd=source, check=True)
        subprocess.run(['ninja', '-C', 'build'], cwd=source, check=True)
        # Meson's install step removes build-only RPATHs; no system files touched.
        subprocess.run(['meson', 'install', '-C', 'build', '--no-rebuild', '--destdir', str(temp/'stage')], cwd=source, check=True)
        library = temp/'stage/usr/lib/xfce4/panel/plugins/libdocklike.so'
        target.mkdir(parents=True, exist_ok=True)
        partial = target/'libdocklike.so.partial'
        shutil.copy2(library, partial)
        partial.replace(artifact)
        stamp.write_text(json.dumps({'revision': REVISION, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}))
    return artifact


def integrate(home, artifact, file):
    # Xfce 4.20 derives the per-user library directory from its system libdir.
    system = list(Path('/usr/lib').glob('*/xfce4/panel/plugins/libdocklike.so'))
    system += list(Path('/usr/lib/xfce4/panel/plugins').glob('libdocklike.so'))
    if len(system) != 1:
        raise RuntimeError('Could not determine the installed Docklike library directory')
    destination = home/'.local'/system[0].relative_to('/usr')
    file(destination, artifact.read_bytes())
    file(home/'.local/share/xfce4/panel/plugins/docklike.desktop', '''[Xfce Panel]
Type=X-XFCE-PanelPlugin
Name=Windows-style Taskbar
Comment=Docklike with live window previews and close controls
Icon=preferences-system
X-XFCE-Module=docklike
X-XFCE-Internal=false
X-XFCE-Unique=false
X-XFCE-API=2.0
''')


if __name__ == '__main__':
    print(build())
