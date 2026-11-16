"""Test exact sandbox identity and native caption binding for Chrome Flatpak."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from maximize_control import resolve_control, valid
from test_maximize_control import API, Accessible


class ChromeCaptionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.proc = Path(directory.name)
        patcher = patch('maximize_chrome._PROC', self.proc)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.process(100, '/app/extra/chrome')
        self.process(101, '/usr/bin/xdg-dbus-proxy')
        self.request = dict(kind='chrome-flatpak', pid=100, title='Chrome test',
                            width=900, height=640, x=811, y=35)
        self.rect = (800, 24, 30, 30)
        self.maximize = Accessible('button', name='Maximize', rect=self.rect,
                                   attributes={'class': 'ImageButton', 'id': 'view_2'})

    def process(self, pid, executable, scope=100, instance=17, app='com.google.Chrome'):
        folder = self.proc / str(pid)
        (folder / 'root').mkdir(parents=True)
        (folder / 'exe').symlink_to(executable)
        (folder / 'cgroup').write_text(f'0::/session/app-flatpak-com.google.Chrome-{scope}.scope\n')
        (folder / 'root/.flatpak-info').write_text(
            f'[Application]\nname={app}\n[Instance]\ninstance-id={instance}\n')

    def resolve(self, *buttons, proxy=101, frame_class='BrowserFrameViewLinuxNative', **request):
        caption = Accessible('panel', *buttons, attributes={'class': frame_class})
        client = Accessible('panel', caption, attributes={'class': 'NonClientView'})
        frame = Accessible('frame', client, name='Chrome test', rect=(0, 0, 900, 640),
                           attributes={'class': 'BrowserRootView'})
        return resolve_control(Accessible('', Accessible('', frame, pid=proxy)),
                               API, self.request | request)

    def test_native_caption_inside_same_sandbox(self):
        self.assertTrue(valid(self.request))
        self.assertEqual(self.resolve(self.maximize), self.rect)
        self.maximize.attributes['id'] = 'view_3'
        self.assertEqual(self.resolve(self.maximize), self.rect)
        self.assertIsNone(self.resolve(self.maximize, x=830))

    def test_other_sandbox_instance_or_unrelated_process_rejected(self):
        self.process(102, '/usr/bin/xdg-dbus-proxy', scope=200)
        self.process(103, '/usr/bin/xdg-dbus-proxy', instance=21)
        self.process(104, '/usr/bin/xdg-dbus-proxy', app='org.example.App')
        self.process(105, '/app/extra/chrome')
        for pid in (99, 102, 103, 104, 105):
            with self.subTest(pid=pid):
                self.assertIsNone(self.resolve(self.maximize, proxy=pid))

    def test_non_caption_and_ambiguous_targets_rejected(self):
        self.assertIsNone(self.resolve(self.maximize, frame_class='BrowserView'))
        self.assertIsNone(self.resolve(self.maximize, self.maximize))
        self.assertIsNone(self.resolve(self.maximize, title='Wrong frame'))
        self.maximize.attributes['id'] = 'view_4'
        self.assertIsNone(self.resolve(self.maximize))


if __name__ == '__main__':
    unittest.main()
