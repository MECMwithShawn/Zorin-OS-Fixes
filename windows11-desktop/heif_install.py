"""Install the tested HEIF decoder privately, without changing system Python."""
import argparse
import fcntl
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
TARGET = Path.home()/'.local/share/zorin11-hub/heif-runtime'
PYTHON = sys.executable
PROBE = """
import pathlib,sys
sys.path.insert(0,sys.argv[1])
import PIL,pillow_heif
root=pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(PIL.__file__).resolve().is_relative_to(root)
assert pathlib.Path(pillow_heif.__file__).resolve().is_relative_to(root)
assert PIL.__version__=='13.0.0' and pillow_heif.__version__=='1.8.1'
"""


def ready(target):
    return target.is_dir() and subprocess.run(
        [PYTHON, '-I', '-c', PROBE, str(target)],
        capture_output=True, timeout=15).returncode == 0


def ensure(target=TARGET):
    target = Path(target).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    with (target.parent/'heif-install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ready(target):
            return target
        version = subprocess.check_output(
            [PYTHON, '-c', 'import sys;print("%d.%d"%sys.version_info[:2])'],
            text=True).strip()
        if version != '3.12':
            raise RuntimeError('The pinned HEIF runtime requires Python 3.12 (Zorin 18).')
        with tempfile.TemporaryDirectory(prefix='.heif-install-', dir=target.parent) as folder:
            staging = Path(folder)
            venv = staging/'venv'
            subprocess.run([PYTHON, '-m', 'venv', str(venv)], check=True)
            candidate = staging/'runtime'
            subprocess.run([str(venv/'bin/python'), '-m', 'pip', 'install',
                '--disable-pip-version-check', '--only-binary=:all:',
                '--require-hashes', '--no-deps', '--target', str(candidate),
                '-r', str(ROOT/'heif-requirements.txt')], check=True)
            if not ready(candidate):
                raise RuntimeError('HEIF decoder validation failed; previous runtime retained.')
            previous = staging/'previous'
            if target.exists():
                target.rename(previous)
            try:
                candidate.rename(target)
            except BaseException:
                if previous.exists():
                    previous.rename(target)
                raise
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=TARGET)
    args = parser.parse_args()
    print('Verified HEIF runtime:', ensure(args.target))
