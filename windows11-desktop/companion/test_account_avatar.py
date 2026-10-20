import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import app


class Profile:
    account_avatar = app.Hub.account_avatar
    account_avatar_uri = app.Hub.account_avatar_uri
    resource = app.Hub.resource


class AvatarTests(unittest.TestCase):
    def test_accounts_service_wins_and_changed_photo_refreshes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            icon = root/'system.png'
            icon.write_bytes(b'first')
            (root/'reference-avatar.jpg').write_bytes(b'stale')
            bus = Mock()
            bus.call_sync.side_effect = [
                Mock(unpack=lambda:('/account',)), Mock(unpack=lambda:(str(icon),)),
                Mock(unpack=lambda:('/account',)), Mock(unpack=lambda:(str(icon),))]
            profile = Profile()
            with patch.object(app.Gio, 'bus_get_sync', return_value=bus), \
                 patch.object(app, 'CONFIG', root), \
                 patch.object(app.time, 'monotonic', side_effect=[0, 1, 6]):
                first = profile.account_avatar_uri()
                self.assertEqual(profile.account_avatar(), icon)
                icon.write_bytes(b'updated photo')
                second = profile.account_avatar_uri()
            self.assertNotEqual(first, second)
            self.assertEqual(bus.call_sync.call_count, 4)

    def test_missing_service_uses_face_then_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            face = root/'.face'
            face.write_bytes(b'face')
            legacy = root/'reference-avatar.jpg'
            legacy.write_bytes(b'legacy')
            with patch.object(app.Gio, 'bus_get_sync', side_effect=app.GLib.Error('unavailable')), \
                 patch.object(app.Path, 'home', return_value=root), \
                 patch.object(app, 'CONFIG', root):
                self.assertEqual(Profile().account_avatar(), face)
                face.unlink()
                self.assertEqual(Profile().account_avatar(), legacy)
                legacy.unlink()
                self.assertIsNone(Profile().account_avatar_uri())

    def test_profile_resource_serves_bounded_png_from_system_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            photo = Path(directory)/'account.jpeg'
            Image.new('RGB', (800, 400), 'red').save(photo)
            profile = Profile()
            profile.account_avatar = lambda:photo
            request = Mock()
            request.get_uri.return_value = 'zorin11://profile/avatar?v=123'
            profile.resource(request)
            stream, length, mime = request.finish.call_args.args
            data = stream.read_bytes(length, None).get_data()
            self.assertEqual(mime, 'image/png')
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size, (256, 128))
                self.assertFalse(image.getexif())


if __name__ == '__main__':
    unittest.main()
