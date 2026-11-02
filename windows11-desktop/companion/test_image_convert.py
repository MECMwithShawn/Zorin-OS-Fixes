import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
import image_convert

FIXTURE = Path(__file__).with_name('test-fixtures')/'portrait.heic'


class ImageConvertTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_heic_to_png_full_size_without_metadata(self):
        source = self.root/'IMG_0001.HEIC'
        source.write_bytes(FIXTURE.read_bytes())
        created = image_convert.convert([str(source)], 'png')
        self.assertEqual(created, [str(self.root/'IMG_0001.png')])
        with Image.open(created[0]) as image:
            self.assertEqual((image.format, image.size), ('PNG', (160, 320)))
            self.assertFalse(image.getexif())
            self.assertGreater(image.getpixel((80, 37))[0], 180)
        self.assertEqual(source.read_bytes(), FIXTURE.read_bytes())

    def test_transparent_png_to_jpg_on_white(self):
        source = self.root/'logo.png'
        Image.new('RGBA', (4, 4), (255, 0, 0, 0)).save(source)
        created = image_convert.convert([str(source)], 'jpg')
        with Image.open(created[0]) as image:
            self.assertEqual((image.format, image.mode), ('JPEG', 'RGB'))
            self.assertGreater(min(image.getpixel((1, 1))), 240)

    def test_never_overwrites_and_skips_folders_others_and_same_format(self):
        source = self.root/'été photo.jpeg'
        Image.new('RGB', (3, 2), 'blue').save(source)
        (self.root/'été photo.png').write_bytes(b'keep')
        (self.root/'notes.txt').write_text('x')
        created = image_convert.convert([str(source), str(self.root), str(self.root/'notes.txt'), 'missing.png'], 'png')
        self.assertEqual(created, [str(self.root/'été photo (2).png')])
        self.assertEqual((self.root/'été photo.png').read_bytes(), b'keep')
        with self.assertRaisesRegex(ValueError, 'already JPG'):
            image_convert.convert([str(source)], 'jpg')
        with self.assertRaisesRegex(ValueError, 'PNG or JPG'):
            image_convert.convert([str(source)], 'gif')

    def test_exif_orientation_applied(self):
        source = self.root/'rotated.jpg'
        exif = Image.Exif()
        exif[0x0112] = 6
        Image.new('RGB', (40, 20), 'green').save(source, exif=exif)
        with Image.open(image_convert.convert([str(source)], 'png')[0]) as image:
            self.assertEqual(image.size, (20, 40))

    def test_command_line_used_by_gnome_files(self):
        source = self.root/'IMG_0002.heic'
        source.write_bytes(FIXTURE.read_bytes())
        result = subprocess.run([sys.executable, str(Path(image_convert.__file__)), 'jpg', str(source)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, str(self.root/'IMG_0002.jpg')))
        bad = subprocess.run([sys.executable, str(Path(image_convert.__file__)), 'png', str(self.root/'nope.txt')],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(bad.returncode, 1)
        self.assertIn('already PNG', bad.stderr)


if __name__ == '__main__':
    unittest.main()
