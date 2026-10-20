import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import file_preview as preview
import file_thumbnails as thumbnails
import thumbnail_cache
import heif_images

FIXTURE = Path(__file__).with_name('test-fixtures')/'portrait.heic'

class HeifTests(unittest.TestCase):
    def test_real_decoder_portrait_dimensions_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'PHOTO.HEIC';path.write_bytes(FIXTURE.read_bytes())
            s=path.stat();data=thumbnails.read(str(path),[s.st_mtime,s.st_size])
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size,(128,256))
                self.assertFalse(image.getexif())
                self.assertNotIn('exif',image.info)
                self.assertGreater(image.getpixel((64,30))[0],180)
                self.assertGreater(image.getpixel((64,220))[2],150)
            result=preview.read(str(path));self.assertEqual(result['kind'],'image')
            with Image.open(io.BytesIO(base64.b64decode(result['image'].split(',')[1]))) as image:
                self.assertEqual(image.size,(160,320));self.assertFalse(image.getexif())
            path.rename(path.with_suffix('.heif'));path=path.with_suffix('.heif')
            self.assertEqual(preview.read(str(path))['kind'],'image')
            self.assertIn('.heic',thumbnail_cache.EXTENSIONS)
            self.assertIn('.heif',thumbnail_cache.EXTENSIONS)

    def test_corrupt_mislabeled_oversized_and_changed_images(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.heic';path.write_bytes(b'not HEIF')
            s=path.stat();self.assertEqual(thumbnails.read(str(path),[s.st_mtime,s.st_size]),b'')
            self.assertEqual(preview.read(str(path))['kind'],'unavailable')
            Image.new('RGB',(10,10),'red').save(path,format='PNG')
            self.assertEqual(preview.read(str(path))['kind'],'unavailable')
            path.write_bytes(FIXTURE.read_bytes())
            with patch.object(preview,'PIXEL_LIMIT',100):self.assertEqual(preview.generate(path)['kind'],'unavailable')
            self.assertEqual(thumbnails.read(str(path),[0,1]),b'')
            with self.assertRaises(ValueError):heif_images.decode(FIXTURE.read_bytes(),256,100)

if __name__=='__main__':unittest.main()
