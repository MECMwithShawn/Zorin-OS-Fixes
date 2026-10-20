from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import heif_install


class HeifInstallTests(unittest.TestCase):
    def test_verified_runtime_is_reused_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'runtime'
            with patch.object(heif_install, 'ready', return_value=True), \
                 patch.object(heif_install.subprocess, 'run') as run:
                self.assertEqual(heif_install.ensure(target), target)
                run.assert_not_called()

    def test_failed_dependency_install_preserves_previous_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'runtime'
            target.mkdir()
            (target/'existing').write_bytes(b'prior decoder')
            with patch.object(heif_install, 'ready', return_value=False), \
                 patch.object(heif_install.subprocess, 'check_output', return_value='3.12\n'), \
                 patch.object(heif_install.subprocess, 'run', side_effect=[
                     subprocess.CompletedProcess([], 0), subprocess.CalledProcessError(1, 'pip')]):
                with self.assertRaises(subprocess.CalledProcessError):
                    heif_install.ensure(target)
            self.assertEqual((target/'existing').read_bytes(), b'prior decoder')
            self.assertEqual(list(target.parent.glob('.heif-install-*')), [])


if __name__ == '__main__':
    unittest.main()
