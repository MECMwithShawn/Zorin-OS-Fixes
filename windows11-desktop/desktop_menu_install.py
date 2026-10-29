"""Per-user adapter for the installed Zorin desktop; never overwrite vendor files."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
UUID = 'zorin11-desktop@zorin-os-fixes'
VENDOR = Path('/usr/share/gnome-shell/extensions/zorin-desktop-icons@zorinos.com')


def prepare(destination=None, vendor=VENDOR):
    destination = destination or Path.home()/'.local/share/gnome-shell/extensions'/UUID
    app = vendor/'app'
    required = ('_createDesktopBackgroundMenu()', '_drawDesktop(', '_prepareMenu()',
                '_updateDesktop()', 'doNewFolder(', 'doSorts(')
    text = (app/'desktopManager.js').read_text()
    if not all(token in text for token in required):
        raise RuntimeError('Unsupported Zorin Desktop Icons version; original desktop retained.')
    if not (app/'ding.js').is_file():
        raise RuntimeError('Zorin Desktop Icons is not installed.')
    destination.mkdir(parents=True, exist_ok=True)
    overlay = destination/'app'
    overlay.mkdir(exist_ok=True)
    links = {overlay/p.name:p for p in app.iterdir() if p.name not in ('desktopManager.js','menu.css','shortcutRename.js')}
    links[overlay/'zorinOriginal'] = app
    for target, source in links.items():
        if target.is_symlink() and target.readlink() == source:
            continue
        if target.exists() or target.is_symlink():
            raise RuntimeError(f'Preserving unexpected desktop adapter file: {target}')
        target.symlink_to(source, target_is_directory=source.is_dir())
    files = {}
    for source in (ROOT/'gnome-desktop-extension').rglob('*'):
        if not source.is_file():
            continue
        relative = source.relative_to(ROOT/'gnome-desktop-extension')
        target = destination/relative
        if source.name in ('desktopManager.js','menu.css','shortcutRename.js'):
            target = overlay/source.name
        files[target] = source.read_bytes()
    return files


def activate():
    """Enable a known extension; a new directory is discovered at next login."""
    from gi.repository import Gio, GLib
    import gnome_setup
    shell = Gio.Settings.new('org.gnome.shell')
    gnome_setup.install(gnome_setup.plan({'org.gnome.shell': {
        'enabled-extensions': list(dict.fromkeys(shell.get_strv('enabled-extensions') + [UUID])),
        'disabled-extensions': [value for value in shell.get_strv('disabled-extensions') if value != UUID],
    }}))
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    # GNOME 46's ReloadExtension API is deprecated and always fails. Queue the
    # enabled setting for login instead of restarting Shell or using unsafe eval.
    return bus.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions',
                  'org.gnome.Shell.Extensions','EnableExtension',GLib.Variant('(s)',(UUID,)),
                  None,Gio.DBusCallFlags.NONE,10000,None).unpack()[0]


def cleanup():
    destination = Path.home()/'.local/share/gnome-shell/extensions'/UUID
    overlay = destination/'app'
    if not overlay.exists():
        return
    for target in overlay.iterdir():
        if target.is_symlink() and str(target.readlink()).startswith(str(VENDOR/'app')):
            target.unlink()
    (destination/'schemas/gschemas.compiled').unlink(missing_ok=True)
    for directory in (overlay, destination/'schemas', destination):
        try:
            directory.rmdir()
        except OSError:
            pass  # Keep files edited after installation.


if __name__ == '__main__':
    import gnome_install
    files = prepare()
    gnome_install.write_files(files)
    destination = Path.home()/'.local/share/gnome-shell/extensions'/UUID
    subprocess.run(['glib-compile-schemas',str(destination/'schemas')],check=True)
    active = activate()
    print('Installed Windows-style desktop menu.' if active else
          'Desktop menu installed. Sign out and back in when convenient to activate it.')
