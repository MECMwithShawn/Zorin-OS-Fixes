import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop_backup as backup


class BackupTests(unittest.TestCase):
    def test_snapshot_and_destination_are_verified_without_following_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photo = root/'photo';photo.write_bytes(b'private account photo fixture')
            link = root/'link';link.symlink_to('/outside/credential-store')
            archive = root/'snapshot.tar.gz'
            sources = {'profile/photo':photo, 'home/link':link}
            manifest = backup.build_archive(archive, sources, {'profile/settings.json':b'{}'}, {})
            self.assertEqual(len(manifest['entries']), 3)
            destination = backup.publish(root/'OneDrive/new folder', archive, manifest)
            self.assertEqual(backup.digest(archive), backup.digest(destination/'desktop-snapshot.tar.gz'))
            self.assertEqual(backup.verify_archive(destination/'desktop-snapshot.tar.gz'), manifest)
            self.assertTrue((destination/'RESTORE-README.txt').is_file())
            config = root/'backup-settings.json'
            backup.remember_destination(root/'OneDrive/new folder', config)
            self.assertEqual(backup.configured_destination(config), root/'OneDrive/new folder')
            config.write_text(json.dumps({'destination':str(root), 'required_mount':'/unmounted-test'}))
            with self.assertRaises(RuntimeError):
                backup.configured_destination(config)

    def test_incomplete_copy_is_not_published_and_existing_backup_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);source = root/'source';source.write_bytes(b'archive content')
            destination = root/'backups';destination.mkdir()
            previous = destination/'previous';previous.mkdir()
            (previous/'keep').write_text('keep')
            with patch.object(backup.shutil, 'copyfile', side_effect=lambda src,dst:Path(dst).write_bytes(b'partial')):
                with self.assertRaises(RuntimeError):
                    backup.publish(destination, source, {})
            self.assertEqual(list(destination.iterdir()), [previous])
            self.assertEqual((previous/'keep').read_text(), 'keep')

    def test_inventory_rejects_corrupt_member(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)/'bad.tar.gz'
            manifest = {'entries':[{'path':'file', 'kind':'file', 'sha256':'0'*64}]}
            with tarfile.open(archive, 'w:gz') as stream:
                for name,data in [('manifest.json', json.dumps(manifest).encode()), ('file',b'changed')]:
                    info=tarfile.TarInfo(name);info.size=len(data);stream.addfile(info,io.BytesIO(data))
            with self.assertRaises(RuntimeError):
                backup.verify_archive(archive)

    def test_selection_excludes_onedrive_credentials_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            for relative in ('.config/zorin11-hub/layout.json',
                             '.config/axentra-onedrive/token.json',
                             'OneDrive/secret.txt',
                             '.local/share/zorin11-hub/__pycache__/app.pyc'):
                path=home/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
            sources=backup.collect(home)
            user_names=[name for name in sources if name.startswith('home/')]
            self.assertEqual(user_names, ['home/.config/zorin11-hub/layout.json'])


if __name__=='__main__':
    unittest.main()
