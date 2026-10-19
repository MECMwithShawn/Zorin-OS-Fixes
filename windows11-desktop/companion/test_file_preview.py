import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import file_preview as preview


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_text_is_returned_as_text_and_truncated(self):
        path=self.root/'example.html';path.write_text('<script>doNotExecute()</script>')
        self.assertEqual(preview.read(str(path))['text'],path.read_text())
        path.write_text('line\n'*1100)
        result=preview.generate(path)
        self.assertTrue(result['truncated']);self.assertLessEqual(result['text'].count('\n'),999)
        path.write_bytes('Hello'.encode('utf-16'))
        self.assertEqual(preview.generate(path)['text'],'Hello')

    def test_limits_binary_and_unsupported_files(self):
        path=self.root/'file.txt';path.write_bytes(b'a\0b')
        self.assertEqual(preview.generate(path)['kind'],'unavailable')
        path.write_bytes(b'x'*(preview.TEXT_LIMIT+1))
        self.assertEqual(preview.generate(path)['kind'],'unavailable')
        self.assertEqual(preview.generate(self.root/'never-read.exe')['kind'],'unavailable')
        fifo=self.root/'pipe.txt';os.mkfifo(fifo)
        self.assertEqual(preview.read(str(fifo))['kind'],'unavailable')
        self.assertEqual(preview.read(str(self.root/'missing.txt'))['kind'],'unavailable')

    def test_raster_is_resized_and_reencoded(self):
        import base64
        path=self.root/'picture.png';Image.new('RGB',(1600,800),'blue').save(path)
        result=preview.read(str(path));self.assertEqual(result['kind'],'image')
        with Image.open(io.BytesIO(base64.b64decode(result['image'].split(',')[1]))) as image:
            self.assertEqual(image.size,(1024,512));self.assertEqual(image.format,'PNG')
        self.assertEqual((result['width'],result['height']),(1600,800))
        with patch.object(preview,'PIXEL_LIMIT',100):
            self.assertEqual(preview.generate(path)['kind'],'unavailable')

    def test_coalesced_requests_discard_old_selection_and_closed_windows(self):
        from app import Hub
        from types import SimpleNamespace
        pending=[];messages=[]
        surface=SimpleNamespace(location='/test',send=messages.append,preview_waiting=None)
        hub=SimpleNamespace(surfaces={str(id(surface)):surface},background=lambda task,done,fail:pending.append(done))
        hub.start_preview=lambda s:Hub.start_preview(hub,s)
        for ident in (1,2,3):Hub.preview_file(hub,surface,{'id':ident,'path':f'/test/{ident}.txt','location':'/test'})
        self.assertEqual(len(pending),1)
        pending.pop(0)({'kind':'text','text':'old'})
        self.assertEqual(messages,[]);self.assertEqual(len(pending),1)
        pending.pop(0)({'kind':'text','text':'latest'})
        self.assertEqual(messages[0]['id'],3)
        Hub.preview_file(hub,surface,{'id':4,'path':'/test/4.txt','location':'/test'})
        hub.surfaces.clear();pending.pop(0)({'kind':'text','text':'closed'})
        self.assertEqual(len(messages),1)
