"""Read-only hardware inventory. Never probes, binds, resets or writes devices."""
import os
from pathlib import Path
import shlex
import subprocess

ICONS = {
    'Display adapters': 'video-display',
    'Network adapters': 'network-wired',
    'Sound, video and game controllers': 'audio-card',
    'Storage controllers': 'drive-harddisk',
    'Disk drives': 'drive-harddisk',
    'USB devices': 'drive-removable-media-usb',
    'USB controllers and hubs': 'network-wired',
    'Human interface devices': 'input-keyboard',
    'Bluetooth': 'bluetooth',
    'Cameras': 'camera-web',
    'System devices': 'computer',
}


def read(path):
    try:
        with path.open(errors='replace') as stream:
            return ' '.join(stream.read(4096).split())
    except OSError:
        return ''


def entries(path):
    try:
        return sorted(path.iterdir())
    except OSError:
        return []


def driver(path):
    link = path / 'driver'
    try:
        return link.resolve(strict=True).name if link.is_symlink() else ''
    except (OSError, RuntimeError):
        return ''


def parent_driver(path, root):
    current = path.resolve()
    boundary = root.resolve()
    while current != boundary and boundary in current.parents:
        bound = driver(current)
        if bound:
            return bound, str(current)
        current = current.parent
    return '', 'Unavailable'


def pci_names():
    try:
        result = subprocess.run(['lspci', '-Dmm'], capture_output=True, text=True,
                                timeout=3, env=dict(os.environ, LC_ALL='C'))
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode:
        return {}
    names = {}
    for line in result.stdout.splitlines():
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) >= 4:
            names[parts[0]] = parts[2] + ' ' + parts[3]
    return names


def pci_category(code):
    if code.startswith('03'):
        return 'Display adapters'
    if code.startswith('02'):
        return 'Network adapters'
    if code.startswith('04'):
        return 'Sound, video and game controllers'
    if code.startswith('01'):
        return 'Storage controllers'
    if code.startswith('0c03'):
        return 'USB controllers and hubs'
    return 'System devices'


def device(kind, path, name, category, fields, drivers=''):
    return dict(id=kind + ':' + path.name, name=name, category=category,
                icon=ICONS[category], driver=drivers or 'Not reported',
                fields=[('Device', name), ('Category', category),
                        ('Location', path.name), *fields,
                        ('Driver', drivers or 'Not reported'),
                        ('System path', str(path.resolve()))])


def collect(root=Path('/sys'), names=None):
    """Snapshot physical PCI/USB devices, whole disks and input endpoints.

    PCI and USB are bus functions; input endpoints and disks can belong to them.
    Empty individual attributes mean unavailable, including unplug races.
    """
    if not root.is_dir():
        raise RuntimeError('The Linux hardware inventory is unavailable.')
    names = pci_names() if names is None else names
    result = []
    warnings = []
    for rel in ('bus/pci/devices', 'bus/usb/devices', 'class/block', 'class/input'):
        if not (root / rel).is_dir():
            warnings.append('Unavailable: ' + rel)
    for path in entries(root / 'bus/pci/devices'):
        vendor, product = read(path / 'vendor'), read(path / 'device')
        if not vendor or not product:
            continue
        code = read(path / 'class').removeprefix('0x')
        bound = driver(path)
        result.append(device('pci', path, names.get(path.name, f'PCI device {vendor}:{product}'),
                             pci_category(code),
                             [('Hardware IDs', f'PCI {vendor}:{product}'),
                              ('Class code', code or 'Unavailable'),
                              ('Binding', 'Driver bound' if bound else 'No driver binding reported')], bound))
    for path in entries(root / 'bus/usb/devices'):
        # USB interfaces are combined under the parent device, avoiding duplicates.
        if ':' in path.name:
            continue
        vendor, product = read(path / 'idVendor'), read(path / 'idProduct')
        if not vendor or not product:
            continue
        bound = sorted({d for interface in entries(path) if ':' in interface.name
                        for d in [driver(interface)] if d})
        if not bound and driver(path):
            bound = [driver(path)]
        name = read(path / 'product') or f'USB device {vendor}:{product}'
        category = 'USB controllers and hubs' if read(path / 'bDeviceClass') == '09' else 'USB devices'
        if 'btusb' in bound:
            category = 'Bluetooth'
            if not read(path / 'product'):
                name = f'Bluetooth adapter ({vendor}:{product})'
        elif 'uvcvideo' in bound:
            category = 'Cameras'
        speed = read(path / 'speed')
        auth = read(path / 'authorized')
        result.append(device('usb', path, name, category,
                             [('Manufacturer', read(path / 'manufacturer') or 'Unavailable'),
                              ('Hardware IDs', f'USB {vendor}:{product}'),
                              ('Authorization', {'0': 'Not authorized', '1': 'Authorized'}.get(auth, 'Unavailable')),
                              ('Link speed', speed + ' Mb/s' if speed else 'Unavailable')], ', '.join(bound)))
    for path in entries(root / 'class/block'):
        # Whole physical disks only; exclude partitions and virtual/loop devices.
        if (path / 'partition').exists() or not (path / 'device').exists():
            continue
        model = read(path / 'device/model') or path.name
        sectors = read(path / 'size')
        size = f'{int(sectors) * 512 / 1024**3:.1f} GiB' if sectors.isdigit() else 'Unavailable'
        bound, source = parent_driver(path / 'device', root)
        result.append(device('disk', path, f'{model} ({path.name})', 'Disk drives',
                             [('Capacity', size),
                              ('Read only', {'0': 'No', '1': 'Yes'}.get(read(path / 'ro'), 'Unavailable')),
                              ('Removable', {'0': 'No', '1': 'Yes'}.get(read(path / 'removable'), 'Unavailable')),
                              ('Driver binding location', source)], bound))
    for path in entries(root / 'class/input'):
        if not path.name.startswith('event'):
            continue
        endpoint = path / 'device'
        name = read(endpoint / 'name')
        if not name:
            continue
        vendor, product = read(endpoint / 'id/vendor'), read(endpoint / 'id/product')
        bound, source = parent_driver(endpoint, root)
        result.append(device('input', path, name, 'Human interface devices',
                             [('Hardware IDs', f'Input {vendor}:{product}' if vendor and product else 'Unavailable'),
                              ('Driver binding location', source)], bound))
    return dict(devices=sorted(result, key=lambda d: (d['category'], d['name'].casefold(), d['id'])),
                warnings=warnings)


def matches(row, query):
    haystack = ' '.join([row['name'], row['category'], row['driver'],
                         *[value for _, value in row['fields']]]).casefold()
    return all(term in haystack for term in query.casefold().split())


def report(row):
    return '\n'.join(f'{name}: {value}' for name, value in row['fields'])
