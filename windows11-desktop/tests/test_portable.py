"""Portability regressions: panel IDs, laptop battery, and local asset imports."""
import io
from pathlib import Path
import sys
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'companion')]
from panel_layout import find_panel, plan
from setup import reference_entries
from terminal import command


class PortableTests(unittest.TestCase):
    def test_nonzero_panel_and_arbitrary_ids(self):
        props={'/panels/panel-4/plugin-ids':[71,92,13,44,51,16,87,68,19,30],
               '/plugins/plugin-71':'zorinmenulite'}
        self.assertEqual(find_panel(props),4)
        kinds=['launcher','separator','docklike','separator','systray',
               'notification-plugin','indicator','pulseaudio','power-manager-plugin','clock']
        ids=props['/panels/panel-4/plugin-ids'];types=dict(zip(ids,kinds))
        alloc=iter([100,101,102])
        result=plan(ids,types,71,98,99,lambda:next(alloc),battery=True)
        self.assertEqual(result['order'],[92,71,99,13,44,19,51,98,30,16,100])
        self.assertEqual(result['new'],{100:'showdesktop'})
        self.assertNotIn(87,result['order']);self.assertNotIn(68,result['order'])

    def test_preserves_other_plugins_and_is_repeatable(self):
        ids=[50,51,52,53,54,55,56,57,58,59,60]
        kinds=['separator','launcher','launcher','docklike','separator','weather',
               'systray','launcher','clock','notification-plugin','showdesktop']
        result=plan(ids,dict(zip(ids,kinds)),51,57,52,lambda:999)
        self.assertEqual(result['order'],ids)
        self.assertFalse(result['new'])

    def test_ambiguous_panels_fail_without_guessing(self):
        with self.assertRaises(ValueError):find_panel({})
        with self.assertRaises(ValueError):find_panel({'/panels/panel-0/plugin-ids':[1],
             '/panels/panel-2/plugin-ids':[2],'/plugins/plugin-1':'zorinmenulite','/plugins/plugin-2':'zorinmenulite'})

    def archive(self,entries):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            for name,data in entries:archive.writestr(name,data)
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def test_windows_backslash_zip(self):
        png=b'\x89PNG\r\n\x1a\nplaceholder'
        with self.archive([('48\\computer.png',png)]) as archive:
            self.assertEqual(reference_entries(archive),[('reference-icons/48/computer.png',png)])

    def test_rejects_export_traversal_and_unexpected_content(self):
        for name in ('../../.bashrc','48/../computer.png','48/secret.txt'):
            with self.archive([(name,b'payload')]) as archive:
                with self.assertRaises(ValueError):reference_entries(archive)

    def test_terminal_keeps_argument_boundaries(self):
        args=['/bin/bash','-c','printf "%s" "hello there"']
        self.assertEqual(command(args,Path('/home/a b')),
                         ['/home/a b/.local/bin/wezterm','start','--',*args])


if __name__=='__main__':unittest.main()
