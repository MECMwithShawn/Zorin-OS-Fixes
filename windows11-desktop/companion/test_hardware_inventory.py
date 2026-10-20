import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import hardware_inventory as h


def put(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def fixture(root):
    for relative in ('bus/pci/devices', 'bus/usb/devices', 'class/block', 'class/input'):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for slot, code in [('0000:01:00.0', '0x030000'), ('0000:02:00.0', '0x020000')]:
        base = f'bus/pci/devices/{slot}'
        put(root, base + '/vendor', '0x1234')
        put(root, base + '/device', '0x5678')
        put(root, base + '/class', code)
    (root / 'bus/pci/drivers/testgpu').mkdir(parents=True)
    (root / 'bus/pci/devices/0000:01:00.0/driver').symlink_to(root / 'bus/pci/drivers/testgpu')
    for location in ('1-2', '1-3'):
        put(root, f'bus/usb/devices/{location}/idVendor', '045e')
        put(root, f'bus/usb/devices/{location}/idProduct', '1234')
        put(root, f'bus/usb/devices/{location}/product', 'Same-name device')
        put(root, f'bus/usb/devices/{location}/authorized', '1')
    # Two interfaces with the same driver should appear once in a device's properties.
    (root / 'bus/usb/drivers/usbhid').mkdir(parents=True)
    for interface in ('1-2:1.0', '1-2:1.1'):
        folder = root / 'bus/usb/devices/1-2' / interface
        folder.mkdir()
        (folder / 'driver').symlink_to(root / 'bus/usb/drivers/usbhid')
        (root / 'bus/usb/devices' / interface).symlink_to(folder)
    for name in ('nvme0n1', 'nvme0n1p1', 'loop0'):
        put(root, f'class/block/{name}/size', '2097152')
    put(root, 'class/block/nvme0n1/device/model', 'Fixture disk')
    put(root, 'class/block/nvme0n1/ro', '0')
    put(root, 'class/block/nvme0n1p1/partition', '1')
    put(root, 'class/block/nvme0n1p1/device/model', 'Excluded partition')
    put(root, 'class/input/event0/device/name', 'Fixture keyboard')
    put(root, 'class/input/event0/device/id/vendor', '1234')
    put(root, 'class/input/event0/device/id/product', '5678')
    return h.collect(root, {'0000:01:00.0': 'Fixture GPU'})


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = fixture(self.root)

    def test_identity_classification_and_binding(self):
        gpu = next(r for r in self.data['devices'] if r['id'] == 'pci:0000:01:00.0')
        self.assertEqual(gpu['name'], 'Fixture GPU')
        self.assertEqual(gpu['category'], 'Display adapters')
        self.assertEqual(gpu['driver'], 'testgpu')
        network = next(r for r in self.data['devices'] if r['category'] == 'Network adapters')
        self.assertEqual(dict(network['fields'])['Binding'], 'No driver binding reported')
        self.assertNotIn('failure', h.report(network).lower())

    def test_usb_interfaces_deduplicated_not_equal_names(self):
        devices = [r for r in self.data['devices'] if r['id'].startswith('usb:')]
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]['name'], devices[1]['name'])
        self.assertNotEqual(devices[0]['id'], devices[1]['id'])
        self.assertEqual(devices[0]['driver'], 'usbhid')

    def test_partitions_virtual_disks_and_capacity(self):
        devices = [r for r in self.data['devices'] if r['category'] == 'Disk drives']
        self.assertEqual(len(devices), 1)
        self.assertEqual(dict(devices[0]['fields'])['Capacity'], '1.0 GiB')
        self.assertEqual(dict(devices[0]['fields'])['Read only'], 'No')

    def test_removal_malformed_values_and_missing_sources(self):
        (self.root / 'bus/pci/devices/0000:01:00.0/vendor').unlink()
        put(self.root, 'class/block/nvme0n1/size', 'malformed')
        result = h.collect(self.root, {})
        self.assertFalse(any(r['id'] == 'pci:0000:01:00.0' for r in result['devices']))
        disk = next(r for r in result['devices'] if r['category'] == 'Disk drives')
        self.assertEqual(dict(disk['fields'])['Capacity'], 'Unavailable')
        (self.root / 'class/empty').mkdir()
        empty = h.collect(self.root / 'class/empty', {})
        self.assertEqual(len(empty['warnings']), 4)
        with self.assertRaises(RuntimeError):
            h.collect(self.root / 'missing', {})

    def test_search_all_terms_and_literal_device_text(self):
        row = self.data['devices'][0]
        row['name'] = '<b>USB & device</b>'
        row['fields'][0] = ('Device', row['name'])
        self.assertTrue(h.matches(row, 'USB DEVICE'))
        self.assertFalse(h.matches(row, 'USB impossible'))
        self.assertIn('Device: <b>USB & device</b>', h.report(row))
        self.assertTrue(h.matches(next(r for r in self.data['devices'] if r['category'] == 'Display adapters'), 'testgpu 1234'))

    def test_parent_driver_and_optional_pci_names(self):
        disk = self.root / 'class/block/nvme0n1/device'
        (disk.parent / 'driver').symlink_to(self.root / 'bus/pci/drivers/testgpu')
        self.assertEqual(h.parent_driver(disk, self.root), ('testgpu', str(disk.parent)))
        output = '0000:01:00.0 "VGA compatible controller" "Vendor" "Model" -r01\n"broken'
        with patch.object(h.subprocess, 'run', return_value=Mock(stdout=output, returncode=0)):
            self.assertEqual(h.pci_names(), {'0000:01:00.0': 'Vendor Model'})
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('lspci', 3)):
            with patch.object(h.subprocess, 'run', side_effect=error):
                self.assertEqual(h.pci_names(), {})

    def test_inventory_never_writes(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        h.collect(self.root, {})
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
