"""The desktop action and companion must not overwrite each other's state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class WallpaperProcessTests(unittest.TestCase):
    def test_concurrent_nested_updates_keep_every_change(self):
        with tempfile.TemporaryDirectory(prefix='axentra-wallpaper-lock-') as directory:
            env = dict(os.environ, ZORIN11_CONFIG_DIR=directory)
            script = '''
import sys,time
import wallpaper
@wallpaper.locked
def change():
    state=wallpaper.load()
    key='worker-'+sys.argv[1]
    state[key]=state.get(key,0)+1
    time.sleep(.005)
    wallpaper.save(state)  # nested lock must not deadlock
for _ in range(20):change()
'''
            children = [subprocess.Popen([sys.executable, '-c', script, str(i)],
                cwd=Path(__file__).resolve().parent, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE) for i in range(3)]
            try:
                for process in children:
                    _, error = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 0, error.decode())
                state = json.loads((Path(directory)/'wallpapers.json').read_text())
                self.assertEqual([state['worker-'+str(i)] for i in range(3)], [20]*3)
            finally:
                for process in children:
                    if process.poll() is None:
                        process.kill()
                        process.wait()


if __name__ == '__main__':
    unittest.main()
