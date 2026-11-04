"""The lock-screen photo reaches the login screen's shared folder, world-readable."""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import lockscreen


class PublishTests(unittest.TestCase):
    def test_publish_copies_a_readable_picture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); shared = root/'login'; shared.mkdir()
            photo = root/'photo.jpg'; photo.write_bytes(b'photo')
            old = os.umask(0o077)
            try:
                with patch.object(lockscreen, 'LOGIN', shared):
                    lockscreen.publish_login(dict(path=str(photo), source='spotlight'))
            finally:
                os.umask(old)
            target = shared/'background.jpg'
            self.assertEqual(target.read_bytes(), b'photo')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
            self.assertEqual([p.name for p in shared.iterdir()], ['background.jpg'])

    def test_publish_is_a_no_op_until_the_login_screen_is_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(lockscreen, 'LOGIN', Path(directory)/'missing'):
                lockscreen.publish_login(dict(path='/nowhere.jpg', source='spotlight'))

    def test_a_missing_photo_keeps_the_previous_one(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory); (shared/'background.jpg').write_bytes(b'old')
            with patch.object(lockscreen, 'LOGIN', shared):
                lockscreen.publish_login(dict(path=str(shared/'gone.jpg'), source='spotlight'))
            self.assertEqual((shared/'background.jpg').read_bytes(), b'old')
            self.assertEqual([p.name for p in shared.iterdir()], ['background.jpg'])


if __name__ == '__main__':
    unittest.main()
